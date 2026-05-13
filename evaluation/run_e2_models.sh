#!/usr/bin/env bash
set -euo pipefail

SELECTED_DIR="data/test/generated/selected"
COMMON_IDS="results/e2_selected_coverage/test/common_ids.txt"
OUT_DIR="results/e2_real_grammar_preference/eight_models"
MODELS_DIR="models"
SEED="seed_42"
CHECKPOINT="checkpoint-70000"
BATCH_SIZE=64
DEVICE="cuda"

LANGUAGES=(
  "02_sov_gn_ac_b_ep"
  "08_sov_gn_er_b_se"
  "18_sov_ng_ac_b_ep"
  "42_svo_gn_er_b_ep"
  "50_svo_ng_ac_b_ep"
  "62_svo_ng_er_d_ep"
  "82_vos_ng_ac_b_ep"
  "94_vos_ng_er_d_ep"
)

usage() {
  cat <<EOF
Usage:
  $0 [options]

Runs E2 scoring sequentially for the 8 representative models.

Options:
  --selected-dir DIR      Selected generation directory.
                          Default: $SELECTED_DIR
  --common-ids PATH       Common ids file.
                          Default: $COMMON_IDS
  --out-dir DIR           Output directory.
                          Default: $OUT_DIR
  --models-dir DIR        Models directory.
                          Default: $MODELS_DIR
  --checkpoint NAME       Checkpoint directory name.
                          Default: $CHECKPOINT
  --batch-size N          Batch size.
                          Default: $BATCH_SIZE
  --device DEVICE         cuda/cpu/mps.
                          Default: $DEVICE
  -h, --help              Show help

No parallel mode. No max-ids mode.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --selected-dir)
      SELECTED_DIR="$2"
      shift 2
      ;;
    --common-ids)
      COMMON_IDS="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --models-dir)
      MODELS_DIR="$2"
      shift 2
      ;;
    --checkpoint)
      CHECKPOINT="$2"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
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

mkdir -p "$OUT_DIR"
mkdir -p "logs/e2"

echo "========== E2: Eight Models Sequential Run =========="
echo "Selected dir: $SELECTED_DIR"
echo "Common ids:   $COMMON_IDS"
echo "Out dir:      $OUT_DIR"
echo "Models dir:   $MODELS_DIR"
echo "Checkpoint:   $CHECKPOINT"
echo "Batch size:   $BATCH_SIZE"
echo "Device:       $DEVICE"
echo

if [[ ! -d "$SELECTED_DIR" ]]; then
  echo "Error: selected dir not found: $SELECTED_DIR"
  exit 1
fi

if [[ ! -f "$COMMON_IDS" ]]; then
  echo "Error: common ids file not found: $COMMON_IDS"
  exit 1
fi

completed=0
failed=0

for LANG in "${LANGUAGES[@]}"; do
  MODEL_PATH="$MODELS_DIR/$LANG/$SEED/$CHECKPOINT"
  LOG_PATH="logs/e2/${LANG}.e2.log"
  SUMMARY_PATH="$OUT_DIR/${LANG}.summary.json"

  echo
  echo "---------- $LANG ----------"
  echo "Model:   $MODEL_PATH"
  echo "Log:     $LOG_PATH"
  echo "Summary: $SUMMARY_PATH"

  if [[ ! -d "$MODEL_PATH" ]]; then
    echo "[failed] model path not found: $MODEL_PATH"
    failed=$((failed + 1))
    continue
  fi

  python evaluation/score_one_model_real_grammar.py \
    --model "$MODEL_PATH" \
    --model-id "$LANG" \
    --selected-dir "$SELECTED_DIR" \
    --common-ids "$COMMON_IDS" \
    --out-dir "$OUT_DIR" \
    --batch-size "$BATCH_SIZE" \
    --device "$DEVICE" \
    2>&1 | tee "$LOG_PATH"

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
echo "Logs:      logs/e2"

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi