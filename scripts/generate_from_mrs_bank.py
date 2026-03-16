#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import subprocess
from pathlib import Path

from delphin import ace
from utils import ACE_BIN


def load_rows(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def generate_results(grammar_dat: str, mrs: str, max_gen: int):
    cmdargs = ["-n", str(max_gen)]
    try:
        resp = ace.generate(
            grammar_dat,
            mrs,
            executable=ACE_BIN,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        resp = ace.generate(
            grammar_dat,
            mrs,
            executable=ACE_BIN,
            cmdargs=cmdargs,
        )
    return resp.get("results", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-gen", type=int, default=200)
    args = ap.parse_args()

    rows = load_rows(Path(args.input))

    out_rows = []

    print(" id  gen  sentences")
    print("--  ---  ------------------------------")

    for row in rows:
        mrs_id = row["id"]
        mrs = row["mrs"]

        results = generate_results(args.grammar, mrs, args.max_gen)

        seen = set()
        surfaces = []

        for r in results:
            surf = r.get("surface")
            if surf and surf not in seen:
                seen.add(surf)
                surfaces.append(surf)

        sent_str = ", ".join(surfaces) if surfaces else "-"
        print(f"{mrs_id:>2}  {len(surfaces):<3}  {sent_str}")

        out_rows.append({
            "id": mrs_id,
            "sent": surfaces,
            "mrs": mrs,
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\nDone.")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()