#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils import derive_language_config


MARKERS = ("ca", "ge", "ob")
JsonDict = Dict[str, Any]


def iter_jsonl(path: Path) -> Iterable[JsonDict]:
    with path.open(encoding="utf-8") as infile:
        for line_no, raw in enumerate(infile, start=1):
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no} is not an object")
            yield row


def strip_marker(token: str) -> Tuple[str, str]:
    lower = token.lower()
    for marker in MARKERS:
        if lower.endswith(marker) and len(token) > len(marker):
            return lower[: -len(marker)], marker
    return lower, ""


def is_anc_verb(token: str) -> bool:
    base, _ = strip_marker(token)
    return base.endswith("ing") and len(base) > 3


def token_matches_head(token: str, expected_head: str) -> bool:
    lower = token.lower()
    expected = expected_head.lower()
    if lower == expected:
        return True
    return any(lower == expected + marker for marker in MARKERS)


def pseudo_iv_head(pseudo_english: str) -> str | None:
    toks = pseudo_english.lower().split()
    for index, token in enumerate(toks):
        base, _ = strip_marker(token)
        if not base.endswith("nmz") or index == 0:
            continue
        head, marker = strip_marker(toks[index - 1])
        if marker == "ge":
            return head
    return None


def pseudo_tv_heads(pseudo_english: str) -> Tuple[str, str] | None:
    toks = pseudo_english.lower().split()
    for index, token in enumerate(toks):
        base, _ = strip_marker(token)
        if not base.endswith("nmz") or index == 0 or index + 1 >= len(toks):
            continue
        a_head, a_marker = strip_marker(toks[index - 1])
        p_head, p_marker = strip_marker(toks[index + 1])
        if a_marker == "ge" and p_marker == "ob":
            return a_head, p_head
    return None


def unique_index(tokens: List[str], predicate) -> int | None:
    matches = [i for i, tok in enumerate(tokens) if predicate(tok)]
    if len(matches) == 1:
        return matches[0]
    return None


def check_iv_row(row: JsonDict, expected_order: str) -> str:
    pseudo = str(row.get("pseudo_english", ""))
    head = pseudo_iv_head(pseudo)
    if head is None:
        return "skip:no_iv_anc"

    tokens = str(row["sent"]).split()
    v_idx = unique_index(tokens, is_anc_verb)
    s_idx = unique_index(tokens, lambda tok: token_matches_head(tok, head))
    if v_idx is None or s_idx is None:
        return "fail:missing_unique_s_or_v"

    actual = "SV" if s_idx < v_idx else "VS"
    return "ok" if actual == expected_order else f"fail:{actual}!={expected_order}"


def check_tv_row(row: JsonDict, expected_order: str) -> str:
    pseudo = str(row.get("pseudo_english", ""))
    heads = pseudo_tv_heads(pseudo)
    if heads is None:
        return "skip:no_tv_anc"

    a_head, p_head = heads
    tokens = str(row["sent"]).split()
    v_idx = unique_index(tokens, is_anc_verb)
    a_idx = unique_index(tokens, lambda tok: token_matches_head(tok, a_head))
    p_idx = unique_index(tokens, lambda tok: token_matches_head(tok, p_head))
    if v_idx is None or a_idx is None or p_idx is None:
        return "fail:missing_unique_a_v_or_p"

    actual = "".join(role for _, role in sorted([(a_idx, "A"), (v_idx, "V"), (p_idx, "P")]))
    return "ok" if actual == expected_order else f"fail:{actual}!={expected_order}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-dir", required=True)
    parser.add_argument("--kind", required=True, choices=["iv", "tv"])
    args = parser.parse_args()

    selected_dir = Path(args.selected_dir)
    files = sorted(selected_dir.glob("*.jsonl"))
    failures = []
    skipped = 0
    checked = 0

    for path in files:
        language = path.stem
        config = derive_language_config(language)
        expected = config["anc_iv_order"] if args.kind == "iv" else config["anc_tv_order"]

        for row in iter_jsonl(path):
            result = (
                check_iv_row(row, expected)
                if args.kind == "iv"
                else check_tv_row(row, expected)
            )
            if result == "ok":
                checked += 1
            elif result.startswith("skip:"):
                skipped += 1
            else:
                failures.append((language, row.get("id"), result, row.get("sent"), row.get("pseudo_english")))

    print(f"files: {len(files)}")
    print(f"checked: {checked}")
    print(f"skipped: {skipped}")
    print(f"failures: {len(failures)}")
    for failure in failures[:20]:
        print("\t".join(str(x) for x in failure))

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
