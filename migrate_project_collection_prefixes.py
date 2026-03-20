#!/usr/bin/env python3
"""
One-time migration for project-owned MongoDB collections.

Copies documents from old unprefixed collection names to the new project-prefixed
names while preserving `_id` values. The migration is idempotent: documents that
already exist in the target collection are skipped.
"""

from __future__ import annotations

import argparse
from typing import Dict, Iterable, Tuple

from app.core.database import get_collection


COLLECTION_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    ("jobs", "lead_jobs"),
    ("leads", "lead_leads"),
    ("saved_searches", "lead_saved_searches"),
    ("credit_ledger", "lead_credit_ledger"),
    ("credit_requests", "lead_credit_requests"),
    ("payment_transactions", "lead_payment_transactions"),
    ("analyzer_forms", "hr_forms"),
    ("analyzer_submissions", "hr_submissions"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate old project collection names to prefixed names.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without inserting documents.",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Optional list of source collection names to migrate.",
    )
    return parser.parse_args()


def iter_mappings(selected_sources: Iterable[str]) -> Iterable[Tuple[str, str]]:
    selected_set = set(selected_sources)
    for source_name, target_name in COLLECTION_MAPPINGS:
        if selected_set and source_name not in selected_set:
            continue
        yield source_name, target_name


def migrate_collection(source_name: str, target_name: str, dry_run: bool) -> Dict[str, int]:
    source = get_collection(source_name)
    target = get_collection(target_name)

    source_count = source.count_documents({})
    target_count_before = target.count_documents({})

    copied = 0
    skipped = 0

    for document in source.find({}):
        if target.find_one({"_id": document["_id"]}, {"_id": 1}):
            skipped += 1
            continue
        copied += 1
        if not dry_run:
            target.insert_one(document)

    target_count_after = target.count_documents({}) if not dry_run else target_count_before + copied

    return {
        "source_count": source_count,
        "target_count_before": target_count_before,
        "copied": copied,
        "skipped": skipped,
        "target_count_after": target_count_after,
    }


def main() -> int:
    args = parse_args()
    mappings = list(iter_mappings(args.only))

    if not mappings:
        print("No matching collections selected.")
        return 1

    print("Project collection migration")
    print(f"Mode: {'dry-run' if args.dry_run else 'write'}")
    print("")

    total_copied = 0
    total_skipped = 0

    for source_name, target_name in mappings:
        stats = migrate_collection(source_name, target_name, args.dry_run)
        total_copied += stats["copied"]
        total_skipped += stats["skipped"]

        print(f"{source_name} -> {target_name}")
        print(f"  source_count:        {stats['source_count']}")
        print(f"  target_count_before: {stats['target_count_before']}")
        print(f"  copied:              {stats['copied']}")
        print(f"  skipped_existing:    {stats['skipped']}")
        print(f"  target_count_after:  {stats['target_count_after']}")
        print("")

    print("Summary")
    print(f"  total_copied:   {total_copied}")
    print(f"  total_skipped:  {total_skipped}")
    print(f"  collections:    {len(mappings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
