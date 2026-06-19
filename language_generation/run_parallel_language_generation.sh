#!/usr/bin/env bash
set -euo pipefail

MRS_JSONL=""
LANGUAGES_DIR="grammars"
OUT_BASE=""
LOG_DIR="logs/generation_parallel"
PARALLEL_JOBS=8
WORKERS=2
CHUNKSIZE=100
MAX_GEN=20
ACE_MODE="persistent"
RESTART_EVERY=10
SKIP_EXISTING=false
DRY_RUN=false
PYTHON_BIN="${PYTHON:-python}"

usage() {
  cat <<EOF
Usage:
  $0 --mrs PATH [options]

Required:
  --mrs PATH                   Input MRS JSONL

Options:
  --languages-dir DIR          Directory containing compiled grammars. Default: grammars
  --out-base DIR               Output base directory. Default: derived from MRS path
  --log-dir DIR                Log directory. Default: logs/generation_parallel
  --parallel-jobs N            Number of grammars to run at once. Default: 8
  --workers N                  Workers inside each grammar generation job. Default: 2
  --chunksize N                Chunk size for generation. Default: 100
  --max-gen N                  Maximum generations per MRS. Default: 20
  --ace-mode MODE              oneoff or persistent. Default: persistent
  --restart-every N            In persistent mode, restart ACE after N items per worker. Default: 10
  --skip-existing              Skip languages whose selected output already exists
  --dry-run                    Print commands without running them
  --python PATH                Python executable. Default: \$PYTHON or python
  -h, --help                   Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mrs)
      MRS_JSONL="$2"
      shift 2
      ;;
    --languages-dir)
      LANGUAGES_DIR="$2"
      shift 2
      ;;
    --out-base)
      OUT_BASE="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    --parallel-jobs)
      PARALLEL_JOBS="$2"
      shift 2
      ;;
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
    --ace-mode)
      ACE_MODE="$2"
      shift 2
      ;;
    --restart-every)
      RESTART_EVERY="$2"
      shift 2
      ;;
    --skip-existing)
      SKIP_EXISTING=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$MRS_JSONL" ]]; then
  echo "Error: missing required argument: --mrs PATH" >&2
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f "$MRS_JSONL" ]]; then
  echo "Error: MRS file not found: $MRS_JSONL" >&2
  exit 1
fi

if [[ ! -d "$LANGUAGES_DIR" ]]; then
  echo "Error: languages directory not found: $LANGUAGES_DIR" >&2
  exit 1
fi

if [[ -z "$OUT_BASE" ]]; then
  MRS_DIR="$(dirname "$MRS_JSONL")"
  OUT_BASE="${MRS_DIR}/generated"
fi

RAW_DIR="${OUT_BASE}/raw"
SELECTED_DIR="${OUT_BASE}/selected"
DETAILS_DIR="${OUT_BASE}/details"
STATUS_DIR="${LOG_DIR}/status"

mkdir -p "$RAW_DIR" "$SELECTED_DIR" "$DETAILS_DIR" "$LOG_DIR"
rm -rf "$STATUS_DIR"
mkdir -p "$STATUS_DIR"

SUMMARY="$LOG_DIR/summary.tsv"
printf "language\tstatus\treason\tseconds\traw_out\tselected_out\tgenerate_log\tselect_log\n" > "$SUMMARY"

shopt -s nullglob
grammar_dirs=("$LANGUAGES_DIR"/[0-9][0-9]_*)
shopt -u nullglob

if [[ "${#grammar_dirs[@]}" -eq 0 ]]; then
  echo "Error: no numbered grammar directories found in $LANGUAGES_DIR" >&2
  exit 1
fi

echo "========== Parallel Language Generation =========="
echo "Project root:   $PROJECT_ROOT"
echo "MRS:            $MRS_JSONL"
echo "Languages dir:  $LANGUAGES_DIR"
echo "Output base:    $OUT_BASE"
echo "Log dir:        $LOG_DIR"
echo "Parallel jobs:  $PARALLEL_JOBS"
echo "Workers/job:    $WORKERS"
echo "Chunksize:      $CHUNKSIZE"
echo "Max gen:        $MAX_GEN"
echo "ACE mode:       $ACE_MODE"
echo "Restart every:  $RESTART_EVERY"
echo "Python:         $PYTHON_BIN"
echo

run_one_language() {
  local grammar_root="$1"
  local lang_id
  local grammar_dat
  local raw_out
  local selected_out
  local details_out
  local gen_log
  local select_log
  local status_file
  local start
  local end
  local seconds

  lang_id="$(basename "$grammar_root")"
  grammar_dat="$grammar_root/$lang_id.dat"
  raw_out="$RAW_DIR/$lang_id.jsonl"
  selected_out="$SELECTED_DIR/$lang_id.jsonl"
  details_out="$DETAILS_DIR/$lang_id.jsonl"
  gen_log="$LOG_DIR/$lang_id.generate.log"
  select_log="$LOG_DIR/$lang_id.select.log"
  status_file="$STATUS_DIR/$lang_id.tsv"

  start="$(date +%s)"

  if [[ ! -f "$grammar_dat" ]]; then
    end="$(date +%s)"
    seconds=$((end - start))
    printf "%s\tfailed\tgrammar_dat_not_found\t%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$seconds" "$raw_out" "$selected_out" "$gen_log" "$select_log" > "$status_file"
    return 0
  fi

  if [[ "$SKIP_EXISTING" == true && -f "$selected_out" ]]; then
    end="$(date +%s)"
    seconds=$((end - start))
    printf "%s\tskipped\tselected_output_exists\t%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$seconds" "$raw_out" "$selected_out" "$gen_log" "$select_log" > "$status_file"
    return 0
  fi

  if [[ "$DRY_RUN" == true ]]; then
    echo "+ $PYTHON_BIN -m language_generation.generate_from_mrs_bank --grammar $grammar_dat --input $MRS_JSONL --out $raw_out --no-mrs --workers $WORKERS --chunksize $CHUNKSIZE --max-gen $MAX_GEN --ace-mode $ACE_MODE --restart-every $RESTART_EVERY > $gen_log 2>&1"
    echo "+ $PYTHON_BIN language_generation/select_overgen.py --input $raw_out --out $selected_out --save-details $details_out > $select_log 2>&1"
    end="$(date +%s)"
    seconds=$((end - start))
    printf "%s\tsuccess\tdry_run\t%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$seconds" "$raw_out" "$selected_out" "$gen_log" "$select_log" > "$status_file"
    return 0
  fi

  if ! "$PYTHON_BIN" -m language_generation.generate_from_mrs_bank \
    --grammar "$grammar_dat" \
    --input "$MRS_JSONL" \
    --out "$raw_out" \
    --no-mrs \
    --workers "$WORKERS" \
    --chunksize "$CHUNKSIZE" \
    --max-gen "$MAX_GEN" \
    --ace-mode "$ACE_MODE" \
    --restart-every "$RESTART_EVERY" \
    > "$gen_log" 2>&1; then
    end="$(date +%s)"
    seconds=$((end - start))
    printf "%s\tfailed\tgeneration_failed\t%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$seconds" "$raw_out" "$selected_out" "$gen_log" "$select_log" > "$status_file"
    return 0
  fi

  if ! "$PYTHON_BIN" language_generation/select_overgen.py \
    --input "$raw_out" \
    --out "$selected_out" \
    --save-details "$details_out" \
    > "$select_log" 2>&1; then
    end="$(date +%s)"
    seconds=$((end - start))
    printf "%s\tfailed\tselection_failed\t%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$seconds" "$raw_out" "$selected_out" "$gen_log" "$select_log" > "$status_file"
    return 0
  fi

  end="$(date +%s)"
  seconds=$((end - start))
  printf "%s\tsuccess\tok\t%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$seconds" "$raw_out" "$selected_out" "$gen_log" "$select_log" > "$status_file"
}

active=0
for grammar_root in "${grammar_dirs[@]}"; do
  lang_id="$(basename "$grammar_root")"
  echo "[launch] $lang_id"
  run_one_language "$grammar_root" &
  active=$((active + 1))

  if [[ "$active" -ge "$PARALLEL_JOBS" ]]; then
    wait -n || true
    active=$((active - 1))
  fi
done

while [[ "$active" -gt 0 ]]; do
  wait -n || true
  active=$((active - 1))
done

find "$STATUS_DIR" -type f -name '*.tsv' -print0 | sort -z | xargs -0 cat >> "$SUMMARY"

echo
echo "========== Done =========="
awk -F '\t' 'NR > 1 { count[$2] += 1 } END { for (s in count) print s, count[s] }' "$SUMMARY" | sort
echo "Summary: $SUMMARY"
