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
ModelLabelKey = Tuple[str, str, str]


LABEL_GROUPS = [
    "top_construction",
    "anc_bucket",
    "top_x_anc",
    "complexity_bucket",
    "construction_detail",
    "detail_x_anc",
]

FOCUS_LABELS: List[LabelKey] = [
    ("top_x_anc", "iv|none"),
    ("top_x_anc", "tv|arg"),
    ("top_x_anc", "iv|arg"),
    ("top_x_anc", "cv|bare"),
    ("anc_bucket", "none"),
    ("anc_bucket", "bare"),
    ("anc_bucket", "arg"),
    ("complexity_bucket", "iv_plain"),
    ("complexity_bucket", "anc_bare"),
    ("complexity_bucket", "anc_overt_arg"),
    ("top_construction", "tv"),
    ("top_construction", "iv"),
    ("top_construction", "cv"),
    ("top_construction", "cop_n"),
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


def load_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    rows = {row["language"]: row for row in read_tsv(path)}
    return rows


def load_item_labels(path: Path, groups: List[str]) -> Dict[str, List[LabelKey]]:
    labels_by_id: Dict[str, List[LabelKey]] = {}
    for row in read_tsv(path):
        if row.get("eval_eligible") != "True":
            continue
        pseudo_id = row["pseudo_id"]
        labels_by_id[pseudo_id] = [(group, row[group]) for group in groups]
    return labels_by_id


def model_sort_key(model_id: str) -> Tuple[int, str]:
    prefix = model_id.split("_", 1)[0]
    return (int(prefix), model_id) if prefix.isdigit() else (10**9, model_id)


def meta_for(model_id: str, manifest: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    row = manifest.get(model_id)
    if row is None:
        return {"id": model_id.split("_", 1)[0], "language": model_id}
    return row


def add_meta(row: Dict[str, Any], model_id: str, manifest: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    meta = meta_for(model_id, manifest)
    out = {"model_id": model_id}
    for field in META_FIELDS:
        out[field] = meta.get(field, "")
    out.update(row)
    return out


def collect_model_stats(
    pred_dir: Path,
    labels_by_id: Dict[str, List[LabelKey]],
) -> Tuple[Counter[ModelLabelKey], Counter[ModelLabelKey], Counter[str], Counter[str]]:
    totals: Counter[ModelLabelKey] = Counter()
    corrects: Counter[ModelLabelKey] = Counter()
    model_totals: Counter[str] = Counter()
    model_corrects: Counter[str] = Counter()

    pred_paths = sorted(pred_dir.glob("*.predictions.tsv"), key=lambda p: model_sort_key(p.name))
    if not pred_paths:
        raise FileNotFoundError(f"No *.predictions.tsv files found in {pred_dir}")

    for pred_path in pred_paths:
        with pred_path.open("r", encoding="utf-8") as f:
            header = next(f, "")
            if not header.startswith("model_id\tid\t"):
                raise ValueError(f"Unexpected prediction header in {pred_path}: {header.strip()}")
            for line_no, line in enumerate(f, start=2):
                parts = line.rstrip("\n").split("\t", 7)
                if len(parts) < 7:
                    continue
                model_id, pseudo_id = parts[0], parts[1]
                row_labels = labels_by_id.get(pseudo_id)
                if not row_labels:
                    continue
                try:
                    ok = int(parts[6])
                except ValueError as e:
                    raise ValueError(
                        f"Invalid correct_tie_ok in {pred_path} line {line_no}: {parts[6]!r}"
                    ) from e

                model_totals[model_id] += 1
                model_corrects[model_id] += ok
                for group, label in row_labels:
                    key = (model_id, group, label)
                    totals[key] += 1
                    corrects[key] += ok

    return totals, corrects, model_totals, model_corrects


def accuracy(correct: int, total: int) -> float | str:
    return correct / total if total else ""


def build_accuracy_rows(
    totals: Counter[ModelLabelKey],
    corrects: Counter[ModelLabelKey],
    manifest: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for model_id, group, label in sorted(
        totals,
        key=lambda k: (model_sort_key(k[0]), LABEL_GROUPS.index(k[1]), k[2]),
    ):
        n = totals[(model_id, group, label)]
        c = corrects[(model_id, group, label)]
        rows.append(
            add_meta(
                {
                    "group": group,
                    "label": label,
                    "n_items": n,
                    "correct_tie_ok": c,
                    "accuracy_tie_ok": accuracy(c, n),
                    "error_rate": 1 - c / n if n else "",
                },
                model_id,
                manifest,
            )
        )
    return rows


def build_accuracy_wide_rows(
    acc_rows: List[Dict[str, Any]],
    manifest: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    labels = sorted(
        {(row["group"], row["label"]) for row in acc_rows},
        key=lambda x: (LABEL_GROUPS.index(x[0]), x[1]),
    )
    accuracy_fields = [safe_label_name(group, label) for group, label in labels]
    field_by_label = {
        (group, label): safe_label_name(group, label) for group, label in labels
    }

    model_ids = sorted({row["model_id"] for row in acc_rows}, key=model_sort_key)
    rows_by_model: Dict[str, Dict[str, Any]] = {
        model_id: add_meta({}, model_id, manifest) for model_id in model_ids
    }
    for row in acc_rows:
        field = field_by_label[(row["group"], row["label"])]
        rows_by_model[row["model_id"]][field] = row["accuracy_tie_ok"]

    return [rows_by_model[model_id] for model_id in model_ids], accuracy_fields


def build_extreme_rows(
    acc_rows: List[Dict[str, Any]],
    manifest: Dict[str, Dict[str, str]],
    min_items: int,
) -> List[Dict[str, Any]]:
    by_model_group: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in acc_rows:
        if int(row["n_items"]) >= min_items and row["accuracy_tie_ok"] != "":
            by_model_group[(row["model_id"], row["group"])].append(row)

    rows: List[Dict[str, Any]] = []
    for (model_id, group), group_rows in sorted(
        by_model_group.items(), key=lambda x: (model_sort_key(x[0][0]), LABEL_GROUPS.index(x[0][1]))
    ):
        weakest = min(group_rows, key=lambda r: (float(r["accuracy_tie_ok"]), -int(r["n_items"]), r["label"]))
        strongest = max(group_rows, key=lambda r: (float(r["accuracy_tie_ok"]), int(r["n_items"]), r["label"]))
        rows.append(
            add_meta(
                {
                    "group": group,
                    "min_items": min_items,
                    "weakest_label": weakest["label"],
                    "weakest_n_items": weakest["n_items"],
                    "weakest_accuracy_tie_ok": weakest["accuracy_tie_ok"],
                    "strongest_label": strongest["label"],
                    "strongest_n_items": strongest["n_items"],
                    "strongest_accuracy_tie_ok": strongest["accuracy_tie_ok"],
                    "accuracy_range": float(strongest["accuracy_tie_ok"]) - float(weakest["accuracy_tie_ok"]),
                },
                model_id,
                manifest,
            )
        )
    return rows


def safe_label_name(group: str, label: str) -> str:
    return f"{group}__{label}".replace("|", "_").replace("+", "plus").replace("-", "_")


def build_focus_rows(
    totals: Counter[ModelLabelKey],
    corrects: Counter[ModelLabelKey],
    model_totals: Counter[str],
    model_corrects: Counter[str],
    manifest: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    model_ids = sorted(model_totals, key=model_sort_key)
    focus_fields = ["overall_n_items", "overall_accuracy_tie_ok"]
    for group, label in FOCUS_LABELS:
        base = safe_label_name(group, label)
        focus_fields.extend([f"{base}_n_items", f"{base}_accuracy_tie_ok"])
    focus_fields.extend(["bare_minus_arg_accuracy", "arg_minus_bare_accuracy"])

    rows: List[Dict[str, Any]] = []
    for model_id in model_ids:
        row: Dict[str, Any] = {
            "overall_n_items": model_totals[model_id],
            "overall_accuracy_tie_ok": accuracy(model_corrects[model_id], model_totals[model_id]),
        }
        acc_lookup: Dict[LabelKey, float] = {}
        for group, label in FOCUS_LABELS:
            key = (model_id, group, label)
            n = totals[key]
            c = corrects[key]
            base = safe_label_name(group, label)
            row[f"{base}_n_items"] = n
            row[f"{base}_accuracy_tie_ok"] = accuracy(c, n)
            if n:
                acc_lookup[(group, label)] = c / n

        bare = acc_lookup.get(("anc_bucket", "bare"))
        arg = acc_lookup.get(("anc_bucket", "arg"))
        row["bare_minus_arg_accuracy"] = bare - arg if bare is not None and arg is not None else ""
        row["arg_minus_bare_accuracy"] = arg - bare if bare is not None and arg is not None else ""
        rows.append(add_meta(row, model_id, manifest))

    return rows, focus_fields


def build_metadata_focus_summary(
    focus_rows: List[Dict[str, Any]],
    focus_fields: List[str],
) -> List[Dict[str, Any]]:
    group_fields = [
        "clause_wo",
        "np_wo",
        "alignment_code",
        "comp_system_code",
        "strategy_code",
        "anc_wo",
    ]
    accuracy_fields = [field for field in focus_fields if field.endswith("_accuracy_tie_ok")]
    accuracy_fields.extend(["bare_minus_arg_accuracy"])

    rows: List[Dict[str, Any]] = []
    for group_field in group_fields:
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in focus_rows:
            buckets[str(row.get(group_field, ""))].append(row)

        for value, bucket_rows in sorted(buckets.items()):
            out: Dict[str, Any] = {
                "metadata_field": group_field,
                "metadata_value": value,
                "n_languages": len(bucket_rows),
            }
            for acc_field in accuracy_fields:
                vals = [float(r[acc_field]) for r in bucket_rows if r.get(acc_field) != ""]
                out[f"mean_{acc_field}"] = sum(vals) / len(vals) if vals else ""
                out[f"min_{acc_field}"] = min(vals) if vals else ""
                out[f"max_{acc_field}"] = max(vals) if vals else ""
            rows.append(out)

    return rows


def fmt_acc(value: Any) -> str:
    return f"{float(value):.4f}" if value != "" else ""


def write_quick_report(
    path: Path,
    focus_rows: List[Dict[str, Any]],
    extreme_rows: List[Dict[str, Any]],
) -> None:
    focus_specs = [
        ("iv|none", "top_x_anc__iv_none_accuracy_tie_ok"),
        ("tv|arg", "top_x_anc__tv_arg_accuracy_tie_ok"),
        ("iv|arg", "top_x_anc__iv_arg_accuracy_tie_ok"),
        ("cv|bare", "top_x_anc__cv_bare_accuracy_tie_ok"),
        ("bare-arg gap", "bare_minus_arg_accuracy"),
    ]

    with path.open("w", encoding="utf-8") as f:
        f.write("[focus category ranges by language]\n")
        for label, field in focus_specs:
            rows = [r for r in focus_rows if r.get(field) != ""]
            rows.sort(key=lambda r: float(r[field]))
            if not rows:
                continue
            low = rows[:5]
            high = rows[-5:][::-1]
            f.write(f"\n{label}\n")
            f.write("lowest:\n")
            for row in low:
                f.write(f"  {row['model_id']}\t{fmt_acc(row[field])}\n")
            f.write("highest:\n")
            for row in high:
                f.write(f"  {row['model_id']}\t{fmt_acc(row[field])}\n")

        f.write("\n[weakest labels by group; min_items applied]\n")
        counts: Counter[Tuple[str, str]] = Counter()
        for row in extreme_rows:
            counts[(row["group"], row["weakest_label"])] += 1
        for (group, label), n in sorted(counts.items(), key=lambda x: (x[0][0], -x[1], x[0][1])):
            f.write(f"{group}\t{label}\t{n} languages\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--item-labels",
        default="evaluation/E2/generated/item_classification/top_anc_detail/item_top_anc_labels.tsv",
    )
    ap.add_argument("--pred-dir", default="results/e2_real_grammar_preference/all_models_bos_eos")
    ap.add_argument("--manifest", default="choices/manifest.tsv")
    ap.add_argument(
        "--out-dir",
        default="evaluation/E2/generated/item_classification/per_language_behavior",
    )
    ap.add_argument("--min-items-for-extremes", type=int, default=20)
    args = ap.parse_args()

    manifest = load_manifest(Path(args.manifest))
    labels_by_id = load_item_labels(Path(args.item_labels), LABEL_GROUPS)
    totals, corrects, model_totals, model_corrects = collect_model_stats(
        Path(args.pred_dir), labels_by_id
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    acc_rows = build_accuracy_rows(totals, corrects, manifest)
    wide_rows, wide_fields = build_accuracy_wide_rows(acc_rows, manifest)
    extreme_rows = build_extreme_rows(acc_rows, manifest, args.min_items_for_extremes)
    focus_rows, focus_fields = build_focus_rows(totals, corrects, model_totals, model_corrects, manifest)
    metadata_focus_rows = build_metadata_focus_summary(focus_rows, focus_fields)

    meta_out_fields = ["model_id"] + META_FIELDS
    write_tsv(
        out_dir / "per_language_category_accuracy.tsv",
        acc_rows,
        meta_out_fields
        + ["group", "label", "n_items", "correct_tie_ok", "accuracy_tie_ok", "error_rate"],
    )
    write_tsv(
        out_dir / "per_language_category_accuracy_wide.tsv",
        wide_rows,
        meta_out_fields + wide_fields,
    )
    write_tsv(
        out_dir / "per_language_strong_weak_categories.tsv",
        extreme_rows,
        meta_out_fields
        + [
            "group",
            "min_items",
            "weakest_label",
            "weakest_n_items",
            "weakest_accuracy_tie_ok",
            "strongest_label",
            "strongest_n_items",
            "strongest_accuracy_tie_ok",
            "accuracy_range",
        ],
    )
    write_tsv(
        out_dir / "per_language_focus_categories.tsv",
        focus_rows,
        meta_out_fields + focus_fields,
    )
    metadata_focus_fields = (
        ["metadata_field", "metadata_value", "n_languages"]
        + [
            f"{stat}_{field}"
            for field in [f for f in focus_fields if f.endswith("_accuracy_tie_ok")]
            + ["bare_minus_arg_accuracy"]
            for stat in ["mean", "min", "max"]
        ]
    )
    write_tsv(
        out_dir / "metadata_focus_summary.tsv",
        metadata_focus_rows,
        metadata_focus_fields,
    )
    write_quick_report(out_dir / "quick_report.txt", focus_rows, extreme_rows)

    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "per_language_category_accuracy": str(out_dir / "per_language_category_accuracy.tsv"),
                "per_language_category_accuracy_wide": str(out_dir / "per_language_category_accuracy_wide.tsv"),
                "per_language_strong_weak_categories": str(out_dir / "per_language_strong_weak_categories.tsv"),
                "per_language_focus_categories": str(out_dir / "per_language_focus_categories.tsv"),
                "metadata_focus_summary": str(out_dir / "metadata_focus_summary.tsv"),
                "quick_report": str(out_dir / "quick_report.txt"),
                "models": len(model_totals),
                "evaluable_items_per_model_min": min(model_totals.values()) if model_totals else 0,
                "evaluable_items_per_model_max": max(model_totals.values()) if model_totals else 0,
                "min_items_for_extremes": args.min_items_for_extremes,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
