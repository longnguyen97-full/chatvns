from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = PROJECT_ROOT / "data" / "raw"
TEXT_EXTENSIONS = {
    ".csv",
    ".html",
    ".htm",
    ".json",
    ".log",
    ".md",
    ".txt",
    ".xml",
}


@dataclass(frozen=True)
class EmptyFile:
    path: Path
    reason: str
    size_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find and optionally delete empty raw data files."
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="Directory to scan. Default: data/raw",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete files. Without this flag the script only prints a dry-run report.",
    )
    parser.add_argument(
        "--remove-empty-dirs",
        action="store_true",
        help="Remove directories that become empty after deleting files.",
    )
    parser.add_argument(
        "--remove-orphan-metadata",
        action="store_true",
        help="Delete *.metadata.json files whose referenced artifact_path no longer exists.",
    )
    parser.add_argument(
        "--max-inspect-bytes",
        type=int,
        default=2_000_000,
        help="Only inspect text/CSV/JSON contents up to this size. Zero-byte files are always matched.",
    )
    return parser.parse_args()


def resolve_scan_root(root: str) -> Path:
    path = Path(root)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def is_empty_json(path: Path) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return value in ({}, [], None, "")


def is_empty_csv(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if any(cell.strip() for cell in row):
                    return False
    except (OSError, UnicodeDecodeError, csv.Error):
        return False
    return True


def classify_empty_file(path: Path, max_inspect_bytes: int) -> str | None:
    size = path.stat().st_size
    if size == 0:
        return "zero-byte"

    if size > max_inspect_bytes or path.suffix.lower() not in TEXT_EXTENSIONS:
        return None

    suffix = path.suffix.lower()
    if suffix == ".json" and is_empty_json(path):
        return "empty-json"
    if suffix == ".csv" and is_empty_csv(path):
        return "empty-csv"

    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None

    if not text.strip():
        return "whitespace-only"
    return None


def find_empty_files(root: Path, max_inspect_bytes: int) -> list[EmptyFile]:
    empty_files: list[EmptyFile] = []
    if not root.exists():
        return empty_files

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        reason = classify_empty_file(path, max_inspect_bytes)
        if reason:
            empty_files.append(
                EmptyFile(path=path, reason=reason, size_bytes=path.stat().st_size)
            )
    return empty_files


def metadata_artifact_path(metadata_path: Path) -> Path | None:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    artifact_path = metadata.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        return None

    resolved = Path(artifact_path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved.resolve()


def find_orphan_metadata(root: Path) -> list[EmptyFile]:
    orphan_metadata: list[EmptyFile] = []
    if not root.exists():
        return orphan_metadata

    for path in root.rglob("*.metadata.json"):
        artifact_path = metadata_artifact_path(path)
        if artifact_path and not artifact_path.exists():
            orphan_metadata.append(
                EmptyFile(
                    path=path,
                    reason="orphan-metadata",
                    size_bytes=path.stat().st_size,
                )
            )
    return orphan_metadata


def delete_files(files: Iterable[EmptyFile]) -> int:
    deleted_count = 0
    for item in files:
        try:
            item.path.unlink()
            deleted_count += 1
        except FileNotFoundError:
            continue
    return deleted_count


def remove_empty_dirs(root: Path) -> int:
    removed_count = 0
    if not root.exists():
        return removed_count

    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
            removed_count += 1
        except OSError:
            continue
    return removed_count


def print_report(files: list[EmptyFile], apply: bool) -> None:
    mode = "DELETE" if apply else "DRY-RUN"
    print(f"{mode}: found {len(files)} removable file(s).")
    for item in files:
        relative = item.path.relative_to(PROJECT_ROOT)
        print(f"- {relative.as_posix()} | {item.reason} | {item.size_bytes} bytes")


def main() -> int:
    args = parse_args()
    root = resolve_scan_root(args.root)

    files = find_empty_files(root, args.max_inspect_bytes)
    if args.remove_orphan_metadata:
        files.extend(find_orphan_metadata(root))

    files = sorted(
        {item.path: item for item in files}.values(),
        key=lambda item: item.path.as_posix(),
    )
    print_report(files, args.apply)

    if not args.apply:
        print("No files were deleted. Re-run with --apply to delete them.")
        return 0

    deleted_count = delete_files(files)
    removed_dir_count = remove_empty_dirs(root) if args.remove_empty_dirs else 0
    print(f"Deleted {deleted_count} file(s). Removed {removed_dir_count} empty dir(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
