#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def strip_one_of_suffixes(token: str, suffixes: List[str]) -> Optional[Tuple[str, str]]:
    """
    If token ends with one of suffixes, return (base, matched_suffix).
    Prefer the longest matching suffix.
    """
    token_l = token.lower()
    for suf in sorted(suffixes, key=len, reverse=True):
        suf_l = suf.lower()
        if token_l.endswith(suf_l):
            base = token_l[: -len(suf_l)] if suf_l else token_l
            return base, suf_l
    return None


def detect_single_suffix_variant_position(
    sents: List[str],
    variant_suffixes: List[str],
) -> Optional[int]:
    """
    Return the token position if:
      - all sentences have the same token length
      - they differ at exactly one token position
      - at that position, each token differs only by one of the allowed suffixes
        from the same base
      - all other token positions are identical
    Otherwise return None.
    """
    if len(sents) <= 1:
        return None
    if not variant_suffixes:
        return None

    tokenized = [tokenize(s) for s in sents]
    sent_len = len(tokenized[0])

    if any(len(toks) != sent_len for toks in tokenized[1:]):
        return None

    differing_positions: List[int] = []

    for i in range(sent_len):
        col = [toks[i].lower() for toks in tokenized]
        if len(set(col)) == 1:
            continue
        differing_positions.append(i)

    if len(differing_positions) != 1:
        return None

    pos = differing_positions[0]
    stripped: List[Tuple[str, str]] = []

    for toks in tokenized:
        info = strip_one_of_suffixes(toks[pos], variant_suffixes)
        if info is None:
            return None
        stripped.append(info)

    bases = {base for base, _ in stripped}
    matched_suffixes = {suf for _, suf in stripped}

    if len(bases) != 1:
        return None

    if not matched_suffixes.issubset({s.lower() for s in variant_suffixes}):
        return None

    return pos


def choose_by_preferred_suffix_variant(
    sents: List[str],
    variant_suffixes: List[str],
    prefer_suffix: str,
) -> Optional[Tuple[str, str]]:
    """
    If all candidates differ only at one token by one of the allowed suffixes,
    choose the one that uses prefer_suffix at that token.
    If multiple candidates match, keep the first (preserve input order).
    """
    if len(sents) <= 1 or not variant_suffixes or not prefer_suffix:
        return None

    pos = detect_single_suffix_variant_position(sents, variant_suffixes)
    if pos is None:
        return None

    prefer_suffix_l = prefer_suffix.lower()

    for sent in sents:
        tok = tokenize(sent)[pos].lower()
        info = strip_one_of_suffixes(tok, variant_suffixes)
        if info is None:
            continue
        _, matched_suffix = info
        if matched_suffix == prefer_suffix_l:
            return sent, "single_suffix_variant_preferred"

    return None


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
    variant_suffixes: Optional[List[str]] = None,
    prefer_suffix: Optional[str] = None,
) -> Tuple[str, str]:
    if not sents:
        return "", "empty"

    if len(sents) == 1:
        return sents[0], "single"

    # 新增规则优先：如果只差一个后缀变体，则按指定偏好保留
    if variant_suffixes and prefer_suffix:
        preferred = choose_by_preferred_suffix_variant(
            sents=sents,
            variant_suffixes=variant_suffixes,
            prefer_suffix=prefer_suffix,
        )
        if preferred is not None:
            return preferred

    # 保留原有逻辑
    if all_same_bag(sents):
        return choose_best_same_bag(sents, left_suffix, right_suffix, rng)

    return rng.choice(sents), "different_bag_random"


def dedupe_keep_order(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def group_sentences_by_id(rows: List[JsonDict]) -> Dict[Any, List[str]]:
    grouped: Dict[Any, List[str]] = defaultdict(list)

    for row in rows:
        if "id" not in row:
            continue

        row_id = row["id"]
        sents = row.get("sent", [])
        if not isinstance(sents, list):
            continue

        valid_sents = [s for s in sents if isinstance(s, str) and s.strip()]
        grouped[row_id].extend(valid_sents)

    for row_id in grouped:
        grouped[row_id] = dedupe_keep_order(grouped[row_id])

    return dict(grouped)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input JSONL with 'id' and 'sent' fields")
    ap.add_argument("--out", required=True, help="Output JSONL with one selected sentence per unique id")
    ap.add_argument("--left-suffix", required=True, help="Suffix that should appear first")
    ap.add_argument("--right-suffix", required=True, help="Suffix that should appear later")
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for tie-breaking and different-bag cases",
    )
    ap.add_argument(
        "--save-details",
        help=(
            "Optional JSONL path. "
            "If provided, save only ids that required selection "
            "(i.e. deduped candidate sentence count > 1), with all candidates and selection reason."
        ),
    )
    ap.add_argument(
        "--variant-suffixes",
        nargs="+",
        default=None,
        help=(
            "Optional list of suffix variants treated as the same base token with different suffixes, "
            "e.g. --variant-suffixes ob ge"
        ),
    )
    ap.add_argument(
        "--prefer-suffix",
        default=None,
        help=(
            "If candidates differ only by one token's suffix and that suffix is in --variant-suffixes, "
            "keep the sentence with this suffix, e.g. --prefer-suffix ge"
        ),
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out)
    details_path = Path(args.save_details).resolve() if args.save_details else None

    if in_path.resolve() == out_path.resolve():
        raise ValueError("--input and --out must be different files")

    if details_path is not None:
        if details_path == in_path.resolve():
            raise ValueError("--save-details must be different from --input")
        if details_path == out_path.resolve():
            raise ValueError("--save-details must be different from --out")

    if args.prefer_suffix and not args.variant_suffixes:
        raise ValueError("--prefer-suffix requires --variant-suffixes")

    if args.variant_suffixes and args.prefer_suffix:
        normalized_variants = {s.lower() for s in args.variant_suffixes}
        if args.prefer_suffix.lower() not in normalized_variants:
            raise ValueError("--prefer-suffix must be one of --variant-suffixes")

    rows = load_jsonl(in_path)
    grouped = group_sentences_by_id(rows)
    rng = random.Random(args.seed)

    out_rows: List[JsonDict] = []
    detail_rows: List[JsonDict] = []

    total_input_rows = len(rows)
    total_unique_ids = 0
    ids_requiring_selection = 0

    total = 0
    overgen = 0
    same_bag_overgen = 0
    resolved_by_order = 0
    resolved_by_preferred_suffix_variant = 0
    same_bag_multiple_match_random = 0
    same_bag_no_match_random = 0
    different_bag_random = 0
    empty_count = 0
    single_count = 0

    for row_id in sorted(grouped.keys()):
        total_unique_ids += 1
        total += 1

        sents = grouped[row_id]

        if len(sents) == 0:
            empty_count += 1
        elif len(sents) == 1:
            single_count += 1
        else:
            overgen += 1
            ids_requiring_selection += 1

        if len(sents) > 1 and all_same_bag(sents):
            same_bag_overgen += 1

        chosen, reason = choose_sentence(
            sents=sents,
            left_suffix=args.left_suffix,
            right_suffix=args.right_suffix,
            rng=rng,
            variant_suffixes=args.variant_suffixes,
            prefer_suffix=args.prefer_suffix,
        )

        if reason == "same_bag_order_resolved":
            resolved_by_order += 1
        elif reason == "single_suffix_variant_preferred":
            resolved_by_preferred_suffix_variant += 1
        elif reason == "same_bag_multiple_match_random":
            same_bag_multiple_match_random += 1
        elif reason == "same_bag_no_match_random":
            same_bag_no_match_random += 1
        elif reason == "different_bag_random":
            different_bag_random += 1

        out_rows.append(
            {
                "id": row_id,
                "sent": chosen,
            }
        )

        if details_path is not None and len(sents) > 1:
            detail_rows.append(
                {
                    "id": row_id,
                    "candidates": sents,
                    "best_sent": chosen,
                    "selection_reason": reason,
                }
            )

    write_jsonl(out_rows, out_path)

    if details_path is not None:
        write_jsonl(detail_rows, details_path)

    print("Done.")
    print(f"Total input rows: {total_input_rows}")
    print(f"Total unique ids: {total_unique_ids}")
    print(f"Rows/ids requiring selection: {ids_requiring_selection}")
    print(f"Overgenerated ids: {overgen}")
    print(f"Same-bag overgenerated ids: {same_bag_overgen}")
    print(f"Resolved by suffix order: {resolved_by_order}")
    print(f"Resolved by preferred suffix variant: {resolved_by_preferred_suffix_variant}")
    print(f"Same-bag multiple match, random choice: {same_bag_multiple_match_random}")
    print(f"Same-bag no order match, random choice: {same_bag_no_match_random}")
    print(f"Different-bag overgenerated, random choice: {different_bag_random}")
    print(f"Empty ids: {empty_count}")
    print(f"Single-candidate ids: {single_count}")
    print(f"Seed: {args.seed}")
    if args.variant_suffixes:
        print(f"Variant suffixes: {args.variant_suffixes}")
    if args.prefer_suffix:
        print(f"Preferred suffix: {args.prefer_suffix}")
    print(f"Main output: {out_path}")
    if details_path is not None:
        print(f"Details output: {details_path}")


if __name__ == "__main__":
    main()