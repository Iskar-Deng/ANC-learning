#!/usr/bin/env bash
set -euo pipefail

SELECTED_DIR="data/test/generated/selected"
COMMON_IDS="evaluation/E2/generated/selected_coverage/test/common_ids.txt"
OUT_DIR="results/e2_real_grammar_preference/all_models_bos_eos"
MODELS_DIR="models"
SEED="seed_42"
CHECKPOINT="checkpoint-70000"
BATCH_SIZE=64
DEVICE="cuda"
SCORE_MODE="bos_eos"
MAX_IDS=""
LOG_DIR="evaluation/E2/generated/logs/e2_bos_eos"

usage() {
  cat <<EOF
Usage:
  $0 [options] [LANG ...]

Runs E2 scoring. If LANG is omitted, languages are read from --selected-dir.

Options:
  --selected-dir DIR   Default: $SELECTED_DIR
  --common-ids PATH    Default: $COMMON_IDS
  --out-dir DIR        Default: $OUT_DIR
  --models-dir DIR     Default: $MODELS_DIR
  --seed NAME          Default: $SEED
  --checkpoint NAME    Default: $CHECKPOINT
  --batch-size N       Default: $BATCH_SIZE
  --device DEVICE      cuda/cpu/mps. Default: $DEVICE
  --score-mode MODE    bos_eos/bos/legacy. Default: $SCORE_MODE
  --max-ids N          Optional smoke-test limit.
  --log-dir DIR        Default: $LOG_DIR
  -h, --help           Show help.

Recommended new E2:
  --score-mode bos_eos

Old E2 reproduction:
  --score-mode legacy
EOF
}

LANGUAGES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --selected-dir) SELECTED_DIR="$2"; shift 2 ;;
    --common-ids) COMMON_IDS="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --models-dir) MODELS_DIR="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --checkpoint) CHECKPOINT="$2"; shift 2 ;;
    --batch-size) BATCH_SIZE="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --score-mode) SCORE_MODE="$2"; shift 2 ;;
    --max-ids) MAX_IDS="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; LANGUAGES+=("$@"); break ;;
    -*)
      echo "Error: unknown argument: $1"
      usage
      exit 1
      ;;
    *)
      LANGUAGES+=("$1")
      shift
      ;;
  esac
done

if [[ ! -d "$SELECTED_DIR" ]]; then
  echo "Error: selected dir not found: $SELECTED_DIR"
  exit 1
fi

if [[ ! -f "$COMMON_IDS" ]]; then
  echo "Error: common ids file not found: $COMMON_IDS"
  exit 1
fi

if [[ ${#LANGUAGES[@]} -eq 0 ]]; then
  while IFS= read -r path; do
    LANGUAGES+=("$(basename "$path" .jsonl)")
  done < <(find "$SELECTED_DIR" -maxdepth 1 -type f -name '[0-9][0-9]_*.jsonl' | sort)
fi

mkdir -p "$OUT_DIR" "$LOG_DIR"

echo "========== E2 Run =========="
echo "Selected dir: $SELECTED_DIR"
echo "Common ids:   $COMMON_IDS"
echo "Out dir:      $OUT_DIR"
echo "Models dir:   $MODELS_DIR"
echo "Seed:         $SEED"
echo "Checkpoint:   $CHECKPOINT"
echo "Batch size:   $BATCH_SIZE"
echo "Device:       $DEVICE"
echo "Score mode:   $SCORE_MODE"
echo "Max ids:      ${MAX_IDS:-all}"
echo "Languages:    ${#LANGUAGES[@]}"
echo

completed=0
failed=0

for LANG in "${LANGUAGES[@]}"; do
  MODEL_PATH="$MODELS_DIR/$LANG/$SEED/$CHECKPOINT"
  SUMMARY_PATH="$OUT_DIR/${LANG}.summary.json"
  LOG_PATH="$LOG_DIR/${LANG}.e2.${SCORE_MODE}.log"

  echo
  echo "---------- $LANG ----------"
  echo "Model:   $MODEL_PATH"
  echo "Summary: $SUMMARY_PATH"
  echo "Log:     $LOG_PATH"

  if [[ ! -d "$MODEL_PATH" ]]; then
    echo "[failed] model path not found: $MODEL_PATH"
    failed=$((failed + 1))
    continue
  fi

  CMD=(
    python evaluation/E2/score_one_model_real_grammar.py
    --model "$MODEL_PATH"
    --model-id "$LANG"
    --selected-dir "$SELECTED_DIR"
    --common-ids "$COMMON_IDS"
    --out-dir "$OUT_DIR"
    --batch-size "$BATCH_SIZE"
    --device "$DEVICE"
    --score-mode "$SCORE_MODE"
  )
  if [[ -n "$MAX_IDS" ]]; then
    CMD+=(--max-ids "$MAX_IDS")
  fi

  "${CMD[@]}" 2>&1 | tee "$LOG_PATH"

  if [[ -f "$SUMMARY_PATH" ]]; then
    echo "[ok] $LANG"
    completed=$((completed + 1))
  else
    echo "[failed] summary not created: $SUMMARY_PATH"
    failed=$((failed + 1))
  fi
done

echo
echo "========== Done =========="
echo "Completed: $completed"
echo "Failed:    $failed"
echo "Outputs:   $OUT_DIR"
echo "Logs:      $LOG_DIR"

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi
