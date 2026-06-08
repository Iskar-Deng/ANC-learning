#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.E1.language_config import config_for_language


JsonDict = Dict[str, Any]


def iter_jsonl(path: Path) -> Iterator[JsonDict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {path} line {line_no}: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"Line {line_no} in {path} is not a JSON object")
            yield obj


def load_rules(phenomenon_dir: Path):
    rules_path = phenomenon_dir / "rules.py"
    if not rules_path.is_file():
        raise FileNotFoundError(f"Missing perturbation rules: {rules_path}")

    spec = importlib.util.spec_from_file_location("e1_phenomenon_rules", rules_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import rules from {rules_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    perturb = getattr(module, "perturb", None)
    if not callable(perturb):
        raise AttributeError(f"{rules_path} must define callable perturb()")

    return module


def get_good_sentence(row: JsonDict) -> str:
    sent = row.get("good", row.get("sent"))
    if not isinstance(sent, str) or not sent.strip():
        raise ValueError(f"Input row missing non-empty 'good' or 'sent': {row}")
    return sent.strip()


def get_source_index(row: JsonDict, fallback_index: int) -> int:
    for key in ("source_index", "source_id", "template_index", "template_id", "id"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                continue
    return fallback_index


def infer_language_from_path(path: Path) -> str | None:
    name = path.name
    if name.endswith(".jsonl"):
        return name[:-6]
    return None


def load_rows(path: Path, language_arg: str | None) -> List[JsonDict]:
    rows: List[JsonDict] = []
    inferred_language = language_arg or infer_language_from_path(path)

    for row in iter_jsonl(path):
        row = dict(row)

        language = row.get("language") or row.get("language_id") or inferred_language
        if not isinstance(language, str) or not language.strip():
            raise ValueError(
                "Input row missing language, and language could not be inferred "
                f"from path: {path}"
            )

        row["language"] = language
        rows.append(row)

    return rows


def sample_rows(rows: List[JsonDict], sample_size: int | None, seed: int) -> List[JsonDict]:
    shuffled = rows[:]
    rng = random.Random(seed)
    rng.shuffle(shuffled)

    if sample_size is None:
        return shuffled

    if sample_size < 1:
        raise ValueError(f"--sample-size must be >= 1, got {sample_size}")

    return shuffled[:sample_size]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenomenon-dir", required=True)
    ap.add_argument("--good-items", required=True, help="JSONL with sent/good field")
    ap.add_argument("--out", required=True)

    ap.add_argument(
        "--language",
        default=None,
        help=(
            "Language id. Optional if each input row has language/language_id, "
            "or if --good-items filename is <language>.jsonl."
        ),
    )
    ap.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Shuffle rows and keep this many. Use 0 with --all instead if needed.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Use all rows after shuffling; overrides --sample-size.",
    )
    ap.add_argument("--seed", type=int, default=42)

    args = ap.parse_args()

    phenomenon_dir = Path(args.phenomenon_dir)
    good_path = Path(args.good_items)
    out_path = Path(args.out)

    rules = load_rules(phenomenon_dir)
    phenomenon_id = getattr(rules, "PHENOMENON_ID", phenomenon_dir.name)
    phenomenon_name = getattr(rules, "PHENOMENON_NAME", phenomenon_id)

    rows = load_rows(good_path, args.language)
    sample_size = None if args.all else args.sample_size
    selected_rows = sample_rows(rows, sample_size=sample_size, seed=args.seed)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for pair_index, row in enumerate(selected_rows, start=1):
            language = row["language"]
            source_index = get_source_index(row, pair_index)
            good = get_good_sentence(row)
            config = config_for_language(language)

            perturbation = rules.perturb(
                good_sentence=good,
                language_config=config,
                source_index=source_index,
                row=row,
            )

            if isinstance(perturbation, str):
                bad = perturbation
                metadata: JsonDict = {}
            elif isinstance(perturbation, dict):
                bad = perturbation.get("bad")
                metadata = dict(perturbation)
                metadata.pop("bad", None)
            else:
                raise TypeError("perturb() must return a bad sentence string or a dict")

            if not isinstance(bad, str) or not bad.strip():
                raise ValueError(f"perturb() returned invalid bad sentence for row: {row}")

            out_row = {
                **row,
                "phenomenon_id": phenomenon_id,
                "phenomenon_name": phenomenon_name,
                "pair_index": pair_index,
                "language": language,
                "source_index": source_index,
                "good": good,
                "bad": bad.strip(),
                **metadata,
            }
            f.write(json.dumps(out_row, ensure_ascii=False) + "\n")

    print(f"Loaded rows: {len(rows)}")
    print(f"Wrote pairs: {len(selected_rows)}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()