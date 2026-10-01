"""Small checks for portable assets, manifest integrity, and safe replacement."""

import binascii
import importlib.util
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock


TEMPLATE = Path(__file__).resolve().parents[1] / "templates/render_cards.py"
spec = importlib.util.spec_from_file_location("renderer", TEMPLATE)
renderer = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(renderer)


def png_bytes():
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", binascii.crc32(kind + body) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", 2160, 2880, 8, 0, 0, 0, 0)
    pixels = zlib.compress(bytes((2160 + 1) * 2880))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class RendererTests(unittest.TestCase):
    def test_assets_resolve_in_supported_layouts_and_explicit_install(self):
        for layout in ("skills", ".agents/skills", ".codex/skills", "home/.agents/skills", "home/.codex/skills", "custom"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                skill = root / layout / "feynman-notes"
                for relative in ("assets/fonts/notosanssc.ttf", "schemas/card-manifest.schema.json"):
                    target = skill / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"asset")
                env = {"FEYNMAN_NOTES_SKILL_DIR": str(skill)} if layout == "custom" else {}
                with mock.patch.dict(os.environ, env, clear=True), \
                     mock.patch.object(renderer, "__file__", str(root / "loose/render_cards.py")), \
                     mock.patch.object(renderer, "SCRIPT_DIR", root / "notes/cards"), \
                     mock.patch.object(Path, "cwd", return_value=root / "notes"), \
                     mock.patch.object(Path, "home", return_value=root / "home"):
                    self.assertEqual(skill.resolve(), renderer.find_skill_dir().resolve())

    def test_invalid_explicit_install_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"FEYNMAN_NOTES_SKILL_DIR": tmp}):
            with self.assertRaises(SystemExit):
                renderer.find_skill_dir()

    def test_manifest_roundtrip_rejects_damaged_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = root / "png"
            png.mkdir()
            image = png / "01_example.png"
            image.write_bytes(png_bytes())
            cards = [("01_example", "<html></html>")]
            gallery = root / "01-cards.html"
            manifest = root / "01-card-manifest.json"
            with mock.patch.object(renderer, "SCRIPT_DIR", root), \
                 mock.patch.object(renderer, "WORKSPACE_ROOT", root):
                renderer.write_gallery("01", "example", cards, gallery)
                renderer.write_manifest("01", "example", cards, png, gallery, manifest, "rendered")
                renderer.validate_staged_episode("01", "example", cards, png, gallery, manifest)
                image.write_bytes(image.read_bytes()[:-10])
                with self.assertRaisesRegex(RuntimeError, "invalid PNG dimensions"):
                    renderer.validate_staged_episode("01", "example", cards, png, gallery, manifest)

    def test_failed_commit_restores_all_old_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png, stage = root / "png", root / "stage"
            png.mkdir()
            stage.mkdir()
            stage_png = stage / "png"
            stage_png.mkdir()
            names = ("01-cards.html", "01-card-manifest.json")
            for name in names:
                (root / name).write_text("old", encoding="utf-8")
                (stage / name).write_text("new", encoding="utf-8")
            (png / "01_example.png").write_bytes(b"old image")
            (stage_png / "01_example.png").write_bytes(b"new image")
            replace = os.replace

            def fail_gallery(source, target):
                if source == stage / names[0]:
                    raise OSError("simulated commit failure")
                return replace(source, target)

            with mock.patch.object(renderer.os, "replace", side_effect=fail_gallery):
                with self.assertRaisesRegex(OSError, "simulated"):
                    renderer.commit_staged_episode("01", root, png, stage_png, stage / names[0], stage / names[1])
            self.assertEqual(b"old image", (png / "01_example.png").read_bytes())
            for name in names:
                self.assertEqual("old", (root / name).read_text(encoding="utf-8"))

    def test_failed_manifest_replace_preserves_old_file_and_stale_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "01-card-manifest.json"
            staged = root / "new.json"
            stale = root / ".01-card-manifest.backup.json"
            formal.write_text("old", encoding="utf-8")
            staged.write_text("new", encoding="utf-8")
            stale.write_text("stale", encoding="utf-8")
            with mock.patch.object(renderer.os, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    renderer.commit_staged_manifest("01", root, staged)
            self.assertEqual("old", formal.read_text(encoding="utf-8"))
            self.assertEqual("new", staged.read_text(encoding="utf-8"))
            self.assertEqual("stale", stale.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
