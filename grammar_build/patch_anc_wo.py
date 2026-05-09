#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Tuple


TARGET_RULES = [
    "trans-erg-poss-lex-rule",
    "trans-poss-acc-lex-rule",
    "trans-nominal-lex-rule",
]


def replace_rule_block(text: str, rule_name: str) -> Tuple[str, int]:
    """
    In the target rule block only, replace HEAD.ANC-WO + with HEAD.ANC-WO -.
    """
    pattern = re.compile(
        rf"({re.escape(rule_name)}\s*:=.*?\n\n)",
        flags=re.DOTALL,
    )

    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        block = match.group(1)

        new_block, n = re.subn(
            r"HEAD\.ANC-WO\s+\+",
            "HEAD.ANC-WO -",
            block,
        )

        count += n
        return new_block

    new_text = pattern.sub(repl, text)
    return new_text, count


def patch_anc_head_opt_comp_phrase(text: str) -> tuple[str, int]:
    """
    Relax anc-head-opt-comp-phrase by removing the SUBJ restriction and
    keeping a weak SPR requirement.
    """
    pattern = re.compile(
        r"(anc-head-opt-comp-phrase\s*:=.*?)"
        r"VAL\s*\[\s*SPR\s*<\s*>\s*,\s*SUBJ\s*<\s*>\s*\]",
        flags=re.DOTALL,
    )

    replacement = r"\1VAL.SPR < [ ] >"

    new_text, count = pattern.subn(replacement, text, count=1)
    return new_text, count


def patch_file(path: Path, dry_run: bool = False) -> None:
    text = path.read_text(encoding="utf-8")

    if "ANC-WO" not in text:
        print(f"[skip] no ANC-WO: {path}")
        return

    total_ancwo = 0
    new_text = text

    for rule in TARGET_RULES:
        new_text, n = replace_rule_block(new_text, rule)
        total_ancwo += n

    new_text, opt_comp_count = patch_anc_head_opt_comp_phrase(new_text)

    if total_ancwo > 0 and opt_comp_count == 0:
        print(
            f"[warn] ANC-WO rule patched, but anc-head-opt-comp-phrase "
            f"was not patched: {path}"
        )

    if new_text == text:
        print(f"[warn] ANC-WO found but no patch applied: {path}")
        return

    if dry_run:
        print(
            f"[dry-run] {path}: "
            f"ANC-WO replacements={total_ancwo}, "
            f"anc-head-opt-comp-phrase replacements={opt_comp_count}"
        )
        return

    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(text, encoding="utf-8")
    path.write_text(new_text, encoding="utf-8")

    print(
        f"[patched] {path}: "
        f"ANC-WO replacements={total_ancwo}, "
        f"anc-head-opt-comp-phrase replacements={opt_comp_count}, "
        f"backup={backup}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tdl",
        required=True,
        help="Path to the language .tdl file to patch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing.",
    )

    args = parser.parse_args()

    path = Path(args.tdl)
    if not path.exists():
        raise FileNotFoundError(path)

    patch_file(path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()