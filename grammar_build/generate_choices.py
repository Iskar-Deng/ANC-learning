#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
from itertools import product
from pathlib import Path
from typing import Dict, List, Tuple


CLAUSE_WOS = ["sov", "svo", "vos"]
NP_WOS = ["gn", "ng"]
ALIGNMENTS = ["nom-acc", "erg-abs"]
COMP_SYSTEMS = ["balancing", "deranking"]
ANC_STRATEGIES = ["sent", "poss-acc", "erg-poss", "nomn"]

ID_WIDTH = 2

ALIGNMENT_CODES = {
    "nom-acc": "ac",
    "erg-abs": "er",
}

COMP_SYSTEM_CODES = {
    "balancing": "b",
    "deranking": "d",
}

STRATEGY_CODES = {
    "sent": "se",
    "poss-acc": "pa",
    "erg-poss": "ep",
    "nomn": "no",
}


ANC_WO_TABLE = {
    ("sov", "gn"): {
        "sent": "sov",
        "poss-acc": "sov",
        "erg-poss": "sov",
        "nomn": "sov",
    },
    ("svo", "gn"): {
        "sent": "svo",
        "poss-acc": "svo",
        "erg-poss": "sov",
        "nomn": "svo",
    },
    ("vos", "gn"): {
        "sent": "vos",
        "poss-acc": "svo",
        "erg-poss": "sov",
        "nomn": "svo",
    },
    ("sov", "ng"): {
        "sent": "sov",
        "poss-acc": "ovs",
        "erg-poss": "vos",
        "nomn": "ovs",
    },
    ("svo", "ng"): {
        "sent": "svo",
        "poss-acc": "vos",
        "erg-poss": "vos",
        "nomn": "vos",
    },
    ("vos", "ng"): {
        "sent": "vos",
        "poss-acc": "vos",
        "erg-poss": "vos",
        "nomn": "vos",
    },
}


def iter_parameter_grid():
    return product(
        CLAUSE_WOS,
        NP_WOS,
        ALIGNMENTS,
        COMP_SYSTEMS,
        ANC_STRATEGIES,
    )


def get_grid_index(
    clause_wo: str,
    np_wo: str,
    alignment: str,
    comp_system: str,
    strategy: str,
) -> int:
    target = (clause_wo, np_wo, alignment, comp_system, strategy)

    for idx, combo in enumerate(iter_parameter_grid()):
        if combo == target:
            return idx

    raise ValueError(f"Combination not found in parameter grid: {target}")


def make_language_id(
    clause_wo: str,
    np_wo: str,
    alignment: str,
    comp_system: str,
    strategy: str,
) -> str:
    idx = get_grid_index(
        clause_wo=clause_wo,
        np_wo=np_wo,
        alignment=alignment,
        comp_system=comp_system,
        strategy=strategy,
    )

    return "_".join(
        [
            f"{idx:0{ID_WIDTH}d}",
            clause_wo,
            np_wo,
            ALIGNMENT_CODES[alignment],
            COMP_SYSTEM_CODES[comp_system],
            STRATEGY_CODES[strategy],
        ]
    )


def finite_p_case_value(alignment: str) -> str:
    """
    Return the finite-clause P case type used by Grammar Matrix choices.
    """
    if alignment == "nom-acc":
        return "acc"

    if alignment == "erg-abs":
        return "abs"

    raise ValueError(alignment)


def case_inventory(alignment: str) -> Dict[str, List]:
    if alignment == "nom-acc":
        return {
            "case_lines": [
                "case-marking=nom-acc",
                "nom-acc-nom-case-name=nominative",
                "nom-acc-acc-case-name=accusative",
            ],
            "case_lrts": [
                ("nominative", "case", "nom", "no"),
                ("accusative", "case", "acc", "ca"),
            ],
        }

    if alignment == "erg-abs":
        return {
            "case_lines": [
                "case-marking=erg-abs",
                "erg-abs-erg-case-name=ergative",
                "erg-abs-abs-case-name=absolutive",
            ],
            "case_lrts": [
                ("ergative", "case", "erg", "ca"),
                ("absolutive", "case", "abs", "no"),
            ],
        }

    raise ValueError(alignment)


def poss_order(np_wo: str) -> str:
    if np_wo == "gn":
        return "head-final"

    if np_wo == "ng":
        return "head-initial"

    raise ValueError(np_wo)


def comp_section(comp_system: str) -> str:
    comp_form = "finite" if comp_system == "balancing" else "nonfinite"

    return "\n".join(
        [
            "section=clausal-comp",
            "  comps1_clause-pos-same=on",
            "    comps1_feat1_name=form",
            f"    comps1_feat1_value={comp_form}",
        ]
    )


def verb_form_lrts(comp_system: str) -> List[str]:
    lines = [
        "  verb-pc1_name=finiteness",
        "  verb-pc1_obligatory=on",
        "  verb-pc1_order=suffix",
        "  verb-pc1_inputs=verb",
        "    verb-pc1_lrt1_name=finite",
        "      verb-pc1_lrt1_feat1_name=form",
        "      verb-pc1_lrt1_feat1_value=finite",
        "      verb-pc1_lrt1_feat1_head=verb",
        "      verb-pc1_lrt1_lri1_inflecting=yes",
        "      verb-pc1_lrt1_lri1_orth=s",
    ]

    if comp_system == "deranking":
        lines += [
            "    verb-pc1_lrt2_name=nonfinite",
            "      verb-pc1_lrt2_feat1_name=form",
            "      verb-pc1_lrt2_feat1_value=nonfinite",
            "      verb-pc1_lrt2_feat1_head=verb",
            "      verb-pc1_lrt2_lri1_inflecting=yes",
            "      verb-pc1_lrt2_lri1_orth=ing",
        ]

    return lines


def nominalclause_section(strategy: str, anc_wo: str) -> str:
    if strategy == "sent":
        return "\n".join(
            [
                "section=nominalclause",
                "  ns1_name=sent",
                "  ns1_nmz_type=sentential",
                "  ns1_nmzRel=yes",
                "  ns1_intrans=on",
                "  ns1_trans=on",
            ]
        )

    gm_type = {
        "poss-acc": "poss-acc",
        "erg-poss": "erg-poss",
        "nomn": "nominal",
    }[strategy]

    return "\n".join(
        [
            "section=nominalclause",
            f"  ns1_name={strategy}",
            f"  ns1_nmz_type={gm_type}",
            "  ns1_det=imp",
            "  ns1_intrans=on",
            "  ns1_trans=on",
            "same-word-order=no",
            f"nmz-clause-word-order={anc_wo}",
            "  nmz_poss_strat1_name=poss-strat1",
            "non_sent_sem=verb-only",
        ]
    )


def nominalization_lrt(strategy: str, alignment: str) -> List[str]:
    lines = [
        "  verb-pc2_name=nominalization",
        "  verb-pc2_order=suffix",
        # Only allow IV/TV lexical classes to undergo nominalization.
        # Do not include verb3/clausal_verb, otherwise CV verbs also receive NMZ
        # and create extra pseudo-English parses.
        "  verb-pc2_inputs=verb1, verb2",
        f"    verb-pc2_lrt1_name={strategy}-nmz",
        "      verb-pc2_lrt1_feat1_name=nominalization",
        f"      verb-pc2_lrt1_feat1_value={strategy}",
        "      verb-pc2_lrt1_feat1_head=verb",
    ]

    if strategy == "poss-acc":
        lines += [
            "      verb-pc2_lrt1_feat3_name=case",
            f"      verb-pc2_lrt1_feat3_value={finite_p_case_value(alignment)}",
            "      verb-pc2_lrt1_feat3_head=obj",
        ]

    elif strategy in {"erg-poss", "nomn"}:
        lines += [
            "      verb-pc2_lrt1_feat3_name=case",
            "      verb-pc2_lrt1_feat3_value=oblique",
            "      verb-pc2_lrt1_feat3_head=obj",
        ]

    lines += [
        "      verb-pc2_lrt1_lri1_inflecting=yes",
        "      verb-pc2_lrt1_lri1_orth=ing",
    ]

    return lines


def case_lrt_block(alignment: str, strategy: str) -> List[str]:
    info = case_inventory(alignment)
    lines = [
        "  noun-pc1_name=case",
        "  noun-pc1_obligatory=on",
        "  noun-pc1_order=suffix",
        "  noun-pc1_inputs=noun, verb-pc2",
    ]

    idx = 1
    for name, feat_name, feat_value, orth in info["case_lrts"]:
        lines += [
            f"    noun-pc1_lrt{idx}_name={name}",
            f"      noun-pc1_lrt{idx}_feat1_name={feat_name}",
            f"      noun-pc1_lrt{idx}_feat1_value={feat_value}",
            f"      noun-pc1_lrt{idx}_feat1_head=itself",
        ]

        if orth == "no":
            lines.append(f"      noun-pc1_lrt{idx}_lri1_inflecting=no")
        else:
            lines += [
                f"      noun-pc1_lrt{idx}_lri1_inflecting=yes",
                f"      noun-pc1_lrt{idx}_lri1_orth={orth}",
            ]

        idx += 1

    lines += [
        f"    noun-pc1_lrt{idx}_name=genitive",
        f"      noun-pc1_lrt{idx}_feat1_name=poss-strat1",
        f"      noun-pc1_lrt{idx}_feat1_value=possessor",
        f"      noun-pc1_lrt{idx}_feat1_head=itself",
        f"      noun-pc1_lrt{idx}_lri1_inflecting=yes",
        f"      noun-pc1_lrt{idx}_lri1_orth=ge",
    ]
    idx += 1

    if strategy in {"erg-poss", "nomn"}:
        lines += [
            f"    noun-pc1_lrt{idx}_name=oblique",
            f"      noun-pc1_lrt{idx}_feat1_name=case",
            f"      noun-pc1_lrt{idx}_feat1_value=oblique",
            f"      noun-pc1_lrt{idx}_feat1_head=itself",
            f"      noun-pc1_lrt{idx}_lri1_inflecting=yes",
            f"      noun-pc1_lrt{idx}_lri1_orth=ob",
        ]

    return lines


def lexicon_section(alignment: str) -> str:
    if alignment == "nom-acc":
        iv_valence = "nom"
        tv_valence = "nom-acc"
        cv_valence = "nom,comps1"
    else:
        iv_valence = "abs"
        tv_valence = "erg-abs"
        cv_valence = "erg,comps1"

    return f"""section=lexicon
  noun1_name=common_noun
  noun1_det=imp
    noun1_stem1_orth=n1
    noun1_stem1_pred=_n1_n_rel
    noun1_stem2_orth=n2
    noun1_stem2_pred=_n2_n_rel
    noun1_stem3_orth=n3
    noun1_stem3_pred=_n3_n_rel
  verb1_name=intran_verb
  verb1_valence={iv_valence}
    verb1_stem1_orth=iv1
    verb1_stem1_pred=_iv1_v_rel
    verb1_stem2_orth=iv2
    verb1_stem2_pred=_iv2_v_rel
  verb2_name=tran_verb
  verb2_valence={tv_valence}
    verb2_stem1_orth=tv1
    verb2_stem1_pred=_tv1_v_rel
    verb2_stem2_orth=tv2
    verb2_stem2_pred=_tv2_v_rel
  verb3_name=clausal_verb
  verb3_valence={cv_valence}
    verb3_stem1_orth=cv1
    verb3_stem1_pred=_cv1_v_rel
    verb3_stem2_orth=cv2
    verb3_stem2_pred=_cv2_v_rel"""


def generate_choices(
    language: str,
    clause_wo: str,
    np_wo: str,
    alignment: str,
    comp_system: str,
    strategy: str,
) -> str:
    anc_wo = ANC_WO_TABLE[(clause_wo, np_wo)][strategy]
    case_info = case_inventory(alignment)

    case_lines = case_info["case_lines"][:]
    if strategy in {"erg-poss", "nomn"}:
        case_lines.append("  case1_name=oblique")

    morphology_lines: List[str] = []
    morphology_lines += case_lrt_block(alignment, strategy)
    morphology_lines += verb_form_lrts(comp_system)
    morphology_lines += nominalization_lrt(strategy, alignment)

    return f"""version=35

section=general
language={language}
punctuation-chars=keep-all
archive=yes

section=word-order
word-order={clause_wo}
has-dets=no
has-aux=no
subord-word-order=same

section=number

section=person
person=none

section=gender

section=case
{chr(10).join(case_lines)}

section=adnom-poss
  poss-strat1_order={poss_order(np_wo)}
  poss-strat1_mod-spec=spec
  poss-strat1_mark-loc=possessor
  poss-strat1_possessor-type=affix
  poss-strat1_possessor-affix-agr=non-agree

section=direct-inverse

section=tense-aspect-mood

section=evidentials

section=other-features
form-fin-nf=on

section=sentential-negation

section=coordination

section=matrix-yes-no

section=wh-q

section=info-str

section=arg-opt

{nominalclause_section(strategy, anc_wo)}

section=lvc

{comp_section(comp_system)}

section=clausalmods

{lexicon_section(alignment)}

section=morphology
{chr(10).join(morphology_lines)}

section=toolbox-import

section=test-sentences

section=gen-options

section=ToolboxLexicon
"""


def make_manifest_row(
    language: str,
    choices_file: str,
    clause_wo: str,
    np_wo: str,
    alignment: str,
    comp_system: str,
    strategy: str,
) -> Dict[str, str]:
    idx = get_grid_index(
        clause_wo=clause_wo,
        np_wo=np_wo,
        alignment=alignment,
        comp_system=comp_system,
        strategy=strategy,
    )

    return {
        "id": f"{idx:0{ID_WIDTH}d}",
        "language": language,
        "choices_file": choices_file,
        "clause_wo": clause_wo,
        "np_wo": np_wo,
        "alignment": alignment,
        "alignment_code": ALIGNMENT_CODES[alignment],
        "comp_system": comp_system,
        "comp_system_code": COMP_SYSTEM_CODES[comp_system],
        "strategy": strategy,
        "strategy_code": STRATEGY_CODES[strategy],
        "anc_wo": ANC_WO_TABLE[(clause_wo, np_wo)][strategy],
    }


def write_manifest(rows: List[Dict[str, str]], path: Path) -> None:
    fieldnames = [
        "id",
        "language",
        "choices_file",
        "clause_wo",
        "np_wo",
        "alignment",
        "alignment_code",
        "comp_system",
        "comp_system_code",
        "strategy",
        "strategy_code",
        "anc_wo",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_one_choices(
    out_dir: Path,
    clause_wo: str,
    np_wo: str,
    alignment: str,
    comp_system: str,
    strategy: str,
) -> Tuple[str, str]:
    language = make_language_id(
        clause_wo=clause_wo,
        np_wo=np_wo,
        alignment=alignment,
        comp_system=comp_system,
        strategy=strategy,
    )

    text = generate_choices(
        language=language,
        clause_wo=clause_wo,
        np_wo=np_wo,
        alignment=alignment,
        comp_system=comp_system,
        strategy=strategy,
    )

    filename = f"{language}.choice"
    path = out_dir / filename
    path.write_text(text, encoding="utf-8")

    return language, filename


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Generate all 96 choices files.")
    parser.add_argument("--clause-wo", choices=CLAUSE_WOS)
    parser.add_argument("--np-wo", choices=NP_WOS)
    parser.add_argument("--alignment", choices=ALIGNMENTS)
    parser.add_argument("--comp-system", choices=COMP_SYSTEMS)
    parser.add_argument("--strategy", choices=ANC_STRATEGIES)
    parser.add_argument("--out-dir", default="choices")
    parser.add_argument("--manifest", default="manifest.tsv")

    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        rows: List[Dict[str, str]] = []

        for clause_wo, np_wo, alignment, comp_system, strategy in iter_parameter_grid():
            language, filename = write_one_choices(
                out_dir=out_dir,
                clause_wo=clause_wo,
                np_wo=np_wo,
                alignment=alignment,
                comp_system=comp_system,
                strategy=strategy,
            )

            rows.append(
                make_manifest_row(
                    language=language,
                    choices_file=filename,
                    clause_wo=clause_wo,
                    np_wo=np_wo,
                    alignment=alignment,
                    comp_system=comp_system,
                    strategy=strategy,
                )
            )

        manifest_path = out_dir / args.manifest
        write_manifest(rows, manifest_path)

        print(f"Wrote {len(rows)} choices files to {out_dir}")
        print(f"Wrote manifest: {manifest_path}")
        return

    missing = [
        name
        for name, value in {
            "--clause-wo": args.clause_wo,
            "--np-wo": args.np_wo,
            "--alignment": args.alignment,
            "--comp-system": args.comp_system,
            "--strategy": args.strategy,
        }.items()
        if value is None
    ]

    if missing:
        parser.error(
            "Default mode generates one choices file and requires: "
            + ", ".join(missing)
            + ". Use --all to generate all 96 choices files."
        )

    language, filename = write_one_choices(
        out_dir=out_dir,
        clause_wo=args.clause_wo,
        np_wo=args.np_wo,
        alignment=args.alignment,
        comp_system=args.comp_system,
        strategy=args.strategy,
    )

    print(f"Wrote: {out_dir / filename}")
    print(f"Language ID: {language}")


if __name__ == "__main__":
    main()