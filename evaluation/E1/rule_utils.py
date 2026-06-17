#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class NpSpan:
    tokens: List[str]
    start: int
    head_offset: int

    @property
    def head_index(self) -> int:
        return self.start + self.head_offset

    @property
    def text(self) -> str:
        return " ".join(self.tokens)


@dataclass(frozen=True)
class TransitiveParse:
    a: NpSpan
    p: NpSpan
    verb_token: str
    verb_index: int


def marker_value(mark: str | None) -> str:
    return mark or "0"


def has_suffix(token: str, suffix: str) -> bool:
    return bool(suffix) and token.endswith(suffix)


def strip_suffix(token: str, suffix: str) -> str:
    if not token.endswith(suffix):
        raise ValueError(f"Expected token ending in {suffix!r}, got: {token}")
    stem = token[: -len(suffix)]
    if not stem:
        raise ValueError(f"Could not strip suffix {suffix!r} from token: {token}")
    return stem


def head_matches_marker(token: str, expected_mark: str | None) -> bool:
    mark = expected_mark or ""
    if mark == "ca":
        return token.endswith("ca")
    if mark == "":
        return not token.endswith("ca") and not token.endswith("ge")
    raise ValueError(f"Unsupported finite marker: {mark!r}")


def parse_np_segment(
    tokens: List[str],
    start: int,
    np_wo: str,
    expected_head_mark: str | None,
) -> NpSpan:
    """
    Parse one generated ordinary NP.

    Supported GOOD shapes:
      simple: head
      GN:     poss-ge head(+case)
      NG:     head(+case) poss-ge

    The head marker is checked against the role expected in this grammar.
    """
    if len(tokens) == 1:
        if not head_matches_marker(tokens[0], expected_head_mark):
            raise ValueError(
                f"NP head marker mismatch at {start}: "
                f"expected {marker_value(expected_head_mark)}, got {tokens}"
            )
        return NpSpan(tokens=tokens, start=start, head_offset=0)

    if len(tokens) != 2:
        raise ValueError(f"Expected one- or two-token NP at {start}, got: {tokens}")

    if np_wo == "gn":
        if not tokens[0].endswith("ge"):
            raise ValueError(f"Expected GN possessor ending in ge at {start}: {tokens}")
        if not head_matches_marker(tokens[1], expected_head_mark):
            raise ValueError(
                f"GN head marker mismatch at {start + 1}: "
                f"expected {marker_value(expected_head_mark)}, got {tokens}"
            )
        return NpSpan(tokens=tokens, start=start, head_offset=1)

    if np_wo == "ng":
        if not tokens[1].endswith("ge"):
            raise ValueError(f"Expected NG possessor ending in ge at {start + 1}: {tokens}")
        if not head_matches_marker(tokens[0], expected_head_mark):
            raise ValueError(
                f"NG head marker mismatch at {start}: "
                f"expected {marker_value(expected_head_mark)}, got {tokens}"
            )
        return NpSpan(tokens=tokens, start=start, head_offset=0)

    raise ValueError(f"Unsupported np_wo: {np_wo}")


def parse_np_options(
    tokens: List[str],
    start: int,
    np_wo: str,
    expected_head_mark: str | None,
) -> List[NpSpan]:
    out: List[NpSpan] = []
    for length in (1, 2):
        if len(tokens) != length:
            continue
        try:
            out.append(parse_np_segment(tokens, start, np_wo, expected_head_mark))
        except ValueError:
            pass
    return out


def finite_verb_like(token: str) -> bool:
    return token.endswith("s") and not token.endswith("ge") and not token.endswith("ca")


def parse_transitive_good(
    tokens: List[str],
    clause_wo: str,
    np_wo: str,
    a_mark: str | None,
    p_mark: str | None,
) -> TransitiveParse:
    """
    Parse generated GOOD surface order without using source block ids.

    Expected clause shapes:
      SOV: A P V-s
      SVO: A V-s P
      VOS: V-s P A
    """
    parses: List[TransitiveParse] = []

    if clause_wo == "sov":
        if len(tokens) < 3:
            raise ValueError(f"Expected at least three tokens for SOV transitive: {tokens}")
        verb_index = len(tokens) - 1
        verb_token = tokens[verb_index]
        if not finite_verb_like(verb_token):
            raise ValueError(f"Expected finite verb at final SOV position: {tokens}")
        arg_tokens = tokens[:-1]
        for a_len in (1, 2):
            p_len = len(arg_tokens) - a_len
            if p_len not in (1, 2):
                continue
            a_opts = parse_np_options(arg_tokens[:a_len], 0, np_wo, a_mark)
            p_opts = parse_np_options(arg_tokens[a_len:], a_len, np_wo, p_mark)
            for a in a_opts:
                for p in p_opts:
                    parses.append(TransitiveParse(a=a, p=p, verb_token=verb_token, verb_index=verb_index))

    elif clause_wo == "svo":
        if len(tokens) < 3:
            raise ValueError(f"Expected at least three tokens for SVO transitive: {tokens}")
        for verb_index in range(1, len(tokens) - 1):
            verb_token = tokens[verb_index]
            if not finite_verb_like(verb_token):
                continue
            a_tokens = tokens[:verb_index]
            p_tokens = tokens[verb_index + 1 :]
            if len(a_tokens) not in (1, 2) or len(p_tokens) not in (1, 2):
                continue
            a_opts = parse_np_options(a_tokens, 0, np_wo, a_mark)
            p_opts = parse_np_options(p_tokens, verb_index + 1, np_wo, p_mark)
            for a in a_opts:
                for p in p_opts:
                    parses.append(TransitiveParse(a=a, p=p, verb_token=verb_token, verb_index=verb_index))

    elif clause_wo == "vos":
        if len(tokens) < 3:
            raise ValueError(f"Expected at least three tokens for VOS transitive: {tokens}")
        verb_index = 0
        verb_token = tokens[0]
        if not finite_verb_like(verb_token):
            raise ValueError(f"Expected finite verb at initial VOS position: {tokens}")
        arg_tokens = tokens[1:]
        for p_len in (1, 2):
            a_len = len(arg_tokens) - p_len
            if a_len not in (1, 2):
                continue
            p_opts = parse_np_options(arg_tokens[:p_len], 1, np_wo, p_mark)
            a_opts = parse_np_options(arg_tokens[p_len:], 1 + p_len, np_wo, a_mark)
            for a in a_opts:
                for p in p_opts:
                    parses.append(TransitiveParse(a=a, p=p, verb_token=verb_token, verb_index=verb_index))

    else:
        raise ValueError(f"Unsupported clause_wo: {clause_wo}")

    if len(parses) != 1:
        raise ValueError(f"Expected exactly one transitive parse, got {len(parses)} for: {tokens}")

    return parses[0]
