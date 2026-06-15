#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List


PHENOMENON_ID = "1.1"
PHENOMENON_NAME = "intran_S_marker"


def foil_marker_for_row(row: Dict[str, Any] | None, fallback_index: int) -> str:
    """
    Alternate between real marker foils without relying on source block layout.
    """
    value: Any = fallback_index
    if row is not None:
        value = row.get("id", row.get("source_id", fallback_index))

    try:
        index = int(value)
    except (TypeError, ValueError):
        index = fallback_index

    return "ca" if index % 2 else "ge"


def split_intransitive_clause(tokens: List[str], clause_wo: str) -> tuple[List[str], int]:
    """
    Return (subject_tokens, subject_start_index).

    Expected generated GOOD shape:
      SOV/SVO: S V-s
      VOS:     V-s S

    S may be one token or a possessive/genitive NP:
      GN: poss-ge head
      NG: head poss-ge
    """
    if len(tokens) < 2:
        raise ValueError(f"Expected at least two tokens, got: {tokens}")

    if clause_wo in {"sov", "svo"}:
        return tokens[:-1], 0

    if clause_wo == "vos":
        return tokens[1:], 1

    raise ValueError(f"Unsupported clause_wo: {clause_wo}")


def subject_head_offset(subject_tokens: List[str], np_wo: str) -> int:
    """
    Locate the head of S inside the subject NP.

    Simple S:
      dog

    GN:
      his-ge dog        -> head is last token

    NG:
      dog his-ge        -> head is first token
    """
    if len(subject_tokens) == 1:
        return 0

    if np_wo == "gn":
        return len(subject_tokens) - 1

    if np_wo == "ng":
        return 0

    raise ValueError(f"Unsupported np_wo: {np_wo}")


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()

    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]

    subject_tokens, subject_start = split_intransitive_clause(tokens, clause_wo)
    head_offset = subject_head_offset(subject_tokens, np_wo)
    target_index = subject_start + head_offset

    foil_marker = foil_marker_for_row(row, source_index)

    bad_tokens = tokens[:]
    bad_tokens[target_index] = bad_tokens[target_index] + foil_marker

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "S",
        "target_index": target_index,
        "target_token": tokens[target_index],
        "subject_span": " ".join(subject_tokens),
        "good_value": "0",
        "bad_value": foil_marker,
        "perturbation": f"add_{foil_marker}_to_intransitive_s_head",
    }
