#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import multiprocessing as mp
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from delphin import ace
from tqdm import tqdm

from utils import ACE_BIN


_WORKER_GRAMMAR: Optional[str] = None
_WORKER_MAX_GEN: int = 200
_WORKER_KEEP_MRS: bool = False
_WORKER_ACE_MODE: str = "oneoff"
_WORKER_RESTART_EVERY: int = 5000
_WORKER_GENERATOR: Any = None
_WORKER_GENERATED_SINCE_RESTART: int = 0


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


def make_generator(grammar_dat: str, max_gen: int) -> Any:
    cmdargs = ["-n", str(max_gen)]

    try:
        return ace.ACEGenerator(
            grammar_dat,
            executable=ACE_BIN,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        return ace.ACEGenerator(
            grammar_dat,
            executable=ACE_BIN,
            cmdargs=cmdargs,
        )


def close_generator(generator: Any) -> None:
    if generator is None:
        return

    close = getattr(generator, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def init_worker(
    grammar_dat: str,
    max_gen: int,
    keep_mrs: bool,
    ace_mode: str,
    restart_every: int,
) -> None:
    global _WORKER_GRAMMAR
    global _WORKER_MAX_GEN
    global _WORKER_KEEP_MRS
    global _WORKER_ACE_MODE
    global _WORKER_RESTART_EVERY
    global _WORKER_GENERATOR
    global _WORKER_GENERATED_SINCE_RESTART

    _WORKER_GRAMMAR = grammar_dat
    _WORKER_MAX_GEN = max_gen
    _WORKER_KEEP_MRS = keep_mrs
    _WORKER_ACE_MODE = ace_mode
    _WORKER_RESTART_EVERY = restart_every
    _WORKER_GENERATOR = None
    _WORKER_GENERATED_SINCE_RESTART = 0


def get_worker_generator() -> Any:
    global _WORKER_GENERATOR
    global _WORKER_GENERATED_SINCE_RESTART

    if _WORKER_GRAMMAR is None:
        raise RuntimeError("Worker grammar was not initialized")

    if _WORKER_GENERATOR is None:
        _WORKER_GENERATOR = make_generator(_WORKER_GRAMMAR, _WORKER_MAX_GEN)
        _WORKER_GENERATED_SINCE_RESTART = 0
        return _WORKER_GENERATOR

    if _WORKER_RESTART_EVERY > 0 and _WORKER_GENERATED_SINCE_RESTART >= _WORKER_RESTART_EVERY:
        close_generator(_WORKER_GENERATOR)
        _WORKER_GENERATOR = make_generator(_WORKER_GRAMMAR, _WORKER_MAX_GEN)
        _WORKER_GENERATED_SINCE_RESTART = 0

    return _WORKER_GENERATOR


def restart_worker_generator() -> None:
    global _WORKER_GENERATOR
    global _WORKER_GENERATED_SINCE_RESTART

    close_generator(_WORKER_GENERATOR)
    _WORKER_GENERATOR = None
    _WORKER_GENERATED_SINCE_RESTART = 0


def generate_results_persistent(mrs: str) -> List[Dict[str, Any]]:
    global _WORKER_GENERATED_SINCE_RESTART

    if not isinstance(mrs, str) or not mrs.strip():
        return []

    generator = get_worker_generator()

    try:
        resp = generator.interact(mrs)
    except Exception:
        restart_worker_generator()
        generator = get_worker_generator()
        resp = generator.interact(mrs)

    _WORKER_GENERATED_SINCE_RESTART += 1

    results = resp.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def process_row(task: Tuple[str, int, bool, str, Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
      ("skipped", None)
      ("ok", out_entry)
      ("overgen", out_entry)
    """
    grammar, max_gen, keep_mrs, ace_mode, row = task

    mrs_id = row.get("id")
    mrs = row.get("mrs")

    if mrs_id is None or not isinstance(mrs, str) or not mrs.strip():
        return ("skipped", None)

    try:
        if ace_mode == "persistent":
            results = generate_results_persistent(mrs)
        else:
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

    for key in ("source_id", "pseudo_index", "sentence", "pseudo_english"):
        if key in row:
            out_entry[key] = row[key]

    if keep_mrs:
        out_entry["mrs"] = mrs

    if len(surfaces) > 1:
        return ("overgen", out_entry)
    return ("ok", out_entry)


def process_row_worker(row: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    if _WORKER_GRAMMAR is None:
        raise RuntimeError("Worker grammar was not initialized")

    return process_row(
        (
            _WORKER_GRAMMAR,
            _WORKER_MAX_GEN,
            _WORKER_KEEP_MRS,
            _WORKER_ACE_MODE,
            row,
        )
    )


def process_chunk_worker(chunk: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, Optional[Dict[str, Any]]]], int]:
    return [process_row_worker(row) for row in chunk], len(chunk)


def iter_row_chunks(
    in_path: Path,
    done_ids: Set[Any],
    skip_done: bool,
    chunksize: int,
) -> Iterator[List[Dict[str, Any]]]:
    chunk: List[Dict[str, Any]] = []

    for row in iter_rows(in_path):
        if skip_done:
            row_id = row.get("id")
            if row_id in done_ids:
                continue

        chunk.append(row)

        if len(chunk) >= chunksize:
            yield chunk
            chunk = []

    if chunk:
        yield chunk


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
    ap.add_argument(
        "--ace-mode",
        choices=("oneoff", "persistent"),
        default="oneoff",
        help="Use one ACE process per item, or keep one ACEGenerator per worker. Default: oneoff",
    )
    ap.add_argument(
        "--restart-every",
        type=int,
        default=5000,
        help="In persistent mode, restart each worker's ACEGenerator after this many items. Use 0 to disable.",
    )

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

    if args.restart_every < 0:
        raise ValueError("--restart-every must be >= 0")

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

    chunk_iter = iter_row_chunks(
        in_path=in_path,
        done_ids=done_ids,
        skip_done=args.resume,
        chunksize=args.chunksize,
    )

    start_time = time.time()
    ctx = mp.get_context("spawn")

    with out_path.open(mode, encoding="utf-8") as f:
        with ctx.Pool(
            processes=args.workers,
            initializer=init_worker,
            initargs=(
                args.grammar,
                args.max_gen,
                not args.no_mrs,
                args.ace_mode,
                args.restart_every,
            ),
        ) as pool:
            results_iter = pool.imap(process_chunk_worker, chunk_iter, chunksize=1)

            if use_tqdm:
                iterator = tqdm(
                    results_iter,
                    total=total_remaining,
                    desc="Generating sentences",
                    dynamic_ncols=True,
                )
                for chunk_results, n_input in iterator:
                    processed_rows += n_input
                    iterator.update(n_input - 1)

                    for status, out_entry in chunk_results:
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
                for chunk_results, n_input in results_iter:
                    processed_rows += n_input

                    if args.log_every > 0 and processed_rows % args.log_every == 0:
                        log_progress(processed_rows, total_remaining, start_time)

                    for status, out_entry in chunk_results:
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
