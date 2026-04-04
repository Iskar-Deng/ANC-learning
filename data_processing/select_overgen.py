#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


JsonDict = Dict[str, Any]


def load_jsonl(path: Path) -> List[JsonDict]:
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
            rows.append(obj)
    return rows


def write_jsonl(rows: List[JsonDict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def tokenize(sent: str) -> List[str]:
    return sent.strip().split()


def bag_of_words(sent: str) -> Counter:
    return Counter(tok.lower() for tok in tokenize(sent))


def all_same_bag(sents: List[str]) -> bool:
    if len(sents) <= 1:
        return True
    first = bag_of_words(sents[0])
    return all(bag_of_words(s) == first for s in sents[1:])


def suffix_positions(sent: str, suffix: str) -> List[int]:
    suffix = suffix.lower()
    toks = tokenize(sent)
    return [i for i, tok in enumerate(toks) if tok.lower().endswith(suffix)]


def sentence_obeys_order(sent: str, left_suffix: str, right_suffix: str) -> bool:
    left_pos = suffix_positions(sent, left_suffix)
    right_pos = suffix_positions(sent, right_suffix)

    if not left_pos or not right_pos:
        return False

    return min(left_pos) < min(right_pos)


def choose_best_same_bag(
    sents: List[str],
    left_suffix: str,
    right_suffix: str,
    rng: random.Random,
) -> Tuple[str, str]:
    good = [s for s in sents if sentence_obeys_order(s, left_suffix, right_suffix)]

    if len(good) == 1:
        return good[0], "same_bag_order_resolved"

    if len(good) >= 2:
        return rng.choice(good), "same_bag_multiple_match_random"

    return rng.choice(sents), "same_bag_no_match_random"


def choose_sentence(
    sents: List[str],
    left_suffix: str,
    right_suffix: str,
    rng: random.Random,
) -> Tuple[str, str]:
    if not sents:
        return "", "empty"

    if len(sents) == 1:
        return sents[0], "single"

    if all_same_bag(sents):
        return choose_best_same_bag(sents, left_suffix, right_suffix, rng)

    return rng.choice(sents), "different_bag_random"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input JSONL with 'sent' field")
    ap.add_argument("--out", required=True, help="Output JSONL with selected sentence")
    ap.add_argument("--left-suffix", required=True, help="Suffix that should appear first")
    ap.add_argument("--right-suffix", required=True, help="Suffix that should appear later")
    ap.add_argument(
        "--keep-all-sent",
        action="store_true",
        help="Keep original 'sent' list in output; otherwise replace it with the selected singleton list",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for tie-breaking and different-bag cases",
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out)

    if in_path.resolve() == out_path.resolve():
        raise ValueError("--input and --out must be different files")
    
    rows = load_jsonl(in_path)
    out_rows: List[JsonDict] = []
    rng = random.Random(args.seed)

    total = 0
    overgen = 0
    same_bag_overgen = 0
    resolved_by_order = 0
    same_bag_multiple_match_random = 0
    same_bag_no_match_random = 0
    different_bag_random = 0

    for row in rows:
        total += 1

        sents = row.get("sent", [])
        if not isinstance(sents, list):
            sents = []

        sents = [s for s in sents if isinstance(s, str) and s.strip()]

        if len(sents) > 1:
            overgen += 1

        if len(sents) > 1 and all_same_bag(sents):
            same_bag_overgen += 1

        chosen, reason = choose_sentence(
            sents,
            args.left_suffix,
            args.right_suffix,
            rng,
        )

        if reason == "same_bag_order_resolved":
            resolved_by_order += 1
        elif reason == "same_bag_multiple_match_random":
            same_bag_multiple_match_random += 1
        elif reason == "same_bag_no_match_random":
            same_bag_no_match_random += 1
        elif reason == "different_bag_random":
            different_bag_random += 1

        new_row = dict(row)
        new_row["best_sent"] = chosen
        new_row["selection_reason"] = reason

        if args.keep_all_sent:
            new_row["sent"] = sents
        else:
            new_row["sent"] = [chosen] if chosen else []

        out_rows.append(new_row)

    write_jsonl(out_rows, out_path)

    print("Done.")
    print(f"Total rows: {total}")
    print(f"Overgenerated rows: {overgen}")
    print(f"Same-bag overgenerated rows: {same_bag_overgen}")
    print(f"Resolved by suffix order: {resolved_by_order}")
    print(f"Same-bag multiple match, random choice: {same_bag_multiple_match_random}")
    print(f"Same-bag no order match, random choice: {same_bag_no_match_random}")
    print(f"Different-bag overgenerated, random choice: {different_bag_random}")
    print(f"Seed: {args.seed}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()