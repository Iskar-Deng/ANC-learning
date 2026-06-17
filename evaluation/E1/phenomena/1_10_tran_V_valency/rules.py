#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, NamedTuple


PHENOMENON_ID = "1.10"
PHENOMENON_NAME = "tran_V_valency"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")
VALENCY_PATH = Path(__file__).with_name("blimp_valency.tsv")


class NpSpan(NamedTuple):
    tokens: List[str]
    start: int
    head_offset: int

    @property
    def head_index(self) -> int:
        return self.start + self.head_offset

    @property
    def text(self) -> str:
        return " ".join(self.tokens)


class TransitiveTemplateMatch(NamedTuple):
    template_name: str
    a: NpSpan
    p: NpSpan
    verb_token: str
    verb_index: int


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
            if row.get("use_for") != "1.10_tran_V_valency":
                continue
            good_stem = normalize_stem(row["good_stem"])
            rows_by_stem[good_stem].append(row)
    return rows_by_stem


TEMPLATES = load_templates()
VALENCY_ROWS = load_valency_rows()


def marker_value(mark: str | None) -> str:
    return mark or "0"


def finite_verb_like(token: str) -> bool:
    return token.endswith("s") and not token.endswith("ca") and not token.endswith("ge")


def head_matches_marker(token: str, expected_mark: str | None) -> bool:
    mark = expected_mark or ""
    if mark == "ca":
        return token.endswith("ca")
    if mark == "":
        return True
    raise ValueError(f"Unsupported finite marker: {mark!r}")


def parse_np(
    tokens: List[str],
    start: int,
    np_wo: str,
    expected_head_mark: str | None,
) -> NpSpan | None:
    if len(tokens) == 1:
        if not head_matches_marker(tokens[0], expected_head_mark):
            return None
        return NpSpan(tokens=tokens, start=start, head_offset=0)

    if len(tokens) != 2:
        return None

    if np_wo == "gn":
        if not tokens[0].endswith("ge"):
            return None
        if not head_matches_marker(tokens[1], expected_head_mark):
            return None
        return NpSpan(tokens=tokens, start=start, head_offset=1)

    if np_wo == "ng":
        if not tokens[1].endswith("ge"):
            return None
        if not head_matches_marker(tokens[0], expected_head_mark):
            return None
        return NpSpan(tokens=tokens, start=start, head_offset=0)

    raise ValueError(f"Unsupported np_wo: {np_wo}")


def spans_for_template(
    template: Dict[str, Any],
    clause_wo: str,
) -> tuple[int, int, int, int, int]:
    a_len = template["a_len"]
    p_len = template["p_len"]

    if clause_wo == "sov":
        return 0, a_len, a_len, p_len, a_len + p_len

    if clause_wo == "svo":
        return 0, a_len, a_len + 1, p_len, a_len

    if clause_wo == "vos":
        return 1 + p_len, a_len, 1, p_len, 0

    raise ValueError(f"Unsupported clause_wo: {clause_wo}")


def template_match(
    template: Dict[str, Any],
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
    a_mark: str | None,
    p_mark: str | None,
) -> TransitiveTemplateMatch | None:
    if clause_wo not in template["clause_wo"]:
        return None

    expected_len = template["a_len"] + template["p_len"] + 1
    if len(tokens) != expected_len:
        return None

    a_start, a_len, p_start, p_len, verb_index = spans_for_template(template, clause_wo)
    verb_token = tokens[verb_index]
    if not finite_verb_like(verb_token):
        return None

    a = parse_np(tokens[a_start : a_start + a_len], a_start, np_wo, a_mark)
    if a is None:
        return None

    p = parse_np(tokens[p_start : p_start + p_len], p_start, np_wo, p_mark)
    if p is None:
        return None

    return TransitiveTemplateMatch(
        template_name=template["name"],
        a=a,
        p=p,
        verb_token=verb_token,
        verb_index=verb_index,
    )


def find_template_match(
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
    a_mark: str | None,
    p_mark: str | None,
    expected_shape: tuple[int, int] | None = None,
) -> TransitiveTemplateMatch | None:
    matches: List[TransitiveTemplateMatch] = []
    for template in TEMPLATES:
        if expected_shape is not None:
            expected_a_len, expected_p_len = expected_shape
            if template["a_len"] != expected_a_len or template["p_len"] != expected_p_len:
                continue

        match = template_match(
            template=template,
            tokens=tokens,
            clause_wo=clause_wo,
            np_wo=np_wo,
            a_mark=a_mark,
            p_mark=p_mark,
        )
        if match is not None:
            matches.append(match)

    if len(matches) == 1:
        return matches[0]

    return None


def template_shape_from_pseudo(row: Dict[str, Any] | None) -> tuple[int, int] | None:
    if row is None:
        return None

    pseudo = row.get("pseudo_english")
    if not isinstance(pseudo, str):
        return None

    tokens = pseudo.strip().split()
    if len(tokens) not in (3, 4, 5):
        return None

    a_len = 2 if len(tokens) >= 2 and tokens[0].endswith("ge") else 1
    p_len = len(tokens) - a_len - 1
    if p_len not in (1, 2):
        return None

    return a_len, p_len


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

    pseudo_english = row.get("pseudo_english") if row is not None else None
    if isinstance(pseudo_english, str) and "nmz" in pseudo_english:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_contains_nominalization_artifact",
            "good": good_sentence,
            "tokens": tokens,
            "pseudo_english": pseudo_english,
        }

    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]
    good_a_mark = language_config["FIN_A_MARK"]
    good_p_mark = language_config["FIN_P_MARK"]

    parsed = find_template_match(
        tokens=tokens,
        clause_wo=clause_wo,
        np_wo=np_wo,
        a_mark=good_a_mark,
        p_mark=good_p_mark,
        expected_shape=template_shape_from_pseudo(row),
    )
    if parsed is None:
        return {
            "skip": True,
            "skip_reason": "template_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "clause_wo": clause_wo,
            "np_wo": np_wo,
            "good_a_mark": marker_value(good_a_mark),
            "good_p_mark": marker_value(good_p_mark),
        }

    verb_index = parsed.verb_index
    verb_token = parsed.verb_token
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

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "V_valency",
        "target_index": verb_index,
        "target_token": verb_token,
        "a_span": parsed.a.text,
        "p_span": parsed.p.text,
        "good_value": "transitive_verb",
        "bad_value": "intransitive_verb",
        "good_stem": good_stem,
        "bad_stem": bad_stem,
        "blimp_source_uid": valency_row["source_uid"],
        "blimp_pair_id": valency_row["pair_id"],
        "blimp_sentence_good": valency_row["sentence_good"],
        "blimp_sentence_bad": valency_row["sentence_bad"],
        "template": parsed.template_name,
        "perturbation": "replace_transitive_verb_with_blimp_intransitive_verb",
    }
