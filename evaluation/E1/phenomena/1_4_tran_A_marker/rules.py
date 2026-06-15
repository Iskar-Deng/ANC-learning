#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List


PHENOMENON_ID = "1.4"
PHENOMENON_NAME = "tran_A_marker"


def np_lengths_for_source(source_index: int) -> tuple[int, int]:
    """
    Source blocks:
      1-40:    A simple,   P simple
      41-80:   A genitive, P simple
      81-120:  A simple,   P genitive
      121-160: A genitive, P genitive

    Generated ordinary genitive NP has two tokens:
      GN: poss-ge head
      NG: head poss-ge
    """
    block = (source_index - 1) // 40

    if block == 0:
        return 1, 1
    if block == 1:
        return 2, 1
    if block == 2:
        return 1, 2
    if block == 3:
        return 2, 2

    raise ValueError(f"source_index out of expected range 1-160: {source_index}")


def split_transitive_clause(
    tokens: List[str],
    clause_wo: str,
    a_len: int,
    p_len: int,
) -> tuple[List[str], List[str], str, int]:
    """
    Return (a_tokens, p_tokens, verb_token, a_start_index).

    Expected GOOD shapes:
      SOV: A P V-s
      SVO: A V-s P
      VOS: V-s P A
    """
    expected_len = a_len + p_len + 1
    if len(tokens) != expected_len:
        raise ValueError(
            f"Expected {expected_len} tokens from A_len={a_len}, P_len={p_len}, "
            f"got {len(tokens)}: {tokens}"
        )

    if clause_wo == "sov":
        a_start = 0
        a_tokens = tokens[:a_len]
        p_tokens = tokens[a_len : a_len + p_len]
        verb_token = tokens[-1]
        return a_tokens, p_tokens, verb_token, a_start

    if clause_wo == "svo":
        a_start = 0
        a_tokens = tokens[:a_len]
        verb_token = tokens[a_len]
        p_tokens = tokens[a_len + 1 :]
        return a_tokens, p_tokens, verb_token, a_start

    if clause_wo == "vos":
        a_start = 1 + p_len
        verb_token = tokens[0]
        p_tokens = tokens[1 : 1 + p_len]
        a_tokens = tokens[a_start:]
        return a_tokens, p_tokens, verb_token, a_start

    raise ValueError(f"Unsupported clause_wo: {clause_wo}")


def head_offset(np_tokens: List[str], np_wo: str) -> int:
    """
    Locate head inside an NP.

    Simple NP:
      dog

    GN:
      his-ge dog        -> head is last token

    NG:
      dog his-ge        -> head is first token
    """
    if len(np_tokens) == 1:
        return 0

    if np_wo == "gn":
        return len(np_tokens) - 1

    if np_wo == "ng":
        return 0

    raise ValueError(f"Unsupported np_wo: {np_wo}")


def strip_suffix(token: str, suffix: str) -> str:
    if not token.endswith(suffix):
        raise ValueError(f"Expected token ending in {suffix!r}, got: {token}")
    stem = token[: -len(suffix)]
    if not stem:
        raise ValueError(f"Could not strip suffix {suffix!r} from token: {token}")
    return stem


def foil_for_source(source_index: int, alignment: str) -> tuple[str, str]:
    """
    Return (bad_value, perturbation_label).

    Odd source ids use the alignment-role contrast:
      nom-acc: A=0  -> A=ca
      erg-abs: A=ca -> A=0

    Even source ids use genitive-marker foil:
      nom-acc: A=0  -> A=ge
      erg-abs: A=ca -> A=ge
    """
    use_ge_foil = source_index % 2 == 0

    if use_ge_foil:
        return "ge", "replace_transitive_a_marker_with_ge"

    if alignment == "nom-acc":
        return "ca", "add_ca_to_transitive_a"

    if alignment == "erg-abs":
        return "0", "remove_ca_from_transitive_a"

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
    good_a_mark = language_config["FIN_A_MARK"] or "0"

    a_len, p_len = np_lengths_for_source(source_index)
    a_tokens, p_tokens, verb_token, a_start = split_transitive_clause(
        tokens=tokens,
        clause_wo=clause_wo,
        a_len=a_len,
        p_len=p_len,
    )

    a_head = head_offset(a_tokens, np_wo)
    target_index = a_start + a_head
    target_token = tokens[target_index]

    bad_value, perturbation_label = foil_for_source(source_index, alignment)

    bad_tokens = tokens[:]
    if alignment == "nom-acc":
        if bad_value == "0":
            raise ValueError("nom-acc A is already zero-marked")
        bad_tokens[target_index] = target_token + bad_value
    elif alignment == "erg-abs":
        a_stem = strip_suffix(target_token, "ca")
        if bad_value == "0":
            bad_tokens[target_index] = a_stem
        elif bad_value == "ge":
            bad_tokens[target_index] = a_stem + "ge"
        else:
            raise ValueError(f"Unsupported bad_value for erg-abs: {bad_value}")
    else:
        raise ValueError(f"Unsupported alignment: {alignment}")

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "A",
        "target_index": target_index,
        "target_token": target_token,
        "a_span": " ".join(a_tokens),
        "p_span": " ".join(p_tokens),
        "verb_token": verb_token,
        "good_value": good_a_mark,
        "bad_value": bad_value,
        "perturbation": perturbation_label,
    }