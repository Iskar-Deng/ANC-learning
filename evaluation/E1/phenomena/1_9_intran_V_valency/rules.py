#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List


PHENOMENON_ID = "1.9"
PHENOMENON_NAME = "intran_V_valency"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")
VALENCY_PATH = Path(__file__).with_name("blimp_valency.tsv")


def load_templates() -> List[Dict[str, Any]]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        return json.load(infile)


def normalize_stem(stem: str) -> str:
    return stem.lower().replace(" ", "")


def load_valency_rows() -> Dict[str, Deque[Dict[str, str]]]:
    rows_by_stem: Dict[str, Deque[Dict[str, str]]] = defaultdict(deque)
    with VALENCY_PATH.open(encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile, delimiter="\t")
        for row in reader:
            if row.get("use_for") != "1.9_intran_V_valency":
                continue
            good_stem = normalize_stem(row["good_stem"])
            rows_by_stem[good_stem].append(row)
    return rows_by_stem


TEMPLATES = load_templates()
VALENCY_ROWS = load_valency_rows()


def finite_verb_like(token: str) -> bool:
    return token.endswith("s") and not token.endswith("ca") and not token.endswith("ge")


def stem_from_finite(token: str) -> str:
    token = token.lower()
    if token.endswith("s"):
        token = token[:-1]
    return normalize_stem(token)


def finite_form(stem: str, sentence_initial: bool) -> str:
    token = normalize_stem(stem) + "s"
    if sentence_initial:
        return token[:1].upper() + token[1:]
    return token


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


def take_next_valency_row(good_stem: str) -> Dict[str, str] | None:
    rows = VALENCY_ROWS.get(good_stem)
    if not rows:
        return None
    return rows.popleft()


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

    verb_index = template["verb_index"]
    verb_token = tokens[verb_index]
    good_stem = stem_from_finite(verb_token)
    valency_row = take_next_valency_row(good_stem)
    if valency_row is None:
        return {
            "skip": True,
            "skip_reason": "no_unused_blimp_valency_pair_for_good_stem",
            "good": good_sentence,
            "tokens": tokens,
            "good_stem": good_stem,
        }

    bad_stem = normalize_stem(valency_row["bad_stem"])
    bad_tokens = tokens[:]
    bad_tokens[verb_index] = finite_form(bad_stem, sentence_initial=(verb_index == 0))

    subject_start = template["subject_start"]
    subject_len = template["subject_len"]
    subject_tokens = tokens[subject_start : subject_start + subject_len]

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "V_valency",
        "target_index": verb_index,
        "target_token": verb_token,
        "subject_span": " ".join(subject_tokens),
        "good_value": "intransitive_verb",
        "bad_value": "transitive_verb",
        "good_stem": good_stem,
        "bad_stem": bad_stem,
        "blimp_source_uid": valency_row["source_uid"],
        "blimp_pair_id": valency_row["pair_id"],
        "blimp_sentence_good": valency_row["sentence_good"],
        "blimp_sentence_bad": valency_row["sentence_bad"],
        "template": template["name"],
        "perturbation": "replace_intransitive_verb_with_blimp_transitive_verb",
    }
