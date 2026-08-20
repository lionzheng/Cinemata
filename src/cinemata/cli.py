"""Cinemata 命令行入口。"""

import argparse
from pathlib import Path

from .pipeline import ManifestError, build_episode
from .providers import MockImageProvider, OpenAIImageProvider, ProviderError
from .render import RenderError, render_video


def main() -> int:
    """解析命令并运行 episode build。"""
    parser = argparse.ArgumentParser(prog="cinemata", description="Build reviewable episodic media artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="compile an episode manifest")
    build.add_argument("manifest", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--image-provider", choices=("mock", "openai"), default="mock")
    build.add_argument("--openai-model", default="gpt-image-1")
    render = subparsers.add_parser("render", help="render build artifacts to MP4")
    render.add_argument("input", type=Path)
    render.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            provider = MockImageProvider() if args.image_provider == "mock" else OpenAIImageProvider(model=args.openai_model)
            outputs = build_episode(args.manifest, args.output, image_provider=provider)
        else:
            outputs = {"video": render_video(args.input, args.output)}
    except (OSError, ManifestError, ProviderError, RenderError, ValueError) as exc:
        parser.error(str(exc))
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
