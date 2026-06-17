#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple


PHENOMENON_ID = "3.4"
PHENOMENON_NAME = "clausal_P_marker"
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
    embedded_construction: str
    matrix_a_len: int
    embedded_s_len: int | None = None
    embedded_a_len: int | None = None
    embedded_p_len: int | None = None

    @property
    def embedded_len(self) -> int:
        if self.embedded_construction == "iv":
            assert self.embedded_s_len is not None
            return self.embedded_s_len + 1
        assert self.embedded_a_len is not None
        assert self.embedded_p_len is not None
        return self.embedded_a_len + self.embedded_p_len + 1

    @property
    def name(self) -> str:
        if self.embedded_construction == "iv":
            return f"{self.base_name}_ma{self.matrix_a_len}_s{self.embedded_s_len}"
        return (
            f"{self.base_name}_ma{self.matrix_a_len}_"
            f"a{self.embedded_a_len}_p{self.embedded_p_len}"
        )


class ClauseMatch(NamedTuple):
    template_name: str
    matrix_a: NpSpan
    matrix_verb_index: int
    matrix_verb_token: str
    embedded_construction: str
    embedded_verb_index: int
    embedded_verb_token: str
    embedded_s: NpSpan | None = None
    embedded_a: NpSpan | None = None
    embedded_p: NpSpan | None = None


def load_templates() -> List[Dict[str, Any]]:
    with TEMPLATE_PATH.open(encoding="utf-8") as infile:
        return json.load(infile)


TEMPLATES = load_templates()


def expand_templates() -> List[TemplateShape]:
    shapes: List[TemplateShape] = []
    for template in TEMPLATES:
        base = template["name"]
        construction = template["embedded_construction"]
        for matrix_a_len in template["matrix_a_lens"]:
            if construction == "iv":
                for s_len in template["embedded_s_lens"]:
                    shapes.append(
                        TemplateShape(
                            base_name=base,
                            embedded_construction="iv",
                            matrix_a_len=matrix_a_len,
                            embedded_s_len=s_len,
                        )
                    )
            elif construction == "tv":
                for a_len in template["embedded_a_lens"]:
                    for p_len in template["embedded_p_lens"]:
                        shapes.append(
                            TemplateShape(
                                base_name=base,
                                embedded_construction="tv",
                                matrix_a_len=matrix_a_len,
                                embedded_a_len=a_len,
                                embedded_p_len=p_len,
                            )
                        )
            else:
                raise ValueError(f"Unsupported embedded construction: {construction}")
    return shapes


SHAPES = expand_templates()


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
    return (
        token.endswith("s")
        and not token.endswith("ca")
        and not token.endswith("ge")
        and not token.endswith("ob")
    )


def nonfinite_verb_like(token: str) -> bool:
    return (
        token.endswith("ing")
        and not token.endswith("ca")
        and not token.endswith("ge")
        and not token.endswith("ob")
    )


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
    if mark == "ge":
        return token.endswith("ge")
    if mark == "ob":
        return token.endswith("ob")
    if mark == "":
        return True
    raise ValueError(f"Unsupported marker: {mark!r}")


def replace_head_marker(token: str, good_mark: str | None, bad_mark: str) -> str:
    good = good_mark or ""
    if good == "":
        stem = token
    else:
        stem = strip_suffix(token, good)

    if bad_mark == "0":
        return stem
    if bad_mark in {"ca", "ge", "ob"}:
        return stem + bad_mark
    raise ValueError(f"Unsupported bad marker: {bad_mark!r}")


def anc_p_foil_marker(language_config: Dict[str, Any]) -> str:
    strategy = language_config["strategy"]
    if strategy == "nomn":
        return "ob"
    if strategy in {"sent", "poss-acc", "erg-poss"}:
        return "ge"
    raise ValueError(f"Unsupported strategy: {strategy}")


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
    embedded_a_mark: str | None,
    embedded_p_mark: str | None,
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

    if shape.embedded_construction == "iv":
        assert shape.embedded_s_len is not None
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
            embedded_construction="iv",
            embedded_verb_index=verb_index,
            embedded_verb_token=embedded_verb,
            embedded_s=embedded_s,
        )

    assert shape.embedded_a_len is not None
    assert shape.embedded_p_len is not None

    if clause_wo == "sov":
        a_start = embedded_start
        p_start = embedded_start + shape.embedded_a_len
        verb_index = embedded_start + shape.embedded_a_len + shape.embedded_p_len
    elif clause_wo == "svo":
        a_start = embedded_start
        verb_index = embedded_start + shape.embedded_a_len
        p_start = embedded_start + shape.embedded_a_len + 1
    elif clause_wo == "vos":
        verb_index = embedded_start
        p_start = embedded_start + 1
        a_start = embedded_start + 1 + shape.embedded_p_len
    else:
        raise ValueError(f"Unsupported clause_wo: {clause_wo}")

    embedded_verb = tokens[verb_index]
    if not token_matches_form(embedded_verb, comp_form):
        return None

    embedded_a = parse_np(
        tokens[a_start : a_start + shape.embedded_a_len],
        a_start,
        np_wo,
        embedded_a_mark,
    )
    if embedded_a is None:
        return None

    embedded_p = parse_np(
        tokens[p_start : p_start + shape.embedded_p_len],
        p_start,
        np_wo,
        embedded_p_mark,
    )
    if embedded_p is None:
        return None

    return ClauseMatch(
        template_name=shape.name,
        matrix_a=matrix_a,
        matrix_verb_index=matrix_verb_index,
        matrix_verb_token=matrix_verb,
        embedded_construction="tv",
        embedded_verb_index=verb_index,
        embedded_verb_token=embedded_verb,
        embedded_a=embedded_a,
        embedded_p=embedded_p,
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
    if len(embedded) < 2:
        return None

    candidates: List[TemplateShape] = []

    if len(embedded) - 1 in (1, 2) and finite_verb_like(embedded[-1]):
        candidates.append(
            TemplateShape(
                base_name="cv_embedded_iv",
                embedded_construction="iv",
                matrix_a_len=matrix_a_len,
                embedded_s_len=len(embedded) - 1,
            )
        )

    for a_len in (1, 2):
        verb_index = a_len
        if verb_index >= len(embedded):
            continue
        if not finite_verb_like(embedded[verb_index]):
            continue
        p_len = len(embedded) - a_len - 1
        if p_len not in (1, 2):
            continue
        candidates.append(
            TemplateShape(
                base_name="cv_embedded_tv",
                embedded_construction="tv",
                matrix_a_len=matrix_a_len,
                embedded_a_len=a_len,
                embedded_p_len=p_len,
            )
        )

    return candidates or None


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
            embedded_a_mark=language_config["FIN_A_MARK"],
            embedded_p_mark=language_config["FIN_P_MARK"],
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
    if parsed is None or parsed.embedded_construction != "tv":
        return {
            "skip": True,
            "skip_reason": "template_match_count_not_one",
            "good": good_sentence,
            "tokens": tokens,
            "clause_wo": language_config["clause_wo"],
            "np_wo": language_config["np_wo"],
            "comp_system": language_config["comp_system"],
            "good_value": marker_value(language_config["FIN_P_MARK"]),
        }

    assert parsed.embedded_a is not None
    assert parsed.embedded_p is not None

    good_mark = language_config["FIN_P_MARK"]
    bad_mark = anc_p_foil_marker(language_config)
    target_index = parsed.embedded_p.head_index
    target_token = tokens[target_index]
    bad_tokens = tokens[:]
    bad_tokens[target_index] = replace_head_marker(
        token=target_token,
        good_mark=good_mark,
        bad_mark=bad_mark,
    )

    return {
        "bad": " ".join(bad_tokens),
        "target_role": "COMP_P",
        "target_index": target_index,
        "target_token": target_token,
        "matrix_a_span": parsed.matrix_a.text,
        "matrix_verb_token": parsed.matrix_verb_token,
        "matrix_verb_index": parsed.matrix_verb_index,
        "embedded_construction": parsed.embedded_construction,
        "embedded_verb_token": parsed.embedded_verb_token,
        "embedded_verb_index": parsed.embedded_verb_index,
        "embedded_a_span": parsed.embedded_a.text,
        "embedded_p_span": parsed.embedded_p.text,
        "embedded_p_head_index": target_index,
        "good_value": marker_value(good_mark),
        "bad_value": bad_mark,
        "strategy": language_config["strategy"],
        "template": parsed.template_name,
        "perturbation": "replace_clausal_complement_p_marker_with_anc_p_marker",
    }
