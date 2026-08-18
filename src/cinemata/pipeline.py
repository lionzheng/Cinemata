"""Deterministic episode compilation primitives."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def build_episode(input_path: Path, output_dir: Path) -> dict[str, Path]:
    """执行第一条端到端流程并写出全部可审阅产物。"""
    manifest = load_manifest(input_path)
    timeline = normalize_timeline(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "timeline": output_dir / "timeline.json",
        "storyboard": output_dir / "storyboard.md",
        "subtitles": output_dir / "subtitles.srt",
        "provenance": output_dir / "provenance.json",
    }
    outputs["timeline"].write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["storyboard"].write_text(render_storyboard(manifest, timeline), encoding="utf-8")
    outputs["subtitles"].write_text(render_subtitles(manifest, timeline), encoding="utf-8")
    provenance = {
        "schema_version": "0.1",
        "project": manifest["project"],
        "episode": manifest["episode"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": {"name": "cinemata-core", "version": "0.1.0"},
        "assets": manifest.get("assets", []),
        "inputs": [{"path": str(input_path), "kind": "episode-manifest"}],
    }
    outputs["provenance"].write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return outputs
