from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bili_transcript.cli import build_parser  # noqa: E402
from bili_transcript.config import (  # noqa: E402
    AUDIO_STREAM_PRIORITY,
    DEFAULT_DEVICE,
    DEFAULT_KEEP_AUDIO,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
)
from bili_transcript.extract import (  # noqa: E402
    format_timestamp,
    group_segments,
    resolve_input,
    segments_from_ai_conclusion,
    subtitle_score,
)
from bili_transcript.installer import install_skill  # noqa: E402


class ResolveInputTests(unittest.TestCase):
    def test_bvid(self) -> None:
        self.assertEqual(resolve_input("BV1xx411c7mD"), ({"bvid": "BV1xx411c7mD"}, 1))

    def test_full_url_with_page(self) -> None:
        result = resolve_input("https://www.bilibili.com/video/BV1xx411c7mD/?p=3")
        self.assertEqual(result, ({"bvid": "BV1xx411c7mD"}, 3))

    def test_av_number(self) -> None:
        self.assertEqual(resolve_input("av12345"), ({"aid": 12345}, 1))

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            resolve_input("https://example.com/not-bilibili")


class FormattingTests(unittest.TestCase):
    def test_timestamp(self) -> None:
        self.assertEqual(format_timestamp(65), "01:05")
        self.assertEqual(format_timestamp(3661), "1:01:01")
        self.assertEqual(format_timestamp(65, srt=True), "00:01:05,000")


class GroupingTests(unittest.TestCase):
    def test_groups_short_segments(self) -> None:
        segments = [
            {"start": 0.0, "end": 2.0, "text": "第一句。"},
            {"start": 2.5, "end": 4.0, "text": "第二句。"},
            {"start": 20.0, "end": 22.0, "text": "新段落。"},
        ]
        paragraphs = group_segments(segments, "zh", max_gap=2.0)
        self.assertEqual(len(paragraphs), 2)
        self.assertEqual(paragraphs[0]["text"], "第一句。第二句。")
        self.assertEqual(paragraphs[1]["start"], 20.0)


class SubtitleTests(unittest.TestCase):
    def test_prefers_human_chinese(self) -> None:
        human = {"lan": "zh-CN", "subtitle_url": "https://example.com/a"}
        ai = {"lan": "ai-zh", "subtitle_url": "https://example.com/b"}
        english = {"lan": "en-US", "subtitle_url": "https://example.com/c"}
        self.assertGreater(subtitle_score(human), subtitle_score(ai))
        self.assertGreater(subtitle_score(ai), subtitle_score(english))

    def test_ai_conclusion_segments(self) -> None:
        payload = {
            "model_result": {
                "subtitle": [
                    {
                        "part_subtitle": [
                            {"start_timestamp": 1.0, "end_timestamp": 2.0, "content": "你好"},
                        ]
                    }
                ]
            }
        }
        self.assertEqual(
            segments_from_ai_conclusion(payload),
            [{"start": 1.0, "end": 2.0, "text": "你好"}],
        )


class DefaultConfigTests(unittest.TestCase):
    def test_fetch_defaults_are_locked(self) -> None:
        args = build_parser().parse_args(["fetch", "BV1xx411c7mD"])
        self.assertEqual(args.model, DEFAULT_MODEL)
        self.assertEqual(args.device, DEFAULT_DEVICE)
        self.assertEqual(args.language, DEFAULT_LANGUAGE)
        self.assertEqual(args.keep_audio, DEFAULT_KEEP_AUDIO)
        self.assertFalse(args.no_asr)
        self.assertFalse(args.no_ai_summary)
        self.assertFalse(args.force)

    def test_preferred_audio_stream(self) -> None:
        self.assertEqual(AUDIO_STREAM_PRIORITY[0], 30216)


class SkillPackagingTests(unittest.TestCase):
    def test_skill_frontmatter(self) -> None:
        skill = Path(__file__).resolve().parent.parent / "skills" / "bili-transcript" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("name: bili-transcript", text)
        self.assertIn("description:", text)

    def test_installer_custom_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destinations = install_skill(set(), custom_dir=Path(tmp))
            self.assertTrue(destinations)
            self.assertTrue((Path(tmp) / "bili-transcript" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
