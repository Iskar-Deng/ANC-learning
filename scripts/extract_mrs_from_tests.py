#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import subprocess
import re
from pathlib import Path

from delphin import ace
from utils import ACE_BIN, MRS_REWRITE_RULES


def load_test_sentences(path: Path):
    tests = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("*"):
            sent = s[1:].strip()
            if sent:
                tests.append((False, sent))
        else:
            tests.append((True, s))
    return tests


def parse_results(grammar_dat: str, sent: str, max_parses: int):
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
    return resp.get("results", [])


def normalize_mrs(mrs: str) -> str:
    for src, tgt in MRS_REWRITE_RULES:
        mrs = mrs.replace(src, tgt)
    mrs = re.sub(r'ICONS:\s*<[^>]*>', 'ICONS: < >', mrs, flags=re.DOTALL)
    return mrs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--tests", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-parses", type=int, default=20)
    ap.add_argument("--first-parse-only", action="store_true")
    args = ap.parse_args()

    tests_path = Path(args.tests)
    out_path = Path(args.out)

    tests = load_test_sentences(tests_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    next_id = 1

    print(" i  type sentence")
    print("--  ---- ---------------------------------------------")

    for i, (is_good, sent) in enumerate(tests, start=1):

        if not is_good:
            continue

        results = parse_results(args.grammar, sent, args.max_parses)
        n = len(results)

        if n == 0:
            print(f"{i:>2} {n:<6} {'no':<5}  {sent}")
            continue

        if args.first_parse_only:
            results = results[:1]

        saved = 0
        for r in results:
            mrs = r.get("mrs")
            if not mrs:
                continue

            mrs = normalize_mrs(mrs)

            rows.append({
                "id": next_id,
                "mrs": mrs,
            })

            next_id += 1
            saved += 1

        print(f"{i:>2}  {n:<4} {sent}")

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\nDone.")
    print(f"Saved {len(rows)} MRS.")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()