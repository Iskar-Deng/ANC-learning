#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
from delphin import ace

def load_test_sentences(path: Path):
    tests = []  # (is_good, sentence)
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("*"):
            sent = s[1:].strip()
            if sent:
                tests.append((False, sent))  # BAD: expect 0 parses
        else:
            tests.append((True, s))         # GOOD: expect >=1 parses
    return tests

def parse_count(ace_bin: str, grammar_dat: str, sent: str, max_parses: int) -> int:
    cmdargs = ["-n", str(max_parses)]
    # Try to silence ACE NOTE output (stderr)
    try:
        resp = ace.parse(
            grammar_dat,
            sent,
            executable=ace_bin,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,   # works in many PyDelphin versions
        )
    except TypeError:
        # Fallback: older PyDelphin doesn't accept stderr=. Still run, may show NOTE.
        resp = ace.parse(
            grammar_dat,
            sent,
            executable=ace_bin,
            cmdargs=cmdargs,
        )
    return len(resp.get("results", []))

def bucket(k: int) -> str:
    if k == 0:
        return "0"
    elif k == 1:
        return "1"
    else:
        return "M"  # multiple

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ace", required=True)
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
        k = parse_count(args.ace, args.grammar, sent, args.max_parses)
        got = bucket(k)
        exp = "G" if is_good else "B"
        ok = (k >= 1) if is_good else (k == 0)
        ok_str = "OK" if ok else "FAIL"
        print(f"{i:>2}  {exp:<3}  {got:<3}  {ok_str:<4} {sent}")
        passed += int(ok)
        if not ok:
            expected = ">=1" if is_good else "0"
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