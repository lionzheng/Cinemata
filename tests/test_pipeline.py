import json
import tempfile
import unittest
from pathlib import Path

from cinemata.pipeline import ManifestError, build_episode, load_manifest, normalize_timeline


ROOT = Path(__file__).parents[1]


class PipelineTest(unittest.TestCase):
    """验证第一条生产流程的核心契约。"""

    def test_build_episode_writes_reviewable_artifacts(self):
        """示例 manifest 应生成四类可审阅产物。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = build_episode(ROOT / "examples" / "episode-01.json", Path(temp_dir))
            self.assertEqual(set(outputs), {"timeline", "storyboard", "subtitles", "provenance"})
            self.assertIn("shot-001", outputs["storyboard"].read_text(encoding="utf-8"))
            self.assertIn("00:00:00,000 --> 00:00:02,500", outputs["subtitles"].read_text(encoding="utf-8"))
            provenance = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
            self.assertEqual(provenance["pipeline"]["name"], "cinemata-core")

    def test_dialogue_must_reference_existing_shot(self):
        """对白引用未知镜头时必须阻止生成错误字幕。"""
        manifest = load_manifest(ROOT / "examples" / "episode-01.json")
        manifest["scenes"][0]["dialogue"][0]["shot_id"] = "missing"
        timeline = normalize_timeline(manifest)
        from cinemata.pipeline import render_subtitles

        with self.assertRaises(ManifestError):
            render_subtitles(manifest, timeline)


if __name__ == "__main__":
    unittest.main()
