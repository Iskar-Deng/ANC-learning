#!/usr/bin/env bash
set -euo pipefail

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

PHEN=""
SAMPLE_SIZE=100
SEED=42
BATCH_SIZE=64
DEVICE="cuda"
SCORE_MODE="bos_eos"
LOWEST_N=20
PYTHON_BIN="${PYTHON:-python}"
MANIFEST="choices/manifest.tsv"
SKIP_MISSING_MODELS=true
CHECK_PARALLEL_IDS=true

usage() {
  cat <<EOF
Usage:
  $0 --phenomenon PHENOMENON [options]

Runs E1 after smoke inspection: batch pairs, score models, and aggregate.

Required:
  --phenomenon NAME            e.g. 1_1_intran_V_form

Options:
  --sample-size N              Batch pair sample size. Default: 100
  --seed N                     Sampling seed. Default: 42
  --batch-size N               Scoring batch size. Default: 64
  --device cuda|cpu|mps        Scoring device. Default: cuda
  --score-mode MODE            legacy, bos, or bos_eos. Default: bos_eos
  --lowest-n N                 Lowest models to list in analysis. Default: 20
  --manifest PATH              Manifest TSV. Default: choices/manifest.tsv
  --python PATH                Python executable. Default: \$PYTHON or python
  --no-skip-missing-models     Fail if a model directory is missing
  --no-check-parallel-ids      Skip same-id-sequence check across pair files
  -h, --help                   Show this help message

Example:
  $0 --phenomenon 1_1_intran_V_form
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phenomenon)
      PHEN="$2"
      shift 2
      ;;
    --sample-size)
      SAMPLE_SIZE="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
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
    --score-mode)
      SCORE_MODE="$2"
      shift 2
      ;;
    --lowest-n)
      LOWEST_N="$2"
      shift 2
      ;;
    --manifest)
      MANIFEST="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --no-skip-missing-models)
      SKIP_MISSING_MODELS=false
      shift
      ;;
    --no-check-parallel-ids)
      CHECK_PARALLEL_IDS=false
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

if [[ -z "$PHEN" ]]; then
  echo "Error: missing required argument: --phenomenon NAME"
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

PHEN_DIR="evaluation/E1/phenomena/$PHEN"
MAT_DIR="e1_materials/$PHEN"
SELECTED_DIR="$MAT_DIR/generated/selected"
PAIR_DIR="$MAT_DIR/pairs"
SCORE_DIR="$MAT_DIR/scores"
ANALYSIS_DIR="$MAT_DIR/analysis"

if [[ ! -d "$PHEN_DIR" ]]; then
  echo "Error: phenomenon directory not found: $PHEN_DIR"
  exit 1
fi

if [[ ! -d "$SELECTED_DIR" ]]; then
  echo "Error: selected GOOD directory not found: $SELECTED_DIR"
  echo "Run evaluation/E1/run_e1_until_smoke.sh first."
  exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "Error: manifest not found: $MANIFEST"
  exit 1
fi

mkdir -p "$PAIR_DIR" "$SCORE_DIR" "$ANALYSIS_DIR"

echo "========== E1 After Smoke =========="
echo "Project root:        $PROJECT_ROOT"
echo "Phenomenon:          $PHEN"
echo "Selected dir:        $SELECTED_DIR"
echo "Pair dir:            $PAIR_DIR"
echo "Score dir:           $SCORE_DIR"
echo "Analysis dir:        $ANALYSIS_DIR"
echo "Sample size:         $SAMPLE_SIZE"
echo "Seed:                $SEED"
echo "Batch size:          $BATCH_SIZE"
echo "Device:              $DEVICE"
echo "Score mode:          $SCORE_MODE"
echo "Skip missing models: $SKIP_MISSING_MODELS"
echo "Python:              $PYTHON_BIN"
echo

echo "========== 1. Batch Generate Minimal Pairs =========="
shopt -s nullglob
selected_files=("$SELECTED_DIR"/[0-9][0-9]_*.jsonl)

if [[ "${#selected_files[@]}" -eq 0 ]]; then
  echo "Error: no selected GOOD files found in $SELECTED_DIR"
  exit 1
fi

for f in "${selected_files[@]}"; do
  lang="$(basename "$f" .jsonl)"
  echo "----- pairs: $lang -----"
  "$PYTHON_BIN" evaluation/E1/apply_perturbation.py \
    --phenomenon-dir "$PHEN_DIR" \
    --good-items "$f" \
    --out "$PAIR_DIR/${lang}.pairs.jsonl" \
    --sample-size "$SAMPLE_SIZE" \
    --seed "$SEED"
done

echo
pair_count="$(find "$PAIR_DIR" -maxdepth 1 -name '*.pairs.jsonl' | wc -l | tr -d ' ')"
echo "Pair files: $pair_count"
wc -l "$PAIR_DIR"/*.pairs.jsonl | tail
echo

if [[ "$CHECK_PARALLEL_IDS" == true ]]; then
  echo "========== 2. Check Sampled Ids Are Parallel =========="
  "$PYTHON_BIN" - "$PAIR_DIR" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])
files = sorted(base.glob("*.pairs.jsonl"))

ref = None
ref_name = ""
bad = []

for p in files:
    ids = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            ids.append(json.loads(line)["id"])

    if ref is None:
        ref = ids
        ref_name = p.name
    elif ids != ref:
        bad.append(p.name)

print("files", len(files))
print("ref", ref_name if files else "")
print("same_id_sequence", len(bad) == 0)
if bad:
    print("different:", bad[:20])
    raise SystemExit(1)
PY
  echo
fi

echo "========== 3. Batch Score Models =========="
score_count=0
skip_count=0

pair_files=("$PAIR_DIR"/*.pairs.jsonl)
for f in "${pair_files[@]}"; do
  lang="$(basename "$f" .pairs.jsonl)"
  model="models/${lang}/seed_42/checkpoint-70000"

  if [[ ! -d "$model" ]]; then
    if [[ "$SKIP_MISSING_MODELS" == true ]]; then
      echo "[skip] missing model: $model"
      skip_count=$((skip_count + 1))
      continue
    fi
    echo "Error: missing model: $model"
    exit 1
  fi

  echo "----- score: $lang -----"
  "$PYTHON_BIN" evaluation/E1/score_e1_pairs.py \
    --model "$model" \
    --pairs "$f" \
    --out "$SCORE_DIR/${lang}.scores.tsv" \
    --summary "$SCORE_DIR/${lang}.summary.json" \
    --batch-size "$BATCH_SIZE" \
    --device "$DEVICE" \
    --score-mode "$SCORE_MODE"
  score_count=$((score_count + 1))
done

echo
echo "Scored models:  $score_count"
echo "Skipped models: $skip_count"
echo

echo "========== 4. Analyze 96 Scores =========="
"$PYTHON_BIN" evaluation/E1/analyze_e1_scores.py \
  --score-dir "$SCORE_DIR" \
  --out-dir "$ANALYSIS_DIR" \
  --manifest "$MANIFEST" \
  --lowest-n "$LOWEST_N"

echo
echo "========== DONE =========="
echo "Quick report: $ANALYSIS_DIR/quick_report.json"
echo "Model table:  $ANALYSIS_DIR/model_summary.tsv"
