#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

SPLITS=(
  "train"
  "dev"
  "test"
)

WORKERS=12
CHUNKSIZE=100
MAX_GEN=20
LOG_DIR="logs/generation"
FORCE=false

usage() {
  cat <<EOF
Usage:
  $0 [options]

Generate and select outputs for all grammars over train/dev/test splits.
Already completed selected outputs are skipped unless --force is given.

Options:
  --workers N        Number of workers. Default: $WORKERS
  --chunksize N      Chunk size. Default: $CHUNKSIZE
  --max-gen N        Max generations per MRS. Default: $MAX_GEN
  --log-dir DIR      Log directory. Default: $LOG_DIR
  --force            Re-run even if selected output already exists
  -h, --help         Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workers)
      WORKERS="$2"
      shift 2
      ;;
    --chunksize)
      CHUNKSIZE="$2"
      shift 2
      ;;
    --max-gen)
      MAX_GEN="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

mkdir -p "$LOG_DIR"

mapfile -t LANGS < <(
  find grammars -mindepth 2 -maxdepth 2 -type f -name '*.dat' \
    -printf '%h\n' \
  | xargs -n1 basename \
  | grep -E '^[0-9][0-9]_' \
  | sort
)

if [[ "${#LANGS[@]}" -eq 0 ]]; then
  echo "Error: no grammar .dat files found under grammars/*/*.dat"
  exit 1
fi

SUMMARY="${LOG_DIR}/all_splits_generation_summary.tsv"
printf "split\tlanguage\tstatus\tinput\traw\tselected\tdetails\tgenerate_log\tselect_log\n" > "$SUMMARY"

echo "========== All Splits Language Generation =========="
echo "Splits:    ${SPLITS[*]}"
echo "Languages: ${#LANGS[@]}"
echo "Workers:   $WORKERS"
echo "Chunksize: $CHUNKSIZE"
echo "Max gen:   $MAX_GEN"
echo "Log dir:   $LOG_DIR"
echo "Force:     $FORCE"
echo

completed=0
skipped_done=0
skipped_missing_input=0
skipped_missing_grammar=0
failed=0

for SPLIT in "${SPLITS[@]}"; do
  INPUT="data/${SPLIT}/${SPLIT}_mrs.jsonl"
  RAW_DIR="data/${SPLIT}/generated/raw"
  SELECTED_DIR="data/${SPLIT}/generated/selected"
  DETAILS_DIR="data/${SPLIT}/generated/details"

  mkdir -p "$RAW_DIR" "$SELECTED_DIR" "$DETAILS_DIR"

  echo
  echo "========== SPLIT: $SPLIT =========="
  echo "Input:        $INPUT"
  echo "Raw dir:      $RAW_DIR"
  echo "Selected dir: $SELECTED_DIR"
  echo "Details dir:  $DETAILS_DIR"
  echo

  if [[ ! -f "$INPUT" ]]; then
    echo "[skip split] missing MRS: $INPUT"
    for LANG_ID in "${LANGS[@]}"; do
      printf "%s\t%s\tskip_missing_input\t%s\t\t\t\t\t\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" >> "$SUMMARY"
    done
    skipped_missing_input=$((skipped_missing_input + ${#LANGS[@]}))
    continue
  fi

  for LANG_ID in "${LANGS[@]}"; do
    GRAMMAR="grammars/${LANG_ID}/${LANG_ID}.dat"
    RAW_OUT="${RAW_DIR}/${LANG_ID}.jsonl"
    SELECTED_OUT="${SELECTED_DIR}/${LANG_ID}.jsonl"
    DETAILS_OUT="${DETAILS_DIR}/${LANG_ID}.jsonl"
    GEN_LOG="${LOG_DIR}/generate_${SPLIT}_${LANG_ID}.log"
    SEL_LOG="${LOG_DIR}/select_${SPLIT}_${LANG_ID}.log"

    echo "---------- $SPLIT / $LANG_ID ----------"

    if [[ ! -f "$GRAMMAR" ]]; then
      echo "[skip] grammar not found: $GRAMMAR"
      printf "%s\t%s\tskip_missing_grammar\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"
      skipped_missing_grammar=$((skipped_missing_grammar + 1))
      echo
      continue
    fi

    if [[ "$FORCE" != true && -s "$SELECTED_OUT" && -s "$DETAILS_OUT" ]]; then
      echo "[skip] selected/details already exist"
      printf "%s\t%s\tskip_done\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"
      skipped_done=$((skipped_done + 1))
      echo
      continue
    fi

    if [[ "$FORCE" == true ]]; then
      rm -f "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT"
    fi

    echo "[1/2] Generating raw output..."
    set +e
    python3 -m language_generation.generate_from_mrs_bank \
      --grammar "$GRAMMAR" \
      --input "$INPUT" \
      --out "$RAW_OUT" \
      --no-mrs \
      --workers "$WORKERS" \
      --chunksize "$CHUNKSIZE" \
      --max-gen "$MAX_GEN" \
      > "$GEN_LOG" 2>&1
    gen_status=$?
    set -e

    if [[ "$gen_status" -ne 0 ]]; then
      echo "[failed] generation failed: $GEN_LOG"
      printf "%s\t%s\tfailed_generation\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"
      failed=$((failed + 1))
      echo
      continue
    fi

    if [[ ! -s "$RAW_OUT" ]]; then
      echo "[failed] raw output missing or empty: $RAW_OUT"
      printf "%s\t%s\tfailed_empty_raw\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"
      failed=$((failed + 1))
      echo
      continue
    fi

    echo "[2/2] Selecting overgeneration output..."
    set +e
    python language_generation/select_overgen.py \
      --input "$RAW_OUT" \
      --out "$SELECTED_OUT" \
      --save-details "$DETAILS_OUT" \
      > "$SEL_LOG" 2>&1
    sel_status=$?
    set -e

    if [[ "$sel_status" -ne 0 ]]; then
      echo "[failed] selection failed: $SEL_LOG"
      printf "%s\t%s\tfailed_selection\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"
      failed=$((failed + 1))
      echo
      continue
    fi

    if [[ ! -s "$SELECTED_OUT" ]]; then
      echo "[failed] selected output missing or empty: $SELECTED_OUT"
      printf "%s\t%s\tfailed_empty_selected\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"
      failed=$((failed + 1))
      echo
      continue
    fi

    echo "[ok] $SPLIT / $LANG_ID"
    echo "Raw:      $RAW_OUT"
    echo "Selected: $SELECTED_OUT"
    echo "Details:  $DETAILS_OUT"
    echo "Gen log:  $GEN_LOG"
    echo "Sel log:  $SEL_LOG"

    printf "%s\t%s\tok\t%s\t%s\t%s\t%s\t%s\t%s\n" \
      "$SPLIT" "$LANG_ID" "$INPUT" "$RAW_OUT" "$SELECTED_OUT" "$DETAILS_OUT" "$GEN_LOG" "$SEL_LOG" >> "$SUMMARY"

    completed=$((completed + 1))
    echo
  done
done

echo
echo "========== DONE =========="
echo "Completed:              $completed"
echo "Skipped done:           $skipped_done"
echo "Skipped missing input:  $skipped_missing_input"
echo "Skipped missing grammar:$skipped_missing_grammar"
echo "Failed:                 $failed"
echo "Summary:                $SUMMARY"

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi