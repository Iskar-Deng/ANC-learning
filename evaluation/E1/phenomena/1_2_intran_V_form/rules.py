#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PHENOMENON_ID = "1.2"
PHENOMENON_NAME = "1_2_intran_V_form"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")


def load_templates() -> List[Dict[str, Any]]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        return json.load(infile)


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
    for requirement in template["required_suffixes"]:
        index = subject_start + requirement["relative_index"]
        if not tokens[index].endswith(requirement["suffix"]):
            return False

    return True


def find_template_match(
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
) -> Dict[str, Any] | None:
    matches = [
        template
        for template in TEMPLATES
        if template_matches(template, tokens, clause_wo, np_wo)
    ]

    if len(matches) == 1:
        return matches[0]

    return None


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
    np_wo = language_config["np_wo"]

    template = find_template_match(tokens, clause_wo, np_wo)
    if template is None:
        return {
            "skip": True,
            "skip_reason": "template_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "clause_wo": clause_wo,
            "np_wo": np_wo,
        }

    target_index = template["verb_index"]
    good_token = tokens[target_index]
    bad_token = finite_to_nonfinite(good_token)

    bad_tokens = tokens[:]
    bad_tokens[target_index] = bad_token

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "V",
        "target_index": target_index,
        "target_token": good_token,
        "subject_span": " ".join(
            tokens[template["subject_start"] : template["subject_start"] + template["subject_len"]]
        ),
        "good_value": "finite_s",
        "bad_value": "nonfinite_ing",
        "template": template["name"],
        "perturbation": "replace_intransitive_finite_s_with_nonfinite_ing",
    }
