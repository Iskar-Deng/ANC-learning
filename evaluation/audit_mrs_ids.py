#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict, Counter
from pathlib import Path

def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                yield line_no, None, "json_error"
                continue
            yield line_no, obj, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", default="results/mrs_audit")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    id_to_lines = defaultdict(list)
    id_to_mrs = defaultdict(set)
    bad_rows = []

    total_rows = 0
    valid_json_rows = 0
    rows_with_id = 0
    rows_with_mrs = 0

    for line_no, obj, err in iter_jsonl(in_path):
        total_rows += 1

        if err is not None or not isinstance(obj, dict):
            bad_rows.append({
                "line_no": line_no,
                "error": err or "not_object",
            })
            continue

        valid_json_rows += 1

        row_id = obj.get("id")
        mrs = obj.get("mrs")

        if row_id is None:
            bad_rows.append({
                "line_no": line_no,
                "error": "missing_id",
            })
        else:
            rows_with_id += 1
            id_to_lines[row_id].append(line_no)

        if not isinstance(mrs, str) or not mrs.strip():
            bad_rows.append({
                "line_no": line_no,
                "id": row_id,
                "error": "missing_or_empty_mrs",
            })
        else:
            rows_with_mrs += 1
            if row_id is not None:
                id_to_mrs[row_id].add(mrs)

    ids = list(id_to_lines.keys())

    int_ids = []
    non_int_ids = []
    for x in ids:
        if isinstance(x, int):
            int_ids.append(x)
        elif isinstance(x, str):
            try:
                int_ids.append(int(x))
            except ValueError:
                non_int_ids.append(x)
        else:
            non_int_ids.append(x)

    duplicate_ids = {
        row_id: lines
        for row_id, lines in id_to_lines.items()
        if len(lines) > 1
    }

    ids_with_multiple_mrs = {
        row_id: {
            "n_mrs": len(mrs_set),
            "lines": id_to_lines[row_id],
        }
        for row_id, mrs_set in id_to_mrs.items()
        if len(mrs_set) > 1
    }

    missing_ids = []
    if int_ids:
        min_id = min(int_ids)
        max_id = max(int_ids)
        observed = set(int_ids)
        missing_ids = [
            i for i in range(min_id, max_id + 1)
            if i not in observed
        ]
    else:
        min_id = None
        max_id = None

    summary = {
        "input": str(in_path),
        "total_rows": total_rows,
        "valid_json_rows": valid_json_rows,
        "rows_with_id": rows_with_id,
        "rows_with_mrs": rows_with_mrs,
        "unique_ids": len(ids),
        "duplicate_id_count": len(duplicate_ids),
        "ids_with_multiple_mrs_count": len(ids_with_multiple_mrs),
        "non_int_id_count": len(non_int_ids),
        "min_int_id": min_id,
        "max_int_id": max_id,
        "missing_id_count_between_min_and_max": len(missing_ids),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with open(out_dir / "duplicate_ids.jsonl", "w", encoding="utf-8") as f:
        for row_id, lines in sorted(duplicate_ids.items(), key=lambda x: str(x[0])):
            f.write(json.dumps({
                "id": row_id,
                "count": len(lines),
                "lines": lines,
            }, ensure_ascii=False) + "\n")

    with open(out_dir / "ids_with_multiple_mrs.jsonl", "w", encoding="utf-8") as f:
        for row_id, info in sorted(ids_with_multiple_mrs.items(), key=lambda x: str(x[0])):
            f.write(json.dumps({
                "id": row_id,
                **info,
            }, ensure_ascii=False) + "\n")

    with open(out_dir / "missing_ids.jsonl", "w", encoding="utf-8") as f:
        for row_id in missing_ids:
            f.write(json.dumps({"id": row_id}, ensure_ascii=False) + "\n")

    with open(out_dir / "bad_rows.jsonl", "w", encoding="utf-8") as f:
        for row in bad_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if non_int_ids:
        with open(out_dir / "non_int_ids.jsonl", "w", encoding="utf-8") as f:
            for row_id in non_int_ids:
                f.write(json.dumps({"id": row_id}, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()