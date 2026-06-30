#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple


PHENOMENON_ID = "6.2"
PHENOMENON_NAME = "anc_omit_A"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")
ANC_MARKERS = ("ca", "ge", "ob")


class Template(NamedTuple):
    name: str
    profile: str
    source_start: int
    source_end: int
    source_construction: str
    overt_arguments: List[str]


class VerbToken(NamedTuple):
    index: int
    token: str
    stem: str
    marker: str


class PseudoAncTvP(NamedTuple):
    p_head: str


def load_templates() -> List[Template]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        raw_templates = json.load(infile)

    return [
        Template(
            name=raw["name"],
            profile=raw["profile"],
            source_start=int(raw["source_start"]),
            source_end=int(raw["source_end"]),
            source_construction=raw["source_construction"],
            overt_arguments=list(raw["overt_arguments"]),
        )
        for raw in raw_templates
    ]


TEMPLATES = load_templates()


def template_for_source(source_index: int) -> Template | None:
    for template in TEMPLATES:
        if template.source_start <= source_index <= template.source_end:
            return template
    return None


def strip_marker(token: str) -> tuple[str, str]:
    lower = token.lower()
    for marker in ANC_MARKERS:
        if lower.endswith(marker) and len(token) > len(marker):
            return token[: -len(marker)], token[-len(marker) :]
    return token, ""


def marker_value(marker: str) -> str:
    return marker or "0"


def marker_for_expected_head(token: str, expected_head: str) -> str | None:
    lower = token.lower()
    expected = expected_head.lower()
    if lower == expected:
        return ""
    for marker in ANC_MARKERS:
        if lower == expected + marker:
            return marker
    return None


def replace_expected_head_marker(
    token: str,
    expected_head: str,
    good_marker: str,
    bad_marker: str,
) -> str:
    marker = marker_for_expected_head(token, expected_head)
    if marker != good_marker:
        raise ValueError(
            f"Expected marker {good_marker!r} on token {token!r}, got {marker!r}"
        )

    base = token[: len(expected_head)]
    if bad_marker in {"", "0"}:
        return base
    if bad_marker in ANC_MARKERS:
        return base + bad_marker
    raise ValueError(f"Unsupported bad marker: {bad_marker!r}")


def is_anc_verb_token(token: str) -> bool:
    base, _ = strip_marker(token)
    lower = base.lower()
    return lower.endswith("ing") and len(lower) > 3


def find_anc_verb(tokens: List[str]) -> VerbToken | None:
    candidates: List[VerbToken] = []
    for index, token in enumerate(tokens):
        base, marker = strip_marker(token)
        lower = base.lower()
        if not lower.endswith("ing"):
            continue
        stem = base[:-3]
        if not stem:
            continue
        candidates.append(VerbToken(index=index, token=token, stem=stem, marker=marker))

    if len(candidates) == 1:
        return candidates[0]
    return None


def finite_from_anc_verb(verb: VerbToken) -> str:
    finite = verb.stem + "s"
    if verb.token[0].isupper():
        finite = finite[:1].upper() + finite[1:]
    return finite


def extract_pseudo_anc_tv_p(pseudo_english: str) -> PseudoAncTvP | None:
    pseudo_tokens = pseudo_english.strip().lower().split()
    candidates: List[PseudoAncTvP] = []

    for index, token in enumerate(pseudo_tokens):
        base, _ = strip_marker(token)
        if not base.endswith("nmz"):
            continue

        # P-only TV nominalizations should have one object-like oblique token
        # adjacent to the nominalized verb, and no possessor A immediately before it.
        if index > 0 and pseudo_tokens[index - 1].endswith("ge"):
            continue

        adjacent = []
        for arg_index in (index - 1, index + 1):
            if arg_index < 0 or arg_index >= len(pseudo_tokens):
                continue
            arg_token = pseudo_tokens[arg_index]
            if arg_token.endswith("ob") and len(arg_token) > 2:
                adjacent.append(arg_token[:-2])

        if len(adjacent) == 1:
            candidates.append(PseudoAncTvP(p_head=adjacent[0]))

    if len(candidates) == 1:
        return candidates[0]
    return None


def find_unique_expected_head_index(tokens: List[str], expected_head: str) -> int | None:
    matches: List[int] = []
    for index, token in enumerate(tokens):
        if is_anc_verb_token(token):
            continue
        if marker_for_expected_head(token, expected_head) is not None:
            matches.append(index)
    if len(matches) == 1:
        return matches[0]
    return None


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    template = template_for_source(source_index)
    if template is None:
        return {
            "skip": True,
            "skip_reason": "source_index_outside_6_2_profile_ranges",
            "good": good_sentence,
            "source_index": source_index,
        }

    pseudo_english = row.get("pseudo_english") if row is not None else None
    if not isinstance(pseudo_english, str) or "nmz" not in pseudo_english:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_missing_anc_nmz",
            "good": good_sentence,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    pseudo_args = extract_pseudo_anc_tv_p(pseudo_english)
    if pseudo_args is None:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_missing_p_only_tv_anc",
            "good": good_sentence,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    tokens = good_sentence.strip().split()
    anc_verb = find_anc_verb(tokens)
    if anc_verb is None:
        return {
            "skip": True,
            "skip_reason": "anc_ing_token_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    p_index = find_unique_expected_head_index(tokens, pseudo_args.p_head)
    if p_index is None:
        return {
            "skip": True,
            "skip_reason": "anc_p_head_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "expected_p_head": pseudo_args.p_head,
            "anc_verb_index": anc_verb.index,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    p_token = tokens[p_index]
    actual_p_marker = marker_for_expected_head(p_token, pseudo_args.p_head)
    good_p_marker = language_config["ANC_P_MARK"] or ""
    if actual_p_marker != good_p_marker:
        return {
            "skip": True,
            "skip_reason": "anc_p_marker_does_not_match_expected_value",
            "good": good_sentence,
            "tokens": tokens,
            "p_index": p_index,
            "p_token": p_token,
            "actual_marker": marker_value(actual_p_marker or ""),
            "expected_marker": marker_value(good_p_marker),
            "expected_p_head": pseudo_args.p_head,
            "anc_verb_index": anc_verb.index,
            "anc_verb_token": anc_verb.token,
            "strategy": language_config["strategy"],
            "alignment": language_config["alignment"],
            "anc_wo": language_config["anc_wo"],
            "anc_wo_choice": language_config.get("anc_wo_choice", language_config["anc_wo"]),
            "anc_iv_order": language_config.get("anc_iv_order", ""),
            "anc_tv_order": language_config.get("anc_tv_order", ""),
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    bad_p_marker = language_config["FIN_P_MARK"] or ""
    bad_tokens = tokens[:]
    bad_tokens[anc_verb.index] = finite_from_anc_verb(anc_verb)
    bad_tokens[p_index] = replace_expected_head_marker(
        p_token,
        pseudo_args.p_head,
        good_p_marker,
        bad_p_marker,
    )

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "ANC_OMITTED_A",
        "target_index": anc_verb.index,
        "target_token": anc_verb.token,
        "target_stem": anc_verb.stem.lower(),
        "target_external_case_marker": marker_value(anc_verb.marker),
        "p_index": p_index,
        "p_token": p_token,
        "expected_p_head": pseudo_args.p_head,
        "p_good_marker": marker_value(good_p_marker),
        "p_bad_marker": marker_value(bad_p_marker),
        "good_value": "tv_anc_with_p_and_omitted_a",
        "bad_value": "finite_tv_predicate_with_p_without_a",
        "anc_profile": template.profile,
        "anc_source_construction": template.source_construction,
        "anc_overt_arguments": ",".join(template.overt_arguments),
        "template": template.name,
        "anc_wo": language_config["anc_wo"],
        "anc_wo_choice": language_config.get("anc_wo_choice", language_config["anc_wo"]),
        "anc_iv_order": language_config.get("anc_iv_order", ""),
        "anc_tv_order": language_config.get("anc_tv_order", ""),
        "strategy": language_config["strategy"],
        "alignment": language_config["alignment"],
        "matrix_role": "P",
        "omitted_argument": "A",
        "perturbation": "replace_tv_p_anc_head_with_finite_tv_predicate_and_sync_p_marker",
    }
