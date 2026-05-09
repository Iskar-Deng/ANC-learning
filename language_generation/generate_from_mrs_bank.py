#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from delphin import ace
from tqdm import tqdm

from utils import ACE_BIN


def iter_rows(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def count_rows(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                count += 1
    return count


def load_done_ids(path: Path) -> Set[Any]:
    done: Set[Any] = set()
    if not path.exists():
        return done

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "id" in obj:
                done.add(obj["id"])
    return done


def generate_results(grammar_dat: str, mrs: str, max_gen: int) -> List[Dict[str, Any]]:
    if not isinstance(mrs, str) or not mrs.strip():
        return []

    cmdargs = ["-n", str(max_gen)]

    try:
        resp = ace.generate(
            grammar_dat,
            mrs,
            executable=ACE_BIN,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        resp = ace.generate(
            grammar_dat,
            mrs,
            executable=ACE_BIN,
            cmdargs=cmdargs,
        )

    results = resp.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def process_row(task: Tuple[str, int, bool, Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
      ("skipped", None)
      ("ok", out_entry)
      ("overgen", out_entry)
    """
    grammar, max_gen, keep_mrs, row = task

    mrs_id = row.get("id")
    mrs = row.get("mrs")

    if mrs_id is None or not isinstance(mrs, str) or not mrs.strip():
        return ("skipped", None)

    try:
        results = generate_results(grammar, mrs, max_gen)
    except Exception:
        return ("skipped", None)

    seen = set()
    surfaces = []

    for r in results:
        surf = r.get("surface")
        if isinstance(surf, str) and surf and surf not in seen:
            seen.add(surf)
            surfaces.append(surf)

    out_entry = {
        "id": mrs_id,
        "sent": surfaces,
    }

    if keep_mrs:
        out_entry["mrs"] = mrs

    if len(surfaces) > 1:
        return ("overgen", out_entry)
    return ("ok", out_entry)


def build_task_iter(
    in_path: Path,
    grammar: str,
    max_gen: int,
    keep_mrs: bool,
    done_ids: Set[Any],
    skip_done: bool,
) -> Iterator[Tuple[str, int, bool, Dict[str, Any]]]:
    for row in iter_rows(in_path):
        if skip_done:
            row_id = row.get("id")
            if row_id in done_ids:
                continue
        yield (grammar, max_gen, keep_mrs, row)


def log_progress(processed: int, total: Optional[int], start_time: float) -> None:
    elapsed = time.time() - start_time
    speed = processed / elapsed if elapsed > 0 else 0.0

    if total is not None and total > 0:
        pct = processed / total * 100
        print(
            f"[progress] {processed}/{total} ({pct:.2f}%) | "
            f"{speed:.2f} rows/s | elapsed {elapsed:.1f}s",
            flush=True,
        )
    else:
        print(
            f"[progress] {processed} rows | "
            f"{speed:.2f} rows/s | elapsed {elapsed:.1f}s",
            flush=True,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-gen", type=int, default=200)

    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunksize", type=int, default=50)

    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--no-mrs", action="store_true")
    ap.add_argument("--print-sentences", action="store_true")
    ap.add_argument("--no-count", action="store_true")
    ap.add_argument(
        "--log-every",
        type=int,
        default=1000,
        help="In non-TTY mode, print progress every N processed rows",
    )

    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done_ids: Set[Any] = set()
    resumed_count = 0

    if args.resume:
        done_ids = load_done_ids(out_path)
        resumed_count = len(done_ids)
        print(f"Resume enabled. Found {resumed_count} completed ids in existing output.", flush=True)

    total_rows = None if args.no_count else count_rows(in_path)
    total_remaining = None
    if total_rows is not None:
        total_remaining = max(total_rows - resumed_count, 0)

    skipped_rows = 0
    overgen_rows = 0
    kept_rows = 0
    processed_rows = 0

    use_tqdm = sys.stderr.isatty()

    if args.print_sentences:
        print(" id  gen  sentences", flush=True)
        print("--  ---  ------------------------------", flush=True)

    mode = "a" if args.resume else "w"

    task_iter = build_task_iter(
        in_path=in_path,
        grammar=args.grammar,
        max_gen=args.max_gen,
        keep_mrs=not args.no_mrs,
        done_ids=done_ids,
        skip_done=args.resume,
    )

    start_time = time.time()

    with out_path.open(mode, encoding="utf-8") as f:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            results_iter = ex.map(process_row, task_iter, chunksize=args.chunksize)

            if use_tqdm:
                iterator = tqdm(
                    results_iter,
                    total=total_remaining,
                    desc="Generating sentences",
                    dynamic_ncols=True,
                )
                for status, out_entry in iterator:
                    processed_rows += 1

                    if status == "skipped" or out_entry is None:
                        skipped_rows += 1
                        continue

                    if status == "overgen":
                        overgen_rows += 1

                    if args.print_sentences:
                        mrs_id = out_entry["id"]
                        surfaces = out_entry["sent"]
                        sent_str = ", ".join(surfaces) if surfaces else "-"
                        print(f"{mrs_id:>2}  {len(surfaces):<3}  {sent_str}", flush=True)

                    f.write(json.dumps(out_entry, ensure_ascii=False) + "\n")
                    kept_rows += 1
            else:
                for status, out_entry in results_iter:
                    processed_rows += 1

                    if args.log_every > 0 and processed_rows % args.log_every == 0:
                        log_progress(processed_rows, total_remaining, start_time)

                    if status == "skipped" or out_entry is None:
                        skipped_rows += 1
                        continue

                    if status == "overgen":
                        overgen_rows += 1

                    if args.print_sentences:
                        mrs_id = out_entry["id"]
                        surfaces = out_entry["sent"]
                        sent_str = ", ".join(surfaces) if surfaces else "-"
                        print(f"{mrs_id:>2}  {len(surfaces):<3}  {sent_str}", flush=True)

                    f.write(json.dumps(out_entry, ensure_ascii=False) + "\n")
                    kept_rows += 1

                if processed_rows > 0 and (args.log_every <= 0 or processed_rows % args.log_every != 0):
                    log_progress(processed_rows, total_remaining, start_time)

    total_for_ratio = kept_rows + skipped_rows
    skip_ratio = (skipped_rows / total_for_ratio) if total_for_ratio > 0 else 0.0
    overgen_ratio = (overgen_rows / kept_rows) if kept_rows > 0 else 0.0

    print("\nDone.", flush=True)
    if args.resume:
        print(f"Previously completed: {resumed_count}", flush=True)
    print(f"Newly saved: {kept_rows}", flush=True)
    print(f"Skipped in this run: {skipped_rows} ({skip_ratio:.2%})", flush=True)
    print(f"Overgenerated in this run: {overgen_rows} ({overgen_ratio:.2%})", flush=True)
    print(f"Output: {out_path}", flush=True)


if __name__ == "__main__":
    main()