"""使用 FFmpeg 将 Cinemata 产物合成为可播放视频。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


class RenderError(RuntimeError):
    """Raised when the local media renderer cannot produce a video."""


def _dialogue_starts(manifest: dict[str, Any], timeline: dict[str, Any]) -> list[tuple[str, float]]:
    """计算对白音频在全片时间轴中的起点。"""
    starts: list[tuple[str, float]] = []
    scene_offset = 0.0
    for scene_index, (scene, normalized) in enumerate(zip(manifest["scenes"], timeline["scenes"]), start=1):
        shot_start = {shot["id"]: shot["start"] for shot in normalized["shots"]}
        for dialogue_index, dialogue in enumerate(scene.get("dialogue", []), start=1):
            starts.append((f"dialogue-{scene_index:02}-{dialogue_index:02}.wav", scene_offset + shot_start[dialogue["shot_id"]]))
        scene_offset += sum(shot["duration"] for shot in normalized["shots"])
    return starts


def render_video(output_dir: Path, output_path: Path) -> Path:
    """将 build 产物合成为 MP4；要求 output_dir 已由 build 命令生成。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RenderError("未找到 ffmpeg，请安装 FFmpeg 并加入 PATH")
    manifest_path = output_dir / "manifest.json"
    timeline_path = output_dir / "timeline.json"
    if not manifest_path.exists() or not timeline_path.exists():
        raise RenderError("输入目录缺少 manifest.json 或 timeline.json，请先运行 cinemata build")
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    shots = [shot for scene in timeline["scenes"] for shot in scene["shots"]]
    if not shots:
        raise RenderError("时间轴没有镜头")
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for shot in shots:
        ppm_path = output_dir / "assets" / f"{shot['id']}.ppm"
        svg_path = output_dir / "assets" / f"{shot['id']}.svg"
        png_path = output_dir / "assets" / f"{shot['id']}.png"
        frame_path = ppm_path if ppm_path.exists() else (png_path if png_path.exists() else svg_path)
        args.extend(["-loop", "1", "-t", str(shot["duration"]), "-i", str(frame_path)])
    dialogue_files = _dialogue_starts(manifest, timeline)
    for filename, _ in dialogue_files:
        args.extend(["-i", str(output_dir / "assets" / filename)])
    filters: list[str] = []
    video_labels: list[str] = []
    for index, shot in enumerate(shots):
        label = f"v{index}"
        filters.append(f"[{index}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1[{label}]")
        video_labels.append(f"[{label}]")
    filters.append(f"{''.join(video_labels)}concat=n={len(shots)}:v=1:a=0[vout]")
    audio_start_index = len(shots)
    audio_labels: list[str] = []
    for offset_index, (_, start) in enumerate(dialogue_files):
        input_index = audio_start_index + offset_index
        label = f"a{offset_index}"
        delay_ms = round(start * 1000)
        filters.append(f"[{input_index}:a]adelay={delay_ms}|{delay_ms}[{label}]")
        audio_labels.append(f"[{label}]")
    if audio_labels:
        filters.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0[aout]")
        audio_map = "[aout]"
    else:
        args.extend(["-f", "lavfi", "-t", str(timeline["duration"]), "-i", "anullsrc=channel_layout=mono:sample_rate=16000"])
        audio_map = f"{audio_start_index}:a"
    subtitle_path = output_dir / "subtitles.srt"
    subtitle_input_index = audio_start_index + max(1, len(dialogue_files))
    if subtitle_path.exists():
        args.extend(["-i", str(subtitle_path)])
    args.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", audio_map, "-t", str(timeline["duration"]), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
    if subtitle_path.exists():
        args.extend(["-map", f"{subtitle_input_index}:s:0", "-c:s", "mov_text", "-metadata:s:s:0", "language=chi"])
    args.extend([str(output_path)])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RenderError(completed.stderr.strip() or "ffmpeg 渲染失败")
    return output_path
