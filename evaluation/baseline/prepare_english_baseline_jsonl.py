#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a plain-text corpus to train/dev JSONL files compatible "
            "with training.train_lm."
        )
    )
    parser.add_argument("--input", default="data/train.txt")
    parser.add_argument("--out-dir", default="data/english_baseline")
    parser.add_argument("--text-field", default="sent")
    parser.add_argument("--dev-size", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing train.jsonl/dev.jsonl/stats.json.",
    )
    return parser.parse_args()


def iter_clean_lines(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8") as infile:
        for raw in infile:
            line = raw.strip()
            if line:
                yield line


def count_clean_lines(path: Path) -> int:
    return sum(1 for _ in iter_clean_lines(path))


def write_jsonl_row(outfile, text_field: str, text: str) -> None:
    outfile.write(json.dumps({text_field: text}, ensure_ascii=False) + "\n")


def refuse_overwrite(paths: Iterable[Path]) -> None:
    existing = [path for path in paths if path.exists()]
    if existing:
        joined = "\n  ".join(str(path) for path in existing)
        raise FileExistsError(
            "Output files already exist. Use --overwrite to replace them:\n  "
            + joined
        )


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    train_path = out_dir / "train.jsonl"
    dev_path = out_dir / "dev.jsonl"
    stats_path = out_dir / "stats.json"

    if not input_path.is_file():
        raise FileNotFoundError(f"Input not found: {input_path}")

    if args.dev_size < 1:
        raise ValueError("--dev-size must be >= 1")

    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.overwrite:
        refuse_overwrite([train_path, dev_path, stats_path])

    print(f"Counting non-empty lines: {input_path}")
    n_lines = count_clean_lines(input_path)
    if args.dev_size >= n_lines:
        raise ValueError(
            f"--dev-size ({args.dev_size}) must be smaller than clean line count ({n_lines})"
        )

    rng = random.Random(args.seed)
    dev_indices = set(rng.sample(range(n_lines), args.dev_size))

    train_count = 0
    dev_count = 0

    print(f"Writing train/dev JSONL to: {out_dir}")
    with train_path.open("w", encoding="utf-8") as train_f, dev_path.open(
        "w", encoding="utf-8"
    ) as dev_f:
        for clean_index, text in enumerate(iter_clean_lines(input_path)):
            if clean_index in dev_indices:
                write_jsonl_row(dev_f, args.text_field, text)
                dev_count += 1
            else:
                write_jsonl_row(train_f, args.text_field, text)
                train_count += 1

    stats: Dict[str, Any] = {
        "input": str(input_path),
        "out_dir": str(out_dir),
        "text_field": args.text_field,
        "seed": args.seed,
        "clean_lines": n_lines,
        "train_lines": train_count,
        "dev_lines": dev_count,
        "dev_size_requested": args.dev_size,
        "train_path": str(train_path),
        "dev_path": str(dev_path),
    }
    with stats_path.open("w", encoding="utf-8") as stats_f:
        json.dump(stats, stats_f, indent=2, ensure_ascii=False)
        stats_f.write("\n")

    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
