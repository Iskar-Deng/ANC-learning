#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Set


def load_ids(path: Path) -> Set[str]:
    ids = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            x = line.strip()
            if x:
                ids.add(x)
    return ids


def parse_float(x: str) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def parse_int(x: str) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def mean(xs: List[float]):
    return sum(xs) / len(xs) if xs else None


def summarize_rows(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "accuracy_tie_ok": None,
            "correct_tie_ok": 0,
            "top5_accuracy": None,
            "top5": 0,
            "mrr": None,
            "mean_rank": None,
            "mean_n_unique_sentences": None,
            "mean_own_sentence_group_size": None,
            "mean_max_languages_count": None,
            "mean_score_gap": None,
            "mean_score_gap_when_wrong": None,
        }

    correct = [parse_int(r["correct_tie_ok"]) for r in rows]
    top5 = [parse_int(r["top5"]) for r in rows]
    mrr = [parse_float(r["mrr"]) for r in rows]
    ranks = [parse_float(r["own_rank"]) for r in rows]

    n_unique = [parse_float(r["n_unique_sentences"]) for r in rows]
    own_group = [parse_float(r["own_sentence_group_size"]) for r in rows]
    max_langs = [parse_float(r["max_languages_count"]) for r in rows]

    gaps = [
        parse_float(r["max_score"]) - parse_float(r["own_score"])
        for r in rows
    ]

    wrong_gaps = [
        gap for gap, c in zip(gaps, correct)
        if c == 0
    ]

    return {
        "n": n,
        "accuracy_tie_ok": mean(correct),
        "correct_tie_ok": sum(correct),
        "top5_accuracy": mean(top5),
        "top5": sum(top5),
        "mrr": mean(mrr),
        "mean_rank": mean(ranks),
        "mean_n_unique_sentences": mean(n_unique),
        "mean_own_sentence_group_size": mean(own_group),
        "mean_max_languages_count": mean(max_langs),
        "mean_score_gap": mean(gaps),
        "mean_score_gap_when_wrong": mean(wrong_gaps),
    }


def read_predictions(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred-dir", required=True)
    ap.add_argument("--subset-ids", required=True)
    ap.add_argument("--subset-name", default="anc")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    pred_dir = Path(args.pred_dir)
    subset_ids = load_ids(Path(args.subset_ids))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pred_files = sorted(pred_dir.glob("*.predictions.tsv"))
    if not pred_files:
        raise FileNotFoundError(f"No prediction files found in {pred_dir}")

    rows_out = []

    for pred_path in pred_files:
        model_id = pred_path.name.replace(".predictions.tsv", "")
        rows = read_predictions(pred_path)

        all_summary = summarize_rows(rows)
        subset_rows = [r for r in rows if r["id"] in subset_ids]
        subset_summary = summarize_rows(subset_rows)
        non_subset_rows = [r for r in rows if r["id"] not in subset_ids]
        non_subset_summary = summarize_rows(non_subset_rows)

        for subset_label, summary in [
            ("all", all_summary),
            (args.subset_name, subset_summary),
            (f"non_{args.subset_name}", non_subset_summary),
        ]:
            rows_out.append({
                "model_id": model_id,
                "subset": subset_label,
                **summary,
            })

        print(json.dumps({
            "model_id": model_id,
            "all_n": all_summary["n"],
            "all_acc": all_summary["accuracy_tie_ok"],
            f"{args.subset_name}_n": subset_summary["n"],
            f"{args.subset_name}_acc": subset_summary["accuracy_tie_ok"],
            f"non_{args.subset_name}_acc": non_subset_summary["accuracy_tie_ok"],
        }, ensure_ascii=False))

    out_tsv = out_dir / f"{args.subset_name}_metrics.tsv"
    fieldnames = [
        "model_id",
        "subset",
        "n",
        "accuracy_tie_ok",
        "correct_tie_ok",
        "top5_accuracy",
        "top5",
        "mrr",
        "mean_rank",
        "mean_n_unique_sentences",
        "mean_own_sentence_group_size",
        "mean_max_languages_count",
        "mean_score_gap",
        "mean_score_gap_when_wrong",
    ]

    with out_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows_out:
            writer.writerow(row)

    with (out_dir / f"{args.subset_name}_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(rows_out, f, indent=2, ensure_ascii=False)

    print(f"\nWrote: {out_tsv}")


if __name__ == "__main__":
    main()