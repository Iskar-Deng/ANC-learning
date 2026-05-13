#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

RAW_DIR="data/train/generated/raw"
SELECTED_DIR="data/train/generated/selected"
DETAILS_DIR="data/train/generated/details"
LOG_DIR="logs/generation"

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

mkdir -p "$SELECTED_DIR" "$DETAILS_DIR" "$LOG_DIR"

SUMMARY="${LOG_DIR}/representative_selection_summary.tsv"
printf "language\tstatus\tinput\tselected\tdetails\tlog\n" > "$SUMMARY"

echo "========== Representative Selection =========="
echo "Raw dir:      $RAW_DIR"
echo "Selected dir: $SELECTED_DIR"
echo "Details dir:  $DETAILS_DIR"
echo "Log dir:      $LOG_DIR"
echo

for LANG in "${LANGS[@]}"; do
  INPUT="${RAW_DIR}/${LANG}.jsonl"
  OUT="${SELECTED_DIR}/${LANG}.jsonl"
  DETAILS="${DETAILS_DIR}/${LANG}.jsonl"
  LOG="${LOG_DIR}/select_${LANG}_train.log"

  echo "========== $LANG =========="

  if [[ ! -f "$INPUT" ]]; then
    echo "[skip] input not found: $INPUT"
    printf "%s\tskip_missing_input\t%s\t%s\t%s\t%s\n" \
      "$LANG" "$INPUT" "$OUT" "$DETAILS" "$LOG" >> "$SUMMARY"
    echo
    continue
  fi

  if python language_generation/select_overgen.py \
    --input "$INPUT" \
    --out "$OUT" \
    --save-details "$DETAILS" \
    > "$LOG" 2>&1
  then
    echo "[done] $LANG"
    echo "Selected: $OUT"
    echo "Details:  $DETAILS"
    echo "Log:      $LOG"
    printf "%s\tok\t%s\t%s\t%s\t%s\n" \
      "$LANG" "$INPUT" "$OUT" "$DETAILS" "$LOG" >> "$SUMMARY"
  else
    echo "[failed] $LANG"
    echo "Log: $LOG"
    printf "%s\tfailed\t%s\t%s\t%s\t%s\n" \
      "$LANG" "$INPUT" "$OUT" "$DETAILS" "$LOG" >> "$SUMMARY"
  fi

  echo
done

echo "========== Selection Summary =========="
cat "$SUMMARY"
echo

echo "========== Key Counts =========="
for LANG in "${LANGS[@]}"; do
  LOG="${LOG_DIR}/select_${LANG}_train.log"
  if [[ ! -f "$LOG" ]]; then
    continue
  fi

  echo "---------- $LANG ----------"
  grep -E \
    "Total input rows|Total unique ids|Rows/ids requiring selection|Overgenerated ids|Same-bag overgenerated ids|Different-bag overgenerated ids|Resolved by S-marker suffix variant|Resolved by ANC A/P order|A/P order multiple match, random choice|Same-bag unresolved, random choice|Different-bag overgenerated, random choice|Empty ids|Single-candidate ids" \
    "$LOG" || true
  echo
done

echo "========== DONE =========="
echo "Summary: $SUMMARY"