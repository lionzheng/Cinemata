"""媒体 provider 的稳定边界和本地可复现实现。"""

from __future__ import annotations

import hashlib
import math
import struct
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


class MockImageProvider:
    """生成确定性的 SVG 占位帧，用于本地开发、审阅和 CI。"""

    name = "mock-image"
    version = "0.1.0"

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
