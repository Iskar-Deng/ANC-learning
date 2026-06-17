#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple


PHENOMENON_ID = "2.3"
PHENOMENON_NAME = "gen_order"
TEMPLATE_PATH = Path(__file__).with_name("templates.json")


class NpSpan(NamedTuple):
    tokens: List[str]
    start: int
    head_offset: int

    @property
    def head_index(self) -> int:
        return self.start + self.head_offset

    @property
    def possessor_index(self) -> int | None:
        if len(self.tokens) != 2:
            return None
        return self.start + (1 - self.head_offset)

    @property
    def text(self) -> str:
        return " ".join(self.tokens)


class TransitiveTemplateMatch(NamedTuple):
    template_name: str
    a: NpSpan
    p: NpSpan
    verb_token: str
    verb_index: int


def load_templates() -> Dict[str, List[Dict[str, Any]]]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        return json.load(infile)


TEMPLATES = load_templates()


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


def target_role_from_source_index(source_index: int) -> str:
    if 1 <= source_index <= 50:
        return "S"
    if 51 <= source_index <= 100:
        return "A"
    if 101 <= source_index <= 150:
        return "P"
    raise ValueError(f"Unexpected source index for 2.3: {source_index}")


def stable_row_index(row: Dict[str, Any] | None, fallback_index: int) -> int:
    if row is not None:
        for key in ("id", "source_id", "pseudo_index", "pair_index"):
            value = row.get(key)
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return fallback_index


def match_intransitive_template(
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
) -> Dict[str, Any] | None:
    matches = []
    for template in TEMPLATES["intransitive"]:
        if clause_wo not in template["clause_wo"]:
            continue
        if np_wo not in template["np_wo"]:
            continue
        if len(tokens) != template["token_count"]:
            continue
        if not finite_verb_like(tokens[template["verb_index"]]):
            continue

        target_start = template["target_start"]
        possessor_index = target_start + template["possessor_offset"]
        if not tokens[possessor_index].endswith("ge"):
            continue
        matches.append(template)

    if len(matches) == 1:
        return matches[0]
    return None


def spans_for_transitive_template(
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


def transitive_template_match(
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

    a_start, a_len, p_start, p_len, verb_index = spans_for_transitive_template(
        template,
        clause_wo,
    )
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


def find_transitive_template_match(
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
    a_mark: str | None,
    p_mark: str | None,
    target_role: str,
) -> TransitiveTemplateMatch | None:
    matches: List[TransitiveTemplateMatch] = []
    for template in TEMPLATES["transitive"]:
        if target_role == "A" and template["a_len"] != 2:
            continue
        if target_role == "P" and template["p_len"] != 2:
            continue

        match = transitive_template_match(
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


def swap_np_order(tokens: List[str], target_np: NpSpan) -> List[str]:
    if len(target_np.tokens) != 2:
        raise ValueError(f"Expected a two-token genitive NP, got: {target_np.text!r}")
    bad_tokens = tokens[:]
    first = target_np.start
    second = target_np.start + 1
    bad_tokens[first], bad_tokens[second] = bad_tokens[second], bad_tokens[first]
    return bad_tokens


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()
    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]
    target_role = target_role_from_source_index(stable_row_index(row, source_index))

    pseudo_english = row.get("pseudo_english") if row is not None else None
    if isinstance(pseudo_english, str) and "nmz" in pseudo_english:
        return {
            "skip": True,
            "skip_reason": "pseudo_english_contains_nominalization_artifact",
            "good": good_sentence,
            "tokens": tokens,
            "pseudo_english": pseudo_english,
        }

    if target_role == "S":
        template = match_intransitive_template(tokens, clause_wo, np_wo)
        if template is None:
            return {
                "skip": True,
                "skip_reason": "intransitive_template_match_count_not_one",
                "good": good_sentence,
                "tokens": tokens,
                "clause_wo": clause_wo,
                "np_wo": np_wo,
            }

        target_start = template["target_start"]
        target_np = NpSpan(
            tokens=tokens[target_start : target_start + 2],
            start=target_start,
            head_offset=template["head_offset"],
        )
        verb_token = tokens[template["verb_index"]]
        verb_index = template["verb_index"]
        template_name = template["name"]
        a_span = None
        p_span = None
    else:
        parsed = find_transitive_template_match(
            tokens=tokens,
            clause_wo=clause_wo,
            np_wo=np_wo,
            a_mark=language_config["FIN_A_MARK"],
            p_mark=language_config["FIN_P_MARK"],
            target_role=target_role,
        )
        if parsed is None:
            return {
                "skip": True,
                "skip_reason": "transitive_template_match_count_not_one",
                "good": good_sentence,
                "tokens": tokens,
                "clause_wo": clause_wo,
                "np_wo": np_wo,
                "target_role": target_role,
                "a_mark": marker_value(language_config["FIN_A_MARK"]),
                "p_mark": marker_value(language_config["FIN_P_MARK"]),
            }

        target_np = parsed.a if target_role == "A" else parsed.p
        verb_token = parsed.verb_token
        verb_index = parsed.verb_index
        template_name = parsed.template_name
        a_span = parsed.a.text
        p_span = parsed.p.text

    possessor_index = target_np.possessor_index
    if possessor_index is None or not tokens[possessor_index].endswith("ge"):
        return {
            "skip": True,
            "skip_reason": "target_np_has_no_genitive_possessor",
            "good": good_sentence,
            "tokens": tokens,
            "target_role": target_role,
            "target_np_span": target_np.text,
        }

    bad_tokens = swap_np_order(tokens, target_np)
    good_value = "possessor_head" if np_wo == "gn" else "head_possessor"
    bad_value = "head_possessor" if np_wo == "gn" else "possessor_head"

    result = {
        "bad": " ".join(bad_tokens),
        "target_role": f"{target_role}_possessor_head_order",
        "target_argument": target_role,
        "target_index": target_np.start,
        "target_token": target_np.text,
        "target_np_span": target_np.text,
        "possessor_index": possessor_index,
        "head_index": target_np.head_index,
        "possessor_token": tokens[possessor_index],
        "head_token": tokens[target_np.head_index],
        "verb_token": verb_token,
        "verb_index": verb_index,
        "good_value": good_value,
        "bad_value": bad_value,
        "template": template_name,
        "perturbation": "swap_np_possessor_and_head_order",
    }

    if a_span is not None:
        result["a_span"] = a_span
    if p_span is not None:
        result["p_span"] = p_span

    return result
