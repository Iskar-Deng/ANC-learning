#!/usr/bin/env bash
set -euo pipefail

TRAIN_DIR="data/train/generated/selected"
DEV_DIR="data/dev/generated/selected"
MODELS_DIR="models"
SEED=42
LANGUAGE_LIST=""
FORCE=false

usage() {
  cat <<EOF
Usage:
  $0 [options]

Sequentially train one LM per generated language using:
  python -m training.train_lm

Options:
  --train-dir DIR        Train selected directory.
                         Default: $TRAIN_DIR
  --dev-dir DIR          Dev selected directory.
                         Default: $DEV_DIR
  --models-dir DIR       Models directory.
                         Default: $MODELS_DIR
  --seed N               Training seed.
                         Default: $SEED
  --language-list PATH   Optional file with one language id per line.
                         If omitted, languages are read from --train-dir.
  --force                Re-train even if final model files appear to exist.
                         This deletes nothing; it only passes --force-check through if unsupported? No.
                         Current script instead skips less aggressively when --force is set.
  -h, --help             Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --train-dir)
      TRAIN_DIR="$2"
      shift 2
      ;;
    --dev-dir)
      DEV_DIR="$2"
      shift 2
      ;;
    --models-dir)
      MODELS_DIR="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
      shift 2
      ;;
    --language-list)
      LANGUAGE_LIST="$2"
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

mkdir -p logs/training
mkdir -p "$MODELS_DIR"

if [[ ! -d "$TRAIN_DIR" ]]; then
  echo "Error: train dir not found: $TRAIN_DIR"
  exit 1
fi

if [[ ! -d "$DEV_DIR" ]]; then
  echo "Error: dev dir not found: $DEV_DIR"
  exit 1
fi

if [[ -n "$LANGUAGE_LIST" ]]; then
  if [[ ! -f "$LANGUAGE_LIST" ]]; then
    echo "Error: language list not found: $LANGUAGE_LIST"
    exit 1
  fi

  mapfile -t LANGUAGES < <(
    grep -v '^[[:space:]]*$' "$LANGUAGE_LIST" \
      | grep -v '^[[:space:]]*#' \
      | sort
  )
else
  mapfile -t LANGUAGES < <(
    find "$TRAIN_DIR" -maxdepth 1 -type f -name '[0-9][0-9]_*.jsonl' \
      -printf '%f\n' \
      | sed 's/\.jsonl$//' \
      | sort
  )
fi

echo "========== Train all LMs sequentially =========="
echo "Train dir:      $TRAIN_DIR"
echo "Dev dir:        $DEV_DIR"
echo "Models dir:     $MODELS_DIR"
echo "Seed:           $SEED"
echo "Language list:  ${LANGUAGE_LIST:-<from train dir>}"
echo "Languages:      ${#LANGUAGES[@]}"
echo "Force:          $FORCE"
echo

SUCCESS_LIST="logs/training/success_train_all.tsv"
SKIP_LIST="logs/training/skipped_train_all.tsv"
FAILED_LIST="logs/training/failed_train_all.tsv"
MISSING_LIST="logs/training/missing_train_all.tsv"

: > "$SUCCESS_LIST"
: > "$SKIP_LIST"
: > "$FAILED_LIST"
: > "$MISSING_LIST"

completed=0
skipped=0
failed=0
missing=0

for LANG in "${LANGUAGES[@]}"; do
  TRAIN_INPUT="$TRAIN_DIR/$LANG.jsonl"
  DEV_INPUT="$DEV_DIR/$LANG.jsonl"
  MODEL_OUT="$MODELS_DIR/$LANG/seed_$SEED"
  LOG_PATH="logs/training/${LANG}.seed_${SEED}.train.log"

  echo
  echo "---------- $LANG ----------"
  echo "Train: $TRAIN_INPUT"
  echo "Dev:   $DEV_INPUT"
  echo "Out:   $MODEL_OUT"
  echo "Log:   $LOG_PATH"

  if [[ ! -f "$TRAIN_INPUT" ]]; then
    echo "[missing] train input not found"
    echo -e "$LANG\tmissing_train\t$TRAIN_INPUT" >> "$MISSING_LIST"
    missing=$((missing + 1))
    continue
  fi

  if [[ ! -f "$DEV_INPUT" ]]; then
    echo "[missing] dev input not found"
    echo -e "$LANG\tmissing_dev\t$DEV_INPUT" >> "$MISSING_LIST"
    missing=$((missing + 1))
    continue
  fi

  # Skip only if final model files already exist.
  # If only checkpoint-* exists, do NOT skip, because train_lm supports automatic resume.
  if [[ "$FORCE" != true ]]; then
    if [[ -f "$MODEL_OUT/model.safetensors" || -f "$MODEL_OUT/pytorch_model.bin" ]]; then
      echo "[skip] final model already exists"
      echo -e "$LANG\t$MODEL_OUT" >> "$SKIP_LIST"
      skipped=$((skipped + 1))
      continue
    fi
  fi

  set +e
  python -m training.train_lm \
    --language "$LANG" \
    --train-input "$TRAIN_INPUT" \
    --dev-input "$DEV_INPUT" \
    --seed "$SEED" \
    2>&1 | tee "$LOG_PATH"

  status=${PIPESTATUS[0]}
  set -e

  if [[ "$status" -ne 0 ]]; then
    echo "[failed] $LANG status=$status"
    echo -e "$LANG\tstatus=$status\t$LOG_PATH" >> "$FAILED_LIST"
    failed=$((failed + 1))
    continue
  fi

  if [[ -f "$MODEL_OUT/model.safetensors" || -f "$MODEL_OUT/pytorch_model.bin" || -d "$MODEL_OUT/checkpoint-70000" ]]; then
    echo "[ok] $LANG"
    echo -e "$LANG\t$MODEL_OUT" >> "$SUCCESS_LIST"
    completed=$((completed + 1))
  else
    echo "[failed] no final model/checkpoint found after training"
    echo -e "$LANG\tno_model_output\t$LOG_PATH" >> "$FAILED_LIST"
    failed=$((failed + 1))
  fi
done

echo
echo "========== Done =========="
echo "Completed: $completed"
echo "Skipped:   $skipped"
echo "Missing:   $missing"
echo "Failed:    $failed"
echo "Models:    $MODELS_DIR"
echo "Logs:      logs/training"
echo "Success:   $SUCCESS_LIST"
echo "Skipped:   $SKIP_LIST"
echo "Missing:   $MISSING_LIST"
echo "Failed:    $FAILED_LIST"

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi