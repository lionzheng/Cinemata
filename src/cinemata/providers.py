"""媒体 provider 的稳定边界和本地可复现实现。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import base64
import struct
import urllib.error
import urllib.request
import wave
from html import escape
from pathlib import Path
from typing import Any, Protocol


class ImageProvider(Protocol):
    """图片 provider 必须根据镜头描述生成一个可引用的资产记录。"""

    def generate(self, shot: dict[str, Any], output_path: Path) -> dict[str, Any]:
        """生成镜头图片并返回 provenance 记录。"""


class VoiceProvider(Protocol):
    """语音 provider 必须为一条对白生成可引用的音频资产。"""

    def generate(self, text: str, duration: float, output_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """生成对白音频并返回 provenance 记录。"""


class ProviderError(RuntimeError):
    """媒体 provider 无法完成生成或返回了无效响应。"""


class MockImageProvider:
    """生成确定性的 SVG 占位帧，用于本地开发、审阅和 CI。"""

    name = "mock-image"
    version = "0.1.0"
    asset_extension = "svg"

    def generate(self, shot: dict[str, Any], output_path: Path) -> dict[str, Any]:
        """把 prompt 渲染为可视化占位帧，不访问外部服务。"""
        prompt = str(shot.get("prompt", "等待媒体 provider 生成画面"))
        raw_digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        digest = raw_digest.hex()[:8]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" role="img" aria-label="Cinemata mock frame">
<rect width="1600" height="900" fill="#27251f"/>
<rect x="60" y="60" width="1480" height="780" fill="none" stroke="#aaa092" stroke-width="3"/>
<text x="100" y="150" fill="#f7f1e8" font-family="sans-serif" font-size="40">CINEMATA MOCK FRAME</text>
<text x="100" y="220" fill="#d8d0c4" font-family="sans-serif" font-size="30">{escape(str(shot.get('id', 'shot')))} · {escape(str(shot.get('type', 'medium')))}</text>
<foreignObject x="100" y="300" width="1400" height="260">
  <div xmlns="http://www.w3.org/1999/xhtml" style="color:#f7f1e8;font:28px sans-serif;line-height:1.4">{escape(prompt)}</div>
</foreignObject>
<text x="100" y="760" fill="#aaa092" font-family="monospace" font-size="24">seed: {digest}</text>
</svg>
"""
        output_path.write_text(svg, encoding="utf-8")
        render_path = output_path.with_suffix(".ppm")
        red, green, blue = 35 + raw_digest[0] // 3, 32 + raw_digest[1] // 4, 28 + raw_digest[2] // 5
        pixel = f"{red} {green} {blue}"
        render_path.write_text(f"P3\n640 360\n255\n" + (pixel + "\n") * (640 * 360), encoding="ascii")
        return {
            "id": str(shot["id"]),
            "kind": "image",
            "uri": output_path.name,
            "license": "Cinemata-generated-mock",
            "source": self.name,
            "render_uri": render_path.name,
            "provider": {"name": self.name, "version": self.version, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()},
        }


class MockVoiceProvider:
    """生成确定性的提示音 WAV，占位验证音频时间轴和导出流程。"""

    name = "mock-voice"
    version = "0.1.0"
    sample_rate = 16_000

    def generate(self, text: str, duration: float, output_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """根据对白哈希生成短音调，不访问外部服务或上传文本。"""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        frequency = 220 + digest[0]
        frame_count = max(1, round(duration * self.sample_rate))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(self.sample_rate)
            frames = bytearray()
            for index in range(frame_count):
                envelope = min(1.0, index / max(1, self.sample_rate * 0.05), (frame_count - index) / max(1, self.sample_rate * 0.05))
                value = int(9000 * envelope * math.sin(2 * math.pi * frequency * index / self.sample_rate))
                frames.extend(struct.pack("<h", value))
            audio.writeframes(frames)
        return {
            "id": str(metadata["id"]),
            "kind": "audio",
            "uri": output_path.name,
            "license": "Cinemata-generated-mock",
            "source": self.name,
            "provider": {"name": self.name, "version": self.version, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()},
        }


class OpenAIImageProvider:
    """调用 OpenAI Images API 生成 PNG；API key 只从环境变量读取。"""

    name = "openai-image"
    version = "0.1.0"
    asset_extension = "png"
    endpoint = "https://api.openai.com/v1/images/generations"

    def __init__(self, api_key: str | None = None, model: str = "gpt-image-1") -> None:
        """初始化 provider，避免把密钥写入 manifest 或命令行历史。"""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        if not self.api_key:
            raise ValueError("使用 openai provider 前请设置 OPENAI_API_KEY")

    def generate(self, shot: dict[str, Any], output_path: Path) -> dict[str, Any]:
        """提交镜头 prompt，下载返回的图片并记录请求摘要。"""
        prompt = str(shot.get("prompt", ""))
        if not prompt.strip():
            raise ValueError(f"镜头 {shot.get('id', 'unknown')} 的 prompt 不能为空")
        payload = json.dumps({"model": self.model, "prompt": prompt, "size": "1536x1024", "n": 1}).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            raise ProviderError(f"OpenAI 图片生成请求失败: {exc}") from exc
        data = result.get("data", [])
        if not data or not isinstance(data[0], dict):
            raise ProviderError("OpenAI 图片生成响应缺少 data[0]")
        item = data[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if item.get("b64_json"):
            output_path.write_bytes(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            try:
                with urllib.request.urlopen(item["url"], timeout=120) as image_response:
                    output_path.write_bytes(image_response.read())
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                raise ProviderError(f"OpenAI 图片下载失败: {exc}") from exc
        else:
            raise ProviderError("OpenAI 图片生成响应缺少 url 或 b64_json")
        return {
            "id": str(shot["id"]), "kind": "image", "uri": output_path.name,
            "license": "provider-dependent", "source": self.name,
            "provider": {"name": self.name, "version": self.version, "model": self.model, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()},
        }
