from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).parents[1] / "scripts" / "save_draft.py"
SPEC = importlib.util.spec_from_file_location("save_draft", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class SaveDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "scratch").mkdir()
        (self.root / "content" / "learning-notes" / "cache-basics").mkdir(parents=True)
        self.body_file = self.root / "scratch" / "body.md"
        self.body_file.write_text("第 01 集精华 · Cache hit\n\n一句话：有副本，就能省掉重复查询。\n\n收束：命中依赖可用副本。", encoding="utf-8")
        self.source = self.root / "content" / "learning-notes" / "cache-basics" / "01.md"
        self.source.write_text("source", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def save(self, **changes):
        options = {
            "workspace_root": self.root,
            "series": "cache-basics",
            "episode": "1",
            "topic": "Cache hit",
            "body_file": "scratch/body.md",
            "source_paths": ["content/learning-notes/cache-basics/01.md"],
            "generated_at": "2026-08-08T00:00:00Z",
        }
        options.update(changes)
        return MODULE.save_draft(**options)

    @staticmethod
    def read_document(path: Path):
        text = path.read_text(encoding="utf-8")
        _, frontmatter, body = text.split("---", 2)
        return yaml.safe_load(frontmatter), body.strip()

    def test_success_saves_markdown_and_core_metadata(self):
        result = self.save()
        self.assertTrue(result["ok"])
        path = self.root / result["saved_path"]
        metadata, body = self.read_document(path)
        self.assertEqual("cache-basics/01-r001", metadata["draft_id"])
        self.assertEqual("cache-basics", metadata["series"])
        self.assertEqual("01", metadata["episode"])
        self.assertEqual("Cache hit", metadata["topic"])
        self.assertEqual(["content/learning-notes/cache-basics/01.md"], metadata["source_paths"])
        self.assertEqual(len(body), metadata["character_count"])
        self.assertEqual(result["logical_body"], body)

    def test_901_characters_are_rejected(self):
        self.body_file.write_text("字" * 901, encoding="utf-8")
        with self.assertRaises(MODULE.SaveDraftError) as caught:
            self.save()
        self.assertEqual("body_too_long", caught.exception.code)
        self.assertFalse((self.root / "artifacts").exists())
        self.body_file.write_text("字" * 450 + "😀" * 450, encoding="utf-8")
        self.assertEqual(900, self.save()["metadata"]["character_count"])

    def test_new_revision_never_overwrites_existing_file(self):
        first = self.save()
        first_path = self.root / first["saved_path"]
        original = first_path.read_bytes()
        self.body_file.write_text("第二版正文", encoding="utf-8")
        second = self.save()
        self.assertTrue(first["saved_path"].endswith("01-r001.md"))
        self.assertTrue(second["saved_path"].endswith("01-r002.md"))
        self.assertEqual(original, first_path.read_bytes())

    def test_bad_parameters_are_rejected(self):
        for changes in (
            {"series": "Cache Basics"},
            {"episode": "²"},
            {"body_file": "../body.md"},
            {"source_paths": ["../source.md"]},
        ):
            with self.subTest(changes=changes), self.assertRaises(MODULE.SaveDraftError):
                self.save(**changes)

    def test_sources_and_normalized_body_are_recorded(self):
        self.body_file.write_bytes("\r\n标题\r\n\r\n正文😀\r\n".encode("utf-8"))
        result = self.save(source_paths=[r"content\learning-notes\cache-basics\01.md"])
        metadata, body = self.read_document(self.root / result["saved_path"])
        self.assertEqual(["content/learning-notes/cache-basics/01.md"], metadata["source_paths"])
        self.assertEqual("标题\n\n正文😀", result["logical_body"])
        self.assertEqual(result["logical_body"], body)
        with self.assertRaises(MODULE.SaveDraftError) as caught:
            self.save(source_paths=["content/learning-notes/cache-basics/01.md"] * 2)
        self.assertEqual("duplicate_source", caught.exception.code)

    def test_cli_emits_one_json_result(self):
        command = [
            sys.executable,
            str(SCRIPT),
            "--workspace-root", str(self.root),
            "--series", "cache-basics",
            "--episode", "1",
            "--topic", "Cache hit",
            "--body-file", "scratch/body.md",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        payload = json.loads(completed.stdout)
        self.assertEqual(0, completed.returncode)
        self.assertTrue(payload["ok"])
        self.assertEqual("", completed.stderr)
        self.assertEqual(1, len(completed.stdout.splitlines()))
        rejected = subprocess.run(command + ["--unknown"], capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(2, rejected.returncode)
        self.assertEqual("invalid_arguments", json.loads(rejected.stdout)["error"]["code"])
        self.assertEqual("", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
