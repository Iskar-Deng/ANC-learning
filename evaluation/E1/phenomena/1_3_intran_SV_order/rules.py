#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PHENOMENON_ID = "1.3"
PHENOMENON_NAME = "intran_SV_order"
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


def sentence_case_tokens(tokens: List[str]) -> List[str]:
    if not tokens:
        return tokens

    cased = [token[:1].lower() + token[1:] for token in tokens]
    cased[0] = cased[0][:1].upper() + cased[0][1:]
    return cased


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

    verb_index = template["verb_index"]
    subject_start = template["subject_start"]
    subject_len = template["subject_len"]
    subject_tokens = tokens[subject_start : subject_start + subject_len]
    verb_token = tokens[verb_index]

    if clause_wo in {"sov", "svo"}:
        bad_tokens = [verb_token] + subject_tokens
        good_order = "SV"
        bad_order = "VS"
        target_index = verb_index
    elif clause_wo == "vos":
        bad_tokens = subject_tokens + [verb_token]
        good_order = "VS"
        bad_order = "SV"
        target_index = verb_index
    else:
        raise ValueError(f"Unsupported clause_wo: {clause_wo}")

    bad_tokens = sentence_case_tokens(bad_tokens)

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "S_V_order",
        "target_index": target_index,
        "target_token": verb_token,
        "subject_span": " ".join(subject_tokens),
        "good_value": good_order,
        "bad_value": bad_order,
        "template": template["name"],
        "perturbation": "swap_intransitive_subject_and_finite_verb_order",
    }
