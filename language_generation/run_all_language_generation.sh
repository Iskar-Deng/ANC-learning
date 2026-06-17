#!/usr/bin/env bash
set -euo pipefail

MRS_JSONL=""
LANGUAGES_DIR="grammars"
OUT_BASE=""
LOG_DIR="logs/generation"
WORKERS=12
CHUNKSIZE=100
MAX_GEN=20
SKIP_EXISTING=false
DRY_RUN=false
NOHUP_MODE=false
PYTHON_BIN="${PYTHON:-python}"

usage() {
  cat <<EOF
Usage:
  $0 --mrs PATH [options]

Required:
  --mrs PATH                   Input MRS JSONL, e.g. data/sample/sample_mrs.jsonl

Options:
  --languages-dir DIR          Directory containing compiled grammars. Default: grammars
  --out-base DIR               Output base directory. Default: derived from MRS path, e.g. data/sample/generated
  --log-dir DIR                Log directory. Default: logs/generation
  --workers N                  Number of workers for generation. Default: 12
  --chunksize N                Chunk size for generation. Default: 100
  --max-gen N                  Maximum generations per MRS. Default: 20
  --skip-existing              Skip languages whose selected output already exists
  --nohup                      Run raw generation in background; selection is not run in this mode
  --dry-run                    Print commands without running them
  --python PATH                Python executable. Default: \$PYTHON or python
  -h, --help                   Show this help message

Example:
  $0 --mrs data/sample/sample_mrs.jsonl
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
    --skip-existing)
      SKIP_EXISTING=true
      shift
      ;;
    --nohup)
      NOHUP_MODE=true
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
      echo "Error: unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$MRS_JSONL" ]]; then
  echo "Error: missing required argument: --mrs PATH"
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f "$MRS_JSONL" ]]; then
  echo "Error: MRS file not found: $MRS_JSONL"
  exit 1
fi

if [[ ! -d "$LANGUAGES_DIR" ]]; then
  echo "Error: languages directory not found: $LANGUAGES_DIR"
  exit 1
fi

if [[ -z "$OUT_BASE" ]]; then
  MRS_DIR="$(dirname "$MRS_JSONL")"
  OUT_BASE="${MRS_DIR}/generated"
fi

RAW_DIR="${OUT_BASE}/raw"
SELECTED_DIR="${OUT_BASE}/selected"
DETAILS_DIR="${OUT_BASE}/details"

mkdir -p "$RAW_DIR" "$SELECTED_DIR" "$DETAILS_DIR" "$LOG_DIR"

FAILED_LIST="$LOG_DIR/failed_generation.tsv"
SKIPPED_LIST="$LOG_DIR/skipped_generation.tsv"
SUCCESS_LIST="$LOG_DIR/success_generation.tsv"
OVERGEN_SUMMARY="$LOG_DIR/overgen_summary.tsv"

printf "language\treason\n" > "$FAILED_LIST"
printf "language\treason\n" > "$SKIPPED_LIST"
printf "language\treason\n" > "$SUCCESS_LIST"

printf "language\tovergenerated_ids\tsame_bag_overgenerated_ids\tdifferent_bag_overgenerated_ids\tresolved_by_s_mark_variant\tresolved_by_anc_ap_order\tap_order_multiple_match_random\tsame_bag_unresolved_random\tdifferent_bag_random\tdetails_file\tselect_log\n" > "$OVERGEN_SUMMARY"

record_failed() {
  local lang_id="$1"
  local reason="$2"
  printf "%s\t%s\n" "$lang_id" "$reason" >> "$FAILED_LIST"
}

record_skipped() {
  local lang_id="$1"
  local reason="$2"
  printf "%s\t%s\n" "$lang_id" "$reason" >> "$SKIPPED_LIST"
}

record_success() {
  local lang_id="$1"
  local reason="$2"
  printf "%s\t%s\n" "$lang_id" "$reason" >> "$SUCCESS_LIST"
}

extract_count_from_log() {
  local log_file="$1"
  local label="$2"
  local value

  value="$(grep -F "$label" "$log_file" | tail -n 1 | sed -E 's/.*: *([0-9]+).*/\1/' || true)"

  if [[ -z "$value" ]]; then
    echo "0"
  else
    echo "$value"
  fi
}

record_overgen_summary() {
  local lang_id="$1"
  local details_out="$2"
  local select_log="$3"

  local overgen
  local same_bag
  local different_bag
  local s_mark
  local ap_order
  local ap_multi
  local same_unresolved
  local different_random

  overgen="$(extract_count_from_log "$select_log" "Overgenerated ids")"
  same_bag="$(extract_count_from_log "$select_log" "Same-bag overgenerated ids")"
  different_bag="$(extract_count_from_log "$select_log" "Different-bag overgenerated ids")"
  s_mark="$(extract_count_from_log "$select_log" "Resolved by S-marker suffix variant")"
  ap_order="$(extract_count_from_log "$select_log" "Resolved by ANC A/P order")"
  ap_multi="$(extract_count_from_log "$select_log" "A/P order multiple match, random choice")"
  same_unresolved="$(extract_count_from_log "$select_log" "Same-bag unresolved, random choice")"
  different_random="$(extract_count_from_log "$select_log" "Different-bag overgenerated, random choice")"

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "$lang_id" \
    "$overgen" \
    "$same_bag" \
    "$different_bag" \
    "$s_mark" \
    "$ap_order" \
    "$ap_multi" \
    "$same_unresolved" \
    "$different_random" \
    "$details_out" \
    "$select_log" >> "$OVERGEN_SUMMARY"
}

echo "========== Generate All Target Languages =========="
echo "Project root:   $PROJECT_ROOT"
echo "MRS:            $MRS_JSONL"
echo "Languages dir:  $LANGUAGES_DIR"
echo "Output base:    $OUT_BASE"
echo "Raw dir:        $RAW_DIR"
echo "Selected dir:   $SELECTED_DIR"
echo "Details dir:    $DETAILS_DIR"
echo "Log dir:        $LOG_DIR"
echo "Workers:        $WORKERS"
echo "Chunksize:      $CHUNKSIZE"
echo "Max gen:        $MAX_GEN"
echo "Python:         $PYTHON_BIN"
echo "Nohup mode:     $NOHUP_MODE"
echo

count=0
skipped=0
failed=0
seen=0

shopt -s nullglob
grammar_dirs=("$LANGUAGES_DIR"/[0-9][0-9]_*)
shopt -u nullglob

if [[ "${#grammar_dirs[@]}" -eq 0 ]]; then
  echo "Error: no numbered grammar directories found in $LANGUAGES_DIR"
  echo "Expected directories like: $LANGUAGES_DIR/62_svo_ng_er_d_ep"
  exit 1
fi

for grammar_root in "${grammar_dirs[@]}"; do
  if [[ ! -d "$grammar_root" ]]; then
    continue
  fi

  lang_id="$(basename "$grammar_root")"
  grammar_dat="$grammar_root/$lang_id.dat"

  raw_out="$RAW_DIR/$lang_id.jsonl"
  selected_out="$SELECTED_DIR/$lang_id.jsonl"
  details_out="$DETAILS_DIR/$lang_id.jsonl"
  gen_log="$LOG_DIR/$lang_id.generate.log"
  select_log="$LOG_DIR/$lang_id.select.log"

  seen=$((seen + 1))

  echo
  echo "---------- $lang_id ----------"

  if [[ ! -f "$grammar_dat" ]]; then
    echo "[failed] grammar dat not found: $grammar_dat"
    record_failed "$lang_id" "grammar_dat_not_found"
    failed=$((failed + 1))
    continue
  fi

  if [[ "$SKIP_EXISTING" == true && -f "$selected_out" ]]; then
    echo "[skip] selected output already exists: $selected_out"
    record_skipped "$lang_id" "selected_output_exists"
    skipped=$((skipped + 1))

    if [[ -f "$select_log" ]]; then
      record_overgen_summary "$lang_id" "$details_out" "$select_log"
    fi

    continue
  fi

  if [[ "$NOHUP_MODE" == true ]]; then
    echo "[nohup] generating raw output only..."
    echo "Log: $gen_log"

    if [[ "$DRY_RUN" == true ]]; then
      echo "+ nohup $PYTHON_BIN -m language_generation.generate_from_mrs_bank --grammar $grammar_dat --input $MRS_JSONL --out $raw_out --no-mrs --workers $WORKERS --chunksize $CHUNKSIZE --max-gen $MAX_GEN > $gen_log 2>&1 &"
      record_success "$lang_id" "dry_run_nohup"
      count=$((count + 1))
      continue
    fi

    nohup "$PYTHON_BIN" -m language_generation.generate_from_mrs_bank \
      --grammar "$grammar_dat" \
      --input "$MRS_JSONL" \
      --out "$raw_out" \
      --no-mrs \
      --workers "$WORKERS" \
      --chunksize "$CHUNKSIZE" \
      --max-gen "$MAX_GEN" \
      > "$gen_log" 2>&1 &

    record_success "$lang_id" "generation_started_nohup"
    count=$((count + 1))
    continue
  fi

  echo "[1/2] Generating raw output..."
  if [[ "$DRY_RUN" == true ]]; then
    echo "+ $PYTHON_BIN -m language_generation.generate_from_mrs_bank --grammar $grammar_dat --input $MRS_JSONL --out $raw_out --no-mrs --workers $WORKERS --chunksize $CHUNKSIZE --max-gen $MAX_GEN > $gen_log 2>&1"
  elif ! "$PYTHON_BIN" -m language_generation.generate_from_mrs_bank \
    --grammar "$grammar_dat" \
    --input "$MRS_JSONL" \
    --out "$raw_out" \
    --no-mrs \
    --workers "$WORKERS" \
    --chunksize "$CHUNKSIZE" \
    --max-gen "$MAX_GEN" \
    > "$gen_log" 2>&1; then

    echo "[failed] generation failed"
    echo "Log: $gen_log"
    record_failed "$lang_id" "generation_failed"
    failed=$((failed + 1))
    continue
  fi

  if [[ "$DRY_RUN" == false && ! -f "$raw_out" ]]; then
    echo "[failed] raw output not created: $raw_out"
    echo "Log: $gen_log"
    record_failed "$lang_id" "raw_output_not_created"
    failed=$((failed + 1))
    continue
  fi

  echo "[2/2] Selecting overgeneration output..."
  if [[ "$DRY_RUN" == true ]]; then
    echo "+ $PYTHON_BIN language_generation/select_overgen.py --input $raw_out --out $selected_out --save-details $details_out > $select_log 2>&1"
    record_success "$lang_id" "dry_run"
    count=$((count + 1))
    continue
  elif ! "$PYTHON_BIN" language_generation/select_overgen.py \
    --input "$raw_out" \
    --out "$selected_out" \
    --save-details "$details_out" \
    > "$select_log" 2>&1; then

    echo "[failed] selection failed"
    echo "Log: $select_log"
    record_failed "$lang_id" "selection_failed"
    failed=$((failed + 1))
    continue
  fi

  if [[ ! -f "$selected_out" ]]; then
    echo "[failed] selected output not created: $selected_out"
    echo "Log: $select_log"
    record_failed "$lang_id" "selected_output_not_created"
    failed=$((failed + 1))
    continue
  fi

  record_overgen_summary "$lang_id" "$details_out" "$select_log"

  echo "[ok] $lang_id"
  echo "Generate log: $gen_log"
  echo "Select log:   $select_log"
  echo "Details:      $details_out"

  record_success "$lang_id" "generated_and_selected"
  count=$((count + 1))
done

echo
echo "========== Done =========="
echo "Grammar dirs seen: $seen"
echo "Completed:         $count"
echo "Skipped:           $skipped"
echo "Failed:            $failed"
echo
echo "Success list:       $SUCCESS_LIST"
echo "Skipped list:       $SKIPPED_LIST"
echo "Failed list:        $FAILED_LIST"
echo "Overgen summary:    $OVERGEN_SUMMARY"
echo
echo "Raw outputs:        $RAW_DIR"
echo "Selected outputs:   $SELECTED_DIR"
echo "Details outputs:    $DETAILS_DIR"

if [[ "$failed" -gt 0 ]]; then
  echo
  echo "Failed languages:"
  tail -n +2 "$FAILED_LIST"
  exit 1
fi
