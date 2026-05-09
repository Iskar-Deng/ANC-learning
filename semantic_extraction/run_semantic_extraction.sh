#!/usr/bin/env bash
set -euo pipefail

INPUT=""
GRAMMAR_NAME="pseudo-english"
GRAMMAR_ROOT=""
CHOICE_FILE=""
MATRIX_ROOT="external/matrix"
MATRIX_GMCS_ROOT="external/matrix/gmcs"
MAX_PARSES=20
OUT_DIR=""
WITH_TRIGGER=true
DEFAULT_COMP_TRIGGER="that"
FREEZER_MEGABYTES=""
PARSE_WORKERS=8
PARSE_CHUNKSIZE=100
PARSE_RESTART_EVERY=5000
SKIP_CUSTOMIZE_GRAMMAR=false
SKIP_LEXICON_UPDATE=false
SKIP_COMPILE=false

usage() {
  cat <<EOF
Usage:
  $0 --input PATH [options]

Required:
  --input PATH                  Input English .txt file, e.g. data/sample.txt

Options:
  --grammar-name NAME           Grammar name. Default: pseudo-english
  --grammar-root DIR            Grammar root. Default: grammars/<grammar-name>
  --choice-file PATH            Choice file. Default: choices/<grammar-name>.choice
  --matrix-root DIR             Grammar Matrix root. Default: external/matrix
  --matrix-gmcs-root DIR        Grammar Matrix gmcs root. Default: external/matrix/gmcs
  --out-dir DIR                 Output directory. Default: derived from input stem, e.g. data/sample/
  --max-parses N                Maximum parses per sentence. Default: 20
  --default-comp-trigger STR    Complementizer trigger string. Default: that
  --freezer-megabytes N         Pass freezer-megabytes to compile_grammar.sh
  --parse-workers N             Number of workers for pseudo-English parsing. Default: 8
  --parse-chunksize N           Chunk size for pseudo-English parsing. Default: 100
  --parse-restart-every N       Restart each ACE parser after N sentences. Default: 5000
  --no-trigger                  Do not write complementizer entries or trigger.mtr
  --skip-customize-grammar      Skip Grammar Matrix customization
  --skip-lexicon-update         Skip grammar lexicon update
  --skip-compile                Skip grammar compilation
  --skip-recompile              Alias for --skip-compile
  -h, --help                    Show this help message

Examples:
  $0 --input data/sample.txt

  $0 --input data/train.txt \\
    --freezer-megabytes 4096 \\
    --parse-workers 8 \\
    --parse-chunksize 100 \\
    --parse-restart-every 5000
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      INPUT="$2"
      shift 2
      ;;
    --grammar-name)
      GRAMMAR_NAME="$2"
      shift 2
      ;;
    --grammar-root)
      GRAMMAR_ROOT="$2"
      shift 2
      ;;
    --choice-file)
      CHOICE_FILE="$2"
      shift 2
      ;;
    --matrix-root)
      MATRIX_ROOT="$2"
      shift 2
      ;;
    --matrix-gmcs-root)
      MATRIX_GMCS_ROOT="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --max-parses)
      MAX_PARSES="$2"
      shift 2
      ;;
    --default-comp-trigger)
      DEFAULT_COMP_TRIGGER="$2"
      shift 2
      ;;
    --freezer-megabytes)
      FREEZER_MEGABYTES="$2"
      shift 2
      ;;
    --parse-workers)
      PARSE_WORKERS="$2"
      shift 2
      ;;
    --parse-chunksize)
      PARSE_CHUNKSIZE="$2"
      shift 2
      ;;
    --parse-restart-every)
      PARSE_RESTART_EVERY="$2"
      shift 2
      ;;
    --no-trigger)
      WITH_TRIGGER=false
      shift
      ;;
    --skip-customize-grammar)
      SKIP_CUSTOMIZE_GRAMMAR=true
      shift
      ;;
    --skip-lexicon-update)
      SKIP_LEXICON_UPDATE=true
      shift
      ;;
    --skip-compile|--skip-recompile)
      SKIP_COMPILE=true
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

if [[ ! -f "$INPUT" ]]; then
  echo "Error: input file not found: $INPUT"
  exit 1
fi

if [[ -n "$FREEZER_MEGABYTES" && ! "$FREEZER_MEGABYTES" =~ ^[0-9]+$ ]]; then
  echo "Error: --freezer-megabytes must be an integer: $FREEZER_MEGABYTES"
  exit 1
fi

if ! [[ "$PARSE_WORKERS" =~ ^[0-9]+$ ]] || [[ "$PARSE_WORKERS" -lt 1 ]]; then
  echo "Error: --parse-workers must be an integer >= 1: $PARSE_WORKERS"
  exit 1
fi

if ! [[ "$PARSE_CHUNKSIZE" =~ ^[0-9]+$ ]] || [[ "$PARSE_CHUNKSIZE" -lt 1 ]]; then
  echo "Error: --parse-chunksize must be an integer >= 1: $PARSE_CHUNKSIZE"
  exit 1
fi

if ! [[ "$PARSE_RESTART_EVERY" =~ ^[0-9]+$ ]]; then
  echo "Error: --parse-restart-every must be an integer >= 0: $PARSE_RESTART_EVERY"
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -z "$GRAMMAR_ROOT" ]]; then
  GRAMMAR_ROOT="grammars/${GRAMMAR_NAME}"
fi

if [[ -z "$CHOICE_FILE" ]]; then
  CHOICE_FILE="choices/${GRAMMAR_NAME}.choice"
fi

if [[ "$SKIP_CUSTOMIZE_GRAMMAR" == false ]]; then
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
else
  if [[ ! -d "$GRAMMAR_ROOT" ]]; then
    echo "Error: grammar root not found and --skip-customize-grammar was set: $GRAMMAR_ROOT"
    exit 1
  fi
fi

INPUT_DIR="$(dirname "$INPUT")"
INPUT_BASE="$(basename "$INPUT")"
STEM="${INPUT_BASE%.*}"

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="${INPUT_DIR}/${STEM}"
fi

mkdir -p "$OUT_DIR"

EXTRACT_JSONL="${OUT_DIR}/${STEM}_extract.jsonl"
EXTRACT_STATS="${OUT_DIR}/${STEM}_extract_stats.json"

PSEUDO_JSONL="${OUT_DIR}/${STEM}_pseudo.jsonl"
LEXICON_JSON="${OUT_DIR}/${STEM}_lexicon.json"
PSEUDO_STATS="${OUT_DIR}/${STEM}_pseudo_stats.json"

MRS_JSONL="${OUT_DIR}/${STEM}_mrs.jsonl"

GRAMMAR_DAT="${GRAMMAR_ROOT}/${GRAMMAR_NAME}.dat"

if [[ ! -f "$GRAMMAR_DAT" && "$SKIP_COMPILE" == true ]]; then
  echo "Error: grammar dat file not found and --skip-compile was set: $GRAMMAR_DAT"
  exit 1
fi

echo "========== Semantic Extraction =========="
echo "Input:              $INPUT"
echo "Output dir:         $OUT_DIR"
echo "Choice file:        $CHOICE_FILE"
echo "Grammar root:       $GRAMMAR_ROOT"
echo "Grammar dat:        $GRAMMAR_DAT"
echo "Freezer MB:         ${FREEZER_MEGABYTES:-default}"
echo "With trigger:       $WITH_TRIGGER"
echo "Parse workers:      $PARSE_WORKERS"
echo "Parse chunksize:    $PARSE_CHUNKSIZE"
echo "Parse restart:      $PARSE_RESTART_EVERY"
echo

if [[ "$SKIP_CUSTOMIZE_GRAMMAR" == true ]]; then
  echo "[1/6] Skipping pseudo-English grammar customization..."
else
  echo "[1/6] Customizing pseudo-English grammar from choice file..."
  python "$MATRIX_ROOT/matrix.py" \
    --customizationroot "$MATRIX_GMCS_ROOT" \
    customize-to-destination \
    "$CHOICE_FILE" \
    "$GRAMMAR_ROOT"
fi

echo
echo "[2/6] Extracting controlled predicate-argument structures..."
python semantic_extraction/extract_basic.py \
  --input "$INPUT" \
  --output "$EXTRACT_JSONL" \
  --stats-output "$EXTRACT_STATS"

echo
echo "[3/6] Generating pseudo-English and lexicon..."
python semantic_extraction/generate_pseudo_english.py \
  --input "$EXTRACT_JSONL" \
  --out-jsonl "$PSEUDO_JSONL" \
  --out-lexicon "$LEXICON_JSON" \
  --out-stats "$PSEUDO_STATS"

echo
if [[ "$SKIP_LEXICON_UPDATE" == true ]]; then
  echo "[4/6] Skipping grammar lexicon update..."
else
  echo "[4/6] Updating grammar lexicon..."

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
fi

echo
if [[ "$SKIP_COMPILE" == true ]]; then
  echo "[5/6] Skipping grammar compilation..."
else
  echo "[5/6] Compiling grammar..."

  COMPILE_ARGS=("$GRAMMAR_DAT")

  if [[ -n "$FREEZER_MEGABYTES" ]]; then
    COMPILE_ARGS+=(--freezer-megabytes "$FREEZER_MEGABYTES")
  fi

  ./grammar_build/compile_grammar.sh "${COMPILE_ARGS[@]}"
fi

if [[ ! -f "$GRAMMAR_DAT" ]]; then
  echo "Error: grammar dat file not found after compilation: $GRAMMAR_DAT"
  exit 1
fi

echo
echo "[6/6] Parsing pseudo-English into MRS..."
python -m semantic_extraction.parse_pseudo_with_grammar \
  --grammar "$GRAMMAR_DAT" \
  --input "$PSEUDO_JSONL" \
  --out "$MRS_JSONL" \
  --max-parses "$MAX_PARSES" \
  --workers "$PARSE_WORKERS" \
  --chunksize "$PARSE_CHUNKSIZE" \
  --restart-every "$PARSE_RESTART_EVERY"

echo
echo "========== Done =========="
echo "Extracted:     $EXTRACT_JSONL"
echo "Extract stats: $EXTRACT_STATS"
echo "Pseudo:        $PSEUDO_JSONL"
echo "Lexicon:       $LEXICON_JSON"
echo "Pseudo stats:  $PSEUDO_STATS"
echo "MRS:           $MRS_JSONL"