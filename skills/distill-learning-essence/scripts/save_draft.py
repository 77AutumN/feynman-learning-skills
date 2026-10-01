#!/usr/bin/env python3
"""Save one learning-essence draft as a new Markdown revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

import yaml


MAX_CHARACTERS = 900
MAX_REVISION = 999
SERIES_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SESSION_RE = re.compile(r"^session-[0-9]{8}-[0-9]{6}$")


class SaveDraftError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SaveDraftError("invalid_arguments", message)


def _series(value: str) -> str:
    value = value.strip()
    if not SERIES_RE.fullmatch(value):
        raise SaveDraftError("invalid_series", "series 必须是小写 kebab-case")
    return value


def _episode(value: str) -> str:
    value = value.strip()
    if SESSION_RE.fullmatch(value):
        return value
    if not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise SaveDraftError("invalid_episode", "episode 必须是正整数或 session-YYYYMMDD-HHMMSS")
    return f"{int(value):02d}"


def _workspace_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    if not root.is_dir():
        raise SaveDraftError("invalid_workspace", f"工作区不存在：{root}")
    return root


def _workspace_file(root: Path, value: str, label: str) -> tuple[Path, str]:
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise SaveDraftError("invalid_path", f"{label} 必须是工作区内的相对路径：{value}")
    path = (root / Path(*pure.parts)).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise SaveDraftError("invalid_path", f"{label} 超出工作区：{value}") from exc
    if not path.is_file():
        raise SaveDraftError("missing_file", f"{label} 不存在：{relative}")
    return path, relative


def _body(root: Path, body_file: str) -> str:
    path, _ = _workspace_file(root, body_file, "body-file")
    try:
        body = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").strip()
    except UnicodeDecodeError as exc:
        raise SaveDraftError("invalid_body", "body-file 必须是 UTF-8 文本") from exc
    if not body:
        raise SaveDraftError("invalid_body", "正文不能为空")
    if len(body) > MAX_CHARACTERS:
        raise SaveDraftError("body_too_long", f"正文为 {len(body)} 字，超过 900 字上限")
    return body


def _sources(root: Path, values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        _, relative = _workspace_file(root, value, "source")
        if relative in result:
            raise SaveDraftError("duplicate_source", f"source 重复：{relative}")
        result.append(relative)
    return result


def _document(metadata: Mapping[str, object], body: str) -> str:
    frontmatter = yaml.safe_dump(
        dict(metadata), allow_unicode=True, sort_keys=False, default_flow_style=False
    ).rstrip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def save_draft(
    *,
    workspace_root: str | Path,
    series: str,
    episode: str,
    topic: str,
    body_file: str,
    source_paths: Sequence[str] = (),
    generated_at: str | None = None,
) -> dict[str, object]:
    root = _workspace_root(workspace_root)
    canonical_series = _series(series)
    canonical_episode = _episode(episode)
    clean_topic = topic.strip()
    if not clean_topic:
        raise SaveDraftError("invalid_topic", "topic 不能为空")
    body = _body(root, body_file)
    sources = _sources(root, source_paths)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    output_dir = (root / "artifacts" / "drafts" / "learning-essence" / canonical_series).resolve()
    if not output_dir.is_relative_to(root):
        raise SaveDraftError("invalid_path", "保存目录超出工作区")
    output_dir.mkdir(parents=True, exist_ok=True)

    for revision in range(1, MAX_REVISION + 1):
        draft_id = f"{canonical_series}/{canonical_episode}-r{revision:03d}"
        metadata: dict[str, object] = {
            "schema": "learning-essence-draft/v1",
            "draft_id": draft_id,
            "series": canonical_series,
            "episode": canonical_episode,
            "topic": clean_topic,
            "generated_at": timestamp,
            "source_paths": sources,
            "character_count": len(body),
        }
        target = output_dir / f"{canonical_episode}-r{revision:03d}.md"
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(_document(metadata, body))
        except FileExistsError:
            continue
        relative = target.relative_to(root).as_posix()
        return {
            "ok": True,
            "saved_path": relative,
            "logical_body": body,
            "logical_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "metadata": metadata,
        }
    raise SaveDraftError("revision_exhausted", "r001..r999 均已存在")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--series", required=True)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--source", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        args = build_parser().parse_args(argv)
        result = save_draft(
            workspace_root=args.workspace_root,
            series=args.series,
            episode=args.episode,
            topic=args.topic,
            body_file=args.body_file,
            source_paths=args.source,
        )
        code = 0
    except SaveDraftError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        code = 2
    except (OSError, yaml.YAMLError) as exc:
        result = {"ok": False, "error": {"code": "save_failed", "message": str(exc)}}
        code = 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
