#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple


PHENOMENON_ID = "5.1"
PHENOMENON_NAME = "anc_ext_S_marker"
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


def foil_marker_for_row(row: Dict[str, Any] | None, fallback_index: int) -> str:
    value: Any = fallback_index
    if row is not None:
        value = row.get("id", row.get("source_id", fallback_index))

    try:
        index = int(value)
    except (TypeError, ValueError):
        index = fallback_index

    return "ca" if index % 2 else "ge"


def strip_marker(token: str) -> tuple[str, str]:
    lower = token.lower()
    for marker in ANC_MARKERS:
        if lower.endswith(marker) and len(token) > len(marker):
            return token[: -len(marker)], token[-len(marker) :]
    return token, ""


def marker_value(marker: str) -> str:
    return marker or "0"


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


def add_marker_to_anc_head(token: str, expected_marker: str, bad_marker: str) -> str:
    base, marker = strip_marker(token)
    if marker != expected_marker:
        raise ValueError(
            f"Expected marker {expected_marker!r} on token {token!r}, got {marker!r}"
        )
    if bad_marker not in ANC_MARKERS:
        raise ValueError(f"Unsupported bad marker: {bad_marker!r}")
    return base + bad_marker


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
            "skip_reason": "source_index_outside_5_1_profile_ranges",
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

    good_marker = language_config["FIN_S_MARK"] or ""
    if anc_verb.marker != good_marker:
        return {
            "skip": True,
            "skip_reason": "anc_external_s_marker_does_not_match_expected_value",
            "good": good_sentence,
            "tokens": tokens,
            "target_index": anc_verb.index,
            "target_token": anc_verb.token,
            "actual_marker": marker_value(anc_verb.marker),
            "expected_marker": marker_value(good_marker),
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    bad_marker = foil_marker_for_row(row, source_index)
    bad_tokens = tokens[:]
    bad_tokens[anc_verb.index] = add_marker_to_anc_head(
        anc_verb.token,
        good_marker,
        bad_marker,
    )

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "ANC_EXT_S",
        "target_index": anc_verb.index,
        "target_token": anc_verb.token,
        "target_stem": anc_verb.stem.lower(),
        "good_value": marker_value(good_marker),
        "bad_value": bad_marker,
        "anc_profile": template.profile,
        "anc_source_construction": template.source_construction,
        "anc_overt_arguments": ",".join(template.overt_arguments) if template.overt_arguments else "none",
        "template": template.name,
        "anc_wo": language_config["anc_wo"],
        "anc_wo_choice": language_config.get("anc_wo_choice", language_config["anc_wo"]),
        "anc_iv_order": language_config.get("anc_iv_order", ""),
        "anc_tv_order": language_config.get("anc_tv_order", ""),
        "strategy": language_config["strategy"],
        "alignment": language_config["alignment"],
        "matrix_role": "S",
        "perturbation": f"add_{bad_marker}_to_anc_external_s_head",
    }
