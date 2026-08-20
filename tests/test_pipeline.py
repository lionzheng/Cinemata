import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinemata.pipeline import ManifestError, build_episode, load_manifest, normalize_timeline
from cinemata.providers import OpenAIImageProvider


ROOT = Path(__file__).parents[1]


class PipelineTest(unittest.TestCase):
    """验证第一条生产流程的核心契约。"""

    def test_build_episode_writes_reviewable_artifacts(self):
        """示例 manifest 应生成四类可审阅产物。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = build_episode(ROOT / "examples" / "episode-01.json", Path(temp_dir))
            self.assertEqual(set(outputs), {"timeline", "storyboard", "review", "subtitles", "provenance", "manifest"})
            self.assertIn("shot-001", outputs["storyboard"].read_text(encoding="utf-8"))
            review = outputs["review"].read_text(encoding="utf-8")
            self.assertIn("Cinemata review draft", review)
            self.assertIn("assets/shot-001.svg", review)
            self.assertTrue((Path(temp_dir) / "assets" / "shot-001.svg").exists())
            self.assertTrue((Path(temp_dir) / "assets" / "shot-001.ppm").exists())
            self.assertTrue((Path(temp_dir) / "assets" / "dialogue-01-01.wav").exists())
            self.assertIn("dialogue-01-01.wav", review)
            self.assertIn("00:00:00,000 --> 00:00:02,500", outputs["subtitles"].read_text(encoding="utf-8"))
            provenance = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
            self.assertEqual(provenance["pipeline"]["name"], "cinemata-core")
            self.assertEqual(len(provenance["assets"]), 5)

    def test_dialogue_must_reference_existing_shot(self):
        """对白引用未知镜头时必须阻止生成错误字幕。"""
        manifest = load_manifest(ROOT / "examples" / "episode-01.json")
        manifest["scenes"][0]["dialogue"][0]["shot_id"] = "missing"
        timeline = normalize_timeline(manifest)
        from cinemata.pipeline import render_subtitles

        with self.assertRaises(ManifestError):
            render_subtitles(manifest, timeline)

    def test_openai_provider_requires_environment_key(self):
        """真实 provider 未配置密钥时应在启动阶段给出明确错误。"""
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            OpenAIImageProvider()


if __name__ == "__main__":
    unittest.main()
