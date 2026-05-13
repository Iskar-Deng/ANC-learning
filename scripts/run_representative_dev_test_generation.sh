#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

SPLITS=(
  "dev"
  "test"
)

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

WORKERS=12
CHUNKSIZE=100
MAX_GEN=20

LOG_DIR="logs/generation"
mkdir -p "$LOG_DIR"

echo "========== Representative Dev/Test Generation =========="
echo "Workers:   $WORKERS"
echo "Chunksize: $CHUNKSIZE"
echo "Max gen:   $MAX_GEN"
echo

for SPLIT in "${SPLITS[@]}"; do
  INPUT="data/${SPLIT}/${SPLIT}_mrs.jsonl"
  RAW_DIR="data/${SPLIT}/generated/raw"
  SELECTED_DIR="data/${SPLIT}/generated/selected"
  DETAILS_DIR="data/${SPLIT}/generated/details"

  mkdir -p "$RAW_DIR" "$SELECTED_DIR" "$DETAILS_DIR"

  if [[ ! -f "$INPUT" ]]; then
    echo "[skip split] missing MRS: $INPUT"
    echo
    continue
  fi

  echo "========== SPLIT: $SPLIT =========="
  echo "Input: $INPUT"
  echo

  for LANG in "${LANGS[@]}"; do
    GRAMMAR="grammars/${LANG}/${LANG}.dat"
    RAW_OUT="${RAW_DIR}/${LANG}.jsonl"
    SELECTED_OUT="${SELECTED_DIR}/${LANG}.jsonl"
    DETAILS_OUT="${DETAILS_DIR}/${LANG}.jsonl"
    GEN_LOG="${LOG_DIR}/generate_${LANG}_${SPLIT}.log"
    SEL_LOG="${LOG_DIR}/select_${LANG}_${SPLIT}.log"

    echo "---------- $SPLIT / $LANG ----------"

    if [[ ! -f "$GRAMMAR" ]]; then
      echo "[skip] grammar not found: $GRAMMAR"
      echo
      continue
    fi

    rm -f "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT"

    python3 -m language_generation.generate_from_mrs_bank \
      --grammar "$GRAMMAR" \
      --input "$INPUT" \
      --out "$RAW_OUT" \
      --no-mrs \
      --workers "$WORKERS" \
      --chunksize "$CHUNKSIZE" \
      --max-gen "$MAX_GEN" \
      > "$GEN_LOG" 2>&1

    python language_generation/select_overgen.py \
      --input "$RAW_OUT" \
      --out "$SELECTED_OUT" \
      --save-details "$DETAILS_OUT" \
      > "$SEL_LOG" 2>&1

    echo "[done] $SPLIT / $LANG"
    echo "Raw:      $RAW_OUT"
    echo "Selected: $SELECTED_OUT"
    echo "Details:  $DETAILS_OUT"
    echo
  done
done

echo "========== DONE =========="