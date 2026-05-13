#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                yield line_no, None, "json_error"
                continue
            if not isinstance(obj, dict):
                yield line_no, None, "not_object"
                continue
            yield line_no, obj, None


def sort_id(x: Any):
    if isinstance(x, int):
        return (0, x)
    if isinstance(x, str):
        try:
            return (0, int(x))
        except ValueError:
            return (1, x)
    return (2, str(x))


def load_selected_file(path: Path):
    """
    Returns:
      id_to_sent: dict[id] = sent
      duplicate_ids: dict[id] = list[line_no]
      bad_rows: list[dict]
    """
    id_to_sent: Dict[Any, str] = {}
    id_to_lines = defaultdict(list)
    bad_rows = []

    for line_no, obj, err in iter_jsonl(path):
        if err is not None:
            bad_rows.append({"line_no": line_no, "error": err})
            continue

        row_id = obj.get("id")
        sent = obj.get("sent")

        if row_id is None:
            bad_rows.append({"line_no": line_no, "error": "missing_id"})
            continue

        if not isinstance(sent, str) or not sent.strip():
            bad_rows.append({"line_no": line_no, "id": row_id, "error": "missing_or_empty_sent"})
            continue

        id_to_lines[row_id].append(line_no)

        # If duplicate id appears, keep the first sentence but record duplicate.
        if row_id not in id_to_sent:
            id_to_sent[row_id] = sent

    duplicate_ids = {
        row_id: lines
        for row_id, lines in id_to_lines.items()
        if len(lines) > 1
    }

    return id_to_sent, duplicate_ids, bad_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected-dir", required=True)
    ap.add_argument("--out-dir", default="results/e2_selected_coverage")
    ap.add_argument("--pattern", default="[0-9][0-9]_*.jsonl")
    ap.add_argument("--write-common-ids", action="store_true")
    ap.add_argument("--max-missing-ids", type=int, default=200)
    args = ap.parse_args()

    selected_dir = Path(args.selected_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(selected_dir.glob(args.pattern))
    if not files:
        raise FileNotFoundError(f"No selected files found in {selected_dir} with pattern {args.pattern}")

    lang_to_ids: Dict[str, Set[Any]] = {}
    lang_to_count: Dict[str, int] = {}
    lang_to_bad_count: Dict[str, int] = {}
    lang_to_duplicate_count: Dict[str, int] = {}

    bad_rows_all = []
    duplicate_rows_all = []

    for path in files:
        lang = path.stem
        id_to_sent, duplicate_ids, bad_rows = load_selected_file(path)

        ids = set(id_to_sent.keys())
        lang_to_ids[lang] = ids
        lang_to_count[lang] = len(ids)
        lang_to_bad_count[lang] = len(bad_rows)
        lang_to_duplicate_count[lang] = len(duplicate_ids)

        for row in bad_rows:
            bad_rows_all.append({"language": lang, **row})

        for row_id, lines in duplicate_ids.items():
            duplicate_rows_all.append({
                "language": lang,
                "id": row_id,
                "count": len(lines),
                "lines": lines,
            })

    all_id_sets = list(lang_to_ids.values())
    common_ids = set.intersection(*all_id_sets)
    union_ids = set.union(*all_id_sets)

    per_lang_rows = []
    for lang in sorted(lang_to_ids):
        ids = lang_to_ids[lang]
        missing_from_union = union_ids - ids
        missing_from_common = common_ids - ids  # should always be empty

        per_lang_rows.append({
            "language": lang,
            "n_ids": len(ids),
            "n_missing_from_union": len(missing_from_union),
            "n_missing_from_common": len(missing_from_common),
            "n_bad_rows": lang_to_bad_count[lang],
            "n_duplicate_ids": lang_to_duplicate_count[lang],
        })

    # For each id, count how many languages have it.
    id_to_langs = defaultdict(list)
    for lang, ids in lang_to_ids.items():
        for row_id in ids:
            id_to_langs[row_id].append(lang)

    missing_by_id_rows = []
    for row_id in sorted(union_ids, key=sort_id):
        present_langs = set(id_to_langs[row_id])
        if len(present_langs) == len(files):
            continue

        missing_langs = sorted(set(lang_to_ids.keys()) - present_langs)
        missing_by_id_rows.append({
            "id": row_id,
            "n_present": len(present_langs),
            "n_missing": len(missing_langs),
            "missing_languages": missing_langs,
        })

    summary = {
        "selected_dir": str(selected_dir),
        "n_files": len(files),
        "min_ids_per_language": min(lang_to_count.values()),
        "max_ids_per_language": max(lang_to_count.values()),
        "mean_ids_per_language": sum(lang_to_count.values()) / len(lang_to_count),
        "union_ids": len(union_ids),
        "common_ids": len(common_ids),
        "ids_missing_in_some_language": len(union_ids - common_ids),
        "languages_with_bad_rows": sum(1 for v in lang_to_bad_count.values() if v > 0),
        "total_bad_rows": len(bad_rows_all),
        "languages_with_duplicate_ids": sum(1 for v in lang_to_duplicate_count.values() if v > 0),
        "total_duplicate_id_entries": len(duplicate_rows_all),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with (out_dir / "per_language.tsv").open("w", encoding="utf-8") as f:
        f.write(
            "language\tn_ids\tn_missing_from_union\tn_missing_from_common\t"
            "n_bad_rows\tn_duplicate_ids\n"
        )
        for row in sorted(per_lang_rows, key=lambda r: r["language"]):
            f.write(
                f"{row['language']}\t{row['n_ids']}\t{row['n_missing_from_union']}\t"
                f"{row['n_missing_from_common']}\t{row['n_bad_rows']}\t"
                f"{row['n_duplicate_ids']}\n"
            )

    with (out_dir / "missing_by_id.jsonl").open("w", encoding="utf-8") as f:
        for row in missing_by_id_rows[: args.max_missing_ids]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with (out_dir / "bad_rows.jsonl").open("w", encoding="utf-8") as f:
        for row in bad_rows_all:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with (out_dir / "duplicate_ids.jsonl").open("w", encoding="utf-8") as f:
        for row in duplicate_rows_all:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.write_common_ids:
        with (out_dir / "common_ids.txt").open("w", encoding="utf-8") as f:
            for row_id in sorted(common_ids, key=sort_id):
                f.write(f"{row_id}\n")

    print(f"\nWrote coverage report to: {out_dir}")


if __name__ == "__main__":
    main()