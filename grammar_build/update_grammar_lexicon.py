#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Update a Grammar Matrix lexicon from a generated lexicon JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


JsonDict = Dict[str, Any]


def load_json(path: Path) -> JsonDict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")

    return data


def get_str_list(data: JsonDict, key: str) -> List[str]:
    value = data.get(key, [])

    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(f"Key '{key}' must be a list, got {type(value).__name__}")

    out: List[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"Key '{key}' item {i} must be a string, got {type(item).__name__}"
            )
        out.append(item)

    return out


def dedupe_keep_order(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def tdl_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def make_noun_name(word: str) -> str:
    return f"{word}-n-lex"


def make_iv_name(word: str) -> str:
    return f"{word}-iv-lex"


def make_tv_name(word: str) -> str:
    return f"{word}-tv-lex"


def make_cv_name(word: str) -> str:
    return f"{word}-cv-lex"


def make_lexicon_tdl(
    data: JsonDict,
    default_comp_trigger: str = "that",
    with_trigger: bool = False,
) -> str:
    nouns = get_str_list(data, "nouns")
    iv_verbs = get_str_list(data, "iv_verbs")
    tv_verbs = get_str_list(data, "tv_verbs")
    cv_verbs = get_str_list(data, "cv_verbs")
    cop_n_verbs = get_str_list(data, "cop_n_verbs")

    # Treat copular-nominal predicates as transitive verbs in the current setup.
    tv_verbs = dedupe_keep_order(tv_verbs + cop_n_verbs)

    # Add complementizer lexical entries only when requested.
    comp_items = [default_comp_trigger] if with_trigger and default_comp_trigger else []

    parts: List[str] = []
    parts.append(';;; -*- Mode: TDL; Coding: utf-8 -*-\n\n')

    parts.append(";;; Nouns\n\n")
    for noun in nouns:
        name = make_noun_name(noun)
        escaped = tdl_escape(noun)
        parts.append(
            f'{name} := common_noun-noun-lex &\n'
            f'  [ STEM < "{escaped}" >,\n'
            f'    SYNSEM.LKEYS.KEYREL.PRED "_{escaped}_n_rel" ].\n\n'
        )

    parts.append(";;; Adjectives\n\n")

    parts.append(";;; Verbs\n\n")

    for verb in iv_verbs:
        name = make_iv_name(verb)
        escaped = tdl_escape(verb)
        parts.append(
            f'{name} := intran_verb-verb-lex &\n'
            f'  [ STEM < "{escaped}" >,\n'
            f'    SYNSEM.LKEYS.KEYREL.PRED "_{escaped}_v_rel" ].\n\n'
        )

    for verb in tv_verbs:
        name = make_tv_name(verb)
        escaped = tdl_escape(verb)
        parts.append(
            f'{name} := tran_verb-verb-lex &\n'
            f'  [ STEM < "{escaped}" >,\n'
            f'    SYNSEM.LKEYS.KEYREL.PRED "_{escaped}_v_rel" ].\n\n'
        )

    for verb in cv_verbs:
        name = make_cv_name(verb)
        escaped = tdl_escape(verb)
        parts.append(
            f'{name} := clausal_verb-verb-lex &\n'
            f'  [ STEM < "{escaped}" >,\n'
            f'    SYNSEM.LKEYS.KEYREL.PRED "_{escaped}_v_rel" ].\n\n'
        )

    parts.append(";;; Adverbs\n\n")

    parts.append(";;; Complementizers\n\n")
    for comp in comp_items:
        escaped = tdl_escape(comp)
        parts.append(
            f'{escaped} := comps1-complementizer-lex-item &\n'
            f'  [ STEM < "{escaped}" > ].\n\n'
        )

    return "".join(parts)


def make_trigger_mtr(data: JsonDict, default_trigger: str = "that") -> str:
    cv_verbs = get_str_list(data, "cv_verbs")

    parts: List[str] = []
    parts.append(';;; -*- Mode: TDL; Coding: utf-8 -*-\n\n')
    parts.append(";;; Semantically Empty Lexical Entries\n\n")

    escaped_trigger = tdl_escape(default_trigger)

    for verb in cv_verbs:
        escaped_verb = tdl_escape(verb)
        parts.append(
            f'{escaped_verb}-comp-trigger := generator_rule &\n'
            f'[ CONTEXT [ RELS <! [ PRED "_{escaped_verb}_v_rel",\n'
            f'                      ARG2 #h ] !> ],\n'
            f'  FLAGS.TRIGGER "{escaped_trigger}" ].\n\n'
        )

    return "".join(parts)


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexicon-json", required=True)
    parser.add_argument("--grammar-root", required=True)
    parser.add_argument("--default-comp-trigger", default="that")
    parser.add_argument(
        "--with-trigger",
        action="store_true",
        help=(
            "Add complementizer entries to lexicon.tdl and update trigger.mtr. "
            "By default, no complementizer or trigger rules are written."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    lexicon_json_path = Path(args.lexicon_json)
    grammar_root = Path(args.grammar_root)

    lexicon_tdl_path = grammar_root / "lexicon.tdl"
    trigger_mtr_path = grammar_root / "trigger.mtr"

    data = load_json(lexicon_json_path)

    lexicon_tdl = make_lexicon_tdl(
        data=data,
        default_comp_trigger=args.default_comp_trigger,
        with_trigger=args.with_trigger,
    )
    write_file(lexicon_tdl_path, lexicon_tdl)
    print(f"Wrote: {lexicon_tdl_path}")

    if args.with_trigger:
        trigger_mtr = make_trigger_mtr(data, args.default_comp_trigger)
        write_file(trigger_mtr_path, trigger_mtr)
        print(f"Wrote: {trigger_mtr_path}")

if __name__ == "__main__":
    main()