#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-/home/dengh/miniconda3/envs/anc/bin/python}"
MODEL="${MODEL:-models/english_baseline/seed_42}"
DEVICE="${DEVICE:-cuda}"
BATCH_SIZE="${BATCH_SIZE:-64}"
OUT_ROOT="${OUT_ROOT:-evaluation/baseline/outputs/english_baseline_seed_42}"

mkdir -p "$OUT_ROOT"

run_one() {
  local phenomenon="$1"
  local tsv="$2"
  local out_dir="$OUT_ROOT/$phenomenon"
  local pairs="$out_dir/pairs.jsonl"
  local scores="$out_dir/scores.tsv"
  local summary="$out_dir/summary.json"

  mkdir -p "$out_dir"

  "$PYTHON_BIN" evaluation/baseline/convert_blimp_valency_tsv.py \
    --input "$tsv" \
    --out "$pairs" \
    --phenomenon "$phenomenon"

  "$PYTHON_BIN" evaluation/E1/score_e1_pairs.py \
    --model "$MODEL" \
    --pairs "$pairs" \
    --out "$scores" \
    --summary "$summary" \
    --batch-size "$BATCH_SIZE" \
    --device "$DEVICE" \
    --score-mode bos_eos
}

run_one \
  "1_9_intran_V_valency" \
  "evaluation/E1/phenomena/1_9_intran_V_valency/blimp_valency.tsv"

run_one \
  "1_10_tran_V_valency" \
  "evaluation/E1/phenomena/1_10_tran_V_valency/blimp_valency.tsv"
