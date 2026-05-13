#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
from pathlib import Path
from typing import Any


def sort_id(x: Any):
    try:
        return (0, int(x))
    except Exception:
        return (1, str(x))


def has_nmz(pseudo: str) -> bool:
    # token-level check; catches listnmz, tv2-nmz, destroy_nmz, etc.
    tokens = pseudo.strip().split()
    return any("nmz" in re.sub(r"^[^\w-]+|[^\w-]+$", "", tok.lower()) for tok in tokens)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/test/test_pseudo.jsonl")
    ap.add_argument("--out-dir", default="results/e2_anc_ids/test_pseudo")
    ap.add_argument("--sample-n", type=int, default=50)
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    rows_with_pseudo = 0
    anc_rows = 0

    all_ids = set()
    anc_ids = set()
    sample_rows = []

    anc_rows_path = out_dir / "anc_rows.jsonl"
    anc_ids_path = out_dir / "anc_ids.txt"
    sample_path = out_dir / "anc_sample.jsonl"
    summary_path = out_dir / "summary.json"

    with in_path.open("r", encoding="utf-8") as fin, \
         anc_rows_path.open("w", encoding="utf-8") as f_anc:

        for line_no, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue

            total_rows += 1

            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            row_id = row.get("id")
            pseudo = row.get("pseudo_english", "")

            if row_id is not None:
                all_ids.add(row_id)

            if not isinstance(pseudo, str) or not pseudo.strip():
                continue

            rows_with_pseudo += 1

            if has_nmz(pseudo):
                anc_rows += 1
                anc_ids.add(row_id)

                out_row = {
                    "line_no": line_no,
                    "id": row_id,
                    "sentence": row.get("sentence"),
                    "pseudo_english": pseudo,
                }
                f_anc.write(json.dumps(out_row, ensure_ascii=False) + "\n")

                if len(sample_rows) < args.sample_n:
                    sample_rows.append(out_row)

    with anc_ids_path.open("w", encoding="utf-8") as f:
        for row_id in sorted(anc_ids, key=sort_id):
            f.write(f"{row_id}\n")

    with sample_path.open("w", encoding="utf-8") as f:
        for row in sample_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "input": str(in_path),
        "total_rows": total_rows,
        "rows_with_pseudo_english": rows_with_pseudo,
        "unique_ids_total": len(all_ids),
        "anc_rows": anc_rows,
        "anc_unique_ids": len(anc_ids),
        "anc_ids_path": str(anc_ids_path),
        "anc_rows_path": str(anc_rows_path),
        "sample_path": str(sample_path),
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()