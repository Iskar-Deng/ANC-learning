#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set


JsonDict = Dict[str, Any]


def load_jsonl(path: Path) -> List[JsonDict]:
    rows: List[JsonDict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num} in {path}: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"Line {line_num} in {path} is not a JSON object")
            rows.append(obj)
    return rows


def write_jsonl(rows: List[JsonDict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_empty_selected_sent(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Original source JSONL, e.g. data/train_mrs.jsonl")
    ap.add_argument(
        "--selected",
        required=True,
        help="Selected output JSONL, e.g. data/train_mrs-test-hebrew-selected.jsonl",
    )
    ap.add_argument("--out", required=True, help="Output JSONL for empty ids traced from source")
    args = ap.parse_args()

    source_path = Path(args.source)
    selected_path = Path(args.selected)
    out_path = Path(args.out)

    source_rows = load_jsonl(source_path)
    selected_rows = load_jsonl(selected_path)

    empty_ids: Set[Any] = set()
    for row in selected_rows:
        row_id = row.get("id")
        if row_id is None:
            continue
        if is_empty_selected_sent(row.get("sent")):
            empty_ids.add(row_id)

    out_rows: List[JsonDict] = []
    for row in source_rows:
        row_id = row.get("id")
        if row_id in empty_ids:
            out_rows.append(row)

    write_jsonl(out_rows, out_path)

    print(f"Source rows: {len(source_rows)}")
    print(f"Selected rows: {len(selected_rows)}")
    print(f"Empty ids in selected: {len(empty_ids)}")
    print(f"Output rows written: {len(out_rows)}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()