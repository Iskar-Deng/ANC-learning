#!/usr/bin/env bash
set -euo pipefail

RAW_DIR=""
SELECTED_DIR=""
DETAILS_DIR=""
LOG_DIR="logs/generation"
SKIP_EXISTING=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage:
  $0 --raw-dir DIR [options]

Required:
  --raw-dir DIR                Raw generation directory, e.g. data/sample/generated/raw

Options:
  --selected-dir DIR           Selected output directory. Default: sibling selected/
  --details-dir DIR            Details output directory. Default: sibling details/
  --log-dir DIR                Log directory. Default: logs/generation
  --skip-existing              Skip languages whose selected output already exists
  --dry-run                    Print commands without running them
  -h, --help                   Show this help message

Example:
  $0 --raw-dir data/sample/generated/raw
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw-dir)
      RAW_DIR="$2"
      shift 2
      ;;
    --selected-dir)
      SELECTED_DIR="$2"
      shift 2
      ;;
    --details-dir)
      DETAILS_DIR="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
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

if [[ -z "$RAW_DIR" ]]; then
  echo "Error: missing required argument: --raw-dir DIR"
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -d "$RAW_DIR" ]]; then
  echo "Error: raw directory not found: $RAW_DIR"
  exit 1
fi

RAW_PARENT="$(dirname "$RAW_DIR")"

if [[ -z "$SELECTED_DIR" ]]; then
  SELECTED_DIR="$RAW_PARENT/selected"
fi

if [[ -z "$DETAILS_DIR" ]]; then
  DETAILS_DIR="$RAW_PARENT/details"
fi

mkdir -p "$SELECTED_DIR" "$DETAILS_DIR" "$LOG_DIR"

FAILED_LIST="$LOG_DIR/failed_selection.tsv"
SKIPPED_LIST="$LOG_DIR/skipped_selection.tsv"
SUCCESS_LIST="$LOG_DIR/success_selection.tsv"
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

echo "========== Rerun Selection Only =========="
echo "Project root:   $PROJECT_ROOT"
echo "Raw dir:        $RAW_DIR"
echo "Selected dir:   $SELECTED_DIR"
echo "Details dir:    $DETAILS_DIR"
echo "Log dir:        $LOG_DIR"
echo

count=0
skipped=0
failed=0
seen=0

shopt -s nullglob
raw_files=("$RAW_DIR"/[0-9][0-9]_*.jsonl)
shopt -u nullglob

if [[ "${#raw_files[@]}" -eq 0 ]]; then
  echo "Error: no numbered raw JSONL files found in $RAW_DIR"
  echo "Expected files like: $RAW_DIR/62_svo_ng_er_d_ep.jsonl"
  exit 1
fi

for raw_in in "${raw_files[@]}"; do
  lang_id="$(basename "$raw_in" .jsonl)"

  selected_out="$SELECTED_DIR/$lang_id.jsonl"
  details_out="$DETAILS_DIR/$lang_id.jsonl"
  select_log="$LOG_DIR/$lang_id.select.log"

  seen=$((seen + 1))

  echo
  echo "---------- $lang_id ----------"

  if [[ "$SKIP_EXISTING" == true && -f "$selected_out" ]]; then
    echo "[skip] selected output already exists: $selected_out"
    record_skipped "$lang_id" "selected_output_exists"

    if [[ -f "$select_log" ]]; then
      record_overgen_summary "$lang_id" "$details_out" "$select_log"
    fi

    skipped=$((skipped + 1))
    continue
  fi

  if [[ "$DRY_RUN" == true ]]; then
    echo "+ python language_generation/select_overgen.py --input $raw_in --out $selected_out --save-details $details_out > $select_log 2>&1"
    record_success "$lang_id" "dry_run"
    count=$((count + 1))
    continue
  fi

  if ! python language_generation/select_overgen.py \
    --input "$raw_in" \
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
  echo "Selected: $selected_out"
  echo "Details:  $details_out"
  echo "Log:      $select_log"

  record_success "$lang_id" "selected"
  count=$((count + 1))
done

echo
echo "========== Done =========="
echo "Raw files seen:     $seen"
echo "Completed:          $count"
echo "Skipped:            $skipped"
echo "Failed:             $failed"
echo
echo "Success list:       $SUCCESS_LIST"
echo "Skipped list:       $SKIPPED_LIST"
echo "Failed list:        $FAILED_LIST"
echo "Overgen summary:    $OVERGEN_SUMMARY"
echo
echo "Selected outputs:   $SELECTED_DIR"
echo "Details outputs:    $DETAILS_DIR"

if [[ "$failed" -gt 0 ]]; then
  echo
  echo "Failed selections:"
  tail -n +2 "$FAILED_LIST"
  exit 1
fi