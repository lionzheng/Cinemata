"""媒体 provider 的稳定边界和本地可复现实现。"""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
from typing import Any, Protocol


class ImageProvider(Protocol):
    """图片 provider 必须根据镜头描述生成一个可引用的资产记录。"""

    def generate(self, shot: dict[str, Any], output_path: Path) -> dict[str, Any]:
        """生成镜头图片并返回 provenance 记录。"""


class MockImageProvider:
    """生成确定性的 SVG 占位帧，用于本地开发、审阅和 CI。"""

    name = "mock-image"
    version = "0.1.0"

    def generate(self, shot: dict[str, Any], output_path: Path) -> dict[str, Any]:
        """把 prompt 渲染为可视化占位帧，不访问外部服务。"""
        prompt = str(shot.get("prompt", "等待媒体 provider 生成画面"))
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
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
        return {
            "id": str(shot["id"]),
            "kind": "image",
            "uri": output_path.name,
            "license": "Cinemata-generated-mock",
            "source": self.name,
            "provider": {"name": self.name, "version": self.version, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()},
        }
