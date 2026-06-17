#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple


PHENOMENON_ID = "1.4"
PHENOMENON_NAME = "tran_A_marker"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")


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


TEMPLATES = load_templates()


def marker_value(mark: str | None) -> str:
    return mark or "0"


def strip_suffix(token: str, suffix: str) -> str:
    if not token.endswith(suffix):
        raise ValueError(f"Expected token ending in {suffix!r}, got: {token}")
    stem = token[: -len(suffix)]
    if not stem:
        raise ValueError(f"Could not strip suffix {suffix!r} from token: {token}")
    return stem


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


def stable_row_index(row: Dict[str, Any] | None, fallback_index: int) -> int:
    if row is not None:
        for key in ("id", "source_id", "pseudo_index", "pair_index"):
            value = row.get(key)
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return fallback_index


def foil_for_a(row: Dict[str, Any] | None, fallback_index: int, alignment: str) -> tuple[str, str]:
    use_ge_foil = stable_row_index(row, fallback_index) % 2 == 0

    if use_ge_foil:
        return "ge", "replace_transitive_a_marker_with_ge"

    if alignment == "nom-acc":
        return "ca", "add_ca_to_transitive_a"

    if alignment == "erg-abs":
        return "0", "remove_ca_from_transitive_a"

    raise ValueError(f"Unsupported alignment: {alignment}")


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()

    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]
    alignment = language_config["alignment"]
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
            "alignment": alignment,
            "good_a_mark": marker_value(good_a_mark),
            "good_p_mark": marker_value(good_p_mark),
        }

    target_index = parsed.a.head_index
    target_token = tokens[target_index]
    bad_value, perturbation_label = foil_for_a(row, source_index, alignment)

    bad_tokens = tokens[:]
    if marker_value(good_a_mark) == "0":
        if bad_value == "0":
            raise ValueError("A is already zero-marked")
        bad_tokens[target_index] = target_token + bad_value
    elif good_a_mark == "ca":
        a_stem = strip_suffix(target_token, "ca")
        if bad_value == "0":
            bad_tokens[target_index] = a_stem
        elif bad_value == "ge":
            bad_tokens[target_index] = a_stem + "ge"
        else:
            raise ValueError(f"Unsupported bad_value for ca-marked A: {bad_value}")
    else:
        raise ValueError(f"Unsupported GOOD A marker: {good_a_mark!r}")

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "A",
        "target_index": target_index,
        "target_token": target_token,
        "a_span": parsed.a.text,
        "p_span": parsed.p.text,
        "verb_token": parsed.verb_token,
        "good_value": marker_value(good_a_mark),
        "bad_value": bad_value,
        "template": parsed.template_name,
        "perturbation": perturbation_label,
    }
