"""Deterministic episode compilation primitives."""

from __future__ import annotations

import json
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .providers import ImageProvider, MockImageProvider, MockVoiceProvider, VoiceProvider


class ManifestError(ValueError):
    """Raised when an episode manifest violates the public data contract."""


def load_manifest(path: Path) -> dict[str, Any]:
    """读取 JSON manifest，并校验首层结构和必填字段。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError("manifest 必须是 JSON 对象")
    for key in ("project", "episode", "scenes"):
        if key not in data:
            raise ManifestError(f"manifest 缺少必填字段: {key}")
    if not isinstance(data["scenes"], list) or not data["scenes"]:
        raise ManifestError("scenes 必须是非空数组")
    return data


def _duration(value: Any, field: str) -> float:
    """校验并标准化时间字段，避免生成负数或不可排序的时间轴。"""
    if not isinstance(value, (int, float)) or value <= 0:
        raise ManifestError(f"{field} 必须是大于 0 的数字")
    return float(value)


def normalize_timeline(manifest: dict[str, Any]) -> dict[str, Any]:
    """把场景和镜头展开成连续时间轴，并保留原始业务标识。"""
    current = 0.0
    scenes: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(manifest["scenes"], start=1):
        if not isinstance(scene, dict) or not scene.get("id"):
            raise ManifestError(f"scenes[{scene_index - 1}] 缺少 id")
        shots = scene.get("shots")
        if not isinstance(shots, list) or not shots:
            raise ManifestError(f"场景 {scene['id']} 必须包含 shots")
        normalized_shots: list[dict[str, Any]] = []
        for shot_index, shot in enumerate(shots, start=1):
            if not isinstance(shot, dict) or not shot.get("id"):
                raise ManifestError(f"场景 {scene['id']} 的镜头 {shot_index} 缺少 id")
            duration = _duration(shot.get("duration"), f"镜头 {shot.get('id', shot_index)}.duration")
            start = current
            current += duration
            normalized_shots.append({
                "id": shot["id"],
                "type": shot.get("type", "medium"),
                "prompt": shot.get("prompt", ""),
                "start": start,
                "end": current,
                "duration": duration,
            })
        scenes.append({
            "id": scene["id"],
            "location": scene.get("location", ""),
            "characters": scene.get("characters", []),
            "shots": normalized_shots,
        })
    return {
        "project": manifest["project"],
        "episode": manifest["episode"],
        "duration": current,
        "scenes": scenes,
    }


def _srt_time(seconds: float) -> str:
    """把秒数格式化为 SRT 要求的时分秒毫秒格式。"""
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def render_subtitles(manifest: dict[str, Any], timeline: dict[str, Any]) -> str:
    """按场景 dialogue 生成可直接导入剪辑软件的 SRT 字幕。"""
    entries: list[str] = []
    index = 1
    scene_offset = 0.0
    for scene, normalized in zip(manifest["scenes"], timeline["scenes"]):
        shot_start = {shot["id"]: shot["start"] for shot in normalized["shots"]}
        for dialogue in scene.get("dialogue", []):
            shot_id = dialogue.get("shot_id")
            if shot_id not in shot_start:
                raise ManifestError(f"对白引用了不存在的镜头: {shot_id}")
            start = scene_offset + shot_start[shot_id]
            duration = _duration(dialogue.get("duration", 2), f"对白 {index}.duration")
            end = start + duration
            speaker = dialogue.get("character", "旁白")
            text = str(dialogue.get("text", "")).strip()
            if not text:
                raise ManifestError(f"对白 {index} 文本不能为空")
            entries.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n[{speaker}] {text}\n")
            index += 1
        scene_offset += sum(shot["duration"] for shot in normalized["shots"])
    return "\n".join(entries)


def render_storyboard(manifest: dict[str, Any], timeline: dict[str, Any]) -> str:
    """生成 Markdown 分镜审阅稿，作为后续媒体 provider 的人工审核入口。"""
    lines = [f"# {manifest['project']} - Episode {manifest['episode']}", "", f"总时长: {timeline['duration']:.2f}s", ""]
    for scene in timeline["scenes"]:
        lines.extend([f"## 场景 `{scene['id']}`", f"地点: {scene['location'] or '未指定'}", f"人物: {', '.join(scene['characters']) or '未指定'}", ""])
        for shot in scene["shots"]:
            lines.append(f"- `{shot['id']}` [{shot['start']:.2f}s - {shot['end']:.2f}s] {shot['type']}: {shot['prompt']}")
        lines.append("")
        for dialogue in manifest["scenes"][timeline["scenes"].index(scene)].get("dialogue", []):
            lines.append(f"  - **{dialogue.get('character', '旁白')}**（{dialogue['shot_id']}）: {dialogue['text']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_review_html(manifest: dict[str, Any], timeline: dict[str, Any], generated_assets: dict[str, str] | None = None, audio_assets: dict[str, str] | None = None) -> str:
    """生成无需构建工具即可打开的浏览器审阅页，便于逐镜头检查内容。"""
    generated_assets = generated_assets or {}
    audio_assets = audio_assets or {}
    scene_blocks: list[str] = []
    for scene_index, scene in enumerate(timeline["scenes"]):
        source_scene = manifest["scenes"][scene_index]
        dialogue_by_shot: dict[str, list[str]] = {}
        for dialogue_index, dialogue in enumerate(source_scene.get("dialogue", []), start=1):
            speaker = escape(str(dialogue.get("character", "旁白")))
            text = escape(str(dialogue.get("text", "")))
            audio_id = f"dialogue-{scene_index + 1:02}-{dialogue_index:02}"
            audio = f"<audio controls preload=\"none\" src=\"{escape(audio_assets[audio_id])}\"></audio>" if audio_id in audio_assets else ""
            dialogue_by_shot.setdefault(dialogue["shot_id"], []).append(f"<p><strong>{speaker}</strong> {text}<br>{audio}</p>")
        shot_cards: list[str] = []
        for shot in scene["shots"]:
            prompt = escape(shot["prompt"] or "等待媒体 provider 生成画面")
            dialogue = "".join(dialogue_by_shot.get(shot["id"], []))
            frame = f"<img src=\"{escape(generated_assets[shot['id']])}\" alt=\"{escape(shot['id'])} mock frame\">" if shot["id"] in generated_assets else f"<span>{escape(shot['type'])}</span>"
            shot_cards.append(
                "<article class=\"shot\">"
                f"<div class=\"frame\">{frame}</div>"
                f"<h3>{escape(shot['id'])}</h3>"
                f"<p class=\"timing\">{shot['start']:.2f}s - {shot['end']:.2f}s</p>"
                f"<p>{prompt}</p>{dialogue}</article>"
            )
        scene_blocks.append(
            f"<section><h2>场景 {escape(scene['id'])}</h2>"
            f"<p class=\"meta\">地点：{escape(scene['location'] or '未指定')}　人物：{escape(', '.join(scene['characters']) or '未指定')}</p>"
            f"<div class=\"shots\">{''.join(shot_cards)}</div></section>"
        )
    title = escape(f"{manifest['project']} - Episode {manifest['episode']}")
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>{title}</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; background: #f4f1eb; color: #25231f; }}
body {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 60px; }}
header {{ border-bottom: 2px solid #25231f; margin-bottom: 28px; }}
h1 {{ margin-bottom: 6px; }}
.summary, .meta, .timing {{ color: #655f55; }}
section {{ margin: 28px 0 40px; }}
.shots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
.shot {{ background: #fff; border: 1px solid #d8d0c4; padding: 14px; box-shadow: 3px 3px 0 #d8d0c4; }}
.shot h3 {{ margin: 12px 0 2px; }}
.shot p {{ line-height: 1.5; }}
.frame {{ aspect-ratio: 16 / 9; display: grid; place-items: center; background: #27251f; color: #f7f1e8; letter-spacing: .06em; text-transform: uppercase; }}
.frame img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.shot audio {{ width: 100%; margin-top: 4px; }}
.frame span {{ border: 1px solid #aaa092; padding: 5px 8px; font-size: .78rem; }}
strong {{ color: #8b3a2e; }}
</style>
</head>
<body>
<header><h1>{title}</h1><p class=\"summary\">Cinemata review draft · 总时长 {timeline['duration']:.2f}s</p></header>
{''.join(scene_blocks)}
</body>
</html>
"""


def build_episode(input_path: Path, output_dir: Path, image_provider: ImageProvider | None = None) -> dict[str, Path]:
    """执行第一条端到端流程并写出全部可审阅产物。"""
    manifest = load_manifest(input_path)
    timeline = normalize_timeline(manifest)
    image_provider = image_provider or MockImageProvider()
    voice_provider: VoiceProvider = MockVoiceProvider()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "timeline": output_dir / "timeline.json",
        "storyboard": output_dir / "storyboard.md",
        "review": output_dir / "review.html",
        "subtitles": output_dir / "subtitles.srt",
        "provenance": output_dir / "provenance.json",
        "manifest": output_dir / "manifest.json",
    }
    generated_assets: list[dict[str, Any]] = []
    generated_asset_urls: dict[str, str] = {}
    for scene in timeline["scenes"]:
        for shot in scene["shots"]:
            extension = getattr(image_provider, "asset_extension", "svg")
            asset_path = output_dir / "assets" / f"{shot['id']}.{extension}"
            generated_asset = image_provider.generate(shot, asset_path)
            generated_asset["uri"] = f"assets/{asset_path.name}"
            generated_assets.append(generated_asset)
            generated_asset_urls[shot["id"]] = generated_asset["uri"]
    audio_asset_urls: dict[str, str] = {}
    for scene_index, scene in enumerate(manifest["scenes"], start=1):
        for dialogue_index, dialogue in enumerate(scene.get("dialogue", []), start=1):
            audio_id = f"dialogue-{scene_index:02}-{dialogue_index:02}"
            audio_path = output_dir / "assets" / f"{audio_id}.wav"
            duration = _duration(dialogue.get("duration", 2), f"对白 {audio_id}.duration")
            audio_asset = voice_provider.generate(str(dialogue.get("text", "")), duration, audio_path, {"id": audio_id})
            audio_asset["uri"] = f"assets/{audio_path.name}"
            generated_assets.append(audio_asset)
            audio_asset_urls[audio_id] = audio_asset["uri"]
    outputs["timeline"].write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["storyboard"].write_text(render_storyboard(manifest, timeline), encoding="utf-8")
    outputs["review"].write_text(render_review_html(manifest, timeline, generated_asset_urls, audio_asset_urls), encoding="utf-8")
    outputs["subtitles"].write_text(render_subtitles(manifest, timeline), encoding="utf-8")
    provenance = {
        "schema_version": "0.1",
        "project": manifest["project"],
        "episode": manifest["episode"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": {"name": "cinemata-core", "version": "0.1.0"},
        "assets": manifest.get("assets", []) + generated_assets,
        "inputs": [{"path": str(input_path), "kind": "episode-manifest"}],
    }
    outputs["provenance"].write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return outputs
