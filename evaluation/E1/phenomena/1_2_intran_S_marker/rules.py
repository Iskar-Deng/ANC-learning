#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PHENOMENON_ID = "1.2"
PHENOMENON_NAME = "intran_S_marker"
TEMPLATES_PATH = Path(__file__).with_name("templates.json")


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


def load_templates() -> List[Dict[str, Any]]:
    with TEMPLATES_PATH.open("r", encoding="utf-8") as f:
        templates = json.load(f)

    if not isinstance(templates, list):
        raise ValueError(f"Expected template list in {TEMPLATES_PATH}")

    return templates


TEMPLATES = load_templates()


def finite_verb_like(token: str) -> bool:
    return token.endswith("s")


def template_matches(
    template: Dict[str, Any],
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
) -> bool:
    if clause_wo not in template["clause_wo"]:
        return False

    if np_wo not in template["np_wo"]:
        return False

    if len(tokens) != template["token_count"]:
        return False

    verb_index = template["verb_index"]
    if not finite_verb_like(tokens[verb_index]):
        return False

    subject_start = template["subject_start"]
    for requirement in template.get("required_suffixes", []):
        token_index = subject_start + requirement["relative_index"]
        if not tokens[token_index].endswith(requirement["suffix"]):
            return False

    return True


def find_template_match(
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
) -> Dict[str, Any]:
    matches = [
        template
        for template in TEMPLATES
        if template_matches(template, tokens, clause_wo, np_wo)
    ]

    if len(matches) != 1:
        return {
            "skip": True,
            "skip_reason": "template_match_count_not_one",
            "template_match_count": len(matches),
            "matched_templates": [template["name"] for template in matches],
        }

    return matches[0]


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()

    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]

    template = find_template_match(tokens, clause_wo, np_wo)
    if template.get("skip"):
        return {
            **template,
            "good": good_sentence,
            "tokens": tokens,
            "clause_wo": clause_wo,
            "np_wo": np_wo,
        }

    subject_start = template["subject_start"]
    subject_len = template["subject_len"]
    subject_tokens = tokens[subject_start : subject_start + subject_len]
    head_offset = template["subject_head_offset"]
    target_index = subject_start + head_offset
    verb_index = template["verb_index"]

    foil_marker = foil_marker_for_row(row, source_index)

    bad_tokens = tokens[:]
    bad_tokens[target_index] = bad_tokens[target_index] + foil_marker

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "S",
        "target_index": target_index,
        "target_token": tokens[target_index],
        "subject_span": " ".join(subject_tokens),
        "verb_token": tokens[verb_index],
        "good_value": "0",
        "bad_value": foil_marker,
        "template": template["name"],
        "perturbation": f"add_{foil_marker}_to_intransitive_s_head",
    }
