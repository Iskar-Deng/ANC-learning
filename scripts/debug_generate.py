#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import subprocess
from pathlib import Path

from delphin import ace
from utils import ACE_BIN


def load_mrs(args):
    if args.mrs is not None:
        return args.mrs.strip()
    if args.input is not None:
        return Path(args.input).read_text(encoding="utf-8").strip()
    raise ValueError("You must provide either --mrs or --input.")


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


def dedupe_surfaces(results):
    seen = set()
    surfaces = []
    for r in results:
        surf = r.get("surface")
        if surf and surf not in seen:
            seen.add(surf)
            surfaces.append(surf)
    return surfaces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--mrs")
    ap.add_argument("--input")
    ap.add_argument("--max-gen", type=int, default=200)
    args = ap.parse_args()

    mrs = load_mrs(args)
    results = generate_results(args.grammar, mrs, args.max_gen)
    surfaces = dedupe_surfaces(results)

    print("gen  sentence")
    print("---  ------------------------------")

    if surfaces:
        for i, sent in enumerate(surfaces, 1):
            print(f"{i:>3}  {sent}")
    else:
        print("  0  -")

    print(f"\nTotal: {len(surfaces)}")


if __name__ == "__main__":
    main()