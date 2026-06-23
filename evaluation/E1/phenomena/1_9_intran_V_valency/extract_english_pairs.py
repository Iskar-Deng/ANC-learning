#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PHENOMENON = "1_9_intran_V_valency"
TSV_NAME = "blimp_valency.tsv"
DEFAULT_REF_LANGUAGE = "00_sov_gn_ac_b_se"


JsonDict = Dict[str, Any]
PairKey = Tuple[str, str]


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


def sampled_keys(path: Path) -> List[PairKey]:
    keys: List[PairKey] = []
    for row in iter_jsonl(path):
        source_uid = row.get("blimp_source_uid")
        pair_id = row.get("blimp_pair_id")
        if not isinstance(source_uid, str) or pair_id is None:
            raise ValueError(f"Missing BLiMP key in {path}: {row}")
        keys.append((source_uid, str(pair_id)))
    return keys


def load_blimp_rows(path: Path) -> Dict[PairKey, Dict[str, str]]:
    rows: Dict[PairKey, Dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile, delimiter="\t")
        for row in reader:
            key = (row["source_uid"], str(row["pair_id"]))
            rows[key] = row
    return rows


def validate_parallel_ids(pairs_dir: Path, ref_keys: List[PairKey]) -> None:
    files = sorted(pairs_dir.glob("*.pairs.jsonl"))
    if not files:
        raise ValueError(f"No pair files found in {pairs_dir}")

    different: List[str] = []
    for path in files:
        if sampled_keys(path) != ref_keys:
            different.append(path.name)

    if different:
        preview = ", ".join(different[:10])
        raise ValueError(
            "Sampled BLiMP id sequence differs across languages; "
            f"first differing files: {preview}"
        )


def build_rows(keys: List[PairKey], blimp_rows: Dict[PairKey, Dict[str, str]]) -> List[JsonDict]:
    out: List[JsonDict] = []
    for i, key in enumerate(keys, start=1):
        if key not in blimp_rows:
            raise ValueError(f"Sampled BLiMP key not found in TSV: {key}")
        row = blimp_rows[key]
        out.append(
            {
                "pair_index": i,
                "phenomenon": PHENOMENON,
                "source_uid": row["source_uid"],
                "pair_id": row["pair_id"],
                "row_id": row.get("row_id", ""),
                "good_stem": row.get("good_stem", ""),
                "bad_stem": row.get("bad_stem", ""),
                "good": row["sentence_good"],
                "bad": row["sentence_bad"],
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

    keys = sampled_keys(ref_path)
    if not args.no_check_parallel_ids:
        validate_parallel_ids(pairs_dir, keys)

    rows = build_rows(keys, load_blimp_rows(Path(args.tsv)))
    count = write_jsonl(Path(args.out), rows)
    print(json.dumps({"out": args.out, "written": count}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
