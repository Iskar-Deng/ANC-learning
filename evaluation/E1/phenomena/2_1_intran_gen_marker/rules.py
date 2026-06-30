#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PHENOMENON_ID = "2.1"
PHENOMENON_NAME = "intran_gen_marker"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")


def load_templates() -> List[Dict[str, Any]]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        return json.load(infile)


TEMPLATES = load_templates()


def finite_verb_like(token: str) -> bool:
    lower = token.lower()
    return lower.endswith("s") and not lower.endswith("ca") and not lower.endswith("ge")


def has_suffix(token: str, suffix: str) -> bool:
    return token.lower().endswith(suffix)


def replace_suffix(token: str, old: str, new: str) -> str:
    if not has_suffix(token, old):
        raise ValueError(f"Token {token!r} does not end in {old!r}")
    return token[: -len(old)] + new


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

    if not finite_verb_like(tokens[template["verb_index"]]):
        return False

    for index in template["gen_indices"]:
        if not has_suffix(tokens[index], "ge"):
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


def perturbation_plan(source_index: int) -> tuple[str, str]:
    bad_marker = "ca" if source_index % 2 == 1 else "0"
    return bad_marker, "single_genitive"


def target_layer_label(gen_depth: int, target_layer: int) -> str:
    if gen_depth == 1:
        return "single_possessor"
    raise ValueError(f"Unsupported genitive depth: {gen_depth}")


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()
    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]

    pseudo_english = row.get("pseudo_english") if row is not None else None
    if isinstance(pseudo_english, str) and "nmz" in pseudo_english:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_contains_nominalization_artifact",
            "good": good_sentence,
            "tokens": tokens,
            "pseudo_english": pseudo_english,
        }

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

    gen_depth = template["gen_depth"]
    target_layer = 1
    bad_marker, plan_group = perturbation_plan(source_index)
    target_index = template["layer_to_gen_index"]["1"]
    target_token = tokens[target_index]

    bad_tokens = tokens[:]
    if bad_marker == "ca":
        bad_tokens[target_index] = replace_suffix(target_token, "ge", "ca")
        perturbation = "replace_genitive_ge_with_ca"
    elif bad_marker == "0":
        bad_tokens[target_index] = replace_suffix(target_token, "ge", "")
        perturbation = "delete_genitive_ge"
    else:
        raise ValueError(f"Unsupported bad marker: {bad_marker}")

    subject_start = template["subject_start"]
    subject_len = template["subject_len"]
    subject_tokens = tokens[subject_start : subject_start + subject_len]

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "genitive_marker",
        "target_index": target_index,
        "target_token": target_token,
        "subject_span": " ".join(subject_tokens),
        "good_value": "ge",
        "bad_value": bad_marker,
        "gen_depth": gen_depth,
        "target_layer": target_layer,
        "target_layer_label": target_layer_label(gen_depth, target_layer),
        "plan_group": plan_group,
        "template": template["name"],
        "perturbation": perturbation,
    }
