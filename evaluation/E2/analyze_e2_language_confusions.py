#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


LabelKey = Tuple[str, str]
ScopeKey = Tuple[str, str, str]
EdgeKey = Tuple[str, str, str, str]


LABEL_GROUPS = [
    "top_construction",
    "anc_bucket",
    "top_x_anc",
    "complexity_bucket",
    "construction_detail",
    "detail_x_anc",
]

META_FIELDS = [
    "id",
    "language",
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

PARAM_FIELDS = [
    "clause_wo",
    "np_wo",
    "alignment_code",
    "comp_system_code",
    "strategy_code",
    "anc_wo",
]

REPORT_SCOPES = [
    ("ALL", "ALL"),
    ("top_x_anc", "iv|none"),
    ("top_x_anc", "tv|arg"),
    ("top_x_anc", "iv|arg"),
    ("top_x_anc", "cv|bare"),
    ("complexity_bucket", "iv_plain"),
    ("complexity_bucket", "anc_bare"),
    ("complexity_bucket", "anc_overt_arg"),
    ("anc_bucket", "arg"),
]


def read_tsv(path: Path) -> Iterable[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


def write_tsv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def model_sort_key(model_id: str) -> Tuple[int, str]:
    prefix = model_id.split("_", 1)[0]
    return (int(prefix), model_id) if prefix.isdigit() else (10**9, model_id)


def load_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    return {row["language"]: row for row in read_tsv(path)}


def load_item_labels(path: Path, groups: List[str]) -> Dict[str, List[LabelKey]]:
    labels_by_id: Dict[str, List[LabelKey]] = {}
    for row in read_tsv(path):
        if row.get("eval_eligible") != "True":
            continue
        labels_by_id[row["pseudo_id"]] = [(group, row[group]) for group in groups]
    return labels_by_id


def meta_for(language: str, manifest: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    return manifest.get(language, {"id": language.split("_", 1)[0], "language": language})


def add_prefixed_meta(
    row: Dict[str, Any],
    prefix: str,
    language: str,
    manifest: Dict[str, Dict[str, str]],
) -> None:
    meta = meta_for(language, manifest)
    row[f"{prefix}_model_id"] = language
    for field in META_FIELDS:
        row[f"{prefix}_{field}"] = meta.get(field, "")


def parse_max_languages(value: str, source_model: str) -> List[str]:
    targets = [x.strip() for x in value.split(",") if x.strip()]
    return [target for target in targets if target != source_model]


def collect_confusions(
    pred_dir: Path,
    labels_by_id: Dict[str, List[LabelKey]],
) -> Tuple[
    Counter[ScopeKey],
    Counter[ScopeKey],
    Counter[ScopeKey],
    Counter[ScopeKey],
    Counter[EdgeKey],
    Dict[EdgeKey, float],
]:
    totals: Counter[ScopeKey] = Counter()
    corrects: Counter[ScopeKey] = Counter()
    errors: Counter[ScopeKey] = Counter()
    tie_size_sums: Counter[ScopeKey] = Counter()
    edge_raw: Counter[EdgeKey] = Counter()
    edge_frac: Dict[EdgeKey, float] = defaultdict(float)

    pred_paths = sorted(pred_dir.glob("*.predictions.tsv"), key=lambda p: model_sort_key(p.name))
    if not pred_paths:
        raise FileNotFoundError(f"No *.predictions.tsv files found in {pred_dir}")

    for pred_path in pred_paths:
        with pred_path.open("r", encoding="utf-8") as f:
            header = next(f, "").rstrip("\n").split("\t")
            try:
                idx_model = header.index("model_id")
                idx_id = header.index("id")
                idx_ok = header.index("correct_tie_ok")
                idx_max_languages = header.index("max_languages")
            except ValueError as e:
                raise ValueError(f"Unexpected prediction header in {pred_path}") from e

            for line_no, line in enumerate(f, start=2):
                parts = line.rstrip("\n").split("\t", len(header) - 1)
                if len(parts) <= idx_max_languages:
                    continue

                model_id = parts[idx_model]
                pseudo_id = parts[idx_id]
                row_labels = labels_by_id.get(pseudo_id)
                if not row_labels:
                    continue

                try:
                    ok = int(parts[idx_ok])
                except ValueError as e:
                    raise ValueError(
                        f"Invalid correct_tie_ok in {pred_path} line {line_no}: {parts[idx_ok]!r}"
                    ) from e

                scopes = [("ALL", "ALL")] + row_labels
                for group, label in scopes:
                    key = (model_id, group, label)
                    totals[key] += 1
                    corrects[key] += ok

                if ok:
                    continue

                targets = parse_max_languages(parts[idx_max_languages], model_id)
                if not targets:
                    continue
                frac = 1.0 / len(targets)

                for group, label in scopes:
                    source_key = (model_id, group, label)
                    errors[source_key] += 1
                    tie_size_sums[source_key] += len(targets)
                    for target in targets:
                        edge_key = (model_id, target, group, label)
                        edge_raw[edge_key] += 1
                        edge_frac[edge_key] += frac

    return totals, corrects, errors, tie_size_sums, edge_raw, edge_frac


def accuracy(correct: int, total: int) -> float | str:
    return correct / total if total else ""


def build_top_edge_rows(
    totals: Counter[ScopeKey],
    corrects: Counter[ScopeKey],
    errors: Counter[ScopeKey],
    edge_raw: Counter[EdgeKey],
    edge_frac: Dict[EdgeKey, float],
    manifest: Dict[str, Dict[str, str]],
    top_n: int,
) -> List[Dict[str, Any]]:
    by_source_scope: Dict[ScopeKey, List[Tuple[str, int, float]]] = defaultdict(list)
    for (source, target, group, label), raw in edge_raw.items():
        by_source_scope[(source, group, label)].append(
            (target, raw, edge_frac[(source, target, group, label)])
        )

    rows: List[Dict[str, Any]] = []
    for (source, group, label), target_rows in sorted(
        by_source_scope.items(),
        key=lambda x: (model_sort_key(x[0][0]), x[0][1], x[0][2]),
    ):
        source_total = totals[(source, group, label)]
        source_correct = corrects[(source, group, label)]
        source_errors = errors[(source, group, label)]
        target_rows.sort(key=lambda x: (-x[2], -x[1], model_sort_key(x[0])))

        for rank, (target, raw, frac) in enumerate(target_rows[:top_n], start=1):
            row: Dict[str, Any] = {
                "group": group,
                "label": label,
                "target_rank": rank,
                "source_n_items": source_total,
                "source_error_items": source_errors,
                "source_accuracy_tie_ok": accuracy(source_correct, source_total),
                "raw_top_count": raw,
                "fractional_top_count": frac,
                "target_share_of_error_mass": frac / source_errors if source_errors else "",
            }
            add_prefixed_meta(row, "source", source, manifest)
            add_prefixed_meta(row, "target", target, manifest)

            matches = 0
            for param in PARAM_FIELDS:
                same = meta_for(source, manifest).get(param, "") == meta_for(target, manifest).get(param, "")
                row[f"same_{param}"] = str(same)
                matches += int(same)
            row["n_matching_params"] = matches
            rows.append(row)

    return rows


def build_source_summary_rows(
    totals: Counter[ScopeKey],
    corrects: Counter[ScopeKey],
    errors: Counter[ScopeKey],
    tie_size_sums: Counter[ScopeKey],
    edge_frac: Dict[EdgeKey, float],
    manifest: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    by_source_scope: Dict[ScopeKey, List[Tuple[str, float]]] = defaultdict(list)
    for source, target, group, label in edge_frac:
        by_source_scope[(source, group, label)].append((target, edge_frac[(source, target, group, label)]))

    rows: List[Dict[str, Any]] = []
    for source, group, label in sorted(
        totals,
        key=lambda x: (model_sort_key(x[0]), x[1], x[2]),
    ):
        total = totals[(source, group, label)]
        correct = corrects[(source, group, label)]
        err = errors[(source, group, label)]
        row: Dict[str, Any] = {
            "group": group,
            "label": label,
            "n_items": total,
            "error_items": err,
            "accuracy_tie_ok": accuracy(correct, total),
            "mean_n_top_languages_on_errors": tie_size_sums[(source, group, label)] / err if err else "",
        }
        add_prefixed_meta(row, "source", source, manifest)

        target_rows = by_source_scope.get((source, group, label), [])
        target_rows.sort(key=lambda x: (-x[1], model_sort_key(x[0])))
        if target_rows:
            top_target, top_mass = target_rows[0]
            row["top_target_model_id"] = top_target
            row["top_target_fractional_count"] = top_mass
            row["top_target_share_of_error_mass"] = top_mass / err if err else ""

        source_meta = meta_for(source, manifest)
        for param in PARAM_FIELDS:
            same_mass = 0.0
            value_mass: Dict[str, float] = defaultdict(float)
            for target, mass in target_rows:
                target_value = meta_for(target, manifest).get(param, "")
                value_mass[target_value] += mass
                if target_value == source_meta.get(param, ""):
                    same_mass += mass
            row[f"same_{param}_mass_share"] = same_mass / err if err else ""
            if value_mass:
                top_value, top_value_mass = sorted(value_mass.items(), key=lambda x: (-x[1], x[0]))[0]
                row[f"top_target_{param}"] = top_value
                row[f"top_target_{param}_share"] = top_value_mass / err if err else ""
        rows.append(row)

    return rows


def build_parameter_mass_rows(
    errors: Counter[ScopeKey],
    edge_frac: Dict[EdgeKey, float],
    manifest: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    source_param_mass: Dict[Tuple[str, str, str, str, str], float] = defaultdict(float)
    type_param_mass: Dict[Tuple[str, str, str, str, str], float] = defaultdict(float)
    type_param_den: Dict[Tuple[str, str, str, str], float] = defaultdict(float)

    for (source, target, group, label), mass in edge_frac.items():
        source_meta = meta_for(source, manifest)
        target_meta = meta_for(target, manifest)
        for param in PARAM_FIELDS:
            source_value = source_meta.get(param, "")
            target_value = target_meta.get(param, "")
            source_param_mass[(source, group, label, param, target_value)] += mass
            type_param_mass[(group, label, param, source_value, target_value)] += mass
            type_param_den[(group, label, param, source_value)] += mass

    source_rows: List[Dict[str, Any]] = []
    for source, group, label, param, target_value in sorted(
        source_param_mass,
        key=lambda x: (model_sort_key(x[0]), x[1], x[2], x[3], x[4]),
    ):
        err = errors[(source, group, label)]
        row: Dict[str, Any] = {
            "group": group,
            "label": label,
            "param": param,
            "source_param_value": meta_for(source, manifest).get(param, ""),
            "target_param_value": target_value,
            "fractional_error_mass": source_param_mass[(source, group, label, param, target_value)],
            "share_of_source_error_mass": source_param_mass[(source, group, label, param, target_value)] / err
            if err
            else "",
        }
        add_prefixed_meta(row, "source", source, manifest)
        source_rows.append(row)

    type_rows: List[Dict[str, Any]] = []
    for group, label, param, source_value, target_value in sorted(type_param_mass):
        den = type_param_den[(group, label, param, source_value)]
        type_rows.append(
            {
                "group": group,
                "label": label,
                "param": param,
                "source_param_value": source_value,
                "target_param_value": target_value,
                "fractional_error_mass": type_param_mass[(group, label, param, source_value, target_value)],
                "share_within_source_param_value": type_param_mass[
                    (group, label, param, source_value, target_value)
                ]
                / den
                if den
                else "",
            }
        )

    return source_rows, type_rows


def write_quick_report(
    path: Path,
    type_param_rows: List[Dict[str, Any]],
    source_summary_rows: List[Dict[str, Any]],
) -> None:
    by_key: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in type_param_rows:
        by_key[(row["group"], row["label"], row["param"], row["source_param_value"])].append(row)

    with path.open("w", encoding="utf-8") as f:
        f.write("[type-level target distributions]\n")
        for group, label in REPORT_SCOPES:
            f.write(f"\n[{group}={label}]\n")
            for param in ["clause_wo", "alignment_code", "strategy_code", "anc_wo"]:
                source_values = sorted(
                    {
                        key[3]
                        for key in by_key
                        if key[0] == group and key[1] == label and key[2] == param
                    }
                )
                for source_value in source_values:
                    rows = by_key[(group, label, param, source_value)]
                    rows.sort(key=lambda r: (-float(r["share_within_source_param_value"]), r["target_param_value"]))
                    parts = [
                        f"{r['target_param_value']}={float(r['share_within_source_param_value']):.3f}"
                        for r in rows[:4]
                    ]
                    f.write(f"{param}:{source_value} -> {', '.join(parts)}\n")

        f.write("\n[top source-language attractions, overall]\n")
        overall = [r for r in source_summary_rows if r["group"] == "ALL" and r["label"] == "ALL"]
        overall.sort(key=lambda r: (-float(r["top_target_share_of_error_mass"] or 0), model_sort_key(r["source_model_id"])))
        for row in overall[:20]:
            f.write(
                f"{row['source_model_id']}\tacc={float(row['accuracy_tie_ok']):.4f}\t"
                f"errors={row['error_items']}\ttop={row.get('top_target_model_id', '')}\t"
                f"share={float(row.get('top_target_share_of_error_mass') or 0):.3f}\n"
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--item-labels",
        default="evaluation/E2/generated/item_classification/top_anc_detail/item_top_anc_labels.tsv",
    )
    ap.add_argument("--pred-dir", default="results/e2_real_grammar_preference/all_models_bos_eos")
    ap.add_argument("--manifest", default="choices/manifest.tsv")
    ap.add_argument("--out-dir", default="evaluation/E2/generated/item_classification/language_confusions")
    ap.add_argument("--top-targets-per-source-scope", type=int, default=10)
    args = ap.parse_args()

    manifest = load_manifest(Path(args.manifest))
    labels_by_id = load_item_labels(Path(args.item_labels), LABEL_GROUPS)
    totals, corrects, errors, tie_size_sums, edge_raw, edge_frac = collect_confusions(
        Path(args.pred_dir),
        labels_by_id,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    top_edge_rows = build_top_edge_rows(
        totals,
        corrects,
        errors,
        edge_raw,
        edge_frac,
        manifest,
        args.top_targets_per_source_scope,
    )
    source_summary_rows = build_source_summary_rows(
        totals,
        corrects,
        errors,
        tie_size_sums,
        edge_frac,
        manifest,
    )
    source_param_rows, type_param_rows = build_parameter_mass_rows(errors, edge_frac, manifest)

    source_meta_fields = [f"source_{field}" for field in ["model_id"] + META_FIELDS]
    target_meta_fields = [f"target_{field}" for field in ["model_id"] + META_FIELDS]
    match_fields = [f"same_{param}" for param in PARAM_FIELDS] + ["n_matching_params"]

    write_tsv(
        out_dir / "language_confusion_top_targets.tsv",
        top_edge_rows,
        [
            "group",
            "label",
            "target_rank",
            *source_meta_fields,
            *target_meta_fields,
            "source_n_items",
            "source_error_items",
            "source_accuracy_tie_ok",
            "raw_top_count",
            "fractional_top_count",
            "target_share_of_error_mass",
            *match_fields,
        ],
    )
    write_tsv(
        out_dir / "language_confusion_source_summary.tsv",
        source_summary_rows,
        [
            "group",
            "label",
            *source_meta_fields,
            "n_items",
            "error_items",
            "accuracy_tie_ok",
            "mean_n_top_languages_on_errors",
            "top_target_model_id",
            "top_target_fractional_count",
            "top_target_share_of_error_mass",
            *[f"same_{param}_mass_share" for param in PARAM_FIELDS],
            *[f"top_target_{param}" for param in PARAM_FIELDS],
            *[f"top_target_{param}_share" for param in PARAM_FIELDS],
        ],
    )
    write_tsv(
        out_dir / "language_confusion_source_parameter_mass.tsv",
        source_param_rows,
        [
            "group",
            "label",
            *source_meta_fields,
            "param",
            "source_param_value",
            "target_param_value",
            "fractional_error_mass",
            "share_of_source_error_mass",
        ],
    )
    write_tsv(
        out_dir / "language_confusion_type_parameter_mass.tsv",
        type_param_rows,
        [
            "group",
            "label",
            "param",
            "source_param_value",
            "target_param_value",
            "fractional_error_mass",
            "share_within_source_param_value",
        ],
    )
    write_quick_report(out_dir / "quick_report.txt", type_param_rows, source_summary_rows)

    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "language_confusion_top_targets": str(out_dir / "language_confusion_top_targets.tsv"),
                "language_confusion_source_summary": str(out_dir / "language_confusion_source_summary.tsv"),
                "language_confusion_source_parameter_mass": str(out_dir / "language_confusion_source_parameter_mass.tsv"),
                "language_confusion_type_parameter_mass": str(out_dir / "language_confusion_type_parameter_mass.tsv"),
                "quick_report": str(out_dir / "quick_report.txt"),
                "source_scopes": len(totals),
                "edge_keys": len(edge_raw),
                "total_error_items_all_models": sum(
                    v for (source, group, label), v in errors.items() if group == "ALL" and label == "ALL"
                ),
                "top_targets_per_source_scope": args.top_targets_per_source_scope,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
