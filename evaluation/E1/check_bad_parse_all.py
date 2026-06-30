#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, Iterator, List


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

NOTE_READINGS_RE = re.compile(r"^NOTE:\s+(\d+)\s+readings,")


def iter_jsonl(path: Path) -> Iterator[JsonDict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            yield obj


def read_tsv(path: Path) -> List[JsonDict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: Iterable[JsonDict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def avg(values: Iterable[float]) -> float:
    vals = list(values)
    return mean(vals) if vals else float("nan")


def load_model_summary(phenomenon_dir: Path) -> Dict[str, JsonDict]:
    path = phenomenon_dir / "analysis" / "model_summary.tsv"
    if not path.exists():
        return {}
    return {row["language"]: row for row in read_tsv(path)}


def load_scores(phenomenon_dir: Path, language: str) -> Dict[str, JsonDict]:
    path = phenomenon_dir / "scores" / f"{language}.scores.tsv"
    if not path.exists():
        return {}
    rows = read_tsv(path)
    out: Dict[str, JsonDict] = {}
    for row in rows:
        # pair_index is stable within a pair file; id is not always unique enough
        # across generated variants.
        out[str(row.get("pair_index", ""))] = row
    return out


def grammar_path(grammars_dir: Path, language: str) -> Path:
    path = grammars_dir / language / f"{language}.dat"
    if not path.exists():
        raise FileNotFoundError(f"Grammar not found for {language}: {path}")
    return path


def parse_bad_sentences(
    *,
    ace: Path,
    grammar: Path,
    sentences: List[str],
    timeout: int,
    batch_size: int,
) -> List[int]:
    if not sentences:
        return []

    out: List[int] = []
    for start in range(0, len(sentences), batch_size):
        out.extend(
            parse_bad_sentence_batch(
                ace=ace,
                grammar=grammar,
                sentences=sentences[start:start + batch_size],
                timeout=timeout,
            )
        )
    return out


def parse_bad_sentence_batch(
    *,
    ace: Path,
    grammar: Path,
    sentences: List[str],
    timeout: int,
) -> List[int]:
    proc = subprocess.run(
        [str(ace), "-g", str(grammar), "-n", "1", "-R"],
        input="\n".join(sentences) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )

    readings: List[int] = []
    for line in proc.stdout.splitlines():
        match = NOTE_READINGS_RE.match(line)
        if match:
            readings.append(int(match.group(1)))

    if len(readings) != len(sentences):
        if len(sentences) == 1:
            return [0]
        out: List[int] = []
        for sentence in sentences:
            out.extend(
                parse_bad_sentence_batch(
                    ace=ace,
                    grammar=grammar,
                    sentences=[sentence],
                    timeout=timeout,
                )
            )
        return out

    return readings


def collect_pair_rows(e1_root: Path) -> List[JsonDict]:
    all_rows: List[JsonDict] = []
    phenomenon_dirs = sorted(
        p for p in e1_root.iterdir()
        if p.is_dir() and (p / "pairs").exists()
    )

    for phenomenon_dir in phenomenon_dirs:
        phenomenon = phenomenon_dir.name
        model_summary = load_model_summary(phenomenon_dir)

        for pair_path in sorted((phenomenon_dir / "pairs").glob("*.pairs.jsonl")):
            language = pair_path.name.replace(".pairs.jsonl", "")
            scores = load_scores(phenomenon_dir, language)
            meta = model_summary.get(language, {})

            for row in iter_jsonl(pair_path):
                pair_index = str(row.get("pair_index", ""))
                score_row = scores.get(pair_index, {})
                bad = str(row.get("bad", "")).strip()
                good = str(row.get("good", "")).strip()
                if not bad:
                    raise ValueError(f"Missing bad sentence in {pair_path}: {row}")

                out = {
                    "phenomenon": phenomenon,
                    "language": language,
                    "pair_index": pair_index,
                    "id": row.get("id", ""),
                    "source_id": row.get("source_id", ""),
                    "phenomenon_id": row.get("phenomenon_id", ""),
                    "phenomenon_name": row.get("phenomenon_name", ""),
                    "good": good,
                    "bad": bad,
                    "correct": score_row.get("correct", ""),
                    "delta": score_row.get("delta", ""),
                    "good_score": score_row.get("good_score", ""),
                    "bad_score": score_row.get("bad_score", ""),
                    "target_role": row.get("target_role", ""),
                    "template": row.get("template", ""),
                    "perturbation": row.get("perturbation", ""),
                }
                for dim in DIMENSIONS:
                    out[dim] = row.get(dim, meta.get(dim, ""))
                all_rows.append(out)

    return all_rows


def write_language_cache(cache_path: Path, rows: List[JsonDict]) -> None:
    fields = [
        "phenomenon",
        "language",
        "pair_index",
        "id",
        "bad_parse_readings",
    ]
    write_tsv(cache_path, rows, fields)


def read_language_cache(cache_path: Path) -> Dict[tuple[str, str], int]:
    out: Dict[tuple[str, str], int] = {}
    for row in read_tsv(cache_path):
        out[(row["phenomenon"], row["pair_index"])] = int(row["bad_parse_readings"])
    return out


def attach_bad_parse(
    *,
    rows: List[JsonDict],
    ace: Path,
    grammars_dir: Path,
    cache_dir: Path,
    timeout: int,
    batch_size: int,
    resume: bool,
) -> List[JsonDict]:
    by_language: Dict[str, List[JsonDict]] = defaultdict(list)
    for row in rows:
        by_language[row["language"]].append(row)

    completed: List[JsonDict] = []
    for i, (language, language_rows) in enumerate(sorted(by_language.items()), start=1):
        cache_path = cache_dir / f"{language}.bad_parse.tsv"
        cached: Dict[tuple[str, str], int] = {}
        if resume and cache_path.exists():
            cached = read_language_cache(cache_path)

        missing_rows = [
            row for row in language_rows
            if (row["phenomenon"], row["pair_index"]) not in cached
        ]

        if missing_rows:
            print(
                f"[{i}/{len(by_language)}] parsing BAD: {language} "
                f"({len(missing_rows)} missing / {len(language_rows)} total)",
                flush=True,
            )
            readings = parse_bad_sentences(
                ace=ace,
                grammar=grammar_path(grammars_dir, language),
                sentences=[row["bad"] for row in missing_rows],
                timeout=timeout,
                batch_size=batch_size,
            )
            for row, n_readings in zip(missing_rows, readings):
                cached[(row["phenomenon"], row["pair_index"])] = n_readings

            cache_rows = []
            for row in language_rows:
                key = (row["phenomenon"], row["pair_index"])
                cache_rows.append(
                    {
                        "phenomenon": row["phenomenon"],
                        "language": language,
                        "pair_index": row["pair_index"],
                        "id": row["id"],
                        "bad_parse_readings": cached[key],
                    }
                )
            write_language_cache(cache_path, cache_rows)
        else:
            print(f"[{i}/{len(by_language)}] cache ok: {language}", flush=True)

        for row in language_rows:
            key = (row["phenomenon"], row["pair_index"])
            n_readings = cached[key]
            enriched = dict(row)
            enriched["bad_parse_readings"] = n_readings
            enriched["bad_parse"] = int(n_readings > 0)
            completed.append(enriched)

    return completed


def summarize_language_phenomenon(rows: List[JsonDict]) -> List[JsonDict]:
    buckets: Dict[tuple[str, str], List[JsonDict]] = defaultdict(list)
    for row in rows:
        buckets[(row["phenomenon"], row["language"])].append(row)

    out: List[JsonDict] = []
    for (phenomenon, language), group in sorted(buckets.items()):
        correct_vals = [int(r["correct"]) for r in group if str(r.get("correct", "")) != ""]
        deltas = [float(r["delta"]) for r in group if str(r.get("delta", "")) != ""]
        parsed = [int(r["bad_parse"]) for r in group]
        parsed_group = [r for r in group if int(r["bad_parse"]) == 1]
        skipped_group = [r for r in group if int(r["bad_parse"]) == 0]

        def subset_acc(subset: List[JsonDict]) -> str:
            vals = [int(r["correct"]) for r in subset if str(r.get("correct", "")) != ""]
            return f"{avg(vals):.6f}" if vals else ""

        base = {
            "phenomenon": phenomenon,
            "language": language,
            "n_pairs": len(group),
            "accuracy_strict": f"{avg(correct_vals):.6f}" if correct_vals else "",
            "mean_delta_good_minus_bad": f"{avg(deltas):.6f}" if deltas else "",
            "bad_parse": sum(parsed),
            "bad_skip": len(parsed) - sum(parsed),
            "bad_parse_rate": f"{avg(parsed):.6f}",
            "accuracy_when_bad_parse": subset_acc(parsed_group),
            "accuracy_when_bad_skip": subset_acc(skipped_group),
        }
        for dim in DIMENSIONS:
            base[dim] = group[0].get(dim, "")
        out.append(base)
    return out


def summarize_phenomenon(rows: List[JsonDict]) -> List[JsonDict]:
    buckets: Dict[str, List[JsonDict]] = defaultdict(list)
    for row in rows:
        buckets[row["phenomenon"]].append(row)

    out: List[JsonDict] = []
    for phenomenon, group in sorted(buckets.items()):
        correct_vals = [int(r["correct"]) for r in group if str(r.get("correct", "")) != ""]
        parsed = [int(r["bad_parse"]) for r in group]
        out.append(
            {
                "phenomenon": phenomenon,
                "n_languages": len({r["language"] for r in group}),
                "n_pairs": len(group),
                "mean_accuracy_strict": f"{avg(correct_vals):.6f}" if correct_vals else "",
                "bad_parse": sum(parsed),
                "bad_skip": len(parsed) - sum(parsed),
                "bad_parse_rate": f"{avg(parsed):.6f}",
            }
        )
    return out


def summarize_group(rows: List[JsonDict], dims: List[str]) -> List[JsonDict]:
    buckets: Dict[tuple[str, ...], List[JsonDict]] = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(dim, "")) for dim in dims)
        buckets[key].append(row)

    out: List[JsonDict] = []
    for key, group in sorted(buckets.items()):
        correct_vals = [int(r["correct"]) for r in group if str(r.get("correct", "")) != ""]
        parsed = [int(r["bad_parse"]) for r in group]
        out.append(
            {
                **{dim: value for dim, value in zip(dims, key)},
                "n_pairs": len(group),
                "n_languages": len({r["language"] for r in group}),
                "mean_accuracy_strict": f"{avg(correct_vals):.6f}" if correct_vals else "",
                "bad_parse": sum(parsed),
                "bad_parse_rate": f"{avg(parsed):.6f}",
            }
        )
    return out


def write_per_phenomenon_outputs(e1_root: Path, rows: List[JsonDict]) -> None:
    by_phen: Dict[str, List[JsonDict]] = defaultdict(list)
    for row in rows:
        by_phen[row["phenomenon"]].append(row)

    pair_fields = [
        "phenomenon",
        "language",
        "pair_index",
        "id",
        "source_id",
        "bad_parse",
        "bad_parse_readings",
        "correct",
        "delta",
        "target_role",
        "template",
        "perturbation",
        "good",
        "bad",
    ]
    lang_fields = [
        "language",
        *DIMENSIONS,
        "n_pairs",
        "accuracy_strict",
        "mean_delta_good_minus_bad",
        "bad_parse",
        "bad_skip",
        "bad_parse_rate",
        "accuracy_when_bad_parse",
        "accuracy_when_bad_skip",
    ]
    group_fields_by_strategy_alignment = [
        "strategy",
        "alignment",
        "n_languages",
        "n_pairs",
        "mean_accuracy_strict",
        "bad_parse",
        "bad_parse_rate",
    ]
    group_fields_by_anc_order = [
        "anc_wo",
        "n_languages",
        "n_pairs",
        "mean_accuracy_strict",
        "bad_parse",
        "bad_parse_rate",
    ]
    group_fields_by_anc_tv_order = [
        "anc_tv_order",
        "n_languages",
        "n_pairs",
        "mean_accuracy_strict",
        "bad_parse",
        "bad_parse_rate",
    ]

    for phenomenon, group in by_phen.items():
        out_dir = e1_root / phenomenon / "analysis"
        write_tsv(out_dir / "bad_parse_by_pair.tsv", group, pair_fields)
        lang_rows = summarize_language_phenomenon(group)
        write_tsv(out_dir / "bad_parse_by_language.tsv", lang_rows, lang_fields)
        write_tsv(
            out_dir / "bad_parse_accuracy_by_strategy_alignment.tsv",
            summarize_group(group, ["strategy", "alignment"]),
            group_fields_by_strategy_alignment,
        )
        write_tsv(
            out_dir / "bad_parse_accuracy_by_anc_wo.tsv",
            summarize_group(group, ["anc_wo"]),
            group_fields_by_anc_order,
        )
        write_tsv(
            out_dir / "bad_parse_accuracy_by_anc_tv_order.tsv",
            summarize_group(group, ["anc_tv_order"]),
            group_fields_by_anc_tv_order,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e1-root", default="e1_materials")
    ap.add_argument("--grammars-dir", default="grammars")
    ap.add_argument("--ace", default="bin/ace-0.9.34/ace")
    ap.add_argument("--out-dir", default="e1_materials/analysis")
    ap.add_argument("--cache-dir", default="e1_materials/analysis/bad_parse_cache")
    ap.add_argument("--timeout-per-language", type=int, default=900)
    ap.add_argument("--batch-size", type=int, default=200)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    e1_root = Path(args.e1_root)
    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir)

    rows = collect_pair_rows(e1_root)
    if not rows:
        raise FileNotFoundError(f"No E1 pair rows found under {e1_root}")

    print(f"Loaded pair rows: {len(rows)}", flush=True)
    rows = attach_bad_parse(
        rows=rows,
        ace=Path(args.ace),
        grammars_dir=Path(args.grammars_dir),
        cache_dir=cache_dir,
        timeout=args.timeout_per_language,
        batch_size=args.batch_size,
        resume=not args.no_resume,
    )

    pair_fields = [
        "phenomenon",
        "language",
        "pair_index",
        "id",
        "source_id",
        *DIMENSIONS,
        "bad_parse",
        "bad_parse_readings",
        "correct",
        "delta",
        "target_role",
        "template",
        "perturbation",
        "good",
        "bad",
    ]
    lang_fields = [
        "phenomenon",
        "language",
        *DIMENSIONS,
        "n_pairs",
        "accuracy_strict",
        "mean_delta_good_minus_bad",
        "bad_parse",
        "bad_skip",
        "bad_parse_rate",
        "accuracy_when_bad_parse",
        "accuracy_when_bad_skip",
    ]
    phen_fields = [
        "phenomenon",
        "n_languages",
        "n_pairs",
        "mean_accuracy_strict",
        "bad_parse",
        "bad_skip",
        "bad_parse_rate",
    ]

    write_tsv(out_dir / "e1_bad_parse_by_pair.tsv", rows, pair_fields)
    language_rows = summarize_language_phenomenon(rows)
    write_tsv(out_dir / "e1_language_phenomenon_accuracy_bad_parse.tsv", language_rows, lang_fields)
    write_tsv(out_dir / "e1_phenomenon_bad_parse_summary.tsv", summarize_phenomenon(rows), phen_fields)
    write_tsv(
        out_dir / "e1_bad_parse_by_strategy_alignment.tsv",
        summarize_group(rows, ["phenomenon", "strategy", "alignment"]),
        ["phenomenon", "strategy", "alignment", "n_languages", "n_pairs", "mean_accuracy_strict", "bad_parse", "bad_parse_rate"],
    )
    write_tsv(
        out_dir / "e1_bad_parse_by_clause_np_alignment.tsv",
        summarize_group(rows, ["phenomenon", "clause_wo", "np_wo", "alignment"]),
        ["phenomenon", "clause_wo", "np_wo", "alignment", "n_languages", "n_pairs", "mean_accuracy_strict", "bad_parse", "bad_parse_rate"],
    )
    write_per_phenomenon_outputs(e1_root, rows)

    print(f"Global language table: {out_dir / 'e1_language_phenomenon_accuracy_bad_parse.tsv'}")
    print(f"Global phenomenon table: {out_dir / 'e1_phenomenon_bad_parse_summary.tsv'}")
    print(f"Global pair table: {out_dir / 'e1_bad_parse_by_pair.tsv'}")


if __name__ == "__main__":
    main()
