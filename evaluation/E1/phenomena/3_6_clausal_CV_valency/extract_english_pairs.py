#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


PHENOMENON = "3_6_clausal_CV_valency"
TSV_NAME = "cv_valency_pairs.tsv"
DEFAULT_REF_LANGUAGE = "00_sov_gn_ac_b_se"


JsonDict = Dict[str, Any]


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def iter_jsonl(path: Path) -> Iterable[JsonDict]:
    with path.open(encoding="utf-8") as infile:
        for line_no, raw in enumerate(infile, start=1):
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            yield row


def row_pair_id(row: JsonDict) -> int:
    for key in ("source_id", "source_index", "id"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
    raise ValueError(f"Could not infer cv_valency pair_id from row: {row}")


def sampled_ids(path: Path) -> List[int]:
    return [row_pair_id(row) for row in iter_jsonl(path)]


def load_cv_rows(path: Path) -> Dict[int, Dict[str, str]]:
    rows: Dict[int, Dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile, delimiter="\t")
        for row in reader:
            rows[int(row["pair_id"])] = row
    return rows


def validate_parallel_ids(pairs_dir: Path, ref_ids: List[int]) -> None:
    files = sorted(pairs_dir.glob("*.pairs.jsonl"))
    if not files:
        raise ValueError(f"No pair files found in {pairs_dir}")

    different: List[str] = []
    for path in files:
        if sampled_ids(path) != ref_ids:
            different.append(path.name)

    if different:
        preview = ", ".join(different[:10])
        raise ValueError(
            "Sampled CV id sequence differs across languages; "
            f"first differing files: {preview}"
        )


def build_rows(ids: List[int], cv_rows: Dict[int, Dict[str, str]]) -> List[JsonDict]:
    out: List[JsonDict] = []
    for i, pair_id in enumerate(ids, start=1):
        if pair_id not in cv_rows:
            raise ValueError(f"Sampled CV pair_id not found in TSV: {pair_id}")
        row = cv_rows[pair_id]
        out.append(
            {
                "pair_index": i,
                "phenomenon": PHENOMENON,
                "pair_id": row["pair_id"],
                "cv_stem": row.get("cv_stem", ""),
                "tv_foil_stem": row.get("tv_foil_stem", ""),
                "embedded_type": row.get("embedded_type", ""),
                "cv_thatS_mean": row.get("cv_thatS_mean", ""),
                "tv_NPVNP_mean": row.get("tv_NPVNP_mean", ""),
                "tv_thatS_mean": row.get("tv_thatS_mean", ""),
                "good": row["good_source"],
                "bad": row["bad_source"],
            }
        )
    return out


def write_jsonl(path: Path, rows: Iterable[JsonDict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as outfile:
        for row in rows:
            outfile.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    root = project_root()
    default_pairs_dir = root / "e1_materials" / PHENOMENON / "pairs"
    default_tsv = Path(__file__).with_name(TSV_NAME)
    default_out = root / "e1_materials" / PHENOMENON / "english_pairs" / "pairs.jsonl"

    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-dir", default=str(default_pairs_dir))
    ap.add_argument("--tsv", default=str(default_tsv))
    ap.add_argument("--out", default=str(default_out))
    ap.add_argument("--ref-language", default=DEFAULT_REF_LANGUAGE)
    ap.add_argument("--no-check-parallel-ids", action="store_true")
    args = ap.parse_args()

    pairs_dir = Path(args.pairs_dir)
    ref_path = pairs_dir / f"{args.ref_language}.pairs.jsonl"
    if not ref_path.is_file():
        raise FileNotFoundError(f"Reference pair file not found: {ref_path}")

    ids = sampled_ids(ref_path)
    if not args.no_check_parallel_ids:
        validate_parallel_ids(pairs_dir, ids)

    rows = build_rows(ids, load_cv_rows(Path(args.tsv)))
    count = write_jsonl(Path(args.out), rows)
    print(json.dumps({"out": args.out, "written": count}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
