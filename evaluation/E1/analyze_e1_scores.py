#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List


JsonDict = Dict[str, Any]


DIMENSIONS = [
    "clause_wo",
    "np_wo",
    "alignment",
    "comp_system",
    "strategy",
    "anc_wo",
    "anc_wo_choice",
    "anc_iv_order",
    "anc_tv_order",
]


def read_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["language"]: row for row in reader}


def load_json(path: Path) -> JsonDict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_tsv(path: Path, rows: List[JsonDict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def avg(rows: Iterable[JsonDict], key: str) -> float:
    vals = [float(row[key]) for row in rows if row.get(key) is not None]
    return mean(vals) if vals else float("nan")


def load_model_rows(score_dir: Path, manifest: Dict[str, Dict[str, str]]) -> List[JsonDict]:
    rows: List[JsonDict] = []

    for summary_path in sorted(score_dir.glob("*.summary.json")):
        summary = load_json(summary_path)
        lang = summary_path.name.replace(".summary.json", "")
        meta = manifest.get(lang, {})
        rows.append(
            {
                "language": lang,
                **meta,
                "n_pairs": summary.get("n_pairs"),
                "accuracy_strict": summary.get("accuracy_strict"),
                "ties": summary.get("ties"),
                "tie_rate": summary.get("tie_rate"),
                "mean_delta_good_minus_bad": summary.get("mean_delta_good_minus_bad"),
                "score_mode": summary.get("score_mode"),
                "model": summary.get("model"),
                "pairs": summary.get("pairs"),
            }
        )

    return rows


def summarize_by_dimension(rows: List[JsonDict]) -> List[JsonDict]:
    out: List[JsonDict] = []

    for dim in DIMENSIONS:
        buckets: Dict[str, List[JsonDict]] = defaultdict(list)
        for row in rows:
            buckets[str(row.get(dim, ""))].append(row)

        for value, group_rows in sorted(buckets.items()):
            out.append(
                {
                    "dimension": dim,
                    "value": value,
                    "n_models": len(group_rows),
                    "mean_accuracy_strict": avg(group_rows, "accuracy_strict"),
                    "min_accuracy_strict": min(float(r["accuracy_strict"]) for r in group_rows),
                    "max_accuracy_strict": max(float(r["accuracy_strict"]) for r in group_rows),
                    "mean_delta_good_minus_bad": avg(group_rows, "mean_delta_good_minus_bad"),
                }
            )

    return out


def summarize_cross(rows: List[JsonDict], dims: List[str]) -> List[JsonDict]:
    buckets: Dict[tuple[str, ...], List[JsonDict]] = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(dim, "")) for dim in dims)
        buckets[key].append(row)

    out: List[JsonDict] = []
    for key, group_rows in sorted(buckets.items()):
        out.append(
            {
                **{dim: value for dim, value in zip(dims, key)},
                "n_models": len(group_rows),
                "mean_accuracy_strict": avg(group_rows, "accuracy_strict"),
                "min_accuracy_strict": min(float(r["accuracy_strict"]) for r in group_rows),
                "max_accuracy_strict": max(float(r["accuracy_strict"]) for r in group_rows),
                "mean_delta_good_minus_bad": avg(group_rows, "mean_delta_good_minus_bad"),
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score-dir", required=True, help="Directory with *.summary.json")
    ap.add_argument("--manifest", default="choices/manifest.tsv")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--lowest-n", type=int, default=20)
    args = ap.parse_args()

    score_dir = Path(args.score_dir)
    out_dir = Path(args.out_dir)
    manifest = read_manifest(Path(args.manifest))

    rows = load_model_rows(score_dir, manifest)
    if not rows:
        raise FileNotFoundError(f"No *.summary.json files found in {score_dir}")

    rows_sorted = sorted(rows, key=lambda r: (float(r["accuracy_strict"]), float(r["mean_delta_good_minus_bad"])))

    model_fields = [
        "language",
        "clause_wo",
        "np_wo",
        "alignment",
        "comp_system",
        "strategy",
        "anc_wo",
        "anc_wo_choice",
        "anc_iv_order",
        "anc_tv_order",
        "n_pairs",
        "accuracy_strict",
        "ties",
        "tie_rate",
        "mean_delta_good_minus_bad",
        "score_mode",
    ]

    write_tsv(out_dir / "model_summary.tsv", rows_sorted, model_fields)

    dim_rows = summarize_by_dimension(rows)
    write_tsv(
        out_dir / "by_dimension.tsv",
        dim_rows,
        [
            "dimension",
            "value",
            "n_models",
            "mean_accuracy_strict",
            "min_accuracy_strict",
            "max_accuracy_strict",
            "mean_delta_good_minus_bad",
        ],
    )

    cross_dims = ["clause_wo", "np_wo", "alignment"]
    cross_rows = summarize_cross(rows, cross_dims)
    write_tsv(
        out_dir / "clause_np_alignment.tsv",
        cross_rows,
        [
            *cross_dims,
            "n_models",
            "mean_accuracy_strict",
            "min_accuracy_strict",
            "max_accuracy_strict",
            "mean_delta_good_minus_bad",
        ],
    )

    lowest_rows = rows_sorted[: args.lowest_n]
    write_tsv(out_dir / "lowest_models.tsv", lowest_rows, model_fields)

    quick = {
        "score_dir": str(score_dir),
        "out_dir": str(out_dir),
        "n_models": len(rows),
        "mean_accuracy_strict": avg(rows, "accuracy_strict"),
        "min_accuracy_strict": min(float(r["accuracy_strict"]) for r in rows),
        "max_accuracy_strict": max(float(r["accuracy_strict"]) for r in rows),
        "mean_delta_good_minus_bad": avg(rows, "mean_delta_good_minus_bad"),
        "lowest_models": [
            {
                "language": r["language"],
                "accuracy_strict": r["accuracy_strict"],
                "mean_delta_good_minus_bad": r["mean_delta_good_minus_bad"],
                "clause_wo": r.get("clause_wo", ""),
                "np_wo": r.get("np_wo", ""),
                "alignment": r.get("alignment", ""),
                "comp_system": r.get("comp_system", ""),
                "strategy": r.get("strategy", ""),
                "anc_wo": r.get("anc_wo", ""),
                "anc_wo_choice": r.get("anc_wo_choice", ""),
                "anc_iv_order": r.get("anc_iv_order", ""),
                "anc_tv_order": r.get("anc_tv_order", ""),
            }
            for r in lowest_rows
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "quick_report.json").open("w", encoding="utf-8") as f:
        json.dump(quick, f, indent=2, ensure_ascii=False)

    print(json.dumps(quick, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
