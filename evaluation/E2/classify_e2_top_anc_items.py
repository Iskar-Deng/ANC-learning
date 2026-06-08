#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


JsonDict = Dict[str, Any]
LabelKey = Tuple[str, str]


def iter_jsonl(path: Path) -> Iterator[JsonDict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {path} line {line_no}: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"Line {line_no} in {path} is not a JSON object")
            yield obj


def load_common_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            x = line.strip()
            if x:
                ids.add(x)
    return ids


def walk_clauses(rec: JsonDict) -> Iterator[JsonDict]:
    cur: Optional[JsonDict] = rec
    while isinstance(cur, dict):
        yield cur
        nxt = cur.get("complement")
        cur = nxt if isinstance(nxt, dict) else None


def cv_depth(rec: JsonDict) -> int:
    depth = 0
    cur = rec.get("complement")
    while isinstance(cur, dict):
        depth += 1
        cur = cur.get("complement")
    return depth


def top_object_type(rec: JsonDict) -> str:
    return (rec.get("object_info") or {}).get("object_type") or "none"


def pp_particle_profile(rec: JsonDict) -> str:
    has_pp = False
    has_particle = False
    for clause in walk_clauses(rec):
        obj = clause.get("object_info") or {}
        if obj.get("object_type") == "pp_obj":
            has_pp = True
        if obj.get("particle"):
            has_particle = True

    if has_pp and has_particle:
        return "pp+particle"
    if has_pp:
        return "pp"
    if has_particle:
        return "particle"
    return "plain"


def construction_detail(rec: JsonDict) -> str:
    """
    Detail inside top_construction, independent of ANC.

    The outer classification should be top_construction x anc_bucket. This
    detail label is only for looking inside each top-level construction.
    """
    construction = rec.get("construction") or "unknown"
    profile = pp_particle_profile(rec)

    if construction == "iv":
        if profile == "plain":
            return "iv_plain"
        return f"iv_{profile}"

    if construction == "tv":
        obj_type = top_object_type(rec)
        if profile != "plain":
            return f"tv_{profile}"
        if obj_type == "direct_obj":
            return "tv_plain_obj"
        if obj_type == "pp_obj":
            return "tv_pp_obj"
        if obj_type == "indirect_obj":
            return "tv_indirect_obj"
        return f"tv_{obj_type}"

    if construction == "cv":
        return "cv_depth2plus" if cv_depth(rec) >= 2 else "cv_depth1"

    if construction == "cop_n":
        return "cop_n"

    return "other"


def complexity_bucket(rec: JsonDict, anc: str) -> str:
    """
    Main high-level bucket for E2 reporting.

    ANC overrides the clause-level categories. For example, a transitive item
    with overt-argument ANC is `anc_overt_arg`, not `tv_plain_obj`.
    """
    if anc == "bare":
        return "anc_bare"
    if anc == "arg":
        return "anc_overt_arg"

    construction = rec.get("construction") or "unknown"
    profile = pp_particle_profile(rec)

    if profile != "plain":
        return "pp_or_particle"
    if construction == "tv":
        return "tv_plain_obj"
    if construction == "iv":
        return "iv_plain"
    if construction == "cop_n":
        return "cop_n"
    if construction == "cv":
        return "cv_depth2plus" if cv_depth(rec) >= 2 else "cv_depth1"
    return "other"


def anc_subtype(pseudo_english: str) -> str:
    """
    Detect ANC subtype using local adjacency around nmz tokens.

    This avoids false positives from unrelated whole-sentence tokens ending in
    ge/ob, such as "message" or "bob".
    """
    tokens = pseudo_english.lower().split()
    nmz_idxs = [i for i, tok in enumerate(tokens) if "nmz" in tok]
    if not nmz_idxs:
        return "none"

    has_ge = any(i > 0 and tokens[i - 1].endswith("ge") for i in nmz_idxs)
    has_ob = any(i + 1 < len(tokens) and tokens[i + 1].endswith("ob") for i in nmz_idxs)

    if has_ge and has_ob:
        return "ge_ob"
    if has_ge:
        return "ge_only"
    if has_ob:
        return "ob_only"
    return "bare"


def anc_bucket(subtype: str) -> str:
    if subtype == "none":
        return "none"
    if subtype == "bare":
        return "bare"
    return "arg"


def write_tsv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def sort_id(x: str) -> tuple[int, Any]:
    try:
        return (0, int(x))
    except ValueError:
        return (1, x)


def write_id_file(path: Path, ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row_id in sorted(set(ids), key=sort_id):
            f.write(f"{row_id}\n")


def write_classified_id_sets(out_dir: Path, item_rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Write E2-evaluable id sets from the same local ANC classification used by
    item labels. This replaces the old pseudo-string nmz sweep.
    """
    eligible = [row for row in item_rows if row["eval_eligible"] == "True"]

    id_sets = {
        "anc_ids": [
            row["pseudo_id"] for row in eligible
            if row["anc_bucket"] != "none"
        ],
        "anc_bare_ids": [
            row["pseudo_id"] for row in eligible
            if row["anc_bucket"] == "bare"
        ],
        "anc_arg_ids": [
            row["pseudo_id"] for row in eligible
            if row["anc_bucket"] == "arg"
        ],
        "anc_ge_only_ids": [
            row["pseudo_id"] for row in eligible
            if row["anc_subtype"] == "ge_only"
        ],
        "anc_ob_only_ids": [
            row["pseudo_id"] for row in eligible
            if row["anc_subtype"] == "ob_only"
        ],
        "anc_ge_ob_ids": [
            row["pseudo_id"] for row in eligible
            if row["anc_subtype"] == "ge_ob"
        ],
    }

    paths: Dict[str, str] = {}
    for name, ids in id_sets.items():
        path = out_dir / f"{name}.txt"
        write_id_file(path, ids)
        paths[name] = str(path)
    return paths


def build_item_rows(
    extract_path: Path,
    pseudo_path: Path,
    common_ids: set[str],
) -> List[Dict[str, Any]]:
    pseudo_rows = list(iter_jsonl(pseudo_path))
    rows: List[Dict[str, Any]] = []
    keep_i = 0
    sentence_mismatches = 0

    for rec in iter_jsonl(extract_path):
        if rec.get("status") != "keep":
            continue

        keep_i += 1
        try:
            pseudo = pseudo_rows[keep_i - 1]
        except IndexError as e:
            raise RuntimeError(
                f"More keep rows in {extract_path} than pseudo rows in {pseudo_path}"
            ) from e

        if rec.get("sentence") != pseudo.get("sentence"):
            sentence_mismatches += 1

        pseudo_id = str(pseudo.get("id"))
        top = rec.get("construction") or "unknown"
        subtype = anc_subtype(str(pseudo.get("pseudo_english") or ""))
        anc = anc_bucket(subtype)
        detail = construction_detail(rec)
        complexity = complexity_bucket(rec, anc)

        rows.append(
            {
                "pseudo_id": pseudo_id,
                "extract_id": rec.get("id"),
                "eval_eligible": str(pseudo_id in common_ids),
                "top_construction": top,
                "anc_bucket": anc,
                "anc_subtype": subtype,
                "top_x_anc": f"{top}|{anc}",
                "top_x_anc_subtype": f"{top}|{subtype}",
                "construction_detail": detail,
                "detail_x_anc": f"{detail}|{anc}",
                "detail_x_anc_subtype": f"{detail}|{subtype}",
                "complexity_bucket": complexity,
                "top_object_type": top_object_type(rec),
                "cv_depth": cv_depth(rec),
                "pp_particle_profile": pp_particle_profile(rec),
                "sentence": pseudo.get("sentence"),
                "pseudo_english": pseudo.get("pseudo_english"),
            }
        )

    if keep_i != len(pseudo_rows) or sentence_mismatches:
        raise RuntimeError(
            "Extract/pseudo alignment failed: "
            f"keep_rows={keep_i}, pseudo_rows={len(pseudo_rows)}, "
            f"sentence_mismatches={sentence_mismatches}"
        )

    return rows


def collect_prediction_stats(
    pred_dir: Path,
    labels_by_id: Dict[str, List[LabelKey]],
) -> Dict[LabelKey, Tuple[int, int]]:
    totals: Counter[LabelKey] = Counter()
    corrects: Counter[LabelKey] = Counter()

    pred_files = sorted(pred_dir.glob("*.predictions.tsv"))
    if not pred_files:
        return {}

    for pred_path in pred_files:
        with pred_path.open("r", encoding="utf-8") as f:
            next(f)
            for line in f:
                parts = line.split("\t", 8)
                if len(parts) < 7:
                    continue
                row_labels = labels_by_id.get(parts[1])
                if not row_labels:
                    continue
                ok = int(parts[6])
                for key in row_labels:
                    totals[key] += 1
                    corrects[key] += ok

    return {key: (totals[key], corrects[key]) for key in totals}


def summarize_counts(
    item_rows: List[Dict[str, Any]],
    prediction_stats: Dict[LabelKey, Tuple[int, int]],
) -> List[Dict[str, Any]]:
    groups = [
        "top_construction",
        "anc_bucket",
        "anc_subtype",
        "top_x_anc",
        "top_x_anc_subtype",
        "complexity_bucket",
        "construction_detail",
        "detail_x_anc",
        "detail_x_anc_subtype",
    ]

    all_counts: Counter[LabelKey] = Counter()
    eval_counts: Counter[LabelKey] = Counter()

    for row in item_rows:
        for group in groups:
            key = (group, str(row[group]))
            all_counts[key] += 1
            if row["eval_eligible"] == "True":
                eval_counts[key] += 1

    n_all = len(item_rows)
    n_eval = sum(1 for row in item_rows if row["eval_eligible"] == "True")

    out_rows: List[Dict[str, Any]] = []
    for key, all_n in sorted(all_counts.items(), key=lambda x: (x[0][0], -x[1], x[0][1])):
        group, label = key
        eval_n = eval_counts[key]
        pairs, correct = prediction_stats.get(key, (0, 0))
        out_rows.append(
            {
                "group": group,
                "label": label,
                "all_items": all_n,
                "all_pct": all_n / n_all if n_all else "",
                "evaluable_items": eval_n,
                "evaluable_pct": eval_n / n_eval if n_eval else "",
                "model_item_pairs": pairs,
                "accuracy_tie_ok": correct / pairs if pairs else "",
            }
        )

    return out_rows


def write_quick_report(path: Path, summary_rows: List[Dict[str, Any]]) -> None:
    report_groups = [
        "top_construction",
        "anc_bucket",
        "anc_subtype",
        "top_x_anc",
        "complexity_bucket",
        "construction_detail",
        "detail_x_anc",
    ]

    with path.open("w", encoding="utf-8") as f:
        for group in report_groups:
            f.write(f"\n[{group}]\n")
            rows = [r for r in summary_rows if r["group"] == group]
            rows.sort(key=lambda r: (-int(r["evaluable_items"]), str(r["label"])))
            for row in rows:
                acc = row["accuracy_tie_ok"]
                acc_str = f"{acc:.4f}" if isinstance(acc, float) else ""
                f.write(
                    f"{row['label']}\t"
                    f"all={row['all_items']} ({row['all_pct']:.2%})\t"
                    f"eval={row['evaluable_items']} ({row['evaluable_pct']:.2%})\t"
                    f"acc={acc_str}\n"
                )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", default="data/test/test_extract.jsonl")
    ap.add_argument("--pseudo", default="data/test/test_pseudo.jsonl")
    ap.add_argument("--common-ids", default="evaluation/E2/generated/selected_coverage/test/common_ids.txt")
    ap.add_argument("--pred-dir", default="results/e2_real_grammar_preference/all_models_bos_eos")
    ap.add_argument("--out-dir", default="evaluation/E2/generated/item_classification/top_anc_detail")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    common_ids = load_common_ids(Path(args.common_ids))
    item_rows = build_item_rows(Path(args.extract), Path(args.pseudo), common_ids)

    label_groups = [
        "top_construction",
        "anc_bucket",
        "anc_subtype",
        "top_x_anc",
        "top_x_anc_subtype",
        "complexity_bucket",
        "construction_detail",
        "detail_x_anc",
        "detail_x_anc_subtype",
    ]
    labels_by_id: Dict[str, List[LabelKey]] = {}
    for row in item_rows:
        if row["eval_eligible"] != "True":
            continue
        labels_by_id[str(row["pseudo_id"])] = [
            (group, str(row[group])) for group in label_groups
        ]

    prediction_stats = collect_prediction_stats(Path(args.pred_dir), labels_by_id)
    summary_rows = summarize_counts(item_rows, prediction_stats)

    item_fields = [
        "pseudo_id",
        "extract_id",
        "eval_eligible",
        "top_construction",
        "anc_bucket",
        "anc_subtype",
        "top_x_anc",
        "top_x_anc_subtype",
        "complexity_bucket",
        "construction_detail",
        "detail_x_anc",
        "detail_x_anc_subtype",
        "top_object_type",
        "cv_depth",
        "pp_particle_profile",
        "sentence",
        "pseudo_english",
    ]
    summary_fields = [
        "group",
        "label",
        "all_items",
        "all_pct",
        "evaluable_items",
        "evaluable_pct",
        "model_item_pairs",
        "accuracy_tie_ok",
    ]

    write_tsv(out_dir / "item_top_anc_labels.tsv", item_rows, item_fields)
    write_tsv(out_dir / "top_anc_summary.tsv", summary_rows, summary_fields)
    write_quick_report(out_dir / "quick_report.txt", summary_rows)
    id_set_paths = write_classified_id_sets(out_dir, item_rows)

    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "item_labels": str(out_dir / "item_top_anc_labels.tsv"),
                "summary": str(out_dir / "top_anc_summary.tsv"),
                "quick_report": str(out_dir / "quick_report.txt"),
                "id_sets": id_set_paths,
                "items": len(item_rows),
                "evaluable_items": sum(1 for row in item_rows if row["eval_eligible"] == "True"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
