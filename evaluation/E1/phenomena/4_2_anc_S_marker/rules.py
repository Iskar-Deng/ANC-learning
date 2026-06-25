#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple


PHENOMENON_ID = "4.2"
PHENOMENON_NAME = "anc_S_marker"
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


def strip_marker(token: str) -> tuple[str, str]:
    lower = token.lower()
    for marker in ANC_MARKERS:
        if lower.endswith(marker) and len(token) > len(marker):
            return token[: -len(marker)], token[-len(marker) :]
    return token, ""


def marker_value(marker: str) -> str:
    return marker or "0"


def extract_pseudo_anc_s_head(pseudo_english: str) -> str | None:
    pseudo_tokens = pseudo_english.strip().lower().split()
    for index, token in enumerate(pseudo_tokens):
        base, _ = strip_marker(token)
        if not base.endswith("nmz"):
            continue
        if index > 0:
            s_token = pseudo_tokens[index - 1]
            if s_token.endswith("ge") and len(s_token) > 2:
                return s_token[:-2]
    return None


def replace_marker(token: str, good_marker: str, bad_marker: str) -> str:
    base, marker = strip_marker(token)
    if marker != good_marker:
        raise ValueError(
            f"Expected marker {good_marker!r} on token {token!r}, got {marker!r}"
        )
    if bad_marker == "0":
        return base
    if bad_marker in ANC_MARKERS:
        return base + bad_marker
    raise ValueError(f"Unsupported bad marker: {bad_marker!r}")


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
    if bad_marker == "0":
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


def expected_anc_s_marker(language_config: Dict[str, Any]) -> str:
    strategy = language_config["strategy"]
    if strategy == "sent":
        return language_config["FIN_S_MARK"] or ""
    if strategy in {"poss-acc", "erg-poss", "nomn"}:
        return "ge"
    raise ValueError(f"Unsupported strategy: {strategy}")


def bad_anc_s_marker(language_config: Dict[str, Any], good_marker: str) -> str:
    strategy = language_config["strategy"]

    if strategy == "sent":
        return "ge"
    if strategy in {"erg-poss", "nomn"}:
        return marker_value(language_config["FIN_S_MARK"] or "")
    if strategy == "poss-acc":
        return marker_value(language_config["FIN_S_MARK"] or "")
    raise ValueError(
        f"Unsupported ANC S marker perturbation: {strategy=} {good_marker=}"
    )


def anc_s_is_before_verb(anc_wo: str) -> bool:
    if anc_wo in {"sov", "svo"}:
        return True
    if anc_wo in {"vos", "ovs"}:
        return False
    raise ValueError(f"Unsupported anc_wo: {anc_wo}")


def find_target_s_index(
    tokens: List[str],
    anc_verb: VerbToken,
    anc_wo: str,
    np_wo: str,
    expected_head: str,
) -> int | None:
    if anc_s_is_before_verb(anc_wo):
        candidate_indices = range(anc_verb.index - 1, -1, -1)
    else:
        candidate_indices = range(anc_verb.index + 1, len(tokens))

    for index in candidate_indices:
        token = tokens[index]
        if is_anc_verb_token(token):
            continue
        if marker_for_expected_head(token, expected_head) is not None:
            return index
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
            "skip_reason": "source_index_outside_4_2_profile_ranges",
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

    expected_s_head = extract_pseudo_anc_s_head(pseudo_english)
    if expected_s_head is None:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_missing_overt_anc_s",
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

    target_index = find_target_s_index(
        tokens,
        anc_verb,
        language_config["anc_wo"],
        language_config["np_wo"],
        expected_s_head,
    )
    if target_index is None:
        return {
            "skip": True,
            "skip_reason": "anc_s_target_not_adjacent_to_anc_verb",
            "good": good_sentence,
            "tokens": tokens,
            "anc_verb_index": anc_verb.index,
            "anc_wo": language_config["anc_wo"],
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    target_token = tokens[target_index]
    actual_marker = marker_for_expected_head(target_token, expected_s_head)
    if actual_marker is None:
        return {
            "skip": True,
            "skip_reason": "anc_s_target_does_not_match_pseudo_head",
            "good": good_sentence,
            "tokens": tokens,
            "target_index": target_index,
            "target_token": target_token,
            "expected_s_head": expected_s_head,
            "anc_verb_index": anc_verb.index,
            "anc_verb_token": anc_verb.token,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    good_marker = expected_anc_s_marker(language_config)
    if actual_marker != good_marker:
        return {
            "skip": True,
            "skip_reason": "anc_s_marker_does_not_match_expected_value",
            "good": good_sentence,
            "tokens": tokens,
            "target_index": target_index,
            "target_token": target_token,
            "actual_marker": marker_value(actual_marker),
            "expected_marker": marker_value(good_marker),
            "expected_s_head": expected_s_head,
            "anc_verb_index": anc_verb.index,
            "anc_verb_token": anc_verb.token,
            "strategy": language_config["strategy"],
            "alignment": language_config["alignment"],
            "anc_wo": language_config["anc_wo"],
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    bad_marker = bad_anc_s_marker(language_config, good_marker)
    bad_tokens = tokens[:]
    bad_tokens[target_index] = replace_expected_head_marker(
        target_token,
        expected_s_head,
        good_marker,
        bad_marker,
    )

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "ANC_S",
        "target_index": target_index,
        "target_token": target_token,
        "anc_verb_token": anc_verb.token,
        "anc_verb_index": anc_verb.index,
        "expected_s_head": expected_s_head,
        "good_value": marker_value(good_marker),
        "bad_value": bad_marker,
        "anc_profile": template.profile,
        "anc_source_construction": template.source_construction,
        "anc_overt_arguments": ",".join(template.overt_arguments),
        "template": template.name,
        "anc_wo": language_config["anc_wo"],
        "strategy": language_config["strategy"],
        "alignment": language_config["alignment"],
        "perturbation": "replace_anc_s_marker_with_ungrammatical_value",
    }
