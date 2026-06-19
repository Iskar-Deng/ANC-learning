#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.E1.score_e1_pairs import (  # noqa: E402
    boundary_token,
    get_device,
    iter_jsonl,
    safe_tsv,
    score_sentences,
)


JsonDict = Dict[str, Any]


def pair_files(pairs_dir: Path) -> List[Path]:
    files = sorted(pairs_dir.glob("*.pairs.jsonl"))
    if not files:
        files = sorted(pairs_dir.glob("*.jsonl"))
    if not files:
        raise ValueError(f"No pair JSONL files found in {pairs_dir}")
    return files


def extract_rows(path: Path) -> List[JsonDict]:
    language = path.name.replace(".pairs.jsonl", "").replace(".jsonl", "")
    rows: List[JsonDict] = []
    for row in iter_jsonl(path):
        good = row.get("blimp_sentence_good")
        bad = row.get("blimp_sentence_bad")
        if not isinstance(good, str) or not good.strip():
            raise ValueError(f"Missing blimp_sentence_good in {path}: {row}")
        if not isinstance(bad, str) or not bad.strip():
            raise ValueError(f"Missing blimp_sentence_bad in {path}: {row}")
        rows.append(
            {
                "pair_index": row.get("pair_index", len(rows) + 1),
                "id": row.get("id", ""),
                "language": row.get("language", language),
                "phenomenon_id": row.get("phenomenon_id", ""),
                "source_index": row.get("source_index", ""),
                "good": good.strip(),
                "bad": bad.strip(),
                "good_stem": row.get("good_stem", ""),
                "bad_stem": row.get("bad_stem", ""),
                "blimp_pair_id": row.get("blimp_pair_id", ""),
                "pseudo_good": row.get("good", ""),
                "pseudo_bad": row.get("bad", ""),
            }
        )
    return rows


def write_jsonl(path: Path, rows: Iterable[JsonDict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_scores(path: Path, rows: List[JsonDict], score_by_sentence: Dict[str, float]) -> JsonDict:
    path.parent.mkdir(parents=True, exist_ok=True)
    correct = 0
    ties = 0
    delta_sum = 0.0

    with path.open("w", encoding="utf-8") as f:
        f.write(
            "pair_index\tid\tlanguage\tphenomenon_id\tblimp_pair_id\t"
            "good_score\tbad_score\tdelta\tcorrect\ttie\t"
            "good_stem\tbad_stem\tgood\tbad\n"
        )
        for i, row in enumerate(rows, start=1):
            gs = score_by_sentence[row["good"]]
            bs = score_by_sentence[row["bad"]]
            delta = gs - bs
            is_tie = abs(delta) <= 1e-8
            is_correct = delta > 1e-8
            correct += int(is_correct)
            ties += int(is_tie)
            delta_sum += delta
            f.write(
                f"{row.get('pair_index', i)}\t"
                f"{safe_tsv(row.get('id', ''))}\t"
                f"{safe_tsv(row.get('language', ''))}\t"
                f"{safe_tsv(row.get('phenomenon_id', ''))}\t"
                f"{safe_tsv(row.get('blimp_pair_id', ''))}\t"
                f"{gs:.8f}\t{bs:.8f}\t{delta:.8f}\t"
                f"{int(is_correct)}\t{int(is_tie)}\t"
                f"{safe_tsv(row.get('good_stem', ''))}\t"
                f"{safe_tsv(row.get('bad_stem', ''))}\t"
                f"{safe_tsv(row.get('good', ''))}\t"
                f"{safe_tsv(row.get('bad', ''))}\n"
            )

    n = len(rows)
    return {
        "language": rows[0].get("language", "") if rows else "",
        "n_pairs": n,
        "accuracy_strict": correct / n if n else 0.0,
        "ties": ties,
        "tie_rate": ties / n if n else 0.0,
        "mean_delta_good_minus_bad": delta_sum / n if n else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Score an English baseline on the exact BLiMP sentences sampled by E1 pair files."
    )
    ap.add_argument("--model", required=True)
    ap.add_argument("--pairs-dir", required=True, help="E1 pairs directory with *.pairs.jsonl")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu", "mps"])
    ap.add_argument(
        "--score-mode",
        default="bos_eos",
        choices=["legacy", "bos", "bos_eos"],
    )
    args = ap.parse_args()

    model_path = Path(args.model)
    pairs_dir = Path(args.pairs_dir)
    out_dir = Path(args.out_dir)
    sampled_dir = out_dir / "sampled_pairs"
    scores_dir = out_dir / "scores"
    summaries_dir = out_dir / "summaries"

    by_file: OrderedDict[str, List[JsonDict]] = OrderedDict()
    all_rows: List[JsonDict] = []
    for path in pair_files(pairs_dir):
        language = path.name.replace(".pairs.jsonl", "").replace(".jsonl", "")
        rows = extract_rows(path)
        by_file[language] = rows
        all_rows.extend(rows)
        write_jsonl(sampled_dir / f"{language}.jsonl", rows)

    unique_sentences = list(OrderedDict.fromkeys(
        sentence
        for row in all_rows
        for sentence in (row["good"], row["bad"])
    ))

    device = get_device(args.device)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or boundary_token(tokenizer)
    model = AutoModelForCausalLM.from_pretrained(model_path)
    if len(tokenizer) != model.get_input_embeddings().weight.shape[0]:
        model.resize_token_embeddings(len(tokenizer))
    model.to(device)
    model.eval()

    print(f"Model:            {model_path}")
    print(f"Pairs dir:        {pairs_dir}")
    print(f"Pair files:       {len(by_file)}")
    print(f"Rows total:       {len(all_rows)}")
    print(f"Unique sentences: {len(unique_sentences)}")
    print(f"Device:           {device}")
    print(f"Score mode:       {args.score_mode}")

    sentence_scores = score_sentences(
        model=model,
        tokenizer=tokenizer,
        sentences=unique_sentences,
        device=device,
        batch_size=args.batch_size,
        score_mode=args.score_mode,
    )
    score_by_sentence = dict(zip(unique_sentences, sentence_scores))

    summaries: List[JsonDict] = []
    for language, rows in by_file.items():
        summary = write_scores(scores_dir / f"{language}.scores.tsv", rows, score_by_sentence)
        summaries.append(summary)
        summary_path = summaries_dir / f"{language}.summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    model_summary = out_dir / "model_summary.tsv"
    out_dir.mkdir(parents=True, exist_ok=True)
    with model_summary.open("w", encoding="utf-8") as f:
        f.write("language\tn_pairs\taccuracy_strict\tties\ttie_rate\tmean_delta_good_minus_bad\n")
        for summary in summaries:
            f.write(
                f"{safe_tsv(summary['language'])}\t"
                f"{summary['n_pairs']}\t"
                f"{summary['accuracy_strict']:.8f}\t"
                f"{summary['ties']}\t"
                f"{summary['tie_rate']:.8f}\t"
                f"{summary['mean_delta_good_minus_bad']:.8f}\n"
            )

    micro_correct = 0
    micro_ties = 0
    micro_delta = 0.0
    for row in all_rows:
        delta = score_by_sentence[row["good"]] - score_by_sentence[row["bad"]]
        micro_correct += int(delta > 1e-8)
        micro_ties += int(abs(delta) <= 1e-8)
        micro_delta += delta

    aggregate = {
        "model": str(model_path),
        "pairs_dir": str(pairs_dir),
        "out_dir": str(out_dir),
        "pair_files": len(by_file),
        "rows_total": len(all_rows),
        "unique_sentences": len(unique_sentences),
        "score_mode": args.score_mode,
        "mean_language_accuracy": sum(s["accuracy_strict"] for s in summaries) / len(summaries),
        "min_language_accuracy": min(s["accuracy_strict"] for s in summaries),
        "max_language_accuracy": max(s["accuracy_strict"] for s in summaries),
        "micro_accuracy": micro_correct / len(all_rows),
        "micro_ties": micro_ties,
        "micro_tie_rate": micro_ties / len(all_rows),
        "micro_mean_delta_good_minus_bad": micro_delta / len(all_rows),
    }
    with (out_dir / "aggregate_summary.json").open("w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2, ensure_ascii=False)

    print(json.dumps(aggregate, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
