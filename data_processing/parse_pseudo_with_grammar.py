#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
python -m data_processing.parse_pseudo_with_grammar \
  --grammar grammars/test_english/test-english.dat \
  --input data/pseudo_english.jsonl \
  --out data/pseudo_parsed.jsonl \
    --max-parses 20
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from delphin import ace
from tqdm import tqdm

from utils import ACE_BIN, MRS_REWRITE_RULES


JsonDict = Dict[str, Any]


def load_pseudo_jsonl(path: Path) -> List[JsonDict]:
    rows: List[JsonDict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num} in {path}: {e}") from e

            if not isinstance(obj, dict):
                raise ValueError(f"Line {line_num} in {path} is not a JSON object")

            pseudo = obj.get("pseudo_english")
            if not isinstance(pseudo, str) or not pseudo.strip():
                continue

            rows.append(obj)

    return rows


def parse_results(grammar_dat: str, sent: str, max_parses: int) -> List[JsonDict]:
    cmdargs = ["-n", str(max_parses)]

    try:
        resp = ace.parse(
            grammar_dat,
            sent,
            executable=ACE_BIN,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        resp = ace.parse(
            grammar_dat,
            sent,
            executable=ACE_BIN,
            cmdargs=cmdargs,
        )

    results = resp.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def normalize_mrs(mrs: str) -> str:
    for src, tgt in MRS_REWRITE_RULES:
        mrs = mrs.replace(src, tgt)

    mrs = re.sub(r"ICONS:\s*<[^>]*>", "ICONS: < >", mrs, flags=re.DOTALL)
    return mrs


def extract_sentence_id(row: JsonDict, fallback: int) -> int:
    id = row.get("id")
    if isinstance(id, int):
        return id
    return fallback


def extract_source_sentence(row: JsonDict) -> Optional[str]:
    sent = row.get("sentence")
    if isinstance(sent, str):
        return sent
    return None


def extract_pseudo_sentence(row: JsonDict) -> str:
    pseudo = row.get("pseudo_english")
    if not isinstance(pseudo, str):
        raise ValueError("Missing or invalid 'pseudo_english'")
    return pseudo.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True, help="Path to compiled ACE grammar .dat")
    ap.add_argument("--input", required=True, help="Input JSONL with pseudo_english field")
    ap.add_argument("--out", required=True, help="Output JSONL for parsed MRS results")
    ap.add_argument("--max-parses", type=int, default=20)
    ap.add_argument("--first-parse-only", action="store_true")
    ap.add_argument("--skip-failed", action="store_true", help="If set, do not write failed parse rows")
    args = ap.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    rows_in = load_pseudo_jsonl(input_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows_out: List[JsonDict] = []

    print(" i   id  parses  pseudo_english")
    print("--  ---  ------  ---------------------------------------------")

    for i, row in enumerate(tqdm(rows_in, desc="Parsing pseudo-English"), start=1):
        id = extract_sentence_id(row, i)
        source_sentence = extract_source_sentence(row)
        pseudo_sentence = extract_pseudo_sentence(row)

        results = parse_results(args.grammar, pseudo_sentence, args.max_parses)
        n = len(results)

        if n == 0:
            print(f"{i:>2}  {id:>3}  {0:<6}  {pseudo_sentence}")
            if not args.skip_failed:
                rows_out.append(
                    {
                        "id": id,
                        "sentence": source_sentence,
                        "pseudo_english": pseudo_sentence,
                        "parse_found": False,
                        "parse_count": 0,
                        "parse_index": None,
                        "mrs": None,
                    }
                )
            continue

        print(f"{i:>2}  {id:>3}  {n:<6}  {pseudo_sentence}")

        if args.first_parse_only:
            results = results[:1]

        saved_any = False
        for parse_index, result in enumerate(results, start=1):
            mrs = result.get("mrs")
            if not isinstance(mrs, str) or not mrs.strip():
                continue

            mrs = normalize_mrs(mrs)

            rows_out.append(
                {
                    "id": id,
                    "sentence": source_sentence,
                    "pseudo_english": pseudo_sentence,
                    "parse_found": True,
                    "parse_count": n,
                    "parse_index": parse_index,
                    "mrs": mrs,
                }
            )
            saved_any = True

        if not saved_any and not args.skip_failed:
            rows_out.append(
                {
                    "id": id,
                    "sentence": source_sentence,
                    "pseudo_english": pseudo_sentence,
                    "parse_found": False,
                    "parse_count": n,
                    "parse_index": None,
                    "mrs": None,
                }
            )

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    success_count = sum(1 for r in rows_out if r["parse_found"])
    print("\nDone.")
    print(f"Saved {len(rows_out)} rows.")
    print(f"Successful parses: {success_count}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()