#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

INPUT="data/train/train_mrs.jsonl"
RAW_DIR="data/train/generated/raw"
LOG_DIR="logs/generation"

WORKERS=12
CHUNKSIZE=100
MAX_GEN=20

LANGS=(
  "62_svo_ng_er_d_ep"
  "18_sov_ng_ac_b_ep"
  "02_sov_gn_ac_b_ep"
  "50_svo_ng_ac_b_ep"
  "82_vos_ng_ac_b_ep"
  "08_sov_gn_er_b_se"
  "42_svo_gn_er_b_ep"
  "94_vos_ng_er_d_ep"
)

mkdir -p "$RAW_DIR" "$LOG_DIR"

echo "========== Representative Generation =========="
echo "Input:     $INPUT"
echo "Raw dir:   $RAW_DIR"
echo "Log dir:   $LOG_DIR"
echo "Workers:   $WORKERS"
echo "Chunksize: $CHUNKSIZE"
echo "Max gen:   $MAX_GEN"
echo

for LANG in "${LANGS[@]}"; do
  GRAMMAR="grammars/${LANG}/${LANG}.dat"
  OUT="${RAW_DIR}/${LANG}.jsonl"
  LOG="${LOG_DIR}/generate_${LANG}.log"

  echo "========== $LANG =========="

  if [[ ! -f "$GRAMMAR" ]]; then
    echo "[skip] grammar not found: $GRAMMAR"
    echo
    continue
  fi

  python3 -m language_generation.generate_from_mrs_bank \
    --grammar "$GRAMMAR" \
    --input "$INPUT" \
    --out "$OUT" \
    --no-mrs \
    --workers "$WORKERS" \
    --chunksize "$CHUNKSIZE" \
    --max-gen "$MAX_GEN" \
    > "$LOG" 2>&1

  echo "[done] $LANG"
  echo "Log: $LOG"
  echo "Out: $OUT"
  echo
done

echo "========== DONE =========="