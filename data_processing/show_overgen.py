#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
out_path = path.with_name(path.stem + "_overgenerate.jsonl")

overgenerated = []
total_overgenerated = 0
duplicate_overgenerated = 0

with path.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        row = json.loads(line)
        sents = row.get("sent", [])

        if not isinstance(sents, list) or len(sents) <= 1:
            continue

        total_overgenerated += 1

        unique_sents = list(dict.fromkeys(sents))
        has_duplicate = len(unique_sents) < len(sents)

        if has_duplicate:
            duplicate_overgenerated += 1

        saved_row = {
            "id": row.get("id"),
            "sent": sents,
            "num_sent": len(sents),
            "num_unique_sent": len(unique_sents),
            "has_duplicate": has_duplicate,
        }
        overgenerated.append(saved_row)

with out_path.open("w", encoding="utf-8") as f:
    for row in overgenerated:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

ratio = (
    duplicate_overgenerated / total_overgenerated
    if total_overgenerated > 0 else 0.0
)

print(f"saved overgenerated samples to: {out_path}")
print(f"total overgenerated samples: {total_overgenerated}")
print(f"samples with duplicate sentences: {duplicate_overgenerated}")
print(f"duplicate ratio: {ratio:.4%}")