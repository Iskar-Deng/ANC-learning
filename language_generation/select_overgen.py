#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


JsonDict = Dict[str, Any]


CLAUSE_WOS = ["sov", "svo", "vos"]
NP_WOS = ["gn", "ng"]

ALIGNMENT_CODES = {
    "ac": "nom-acc",
    "er": "erg-abs",
}

COMP_SYSTEM_CODES = {
    "b": "balancing",
    "d": "deranking",
}

STRATEGY_CODES = {
    "se": "sent",
    "pa": "poss-acc",
    "ep": "erg-poss",
    "no": "nomn",
}

ANC_WO_TABLE = {
    ("sov", "gn"): {
        "sent": "sov",
        "poss-acc": "sov",
        "erg-poss": "sov",
        "nomn": "sov",
    },
    ("svo", "gn"): {
        "sent": "svo",
        "poss-acc": "svo",
        "erg-poss": "sov",
        "nomn": "svo",
    },
    ("vos", "gn"): {
        "sent": "vos",
        "poss-acc": "svo",
        "erg-poss": "sov",
        "nomn": "svo",
    },
    ("sov", "ng"): {
        "sent": "sov",
        "poss-acc": "ovs",
        "erg-poss": "vos",
        "nomn": "ovs",
    },
    ("svo", "ng"): {
        "sent": "svo",
        "poss-acc": "vos",
        "erg-poss": "vos",
        "nomn": "vos",
    },
    ("vos", "ng"): {
        "sent": "vos",
        "poss-acc": "vos",
        "erg-poss": "vos",
        "nomn": "vos",
    },
}


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


def sort_key(value: Any) -> Tuple[int, Any]:
    if isinstance(value, int):
        return (0, value)

    if isinstance(value, str):
        try:
            return (0, int(value))
        except ValueError:
            return (1, value)

    return (2, str(value))


def parse_language_id(language: str) -> JsonDict:
    """
    Parse a compact language id such as:
      62_svo_ng_er_d_ep
    """
    parts = language.split("_")

    if len(parts) != 6:
        raise ValueError(
            f"Invalid language id: {language}. "
            "Expected format: <id>_<clause_wo>_<np_wo>_<alignment>_<comp>_<strategy>"
        )

    numeric_id, clause_wo, np_wo, alignment_code, comp_code, strategy_code = parts

    if clause_wo not in CLAUSE_WOS:
        raise ValueError(f"Invalid clause word order in language id: {clause_wo}")

    if np_wo not in NP_WOS:
        raise ValueError(f"Invalid NP word order in language id: {np_wo}")

    if alignment_code not in ALIGNMENT_CODES:
        raise ValueError(f"Invalid alignment code in language id: {alignment_code}")

    if comp_code not in COMP_SYSTEM_CODES:
        raise ValueError(f"Invalid complement-system code in language id: {comp_code}")

    if strategy_code not in STRATEGY_CODES:
        raise ValueError(f"Invalid ANC strategy code in language id: {strategy_code}")

    alignment = ALIGNMENT_CODES[alignment_code]
    comp_system = COMP_SYSTEM_CODES[comp_code]
    strategy = STRATEGY_CODES[strategy_code]
    anc_wo = ANC_WO_TABLE[(clause_wo, np_wo)][strategy]

    return {
        "id": numeric_id,
        "language": language,
        "clause_wo": clause_wo,
        "np_wo": np_wo,
        "alignment_code": alignment_code,
        "alignment": alignment,
        "comp_system_code": comp_code,
        "comp_system": comp_system,
        "strategy_code": strategy_code,
        "strategy": strategy,
        "anc_wo": anc_wo,
    }


def derive_fin_marks(alignment: str) -> Dict[str, str]:
    """
    Empty string means zero marking.
    """
    if alignment == "nom-acc":
        return {
            "FIN_S_MARK": "",
            "FIN_A_MARK": "",
            "FIN_P_MARK": "ca",
        }

    if alignment == "erg-abs":
        return {
            "FIN_S_MARK": "",
            "FIN_A_MARK": "ca",
            "FIN_P_MARK": "",
        }

    raise ValueError(alignment)


def derive_anc_marks(strategy: str, fin_marks: Dict[str, str]) -> Dict[str, str]:
    """
    Empty string means zero marking.
    """
    if strategy == "sent":
        return {
            "ANC_S_MARK": fin_marks["FIN_S_MARK"],
            "ANC_A_MARK": fin_marks["FIN_A_MARK"],
            "ANC_P_MARK": fin_marks["FIN_P_MARK"],
        }

    if strategy == "poss-acc":
        return {
            "ANC_S_MARK": "ge",
            "ANC_A_MARK": "ge",
            "ANC_P_MARK": fin_marks["FIN_P_MARK"],
        }

    if strategy == "erg-poss":
        return {
            "ANC_S_MARK": "ge",
            "ANC_A_MARK": "ob",
            "ANC_P_MARK": "ge",
        }

    if strategy == "nomn":
        return {
            "ANC_S_MARK": "ge",
            "ANC_A_MARK": "ge",
            "ANC_P_MARK": "ob",
        }

    raise ValueError(strategy)


def derive_language_config(language: str) -> JsonDict:
    params = parse_language_id(language)
    fin_marks = derive_fin_marks(params["alignment"])
    anc_marks = derive_anc_marks(params["strategy"], fin_marks)

    return {
        **params,
        **fin_marks,
        **anc_marks,
    }


def expected_ap_order(anc_wo: str) -> Tuple[str, str]:
    """
    Return the expected relative order of A and P inside a transitive ANC.
    S is treated as the transitive subject position A; O is treated as P.
    """
    if "s" not in anc_wo or "o" not in anc_wo:
        raise ValueError(f"Invalid ANC word order: {anc_wo}")

    if anc_wo.index("s") < anc_wo.index("o"):
        return ("A", "P")

    return ("P", "A")


def nonempty_marks(marks: Sequence[str]) -> List[str]:
    return sorted({m.lower() for m in marks if m}, key=len, reverse=True)


def strip_mark(token: str, marks: Sequence[str]) -> Tuple[str, str]:
    """
    Return (base, mark). Empty mark means zero marking.
    """
    tok = token.lower()

    for mark in nonempty_marks(marks):
        if tok.endswith(mark) and len(tok) > len(mark):
            return tok[: -len(mark)], mark

    return tok, ""


def strip_mark_with_allowed_set(token: str, allowed_marks: Sequence[str]) -> Tuple[str, str]:
    """
    Same as strip_mark(), but the resulting mark must be in allowed_marks.
    Empty mark is allowed only if it is in allowed_marks.
    """
    allowed = {m.lower() for m in allowed_marks}
    base, mark = strip_mark(token, list(allowed))

    if mark in allowed:
        return base, mark

    if "" in allowed:
        return token.lower(), ""

    return token.lower(), "__NO_ALLOWED_MARK__"


def base_bag(sent: str, allowed_marks: Sequence[str]) -> Optional[Counter]:
    """
    Return the token bag after stripping allowed ANC markers.
    If any token cannot be interpreted with the allowed marker set, return None.
    """
    bag: Counter = Counter()

    for tok in tokenize(sent):
        base, mark = strip_mark_with_allowed_set(tok, allowed_marks)

        if mark == "__NO_ALLOWED_MARK__":
            return None

        bag[base] += 1

    return bag


def marks_by_base(sent: str, allowed_marks: Sequence[str]) -> Optional[Dict[str, Counter]]:
    """
    Map each stripped base to a counter of observed markers in this sentence.
    """
    result: Dict[str, Counter] = defaultdict(Counter)

    for tok in tokenize(sent):
        base, mark = strip_mark_with_allowed_set(tok, allowed_marks)

        if mark == "__NO_ALLOWED_MARK__":
            return None

        result[base][mark] += 1

    return result


def detect_single_bag_suffix_variant(
    sents: List[str],
    allowed_marks: Sequence[str],
) -> Optional[str]:
    """
    Rule 2 detector.

    Detect candidates whose token bags differ only by the suffix attached to
    one base token. Token positions may differ.

    Example:
      Debraob cooking comes
      Cooking debrage comes

    Both normalize to the same base bag:
      debra cooking comes

    The changed base is:
      debra: ob vs ge
    """
    if len(sents) <= 1:
        return None

    base_bags: List[Counter] = []

    for sent in sents:
        bag = base_bag(sent, allowed_marks)
        if bag is None:
            return None
        base_bags.append(bag)

    first_base_bag = base_bags[0]
    if any(bag != first_base_bag for bag in base_bags[1:]):
        return None

    marks_per_sent: List[Dict[str, Counter]] = []

    for sent in sents:
        marks = marks_by_base(sent, allowed_marks)
        if marks is None:
            return None
        marks_per_sent.append(marks)

    changed_bases: List[str] = []

    for base in first_base_bag:
        first_marks = marks_per_sent[0].get(base, Counter())

        if any(marks.get(base, Counter()) != first_marks for marks in marks_per_sent[1:]):
            changed_bases.append(base)

    if len(changed_bases) != 1:
        return None

    changed_base = changed_bases[0]

    observed_marks = set()
    for marks in marks_per_sent:
        observed_marks.update(marks[changed_base].keys())

    allowed = {m.lower() for m in allowed_marks}

    if not observed_marks.issubset(allowed):
        return None

    if len(observed_marks) <= 1:
        return None

    return changed_base


def choose_by_s_mark_variant(
    sents: List[str],
    anc_s_mark: str,
    allowed_marks: Sequence[str],
) -> Optional[Tuple[str, str]]:
    """
    Rule 2:
    If candidate token bags differ only by one base token's ANC marker,
    choose the candidate whose marker is ANC_S_MARK. ANC_S_MARK may be empty.
    """
    changed_base = detect_single_bag_suffix_variant(sents, allowed_marks)

    if changed_base is None:
        return None

    target_mark = anc_s_mark.lower()

    for sent in sents:
        marks = marks_by_base(sent, allowed_marks)
        if marks is None:
            continue

        if marks.get(changed_base, Counter()).get(target_mark, 0) > 0:
            return sent, "single_bag_suffix_variant_s_mark"

    return None


def differing_positions_for_same_length_sents(sents: List[str]) -> Optional[List[int]]:
    if len(sents) <= 1:
        return None

    tokenized = [tokenize(s) for s in sents]
    sent_len = len(tokenized[0])

    if any(len(toks) != sent_len for toks in tokenized[1:]):
        return None

    differing_positions: List[int] = []

    for i in range(sent_len):
        col = [toks[i].lower() for toks in tokenized]
        if len(set(col)) > 1:
            differing_positions.append(i)

    return differing_positions


def is_two_token_swap_at_positions(sents: List[str], positions: List[int]) -> bool:
    if len(positions) != 2:
        return False

    tokenized = [tokenize(s) for s in sents]
    i, j = positions

    first_pair = sorted([tokenized[0][i].lower(), tokenized[0][j].lower()])

    for toks in tokenized[1:]:
        pair = sorted([toks[i].lower(), toks[j].lower()])
        if pair != first_pair:
            return False

    return True


def role_for_token(token: str, anc_a_mark: str, anc_p_mark: str) -> Optional[str]:
    """
    Classify a token as A or P using A/P markers.
    """
    a_mark = anc_a_mark.lower()
    p_mark = anc_p_mark.lower()

    if a_mark == p_mark:
        return None

    tok = token.lower()

    if a_mark and tok.endswith(a_mark):
        return "A"

    if p_mark and tok.endswith(p_mark):
        return "P"

    if a_mark == "" and p_mark:
        return "A"

    if p_mark == "" and a_mark:
        return "P"

    return None


def choose_by_ap_order_swap(
    sents: List[str],
    anc_wo: str,
    anc_a_mark: str,
    anc_p_mark: str,
    rng: random.Random,
) -> Optional[Tuple[str, str]]:
    """
    Rule 1:
    If candidates differ only by the order of two tokens, and those tokens can
    be identified as A/P by their ANC markers, choose the candidate matching
    the expected A/P order from ANC_WO.
    """
    if len(sents) <= 1:
        return None

    if not all_same_bag(sents):
        return None

    positions = differing_positions_for_same_length_sents(sents)
    if positions is None:
        return None

    if not is_two_token_swap_at_positions(sents, positions):
        return None

    expected = expected_ap_order(anc_wo)
    i, j = positions

    good: List[str] = []

    for sent in sents:
        toks = tokenize(sent)

        role_i = role_for_token(toks[i], anc_a_mark, anc_p_mark)
        role_j = role_for_token(toks[j], anc_a_mark, anc_p_mark)

        if role_i is None or role_j is None:
            continue

        if (role_i, role_j) == expected:
            good.append(sent)

    if len(good) == 1:
        return good[0], "same_bag_two_token_swap_order_resolved"

    if len(good) > 1:
        return rng.choice(good), "same_bag_two_token_swap_multiple_match_random"

    return None


def choose_sentence(
    sents: List[str],
    config: JsonDict,
    rng: random.Random,
) -> Tuple[str, str]:
    if not sents:
        return "", "empty"

    if len(sents) == 1:
        return sents[0], "single"

    allowed_marks = [
        config["ANC_S_MARK"],
        config["ANC_A_MARK"],
        config["ANC_P_MARK"],
        config["FIN_S_MARK"],
        config["FIN_A_MARK"],
        config["FIN_P_MARK"],
    ]

    preferred = choose_by_s_mark_variant(
        sents=sents,
        anc_s_mark=config["ANC_S_MARK"],
        allowed_marks=allowed_marks,
    )
    if preferred is not None:
        return preferred

    ordered = choose_by_ap_order_swap(
        sents=sents,
        anc_wo=config["anc_wo"],
        anc_a_mark=config["ANC_A_MARK"],
        anc_p_mark=config["ANC_P_MARK"],
        rng=rng,
    )
    if ordered is not None:
        return ordered

    if all_same_bag(sents):
        return rng.choice(sents), "same_bag_unresolved_random"

    return rng.choice(sents), "different_bag_random"


def infer_language_from_input(path: Path) -> str:
    return path.stem


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input JSONL with 'id' and 'sent' fields")
    ap.add_argument("--out", required=True, help="Output JSONL with one selected sentence per unique id")
    ap.add_argument(
        "--language",
        default=None,
        help=(
            "Compact language id, e.g. 62_svo_ng_er_d_ep. "
            "If omitted, infer from input filename stem."
        ),
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for unresolved tie-breaking",
    )
    ap.add_argument(
        "--save-details",
        help=(
            "Optional JSONL path. If provided, save only ids that required "
            "selection, with all candidates and the selection reason."
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

    language = args.language or infer_language_from_input(in_path)
    config = derive_language_config(language)

    rows = load_jsonl(in_path)
    grouped = group_sentences_by_id(rows)
    rng = random.Random(args.seed)

    out_rows: List[JsonDict] = []
    detail_rows: List[JsonDict] = []

    total_input_rows = len(rows)
    total_unique_ids = 0
    ids_requiring_selection = 0

    overgen = 0
    same_bag_overgen = 0
    different_bag_overgen = 0

    single_count = 0
    empty_count = 0

    resolved_by_s_mark_variant = 0
    resolved_by_ap_order = 0
    ap_order_multiple_match_random = 0
    same_bag_unresolved_random = 0
    different_bag_random = 0

    for row_id in sorted(grouped.keys(), key=sort_key):
        total_unique_ids += 1
        sents = grouped[row_id]

        if len(sents) == 0:
            empty_count += 1
        elif len(sents) == 1:
            single_count += 1
        else:
            overgen += 1
            ids_requiring_selection += 1

            if all_same_bag(sents):
                same_bag_overgen += 1
            else:
                different_bag_overgen += 1

        chosen, reason = choose_sentence(
            sents=sents,
            config=config,
            rng=rng,
        )

        if reason == "single_bag_suffix_variant_s_mark":
            resolved_by_s_mark_variant += 1
        elif reason == "same_bag_two_token_swap_order_resolved":
            resolved_by_ap_order += 1
        elif reason == "same_bag_two_token_swap_multiple_match_random":
            ap_order_multiple_match_random += 1
        elif reason == "same_bag_unresolved_random":
            same_bag_unresolved_random += 1
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
                    "language": language,
                    "config": config,
                }
            )

    write_jsonl(out_rows, out_path)

    if details_path is not None:
        write_jsonl(detail_rows, details_path)

    print("Done.")
    print(f"Language: {language}")
    print(f"Clause WO: {config['clause_wo']}")
    print(f"NP WO: {config['np_wo']}")
    print(f"Alignment: {config['alignment']}")
    print(f"Complement system: {config['comp_system']}")
    print(f"ANC strategy: {config['strategy']}")
    print(f"ANC WO: {config['anc_wo']}")
    print(
        "ANC marks: "
        f"S={config['ANC_S_MARK'] or '0'}, "
        f"A={config['ANC_A_MARK'] or '0'}, "
        f"P={config['ANC_P_MARK'] or '0'}"
    )
    print(f"Expected A/P order: {'-'.join(expected_ap_order(config['anc_wo']))}")
    print()
    print(f"Total input rows: {total_input_rows}")
    print(f"Total unique ids: {total_unique_ids}")
    print(f"Rows/ids requiring selection: {ids_requiring_selection}")
    print(f"Overgenerated ids: {overgen}")
    print(f"Same-bag overgenerated ids: {same_bag_overgen}")
    print(f"Different-bag overgenerated ids: {different_bag_overgen}")
    print(f"Resolved by S-marker suffix variant: {resolved_by_s_mark_variant}")
    print(f"Resolved by ANC A/P order: {resolved_by_ap_order}")
    print(f"A/P order multiple match, random choice: {ap_order_multiple_match_random}")
    print(f"Same-bag unresolved, random choice: {same_bag_unresolved_random}")
    print(f"Different-bag overgenerated, random choice: {different_bag_random}")
    print(f"Empty ids: {empty_count}")
    print(f"Single-candidate ids: {single_count}")
    print(f"Seed: {args.seed}")
    print(f"Main output: {out_path}")

    if details_path is not None:
        print(f"Details output: {details_path}")


if __name__ == "__main__":
    main()