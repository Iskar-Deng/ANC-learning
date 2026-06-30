#!/usr/bin/env bash
set -euo pipefail

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

PHEN=""
SMOKE_LANG=""
SAMPLE_SIZE=100
SEED=42
PARSE_WORKERS=8
GEN_WORKERS=12
CHUNKSIZE=50
MAX_GEN=20
SKIP_EXISTING_GENERATION=false
PYTHON_BIN="${PYTHON:-python}"
EXTERNAL_ANC_LEXICON=""
FORCE_ANC_SOURCE_CONSTRUCTION=""

usage() {
  cat <<EOF
Usage:
  $0 --phenomenon PHENOMENON [options]

Runs E1 through smoke-pair generation, then stops for manual inspection.

Required:
  --phenomenon NAME            e.g. 1_1_intran_V_form

Options:
  --smoke-lang LANG            Smoke-test language. Default: random generated language
  --sample-size N              Smoke pair sample size. Default: 100
  --seed N                     Sampling seed. Default: 42
  --parse-workers N            Pseudo-English parse workers. Default: 8
  --gen-workers N              Target generation workers. Default: 12
  --chunksize N                Parse/generation chunksize. Default: 50
  --max-gen N                  Max generations per MRS. Default: 20
  --skip-existing-generation   Pass through to run_all_language_generation.sh
  --python PATH                Python executable. Default: \$PYTHON or python
  --external-anc-lexicon PATH  Optional pseudo-English ANC lexicon seed
  --force-anc-source-construction iv|tv
                               Optional ANC candidate filter for pseudo-English
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
    --smoke-lang)
      SMOKE_LANG="$2"
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
    --parse-workers)
      PARSE_WORKERS="$2"
      shift 2
      ;;
    --gen-workers)
      GEN_WORKERS="$2"
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
    --skip-existing-generation)
      SKIP_EXISTING_GENERATION=true
      shift
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --external-anc-lexicon)
      EXTERNAL_ANC_LEXICON="$2"
      shift 2
      ;;
    --force-anc-source-construction)
      FORCE_ANC_SOURCE_CONSTRUCTION="$2"
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

if [[ -z "$PHEN" ]]; then
  echo "Error: missing required argument: --phenomenon NAME"
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

PHEN_DIR="evaluation/E1/phenomena/$PHEN"
MAT_DIR="e1_materials/$PHEN"
SOURCE="$PHEN_DIR/source.txt"
RULES="$PHEN_DIR/rules.py"
PSEUDO_GRAMMAR="grammars/pseudo-english/pseudo-english.dat"

EXTRACT="$MAT_DIR/${PHEN}_extract.jsonl"
EXTRACT_STATS="$MAT_DIR/${PHEN}_extract_stats.json"
PSEUDO="$MAT_DIR/${PHEN}_pseudo.jsonl"
LEXICON="$MAT_DIR/${PHEN}_lexicon.json"
PSEUDO_STATS="$MAT_DIR/${PHEN}_pseudo_stats.json"
MRS="$MAT_DIR/${PHEN}_mrs.jsonl"
GEN_BASE="$MAT_DIR/generated"
GEN_LOG_DIR="$MAT_DIR/logs/generation"

if [[ ! -f "$SOURCE" ]]; then
  echo "Error: source not found: $SOURCE"
  exit 1
fi

if [[ ! -f "$RULES" ]]; then
  echo "Error: rules not found: $RULES"
  exit 1
fi

if [[ ! -f "$PSEUDO_GRAMMAR" ]]; then
  echo "Error: pseudo-English grammar not found: $PSEUDO_GRAMMAR"
  exit 1
fi

mkdir -p "$MAT_DIR"

echo "========== E1 Until Smoke =========="
echo "Project root:      $PROJECT_ROOT"
echo "Phenomenon:        $PHEN"
echo "Source:            $SOURCE"
echo "Smoke language:    ${SMOKE_LANG:-random after generation}"
echo "Sample size:       $SAMPLE_SIZE"
echo "Seed:              $SEED"
echo "Python:            $PYTHON_BIN"
echo "External ANC lex:  ${EXTERNAL_ANC_LEXICON:-none}"
echo "Force ANC source:  ${FORCE_ANC_SOURCE_CONSTRUCTION:-none}"
echo

echo "========== 1. Extract English Sources =========="
"$PYTHON_BIN" semantic_extraction/extract_basic.py \
  --input "$SOURCE" \
  --output "$EXTRACT" \
  --stats-output "$EXTRACT_STATS"

echo
cat "$EXTRACT_STATS"
echo

echo "========== 2. Generate Pseudo-English =========="
PSEUDO_CMD=(
  "$PYTHON_BIN" semantic_extraction/generate_pseudo_english.py
  --input "$EXTRACT"
  --out-jsonl "$PSEUDO"
  --out-lexicon "$LEXICON"
  --out-stats "$PSEUDO_STATS"
)

if [[ -n "$EXTERNAL_ANC_LEXICON" ]]; then
  PSEUDO_CMD+=(--external-anc-lexicon "$EXTERNAL_ANC_LEXICON")
fi

if [[ -n "$FORCE_ANC_SOURCE_CONSTRUCTION" ]]; then
  PSEUDO_CMD+=(--force-anc-source-construction "$FORCE_ANC_SOURCE_CONSTRUCTION")
fi

"${PSEUDO_CMD[@]}"

echo
echo "----- pseudo-English sample -----"
head -20 "$PSEUDO"
echo
echo "----- pseudo-English stats -----"
cat "$PSEUDO_STATS"
echo

echo "========== 3. Parse Pseudo-English To MRS =========="
PARSE_CMD=(
  "$PYTHON_BIN" -m semantic_extraction.parse_pseudo_with_grammar
  --grammar "$PSEUDO_GRAMMAR"
  --input "$PSEUDO"
  --out "$MRS"
  --max-parses 20
  --first-parse-only
  --skip-failed
  --workers "$PARSE_WORKERS"
  --chunksize "$CHUNKSIZE"
  --restart-every 5000
)

if [[ -n "$FORCE_ANC_SOURCE_CONSTRUCTION" ]]; then
  PARSE_CMD+=(--prefer-anc-source-construction "$FORCE_ANC_SOURCE_CONSTRUCTION")
fi

"${PARSE_CMD[@]}"

echo
wc -l "$PSEUDO" "$MRS"
echo

echo "========== 4. Generate GOOD Sentences With 96 Grammars =========="
GEN_CMD=(
  bash language_generation/run_all_language_generation.sh
  --mrs "$MRS"
  --out-base "$GEN_BASE"
  --log-dir "$GEN_LOG_DIR"
  --python "$PYTHON_BIN"
  --workers "$GEN_WORKERS"
  --chunksize "$CHUNKSIZE"
  --max-gen "$MAX_GEN"
)

if [[ "$SKIP_EXISTING_GENERATION" == true ]]; then
  GEN_CMD+=(--skip-existing)
fi

"${GEN_CMD[@]}"

if [[ -z "$SMOKE_LANG" ]]; then
  SMOKE_LANG="$(
    "$PYTHON_BIN" - "$GEN_BASE/selected" <<'PY'
import random
import sys
from pathlib import Path

selected_dir = Path(sys.argv[1])
files = sorted(selected_dir.glob("*.jsonl"))
if not files:
    raise SystemExit(f"No selected generation files found in {selected_dir}")
print(random.choice(files).stem)
PY
  )"
  echo
  echo "Random smoke language: $SMOKE_LANG"
fi

SMOKE_GOOD="$GEN_BASE/selected/${SMOKE_LANG}.jsonl"
SMOKE_PAIR="$MAT_DIR/pairs/${SMOKE_LANG}.pairs.jsonl"

if [[ ! -f "$SMOKE_GOOD" ]]; then
  echo "Error: smoke selected output not found: $SMOKE_GOOD"
  exit 1
fi

echo
echo "========== 5. Smoke Test Minimal Pairs =========="
mkdir -p "$MAT_DIR/pairs"

"$PYTHON_BIN" evaluation/E1/apply_perturbation.py \
  --phenomenon-dir "$PHEN_DIR" \
  --good-items "$SMOKE_GOOD" \
  --out "$SMOKE_PAIR" \
  --sample-size "$SAMPLE_SIZE" \
  --seed "$SEED"

echo
echo "----- smoke pair sample -----"
head -5 "$SMOKE_PAIR"
echo
echo "========== STOP =========="
echo "Inspect the smoke pairs above before batch scoring."
echo "Then run:"
echo "  evaluation/E1/run_e1_after_smoke.sh --phenomenon $PHEN"
