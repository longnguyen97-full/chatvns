from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.config import RAW_DIR


TIMESTAMP_PREFIX_LENGTH = 16
RAW_CATEGORIES = ["html", "text", "csv", "pdf", "images", "metadata"]
PRESERVED_FILENAMES = {"stock_overview_timeseries.csv"}


@dataclass(frozen=True)
class PruneCandidate:
    path: Path
    category: str
    scope: str
    logical_name: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune old timestamped artifacts under data/raw.")
    parser.add_argument("--keep", type=int, default=2, help="How many newest versions to keep per artifact.")
    parser.add_argument("--scope", help="Optional ticker/scope filter such as HPG, FPT, VCB, market.")
    parser.add_argument("--apply", action="store_true", help="Actually delete files. Without this flag, only dry-run.")
    return parser.parse_args()


def logical_name_for_file(path: Path) -> str | None:
    if path.name in PRESERVED_FILENAMES:
        return None
    if "__" not in path.name:
        return None
    prefix, remainder = path.name.split("__", 1)
    if len(prefix) != TIMESTAMP_PREFIX_LENGTH or "T" not in prefix:
        return None
    return remainder


def collect_candidates(scope_filter: str | None = None) -> list[PruneCandidate]:
    candidates: list[PruneCandidate] = []
    for category in RAW_CATEGORIES:
        category_dir = RAW_DIR / category
        if not category_dir.exists():
            continue
        for scope_dir in category_dir.iterdir():
            if not scope_dir.is_dir():
                continue
            scope = scope_dir.name
            if scope_filter and scope.lower() != scope_filter.lower():
                continue
            for path in scope_dir.iterdir():
                if not path.is_file():
                    continue
                logical_name = logical_name_for_file(path)
                if logical_name is None:
                    continue
                candidates.append(
                    PruneCandidate(
                        path=path,
                        category=category,
                        scope=scope,
                        logical_name=logical_name,
                    )
                )
    return candidates


def partition_candidates(candidates: list[PruneCandidate], keep: int) -> tuple[list[PruneCandidate], list[PruneCandidate]]:
    grouped: dict[tuple[str, str, str], list[PruneCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.category, candidate.scope, candidate.logical_name)].append(candidate)

    kept: list[PruneCandidate] = []
    deleted: list[PruneCandidate] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: item.path.name, reverse=True)
        kept.extend(ordered[:keep])
        deleted.extend(ordered[keep:])
    return kept, deleted


def format_summary(candidates: list[PruneCandidate]) -> dict[str, int]:
    summary: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        summary[candidate.category] += 1
    return dict(sorted(summary.items()))


def main() -> int:
    args = parse_args()
    candidates = collect_candidates(scope_filter=args.scope)
    kept, deleted = partition_candidates(candidates, keep=max(args.keep, 0))

    print(f"Found timestamped raw artifacts: {len(candidates)}")
    print(f"Will keep: {len(kept)}")
    print(f"Will prune: {len(deleted)}")
    print(f"Prune summary by category: {format_summary(deleted)}")

    for candidate in deleted[:50]:
        print(f"- {candidate.path.relative_to(RAW_DIR.parent).as_posix()}")
    if len(deleted) > 50:
        print(f"... and {len(deleted) - 50} more")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to delete these files.")
        return 0

    removed = 0
    for candidate in deleted:
        try:
            candidate.path.unlink()
            removed += 1
        except OSError as exc:
            print(f"Failed to delete {candidate.path.as_posix()}: {exc}")

    print(f"Deleted files: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
