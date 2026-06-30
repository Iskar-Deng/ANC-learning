#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parse pseudo-English JSONL with an ACE grammar and write MRS JSONL.

Single-process example:

python -m semantic_extraction.parse_pseudo_with_grammar \
  --grammar grammars/pseudo-english/pseudo-english.dat \
  --input data/sample/sample_pseudo.jsonl \
  --out data/sample/sample_mrs.jsonl \
  --max-parses 20

Parallel example:

python -m semantic_extraction.parse_pseudo_with_grammar \
  --grammar grammars/pseudo-english/pseudo-english.dat \
  --input data/train/train_pseudo.jsonl \
  --out data/train/train_mrs.jsonl \
  --max-parses 20 \
  --workers 12 \
  --chunksize 100 \
  --restart-every 5000
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from delphin import ace
from tqdm import tqdm

from utils import ACE_BIN, MRS_REWRITE_RULES


JsonDict = Dict[str, Any]


# Worker globals. Each worker owns one ACEParser and restarts it periodically.
_WORKER_GRAMMAR: Optional[str] = None
_WORKER_MAX_PARSES: int = 20
_WORKER_FIRST_PARSE_ONLY: bool = False
_WORKER_SKIP_FAILED: bool = False
_WORKER_RESTART_EVERY: int = 5000
_WORKER_PREFER_ANC_SOURCE_CONSTRUCTION: Optional[str] = None
_WORKER_PARSER: Any = None
_WORKER_PARSED_SINCE_RESTART: int = 0


def iter_pseudo_jsonl(path: Path) -> Iterator[JsonDict]:
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

            pseudo = obj.get("pseudo_english")
            if not isinstance(pseudo, str) or not pseudo.strip():
                continue

            yield obj


def count_valid_pseudo_rows(path: Path) -> int:
    count = 0
    for _ in iter_pseudo_jsonl(path):
        count += 1
    return count


def normalize_mrs(mrs: str) -> str:
    for src, tgt in MRS_REWRITE_RULES:
        mrs = mrs.replace(src, tgt)

    mrs = re.sub(r"ICONS:\s*<[^>]*>", "ICONS: < >", mrs, flags=re.DOTALL)
    return mrs


def extract_sentence_id(row: JsonDict, fallback: int) -> int:
    id_value = row.get("id")
    if isinstance(id_value, int):
        return id_value
    return fallback


def extract_source_sentence(row: JsonDict) -> Optional[str]:
    sent = row.get("sentence")
    if isinstance(sent, str):
        return sent
    return None


def extract_pseudo_sentence(row: JsonDict) -> str:
    pseudo = row.get("pseudo_english")
    if not isinstance(pseudo, str):
        raise ValueError("Missing or invalid 'pseudo_english'")
    return pseudo.strip()


def carryover_metadata(row: JsonDict) -> JsonDict:
    metadata: JsonDict = {}
    for key in ("source_id", "pseudo_index"):
        if key in row:
            metadata[key] = row[key]
    return metadata


def strip_pseudo_marker(token: str) -> str:
    for marker in ("ca", "ge", "ob"):
        if token.endswith(marker) and len(token) > len(marker):
            return token[: -len(marker)]
    return token


def extract_nmz_stems(pseudo_sentence: str) -> List[str]:
    stems: List[str] = []
    for raw_token in pseudo_sentence.split():
        token = strip_pseudo_marker(raw_token.lower())
        if token.endswith("nmz") and len(token) > 3:
            stems.append(token[:-3])
    return stems


def rel_segment_for_pred(mrs: str, pred: str) -> str | None:
    pred_text = f'"_{pred}_v_rel"'
    pred_index = mrs.find(pred_text)
    if pred_index < 0:
        return None

    next_rel = mrs.find(" ]  [", pred_index)
    if next_rel < 0:
        next_rel = mrs.find(" ] >", pred_index)
    if next_rel < 0:
        return mrs[pred_index:]

    return mrs[pred_index:next_rel]


def result_matches_anc_construction(
    result: JsonDict,
    stems: List[str],
    construction: str,
) -> bool:
    mrs = result.get("mrs")
    if not isinstance(mrs, str):
        return False

    for stem in stems:
        segment = rel_segment_for_pred(mrs, stem)
        if segment is None:
            return False
        has_arg2 = " ARG2:" in segment
        if construction == "iv" and has_arg2:
            return False
        if construction == "tv" and not has_arg2:
            return False
    return True


def prefer_anc_parse_results(
    row: JsonDict,
    results: List[JsonDict],
    preferred_construction: str | None,
) -> List[JsonDict]:
    if preferred_construction is None or not results:
        return results

    pseudo_sentence = extract_pseudo_sentence(row)
    stems = extract_nmz_stems(pseudo_sentence)
    if not stems:
        return results

    preferred: List[JsonDict] = []
    other: List[JsonDict] = []
    for result in results:
        if result_matches_anc_construction(result, stems, preferred_construction):
            preferred.append(result)
        else:
            other.append(result)

    if not preferred:
        return results
    return preferred + other


def make_parser(grammar_dat: str, max_parses: int) -> Any:
    cmdargs = ["-n", str(max_parses)]

    try:
        return ace.ACEParser(
            grammar_dat,
            executable=ACE_BIN,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        return ace.ACEParser(
            grammar_dat,
            executable=ACE_BIN,
            cmdargs=cmdargs,
        )


def close_parser(parser: Any) -> None:
    if parser is None:
        return

    close = getattr(parser, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def parse_with_oneoff(grammar_dat: str, sent: str, max_parses: int) -> List[JsonDict]:
    """
    Conservative fallback: parse one sentence with ace.parse().
    This is slower but useful if persistent ACEParser fails.
    """
    cmdargs = ["-n", str(max_parses)]

    try:
        resp = ace.parse(
            grammar_dat,
            sent,
            executable=ACE_BIN,
            cmdargs=cmdargs,
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        resp = ace.parse(
            grammar_dat,
            sent,
            executable=ACE_BIN,
            cmdargs=cmdargs,
        )

    results = resp.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def init_worker(
    grammar_dat: str,
    max_parses: int,
    first_parse_only: bool,
    skip_failed: bool,
    restart_every: int,
    prefer_anc_source_construction: str | None,
) -> None:
    global _WORKER_GRAMMAR
    global _WORKER_MAX_PARSES
    global _WORKER_FIRST_PARSE_ONLY
    global _WORKER_SKIP_FAILED
    global _WORKER_RESTART_EVERY
    global _WORKER_PREFER_ANC_SOURCE_CONSTRUCTION
    global _WORKER_PARSER
    global _WORKER_PARSED_SINCE_RESTART

    _WORKER_GRAMMAR = grammar_dat
    _WORKER_MAX_PARSES = max_parses
    _WORKER_FIRST_PARSE_ONLY = first_parse_only
    _WORKER_SKIP_FAILED = skip_failed
    _WORKER_RESTART_EVERY = restart_every
    _WORKER_PREFER_ANC_SOURCE_CONSTRUCTION = prefer_anc_source_construction
    _WORKER_PARSER = None
    _WORKER_PARSED_SINCE_RESTART = 0


def get_worker_parser() -> Any:
    global _WORKER_PARSER
    global _WORKER_PARSED_SINCE_RESTART

    if _WORKER_GRAMMAR is None:
        raise RuntimeError("Worker grammar was not initialized")

    if _WORKER_PARSER is None:
        _WORKER_PARSER = make_parser(_WORKER_GRAMMAR, _WORKER_MAX_PARSES)
        _WORKER_PARSED_SINCE_RESTART = 0
        return _WORKER_PARSER

    if _WORKER_RESTART_EVERY > 0 and _WORKER_PARSED_SINCE_RESTART >= _WORKER_RESTART_EVERY:
        close_parser(_WORKER_PARSER)
        _WORKER_PARSER = make_parser(_WORKER_GRAMMAR, _WORKER_MAX_PARSES)
        _WORKER_PARSED_SINCE_RESTART = 0

    return _WORKER_PARSER


def restart_worker_parser() -> None:
    global _WORKER_PARSER
    global _WORKER_PARSED_SINCE_RESTART

    close_parser(_WORKER_PARSER)
    _WORKER_PARSER = None
    _WORKER_PARSED_SINCE_RESTART = 0


def parse_results_persistent(sent: str) -> List[JsonDict]:
    """
    Parse one sentence with a persistent ACEParser.
    If the ACE process crashes, restart once and retry.
    """
    global _WORKER_PARSED_SINCE_RESTART

    if _WORKER_GRAMMAR is None:
        raise RuntimeError("Worker grammar was not initialized")

    parser = get_worker_parser()

    try:
        resp = parser.interact(sent)
    except Exception:
        restart_worker_parser()
        parser = get_worker_parser()
        resp = parser.interact(sent)

    _WORKER_PARSED_SINCE_RESTART += 1

    results = resp.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def build_output_rows_for_item(
    row: JsonDict,
    fallback_id: int,
    results: List[JsonDict],
    first_parse_only: bool,
    skip_failed: bool,
) -> Tuple[List[JsonDict], int]:
    """
    Return output rows and successful-parse count for one input row.
    """
    id_value = extract_sentence_id(row, fallback_id)
    source_sentence = extract_source_sentence(row)
    pseudo_sentence = extract_pseudo_sentence(row)
    metadata = carryover_metadata(row)

    n = len(results)

    if n == 0:
        if skip_failed:
            return [], 0

        return [
            {
                "id": id_value,
                "sentence": source_sentence,
                "pseudo_english": pseudo_sentence,
                "parse_found": False,
                "parse_count": 0,
                "parse_index": None,
                "mrs": None,
                **metadata,
            }
        ], 0

    if first_parse_only:
        results = results[:1]

    out_rows: List[JsonDict] = []
    success_count = 0

    for parse_index, result in enumerate(results, start=1):
        mrs = result.get("mrs")
        if not isinstance(mrs, str) or not mrs.strip():
            continue

        mrs = normalize_mrs(mrs)

        out_rows.append(
            {
                "id": id_value,
                "sentence": source_sentence,
                "pseudo_english": pseudo_sentence,
                "parse_found": True,
                "parse_count": n,
                "parse_index": parse_index,
                "mrs": mrs,
                **metadata,
            }
        )
        success_count += 1

    if not out_rows and not skip_failed:
        out_rows.append(
            {
                "id": id_value,
                "sentence": source_sentence,
                "pseudo_english": pseudo_sentence,
                "parse_found": False,
                "parse_count": n,
                "parse_index": None,
                "mrs": None,
                **metadata,
            }
        )

    return out_rows, success_count


def parse_one_row_single_process(
    grammar_dat: str,
    row: JsonDict,
    fallback_id: int,
    max_parses: int,
    first_parse_only: bool,
    skip_failed: bool,
    prefer_anc_source_construction: str | None,
) -> Tuple[List[JsonDict], int]:
    pseudo_sentence = extract_pseudo_sentence(row)
    results = parse_with_oneoff(grammar_dat, pseudo_sentence, max_parses)
    results = prefer_anc_parse_results(row, results, prefer_anc_source_construction)

    return build_output_rows_for_item(
        row=row,
        fallback_id=fallback_id,
        results=results,
        first_parse_only=first_parse_only,
        skip_failed=skip_failed,
    )


def parse_chunk_worker(chunk: List[Tuple[int, JsonDict]]) -> Tuple[List[JsonDict], int, int]:
    """
    Worker function for one chunk.

    Returns:
      output rows, successful parse rows, number of input rows processed
    """
    out_rows: List[JsonDict] = []
    success_count = 0

    for fallback_id, row in chunk:
        pseudo_sentence = extract_pseudo_sentence(row)
        results = parse_results_persistent(pseudo_sentence)
        results = prefer_anc_parse_results(
            row,
            results,
            _WORKER_PREFER_ANC_SOURCE_CONSTRUCTION,
        )

        rows, n_success = build_output_rows_for_item(
            row=row,
            fallback_id=fallback_id,
            results=results,
            first_parse_only=_WORKER_FIRST_PARSE_ONLY,
            skip_failed=_WORKER_SKIP_FAILED,
        )

        out_rows.extend(rows)
        success_count += n_success

    return out_rows, success_count, len(chunk)


def iter_indexed_chunks(path: Path, chunksize: int) -> Iterator[List[Tuple[int, JsonDict]]]:
    chunk: List[Tuple[int, JsonDict]] = []

    for i, row in enumerate(iter_pseudo_jsonl(path), start=1):
        chunk.append((i, row))

        if len(chunk) >= chunksize:
            yield chunk
            chunk = []

    if chunk:
        yield chunk


def parse_single_process(args: argparse.Namespace, input_path: Path, out_path: Path, total: Optional[int]) -> None:
    saved_count = 0
    success_count = 0

    with out_path.open("w", encoding="utf-8") as f:
        iterator = enumerate(
            tqdm(iter_pseudo_jsonl(input_path), total=total, desc="Parsing pseudo-English"),
            start=1,
        )

        for i, row in iterator:
            rows, n_success = parse_one_row_single_process(
                grammar_dat=args.grammar,
                row=row,
                fallback_id=i,
                max_parses=args.max_parses,
                first_parse_only=args.first_parse_only,
                skip_failed=args.skip_failed,
                prefer_anc_source_construction=args.prefer_anc_source_construction,
            )

            for out_row in rows:
                f.write(json.dumps(out_row, ensure_ascii=False) + "\n")

            saved_count += len(rows)
            success_count += n_success

    print("\nDone.")
    print(f"Saved {saved_count} rows.")
    print(f"Successful parses: {success_count}")
    print(f"Output: {out_path}")


def parse_parallel(args: argparse.Namespace, input_path: Path, out_path: Path, total: Optional[int]) -> None:
    saved_count = 0
    success_count = 0

    ctx = mp.get_context("spawn")

    with out_path.open("w", encoding="utf-8") as f:
        with ctx.Pool(
            processes=args.workers,
            initializer=init_worker,
            initargs=(
                args.grammar,
                args.max_parses,
                args.first_parse_only,
                args.skip_failed,
                args.restart_every,
                args.prefer_anc_source_construction,
            ),
        ) as pool:
            chunk_iter = iter_indexed_chunks(input_path, args.chunksize)

            with tqdm(total=total, desc="Parsing pseudo-English") as pbar:
                for rows, n_success, n_input in pool.imap(parse_chunk_worker, chunk_iter, chunksize=1):
                    for out_row in rows:
                        f.write(json.dumps(out_row, ensure_ascii=False) + "\n")

                    saved_count += len(rows)
                    success_count += n_success
                    pbar.update(n_input)

    print("\nDone.")
    print(f"Saved {saved_count} rows.")
    print(f"Successful parses: {success_count}")
    print(f"Output: {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True, help="Path to compiled ACE grammar .dat")
    ap.add_argument("--input", required=True, help="Input JSONL with pseudo_english field")
    ap.add_argument("--out", required=True, help="Output JSONL for parsed MRS results")
    ap.add_argument("--max-parses", type=int, default=20)
    ap.add_argument("--first-parse-only", action="store_true")
    ap.add_argument("--skip-failed", action="store_true", help="If set, do not write failed parse rows")
    ap.add_argument(
        "--no-count",
        action="store_true",
        help="Do not pre-count valid input rows for tqdm total",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes. Default: 1",
    )
    ap.add_argument(
        "--chunksize",
        type=int,
        default=100,
        help="Number of input rows per worker task. Default: 100",
    )
    ap.add_argument(
        "--restart-every",
        type=int,
        default=5000,
        help=(
            "Restart each worker's ACEParser after this many sentences. "
            "Use 0 to disable periodic restart. Default: 5000"
        ),
    )
    ap.add_argument(
        "--prefer-anc-source-construction",
        choices=["iv", "tv"],
        default=None,
        help=(
            "When pseudo-English has multiple parses for an ANC token, prefer "
            "parses whose nominalized verb looks like this source construction. "
            "For iv, the nominalized verb relation must not have ARG2; for tv, "
            "it must have ARG2. If no parse matches, the original parse order is kept."
        ),
    )

    args = ap.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    grammar_path = Path(args.grammar)
    if not grammar_path.exists():
        raise FileNotFoundError(f"Grammar file not found: {grammar_path}")

    if args.workers < 1:
        raise ValueError("--workers must be >= 1")

    if args.chunksize < 1:
        raise ValueError("--chunksize must be >= 1")

    if args.restart_every < 0:
        raise ValueError("--restart-every must be >= 0")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = None if args.no_count else count_valid_pseudo_rows(input_path)

    print("========== Parse Pseudo-English with Grammar ==========")
    print(f"Grammar:        {args.grammar}")
    print(f"Input:          {input_path}")
    print(f"Output:         {out_path}")
    print(f"Max parses:     {args.max_parses}")
    print(f"Workers:        {args.workers}")
    print(f"Chunksize:      {args.chunksize}")
    print(f"Restart every:  {args.restart_every}")
    print(f"First only:     {args.first_parse_only}")
    print(f"Skip failed:    {args.skip_failed}")
    print(f"Prefer ANC:     {args.prefer_anc_source_construction or 'none'}")
    print()

    if args.workers == 1:
        parse_single_process(args, input_path, out_path, total)
    else:
        parse_parallel(args, input_path, out_path, total)


if __name__ == "__main__":
    main()
