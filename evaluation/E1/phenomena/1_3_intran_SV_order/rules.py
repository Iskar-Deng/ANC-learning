#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List


PHENOMENON_ID = "1.3"
PHENOMENON_NAME = "intran_SV_order"


def split_intransitive_clause(tokens: List[str], clause_wo: str) -> tuple[List[str], str]:
    """
    Expected GOOD shape:
      SOV/SVO: S V-s
      VOS:     V-s S
    """
    if len(tokens) < 2:
        raise ValueError(f"Expected at least two tokens, got: {tokens}")

    if clause_wo in {"sov", "svo"}:
        return tokens[:-1], tokens[-1]

    if clause_wo == "vos":
        return tokens[1:], tokens[0]

    raise ValueError(f"Unsupported clause_wo: {clause_wo}")


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()
    clause_wo = language_config["clause_wo"]

    subject_tokens, verb_token = split_intransitive_clause(tokens, clause_wo)

    if clause_wo in {"sov", "svo"}:
        bad_tokens = [verb_token] + subject_tokens
        good_order = "SV"
        bad_order = "VS"
        target_index = len(tokens) - 1
    elif clause_wo == "vos":
        bad_tokens = subject_tokens + [verb_token]
        good_order = "VS"
        bad_order = "SV"
        target_index = 0
    else:
        raise ValueError(f"Unsupported clause_wo: {clause_wo}")

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "S_V_order",
        "target_index": target_index,
        "target_token": verb_token,
        "subject_span": " ".join(subject_tokens),
        "good_value": good_order,
        "bad_value": bad_order,
        "perturbation": "swap_intransitive_subject_and_finite_verb_order",
    }
