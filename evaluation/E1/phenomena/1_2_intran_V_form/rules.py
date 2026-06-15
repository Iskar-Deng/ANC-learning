#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List


PHENOMENON_ID = "1.2"
PHENOMENON_NAME = "1_2_intran_V_form"


def finite_verb_index(tokens: List[str], clause_wo: str) -> int:
    """
    Expected GOOD shape for basic intransitive clauses:
      SOV/SVO: S V-s
      VOS:     V-s S
    """
    if len(tokens) < 2:
        raise ValueError(f"Expected at least two tokens, got: {tokens}")

    if clause_wo in {"sov", "svo"}:
        return len(tokens) - 1

    if clause_wo == "vos":
        return 0

    raise ValueError(f"Unsupported clause_wo: {clause_wo}")


def finite_to_nonfinite(token: str) -> str:
    """
    Convert finite V-s to nonfinite V-ing.

    In these grammars, finite verb form is always suffix -s, and nonfinite
    form is suffix -ing.
    """
    if not token.endswith("s"):
        raise ValueError(f"Expected finite verb token ending in -s, got: {token}")

    stem = token[:-1]
    if not stem:
        raise ValueError(f"Could not recover stem from finite verb token: {token}")

    return stem + "ing"


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()
    clause_wo = language_config["clause_wo"]

    target_index = finite_verb_index(tokens, clause_wo)
    good_token = tokens[target_index]
    bad_token = finite_to_nonfinite(good_token)

    bad_tokens = tokens[:]
    bad_tokens[target_index] = bad_token

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "V",
        "target_index": target_index,
        "target_token": good_token,
        "good_value": "finite_s",
        "bad_value": "nonfinite_ing",
        "perturbation": "replace_intransitive_finite_s_with_nonfinite_ing",
    }