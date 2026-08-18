"""Cinemata 命令行入口。"""

import argparse
from pathlib import Path

from .pipeline import ManifestError, build_episode


def main() -> int:
    """解析命令并运行 episode build。"""
    parser = argparse.ArgumentParser(prog="cinemata", description="Build reviewable episodic media artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="compile an episode manifest")
    build.add_argument("manifest", type=Path)
    build.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        outputs = build_episode(args.manifest, args.output)
    except (OSError, ManifestError, ValueError) as exc:
        parser.error(str(exc))
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
