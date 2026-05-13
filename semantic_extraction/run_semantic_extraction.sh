#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

INPUT=""
UPDATE_GRAMMAR=false

GRAMMAR_NAME="pseudo-english"
GRAMMAR_ROOT="grammars/pseudo-english"
CHOICE_FILE="choices/pseudo-english.choice"
MATRIX_ROOT="external/matrix"
MATRIX_GMCS_ROOT="external/matrix/gmcs"

MAX_PARSES=20
PARSE_WORKERS=8
PARSE_CHUNKSIZE=100
PARSE_RESTART_EVERY=5000
FREEZER_MEGABYTES=4096

WITH_TRIGGER=true
DEFAULT_COMP_TRIGGER="that"

usage() {
  cat <<EOF
Usage:
  $0 --input PATH [--update-grammar]

Required:
  --input PATH        Input English .txt file, e.g. data/train.txt

Options:
  --update-grammar   Customize/update/compile pseudo-English grammar.
                     Normally use this for train only.
  -h, --help         Show this help message

Examples:
  # Train: update pseudo-English grammar from train lexicon
  $0 --input data/train.txt --update-grammar

  # Dev/test: reuse train-built pseudo-English grammar
  $0 --input data/dev.txt
  $0 --input data/test.txt
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      INPUT="$2"
      shift 2
      ;;
    --update-grammar)
      UPDATE_GRAMMAR=true
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

if [[ -z "$INPUT" ]]; then
  echo "Error: missing required argument: --input PATH"
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f "$INPUT" ]]; then
  echo "Error: input file not found: $INPUT"
  exit 1
fi

INPUT_DIR="$(dirname "$INPUT")"
INPUT_BASE="$(basename "$INPUT")"
STEM="${INPUT_BASE%.*}"

OUT_DIR="${INPUT_DIR}/${STEM}"
mkdir -p "$OUT_DIR"

EXTRACT_JSONL="${OUT_DIR}/${STEM}_extract.jsonl"
EXTRACT_STATS="${OUT_DIR}/${STEM}_extract_stats.json"

PSEUDO_JSONL="${OUT_DIR}/${STEM}_pseudo.jsonl"
LEXICON_JSON="${OUT_DIR}/${STEM}_lexicon.json"
PSEUDO_STATS="${OUT_DIR}/${STEM}_pseudo_stats.json"

MRS_JSONL="${OUT_DIR}/${STEM}_mrs.jsonl"

GRAMMAR_DAT="${GRAMMAR_ROOT}/${GRAMMAR_NAME}.dat"

echo "========== Semantic Extraction =========="
echo "Input:          $INPUT"
echo "Output dir:     $OUT_DIR"
echo "Update grammar: $UPDATE_GRAMMAR"
echo "Grammar root:   $GRAMMAR_ROOT"
echo "Grammar dat:    $GRAMMAR_DAT"
echo "Freezer MB:     $FREEZER_MEGABYTES"
echo "Max parses:     $MAX_PARSES"
echo "Parse workers:  $PARSE_WORKERS"
echo "Chunksize:      $PARSE_CHUNKSIZE"
echo "Restart every:  $PARSE_RESTART_EVERY"
echo

echo "[1/5] Extracting controlled predicate-argument structures..."
python semantic_extraction/extract_basic.py \
  --input "$INPUT" \
  --output "$EXTRACT_JSONL" \
  --stats-output "$EXTRACT_STATS"

echo
echo "[2/5] Generating pseudo-English and lexicon..."
python semantic_extraction/generate_pseudo_english.py \
  --input "$EXTRACT_JSONL" \
  --out-jsonl "$PSEUDO_JSONL" \
  --out-lexicon "$LEXICON_JSON" \
  --out-stats "$PSEUDO_STATS"

echo
if [[ "$UPDATE_GRAMMAR" == true ]]; then
  echo "[3/5] Updating pseudo-English grammar..."

  if [[ ! -f "$CHOICE_FILE" ]]; then
    echo "Error: choice file not found: $CHOICE_FILE"
    exit 1
  fi

  if [[ ! -f "$MATRIX_ROOT/matrix.py" ]]; then
    echo "Error: matrix.py not found: $MATRIX_ROOT/matrix.py"
    exit 1
  fi

  if [[ ! -d "$MATRIX_GMCS_ROOT" ]]; then
    echo "Error: Grammar Matrix gmcs root not found: $MATRIX_GMCS_ROOT"
    exit 1
  fi

  python "$MATRIX_ROOT/matrix.py" \
    --customizationroot "$MATRIX_GMCS_ROOT" \
    customize-to-destination \
    "$CHOICE_FILE" \
    "$GRAMMAR_ROOT"

  UPDATE_ARGS=(
    --lexicon-json "$LEXICON_JSON"
    --grammar-root "$GRAMMAR_ROOT"
  )

  if [[ "$WITH_TRIGGER" == true ]]; then
    UPDATE_ARGS+=(
      --with-trigger
      --default-comp-trigger "$DEFAULT_COMP_TRIGGER"
    )
  fi

  python grammar_build/update_grammar_lexicon.py "${UPDATE_ARGS[@]}"

  ./grammar_build/compile_grammar.sh \
    "$GRAMMAR_DAT" \
    --freezer-megabytes "$FREEZER_MEGABYTES"
else
  echo "[3/5] Skipping grammar update..."
fi

if [[ ! -f "$GRAMMAR_DAT" ]]; then
  echo "Error: grammar dat file not found: $GRAMMAR_DAT"
  echo "Run with --update-grammar first, normally on data/train.txt."
  exit 1
fi

echo
echo "[4/5] Parsing pseudo-English into MRS..."
python -m semantic_extraction.parse_pseudo_with_grammar \
  --grammar "$GRAMMAR_DAT" \
  --input "$PSEUDO_JSONL" \
  --out "$MRS_JSONL" \
  --max-parses "$MAX_PARSES" \
  --workers "$PARSE_WORKERS" \
  --chunksize "$PARSE_CHUNKSIZE" \
  --restart-every "$PARSE_RESTART_EVERY"

echo
echo "[5/5] Done."

echo
echo "========== Outputs =========="
echo "Extracted:     $EXTRACT_JSONL"
echo "Extract stats: $EXTRACT_STATS"
echo "Pseudo:        $PSEUDO_JSONL"
echo "Lexicon:       $LEXICON_JSON"
echo "Pseudo stats:  $PSEUDO_STATS"
echo "MRS:           $MRS_JSONL"