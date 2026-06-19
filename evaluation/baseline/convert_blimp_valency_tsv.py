#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert BLiMP-derived valency TSV files to E1-style JSONL pairs."
    )
    parser.add_argument("--input", required=True, help="Input blimp_valency.tsv")
    parser.add_argument("--out", required=True, help="Output JSONL pair file")
    parser.add_argument(
        "--phenomenon",
        default=None,
        help="Optional phenomenon label to store on each output row.",
    )
    parser.add_argument(
        "--skip-lexically-identical",
        action="store_true",
        help="Skip rows whose lexically_identical column is true.",
    )
    return parser.parse_args()


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def iter_rows(path: Path) -> Iterable[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile, delimiter="\t")
        required = {"row_id", "sentence_good", "sentence_bad"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
        yield from reader


def make_pair(row: Dict[str, str], phenomenon: str | None) -> Dict[str, Any]:
    good = row["sentence_good"].strip()
    bad = row["sentence_bad"].strip()
    if not good or not bad:
        raise ValueError(f"Empty good/bad sentence in row: {row}")

    out: Dict[str, Any] = {
        "id": int(row["row_id"]),
        "good": good,
        "bad": bad,
        "source_uid": row.get("source_uid"),
        "pair_id": row.get("pair_id"),
        "use_for": row.get("use_for"),
        "good_stem": row.get("good_stem"),
        "bad_stem": row.get("bad_stem"),
        "lexically_identical": parse_bool(row.get("lexically_identical", "false")),
        "benchmark_source": "blimp_valency_tsv",
    }
    if phenomenon is not None:
        out["phenomenon"] = phenomenon
    return out


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    out_path = Path(args.out)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input TSV not found: {input_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    with out_path.open("w", encoding="utf-8") as outfile:
        for row in iter_rows(input_path):
            if args.skip_lexically_identical and parse_bool(
                row.get("lexically_identical", "false")
            ):
                skipped += 1
                continue
            pair = make_pair(row, args.phenomenon)
            outfile.write(json.dumps(pair, ensure_ascii=False) + "\n")
            written += 1

    print(
        json.dumps(
            {
                "input": str(input_path),
                "out": str(out_path),
                "written": written,
                "skipped": skipped,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
