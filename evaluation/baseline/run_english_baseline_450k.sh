#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-/home/dengh/miniconda3/envs/anc/bin/python}"
LOG_DIR="evaluation/baseline/logs"
LOG_FILE="$LOG_DIR/english_baseline_450k.nohup.log"

mkdir -p "$LOG_DIR"

nohup "$PYTHON_BIN" evaluation/baseline/train_english_baseline_450k.py \
  --language english_baseline \
  --train-input data/english_baseline/train.jsonl \
  --dev-input data/english_baseline/dev.jsonl \
  --output-dir models/english_baseline/seed_42 \
  --seed 42 \
  --max-steps 450000 \
  --resume-from-checkpoint models/english_baseline/seed_42/checkpoint-200000 \
  > "$LOG_FILE" 2>&1 &

echo "Started English baseline continuation."
echo "PID: $!"
echo "Log: $LOG_FILE"
