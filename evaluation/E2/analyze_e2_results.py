#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Set


METRICS = [
    "accuracy_tie_ok",
    "strict_unique_top1_accuracy",
    "top5_accuracy",
    "mrr",
    "mean_rank",
    "mean_unique_sentences_per_id",
    "mean_own_sentence_group_size",
    "mean_max_languages_count",
    "mean_max_unique_sentences_count",
]


PRED_METRICS = [
    "accuracy_tie_ok",
    "strict_unique_top1_accuracy",
    "top5_accuracy",
    "mrr",
    "mean_rank",
    "mean_n_unique_sentences",
    "mean_own_sentence_group_size",
    "mean_max_languages_count",
    "mean_score_gap",
    "mean_score_gap_when_wrong",
]


def read_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["language"]: row for row in reader}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_ids(path: Optional[Path]) -> Set[str]:
    if path is None:
        return set()
    ids: Set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            x = line.strip()
            if x:
                ids.add(x)
    return ids


def parse_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def parse_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def avg(rows: Iterable[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [parse_float(row.get(key)) for row in rows if row.get(key) is not None]
    vals = [v for v in vals if v == v]
    return mean(vals) if vals else None


def write_tsv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def summarize_group(rows: List[Dict[str, Any]], metrics: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"n_models": len(rows)}
    for metric in metrics:
        out[metric] = avg(rows, metric)
    return out


def summarize_prediction_rows(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "accuracy_tie_ok": None,
            "strict_unique_top1_accuracy": None,
            "top5_accuracy": None,
            "mrr": None,
            "mean_rank": None,
            "mean_n_unique_sentences": None,
            "mean_own_sentence_group_size": None,
            "mean_max_languages_count": None,
            "mean_score_gap": None,
            "mean_score_gap_when_wrong": None,
        }

    correct = [parse_int(r["correct_tie_ok"]) for r in rows]
    strict = [parse_int(r["strict_unique_top1"]) for r in rows]
    top5 = [parse_int(r["top5"]) for r in rows]
    mrr = [parse_float(r["mrr"]) for r in rows]
    ranks = [parse_float(r["own_rank"]) for r in rows]
    n_unique = [parse_float(r["n_unique_sentences"]) for r in rows]
    own_group = [parse_float(r["own_sentence_group_size"]) for r in rows]
    max_langs = [parse_float(r["max_languages_count"]) for r in rows]
    gaps = [parse_float(r["max_score"]) - parse_float(r["own_score"]) for r in rows]
    wrong_gaps = [gap for gap, ok in zip(gaps, correct) if ok == 0]

    return {
        "n": n,
        "accuracy_tie_ok": mean(correct),
        "strict_unique_top1_accuracy": mean(strict),
        "top5_accuracy": mean(top5),
        "mrr": mean(mrr),
        "mean_rank": mean(ranks),
        "mean_n_unique_sentences": mean(n_unique),
        "mean_own_sentence_group_size": mean(own_group),
        "mean_max_languages_count": mean(max_langs),
        "mean_score_gap": mean(gaps),
        "mean_score_gap_when_wrong": mean(wrong_gaps) if wrong_gaps else None,
    }


def split_top_language(max_languages: str) -> str:
    return max_languages.split(",", 1)[0] if max_languages else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred-dir", default="results/e2_real_grammar_preference/all_models_bos_eos")
    ap.add_argument("--manifest", default="choices/manifest.tsv")
    ap.add_argument(
        "--anc-ids",
        default="evaluation/E2/generated/item_classification/top_anc_detail/anc_ids.txt",
    )
    ap.add_argument("--out-dir", default="evaluation/E2/generated/analysis/bos_eos")
    ap.add_argument("--top-error-n", type=int, default=50)
    args = ap.parse_args()

    pred_dir = Path(args.pred_dir)
    manifest = read_manifest(Path(args.manifest))
    anc_ids = load_ids(Path(args.anc_ids) if args.anc_ids else None)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_rows: List[Dict[str, Any]] = []
    for summary_path in sorted(pred_dir.glob("*.summary.json")):
        summary = load_json(summary_path)
        model_id = summary["model_id"]
        row = {"model_id": model_id, **manifest.get(model_id, {}), **summary}
        model_rows.append(row)

    if not model_rows:
        raise FileNotFoundError(f"No summary files found in {pred_dir}")

    write_tsv(
        out_dir / "model_summary.tsv",
        model_rows,
        [
            "model_id",
            "clause_wo",
            "np_wo",
            "alignment",
            "comp_system",
            "strategy",
            "anc_wo",
            *METRICS,
        ],
    )

    group_rows: List[Dict[str, Any]] = []
    for dim in ["clause_wo", "np_wo", "alignment", "comp_system", "strategy", "anc_wo"]:
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in model_rows:
            buckets[row.get(dim, "")].append(row)
        for value, rows in sorted(buckets.items()):
            group_rows.append({"group": dim, "value": value, **summarize_group(rows, METRICS)})

    write_tsv(out_dir / "by_dimension.tsv", group_rows, ["group", "value", "n_models", *METRICS])

    cross_rows: List[Dict[str, Any]] = []
    for comp in sorted({r["comp_system"] for r in model_rows}):
        for strategy in sorted({r["strategy"] for r in model_rows}):
            rows = [r for r in model_rows if r["comp_system"] == comp and r["strategy"] == strategy]
            cross_rows.append({
                "comp_system": comp,
                "strategy": strategy,
                **summarize_group(rows, METRICS),
            })

    write_tsv(out_dir / "comp_by_strategy.tsv", cross_rows, ["comp_system", "strategy", "n_models", *METRICS])

    subset_rows: List[Dict[str, Any]] = []
    top_prediction_counter: Counter[str] = Counter()
    top_strategy_counter: Counter[str] = Counter()
    top_comp_strategy_counter: Counter[str] = Counter()
    error_examples: List[Dict[str, Any]] = []

    pred_files = sorted(pred_dir.glob("*.predictions.tsv"))
    for pred_path in pred_files:
        model_id = pred_path.name.replace(".predictions.tsv", "")
        model_meta = manifest.get(model_id, {})
        all_rows: List[Dict[str, str]] = []
        anc_rows_for_model: List[Dict[str, str]] = []
        non_anc_rows_for_model: List[Dict[str, str]] = []

        with pred_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                all_rows.append(row)
                row_id = row["id"]
                target = anc_rows_for_model if row_id in anc_ids else non_anc_rows_for_model
                target.append(row)

                if parse_int(row["correct_tie_ok"]) == 0:
                    top_lang = split_top_language(row["max_languages"])
                    top_prediction_counter[top_lang] += 1
                    if top_lang in manifest:
                        top_meta = manifest[top_lang]
                        top_strategy_counter[top_meta["strategy"]] += 1
                        top_comp_strategy_counter[f"{top_meta['comp_system']}|{top_meta['strategy']}"] += 1

                    if len(error_examples) < args.top_error_n * 4:
                        gap = parse_float(row["max_score"]) - parse_float(row["own_score"])
                        top_meta = manifest.get(top_lang, {})
                        error_examples.append({
                            "model_id": model_id,
                            "id": row_id,
                            "score_gap": gap,
                            "own_rank": row["own_rank"],
                            "own_comp_system": model_meta.get("comp_system", ""),
                            "own_strategy": model_meta.get("strategy", ""),
                            "top_language": top_lang,
                            "top_comp_system": top_meta.get("comp_system", ""),
                            "top_strategy": top_meta.get("strategy", ""),
                            "max_languages": row["max_languages"],
                            "own_sentence": row["own_sentence"],
                            "best_sentences": row["best_sentences"],
                        })

        for subset_name, rows in [
            ("all", all_rows),
            ("anc", anc_rows_for_model),
            ("non_anc", non_anc_rows_for_model),
        ]:
            subset_rows.append({
                "model_id": model_id,
                "subset": subset_name,
                **model_meta,
                **summarize_prediction_rows(rows),
            })

    write_tsv(
        out_dir / "subset_by_model.tsv",
        subset_rows,
        [
            "model_id",
            "subset",
            "clause_wo",
            "np_wo",
            "alignment",
            "comp_system",
            "strategy",
            "anc_wo",
            *PRED_METRICS,
        ],
    )

    subset_group_rows: List[Dict[str, Any]] = []
    for subset_name in ["all", "anc", "non_anc"]:
        rows = [r for r in subset_rows if r["subset"] == subset_name]
        subset_group_rows.append({"subset": subset_name, "group": "all", "value": "all", **summarize_group(rows, PRED_METRICS)})
        for dim in ["comp_system", "strategy", "alignment", "clause_wo", "np_wo", "anc_wo"]:
            buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in rows:
                buckets[row.get(dim, "")].append(row)
            for value, bucket_rows in sorted(buckets.items()):
                subset_group_rows.append({
                    "subset": subset_name,
                    "group": dim,
                    "value": value,
                    **summarize_group(bucket_rows, PRED_METRICS),
                })

    write_tsv(
        out_dir / "subset_by_dimension.tsv",
        subset_group_rows,
        ["subset", "group", "value", "n_models", *PRED_METRICS],
    )

    error_examples.sort(key=lambda r: r["score_gap"], reverse=True)
    write_tsv(
        out_dir / "top_error_examples.tsv",
        error_examples[: args.top_error_n],
        [
            "model_id",
            "id",
            "score_gap",
            "own_rank",
            "own_comp_system",
            "own_strategy",
            "top_language",
            "top_comp_system",
            "top_strategy",
            "max_languages",
            "own_sentence",
            "best_sentences",
        ],
    )

    counters = {
        "top_wrong_language": top_prediction_counter.most_common(30),
        "top_wrong_strategy": top_strategy_counter.most_common(),
        "top_wrong_comp_strategy": top_comp_strategy_counter.most_common(),
        "n_models": len(model_rows),
        "n_prediction_files": len(pred_files),
        "n_anc_ids": len(anc_ids),
    }
    with (out_dir / "counters.json").open("w", encoding="utf-8") as f:
        json.dump(counters, f, indent=2, ensure_ascii=False)

    print(json.dumps(counters, indent=2, ensure_ascii=False))
    print(f"Wrote analysis tables to: {out_dir}")


if __name__ == "__main__":
    main()
