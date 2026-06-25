#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple


PHENOMENON_ID = "4.6"
PHENOMENON_NAME = "anc_AV_order"
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


class PseudoAncTvArgs(NamedTuple):
    a_head: str
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


def extract_pseudo_anc_tv_args(pseudo_english: str) -> PseudoAncTvArgs | None:
    pseudo_tokens = pseudo_english.strip().lower().split()
    for index, token in enumerate(pseudo_tokens):
        base, _ = strip_marker(token)
        if not base.endswith("nmz"):
            continue
        if index <= 0 or index + 1 >= len(pseudo_tokens):
            continue

        a_token = pseudo_tokens[index - 1]
        p_token = pseudo_tokens[index + 1]
        if not a_token.endswith("ge") or len(a_token) <= 2:
            continue
        if not p_token.endswith("ob") or len(p_token) <= 2:
            continue
        return PseudoAncTvArgs(a_head=a_token[:-2], p_head=p_token[:-2])
    return None


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


def expected_anc_a_marker(language_config: Dict[str, Any]) -> str:
    strategy = language_config["strategy"]
    if strategy == "sent":
        return language_config["FIN_A_MARK"] or ""
    if strategy in {"poss-acc", "nomn"}:
        return "ge"
    if strategy == "erg-poss":
        return "ob"
    raise ValueError(f"Unsupported strategy: {strategy}")


def expected_anc_p_marker(language_config: Dict[str, Any]) -> str:
    strategy = language_config["strategy"]
    if strategy == "sent":
        return language_config["FIN_P_MARK"] or ""
    if strategy == "poss-acc":
        return language_config["FIN_P_MARK"] or ""
    if strategy == "erg-poss":
        return "ge"
    if strategy == "nomn":
        return "ob"
    raise ValueError(f"Unsupported strategy: {strategy}")


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


def contiguous_span(indices: List[int]) -> tuple[int, int] | None:
    ordered = sorted(indices)
    if ordered != list(range(ordered[0], ordered[-1] + 1)):
        return None
    return ordered[0], ordered[-1] + 1


def swap_a_with_vp_chunk(
    tokens: List[str],
    a_index: int,
    p_index: int,
    v_index: int,
) -> tuple[List[str], str, str, List[str], List[str]] | None:
    vp_span = contiguous_span([p_index, v_index])
    if vp_span is None:
        return None

    a_span = (a_index, a_index + 1)
    if a_span[1] == vp_span[0]:
        # GOOD: A [P V] or A [V P] -> BAD: [P V] A / [V P] A
        good_value, bad_value = "AV", "VA"
        bad_tokens = (
            tokens[: a_span[0]]
            + tokens[vp_span[0] : vp_span[1]]
            + tokens[a_span[0] : a_span[1]]
            + tokens[vp_span[1] :]
        )
    elif vp_span[1] == a_span[0]:
        # GOOD: [V P] A or [P V] A -> BAD: A [V P] / A [P V]
        good_value, bad_value = "VA", "AV"
        bad_tokens = (
            tokens[: vp_span[0]]
            + tokens[a_span[0] : a_span[1]]
            + tokens[vp_span[0] : vp_span[1]]
            + tokens[a_span[1] :]
        )
    else:
        return None

    anc_span = contiguous_span([a_index, p_index, v_index])
    if anc_span is None:
        return None

    return (
        bad_tokens,
        good_value,
        bad_value,
        tokens[a_span[0] : a_span[1]],
        tokens[vp_span[0] : vp_span[1]],
    )


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
            "skip_reason": "source_index_outside_4_6_profile_ranges",
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

    pseudo_args = extract_pseudo_anc_tv_args(pseudo_english)
    if pseudo_args is None:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_missing_overt_anc_a_or_p",
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

    a_index = find_unique_expected_head_index(tokens, pseudo_args.a_head)
    if a_index is None:
        return {
            "skip": True,
            "skip_reason": "anc_a_target_head_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "expected_a_head": pseudo_args.a_head,
            "expected_p_head": pseudo_args.p_head,
            "anc_verb_index": anc_verb.index,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    p_index = find_unique_expected_head_index(tokens, pseudo_args.p_head)
    if p_index is None:
        return {
            "skip": True,
            "skip_reason": "anc_p_validation_head_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "expected_a_head": pseudo_args.a_head,
            "expected_p_head": pseudo_args.p_head,
            "anc_verb_index": anc_verb.index,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    a_token = tokens[a_index]
    actual_a_marker = marker_for_expected_head(a_token, pseudo_args.a_head)
    if actual_a_marker is None:
        return {
            "skip": True,
            "skip_reason": "anc_a_target_does_not_match_pseudo_head",
            "good": good_sentence,
            "tokens": tokens,
            "a_index": a_index,
            "a_token": a_token,
            "expected_a_head": pseudo_args.a_head,
            "expected_p_head": pseudo_args.p_head,
            "anc_verb_index": anc_verb.index,
            "anc_verb_token": anc_verb.token,
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    good_a_marker = expected_anc_a_marker(language_config)
    if actual_a_marker != good_a_marker:
        return {
            "skip": True,
            "skip_reason": "anc_a_marker_does_not_match_expected_value",
            "good": good_sentence,
            "tokens": tokens,
            "a_index": a_index,
            "a_token": a_token,
            "actual_marker": marker_value(actual_a_marker),
            "expected_marker": marker_value(good_a_marker),
            "expected_a_head": pseudo_args.a_head,
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

    p_token = tokens[p_index]
    actual_p_marker = marker_for_expected_head(p_token, pseudo_args.p_head)
    good_p_marker = expected_anc_p_marker(language_config)
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
            "expected_a_head": pseudo_args.a_head,
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

    swapped = swap_a_with_vp_chunk(
        tokens,
        a_index,
        p_index,
        anc_verb.index,
    )
    if swapped is None:
        return {
            "skip": True,
            "skip_reason": "anc_a_vp_order_not_contiguous_or_unexpected",
            "good": good_sentence,
            "tokens": tokens,
            "a_index": a_index,
            "p_index": p_index,
            "anc_verb_index": anc_verb.index,
            "anc_wo": language_config["anc_wo"],
            "anc_wo_choice": language_config.get("anc_wo_choice", language_config["anc_wo"]),
            "anc_iv_order": language_config.get("anc_iv_order", ""),
            "anc_tv_order": language_config.get("anc_tv_order", ""),
            "source_index": source_index,
            "profile": template.profile,
            "pseudo_english": pseudo_english,
        }

    bad_tokens, good_value, bad_value, a_span_tokens, vp_chunk_tokens = swapped

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "ANC_AV_order",
        "target_index": a_index,
        "target_token": a_token,
        "anc_verb_token": anc_verb.token,
        "anc_verb_index": anc_verb.index,
        "expected_a_head": pseudo_args.a_head,
        "expected_p_head": pseudo_args.p_head,
        "p_validation_index": p_index,
        "p_validation_token": tokens[p_index],
        "a_span": " ".join(a_span_tokens),
        "p_span": p_token,
        "vp_chunk": " ".join(vp_chunk_tokens),
        "good_value": good_value,
        "bad_value": bad_value,
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
        "perturbation": "swap_anc_a_span_with_vp_chunk",
    }
