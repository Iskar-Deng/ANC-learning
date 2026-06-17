#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple


PHENOMENON_ID = "3.2"
PHENOMENON_NAME = "clausal_S_marker"
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


class TemplateShape(NamedTuple):
    base_name: str
    matrix_a_len: int
    embedded_s_len: int

    @property
    def embedded_len(self) -> int:
        return self.embedded_s_len + 1

    @property
    def name(self) -> str:
        return f"{self.base_name}_ma{self.matrix_a_len}_s{self.embedded_s_len}"


class ClauseMatch(NamedTuple):
    template_name: str
    matrix_a: NpSpan
    matrix_verb_index: int
    matrix_verb_token: str
    embedded_s: NpSpan
    embedded_verb_index: int
    embedded_verb_token: str


def load_templates() -> List[Dict[str, Any]]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        return json.load(infile)


TEMPLATES = load_templates()


def expand_templates() -> List[TemplateShape]:
    shapes: List[TemplateShape] = []
    for template in TEMPLATES:
        if template["embedded_construction"] != "iv":
            raise ValueError("3.2 only supports embedded IV complements")
        for matrix_a_len in template["matrix_a_lens"]:
            for s_len in template["embedded_s_lens"]:
                shapes.append(
                    TemplateShape(
                        base_name=template["name"],
                        matrix_a_len=matrix_a_len,
                        embedded_s_len=s_len,
                    )
                )
    return shapes


SHAPES = expand_templates()


def marker_value(mark: str | None) -> str:
    return mark or "0"


def finite_verb_like(token: str) -> bool:
    return token.endswith("s") and not token.endswith("ca") and not token.endswith("ge")


def nonfinite_verb_like(token: str) -> bool:
    return token.endswith("ing") and not token.endswith("ca") and not token.endswith("ge")


def expected_comp_form(comp_system: str) -> str:
    if comp_system == "balancing":
        return "finite_s"
    if comp_system == "deranking":
        return "nonfinite_ing"
    raise ValueError(f"Unsupported comp_system: {comp_system}")


def token_matches_form(token: str, form: str) -> bool:
    if form == "finite_s":
        return finite_verb_like(token)
    if form == "nonfinite_ing":
        return nonfinite_verb_like(token)
    raise ValueError(f"Unsupported verb form: {form}")


def head_matches_marker(token: str, expected_mark: str | None) -> bool:
    mark = expected_mark or ""
    if mark == "ca":
        return token.endswith("ca")
    if mark == "":
        return True
    raise ValueError(f"Unsupported marker: {mark!r}")


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


def matrix_positions(shape: TemplateShape, clause_wo: str) -> tuple[int, int, int]:
    embedded_len = shape.embedded_len
    if clause_wo == "sov":
        return 0, shape.matrix_a_len, shape.matrix_a_len + embedded_len
    if clause_wo == "svo":
        return 0, shape.matrix_a_len + 1, shape.matrix_a_len
    if clause_wo == "vos":
        return 1 + embedded_len, 1, 0
    raise ValueError(f"Unsupported clause_wo: {clause_wo}")


def match_shape(
    shape: TemplateShape,
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
    comp_form: str,
    matrix_a_mark: str | None,
    embedded_s_mark: str | None,
) -> ClauseMatch | None:
    expected_len = shape.matrix_a_len + shape.embedded_len + 1
    if len(tokens) != expected_len:
        return None

    matrix_a_start, embedded_start, matrix_verb_index = matrix_positions(shape, clause_wo)
    matrix_verb = tokens[matrix_verb_index]
    if not finite_verb_like(matrix_verb):
        return None

    matrix_a = parse_np(
        tokens[matrix_a_start : matrix_a_start + shape.matrix_a_len],
        matrix_a_start,
        np_wo,
        matrix_a_mark,
    )
    if matrix_a is None:
        return None

    if clause_wo in {"sov", "svo"}:
        s_start = embedded_start
        verb_index = embedded_start + shape.embedded_s_len
    elif clause_wo == "vos":
        verb_index = embedded_start
        s_start = embedded_start + 1
    else:
        raise ValueError(f"Unsupported clause_wo: {clause_wo}")

    embedded_verb = tokens[verb_index]
    if not token_matches_form(embedded_verb, comp_form):
        return None

    embedded_s = parse_np(
        tokens[s_start : s_start + shape.embedded_s_len],
        s_start,
        np_wo,
        embedded_s_mark,
    )
    if embedded_s is None:
        return None

    return ClauseMatch(
        template_name=shape.name,
        matrix_a=matrix_a,
        matrix_verb_index=matrix_verb_index,
        matrix_verb_token=matrix_verb,
        embedded_s=embedded_s,
        embedded_verb_index=verb_index,
        embedded_verb_token=embedded_verb,
    )


def shapes_from_pseudo(row: Dict[str, Any] | None) -> List[TemplateShape] | None:
    if row is None:
        return None

    pseudo = row.get("pseudo_english")
    if not isinstance(pseudo, str):
        return None

    pseudo_tokens = pseudo.strip().lower().split()
    if "that" not in pseudo_tokens:
        return None

    that_index = pseudo_tokens.index("that")
    matrix_a_len = that_index - 1
    if matrix_a_len not in (1, 2):
        return None

    embedded = pseudo_tokens[that_index + 1 :]
    s_len = len(embedded) - 1
    if s_len not in (1, 2):
        return None
    if not finite_verb_like(embedded[-1]):
        return None

    return [
        TemplateShape(
            base_name="cv_embedded_iv",
            matrix_a_len=matrix_a_len,
            embedded_s_len=s_len,
        )
    ]


def candidate_shapes(row: Dict[str, Any] | None) -> Iterable[TemplateShape]:
    return shapes_from_pseudo(row) or SHAPES


def find_match(
    tokens: List[str],
    language_config: Dict[str, Any],
    row: Dict[str, Any] | None,
) -> ClauseMatch | None:
    clause_wo = language_config["clause_wo"]
    np_wo = language_config["np_wo"]
    comp_form = expected_comp_form(language_config["comp_system"])

    matches: List[ClauseMatch] = []
    for shape in candidate_shapes(row):
        match = match_shape(
            shape=shape,
            tokens=tokens,
            clause_wo=clause_wo,
            np_wo=np_wo,
            comp_form=comp_form,
            matrix_a_mark=language_config["FIN_A_MARK"],
            embedded_s_mark=language_config["FIN_S_MARK"],
        )
        if match is not None:
            matches.append(match)

    if len(matches) == 1:
        return matches[0]

    return None


def perturb(
    good_sentence: str,
    language_config: Dict[str, Any],
    source_index: int,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tokens = good_sentence.strip().split()
    parsed = find_match(tokens=tokens, language_config=language_config, row=row)

    if parsed is None:
        return {
            "skip": True,
            "skip_reason": "template_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "clause_wo": language_config["clause_wo"],
            "np_wo": language_config["np_wo"],
            "comp_system": language_config["comp_system"],
        }

    target_index = parsed.embedded_s.head_index
    target_token = tokens[target_index]
    bad_tokens = tokens[:]
    bad_tokens[target_index] = target_token + "ge"

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "COMP_S",
        "target_index": target_index,
        "target_token": target_token,
        "matrix_a_span": parsed.matrix_a.text,
        "matrix_verb_token": parsed.matrix_verb_token,
        "matrix_verb_index": parsed.matrix_verb_index,
        "embedded_s_span": parsed.embedded_s.text,
        "embedded_s_head_index": target_index,
        "embedded_verb_token": parsed.embedded_verb_token,
        "embedded_verb_index": parsed.embedded_verb_index,
        "good_value": "0",
        "bad_value": "ge",
        "template": parsed.template_name,
        "perturbation": "add_ge_to_clausal_complement_s_head",
    }
