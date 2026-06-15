#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict

from evaluation.E1.rule_utils import marker_value, parse_transitive_good, strip_suffix


PHENOMENON_ID = "1.5"
PHENOMENON_NAME = "tran_P_marker"


def stable_row_index(row: Dict[str, Any] | None, fallback_index: int) -> int:
    if row is not None:
        for key in ("id", "source_id", "pseudo_index", "pair_index"):
            value = row.get(key)
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return fallback_index


def foil_for_p(row: Dict[str, Any] | None, fallback_index: int, alignment: str) -> tuple[str, str]:
    use_ge_foil = stable_row_index(row, fallback_index) % 2 == 0

    if use_ge_foil:
        return "ge", "replace_transitive_p_marker_with_ge"

    if alignment == "nom-acc":
        return "0", "remove_ca_from_transitive_p"

    if alignment == "erg-abs":
        return "ca", "add_ca_to_transitive_p"

    raise ValueError(f"Unsupported alignment: {alignment}")


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()

    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]
    alignment = language_config["alignment"]
    good_a_mark = language_config["FIN_A_MARK"]
    good_p_mark = language_config["FIN_P_MARK"]

    parsed = parse_transitive_good(
        tokens=tokens,
        clause_wo=clause_wo,
        np_wo=np_wo,
        a_mark=good_a_mark,
        p_mark=good_p_mark,
    )

    target_index = parsed.p.head_index
    target_token = tokens[target_index]
    bad_value, perturbation_label = foil_for_p(row, source_index, alignment)

    bad_tokens = tokens[:]
    if marker_value(good_p_mark) == "0":
        if bad_value == "0":
            raise ValueError("P is already zero-marked")
        bad_tokens[target_index] = target_token + bad_value
    elif good_p_mark == "ca":
        p_stem = strip_suffix(target_token, "ca")
        if bad_value == "0":
            bad_tokens[target_index] = p_stem
        elif bad_value == "ge":
            bad_tokens[target_index] = p_stem + "ge"
        else:
            raise ValueError(f"Unsupported bad_value for ca-marked P: {bad_value}")
    else:
        raise ValueError(f"Unsupported GOOD P marker: {good_p_mark!r}")

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "P",
        "target_index": target_index,
        "target_token": target_token,
        "a_span": parsed.a.text,
        "p_span": parsed.p.text,
        "verb_token": parsed.verb_token,
        "good_value": marker_value(good_p_mark),
        "bad_value": bad_value,
        "perturbation": perturbation_label,
    }
