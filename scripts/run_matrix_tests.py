#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

from delphin import ace
from utils import ACE_BIN


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


def parse_count(grammar_dat: str, sent: str, max_parses: int) -> int:
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
    return len(resp.get("results", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--tests", required=True)
    ap.add_argument("--max-parses", type=int, default=50)
    args = ap.parse_args()

    tests_path = Path(args.tests)
    if not tests_path.exists():
        raise SystemExit(f"ERROR: tests file not found: {tests_path}")

    tests = load_test_sentences(tests_path)
    if not tests:
        raise SystemExit("ERROR: no tests found in test_sentences")

    fails = []

    print(" i  exp  got  ok   sentence")
    print("--  ---  ---  ---  ------------------------------")

    passed = 0

    for i, (is_good, sent) in enumerate(tests, start=1):
        k = parse_count(args.grammar, sent, args.max_parses)

        exp = "G" if is_good else "B"
        ok = (k == 1) if is_good else (k == 0)
        ok_str = "OK" if ok else "FAIL"

        print(f"{i:>2}  {exp:<3}  {k:<3}  {ok_str:<4} {sent}")

        passed += int(ok)

        if not ok:
            expected = "1" if is_good else "0"
            fails.append((i, exp, expected, k, sent))

    print("--  ---  ---  ---  ------------------------------")
    print(f"Summary: {passed}/{len(tests)} OK")

    if fails:
        print("\nFAILURES:")
        for i, exp, expected, k, sent in fails:
            print(f"- #{i} exp={exp} expected={expected} got={k} :: {sent}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()