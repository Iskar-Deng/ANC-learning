#!/usr/bin/env bash
set -euo pipefail

LEXICON_JSON=""
CHOICES_DIR="choices"
GRAMMARS_DIR="grammars"
MATRIX_ROOT="external/matrix"
MATRIX_GMCS_ROOT="external/matrix/gmcs"
LOG_DIR="logs/grammar_build"
FREEZER_MEGABYTES=""
SKIP_EXISTING=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage:
  $0 --lexicon-json PATH [options]

Required:
  --lexicon-json PATH          Lexicon JSON used to update all target grammars

Options:
  --choices-dir DIR            Default: choices
  --grammars-dir DIR           Default: grammars
  --matrix-root DIR            Default: external/matrix
  --matrix-gmcs-root DIR       Default: external/matrix/gmcs
  --log-dir DIR                Default: logs/grammar_build
  --freezer-megabytes N        Pass freezer-megabytes to compile_grammar.sh
  --skip-existing              Skip grammars whose .dat file already exists
  --dry-run                    Print commands without running them
  -h, --help                   Show this help message

Example:
  $0 --lexicon-json data/sample/sample_lexicon.json

Example with large train lexicon:
  $0 --lexicon-json data/train/train_lexicon.json --freezer-megabytes 4096
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lexicon-json)
      LEXICON_JSON="$2"
      shift 2
      ;;
    --choices-dir)
      CHOICES_DIR="$2"
      shift 2
      ;;
    --grammars-dir)
      GRAMMARS_DIR="$2"
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
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    --freezer-megabytes)
      FREEZER_MEGABYTES="$2"
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

if [[ -z "$LEXICON_JSON" ]]; then
  echo "Error: missing required argument: --lexicon-json PATH"
  usage
  exit 1
fi

if [[ -n "$FREEZER_MEGABYTES" && ! "$FREEZER_MEGABYTES" =~ ^[0-9]+$ ]]; then
  echo "Error: --freezer-megabytes must be an integer: $FREEZER_MEGABYTES"
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f "$LEXICON_JSON" ]]; then
  echo "Error: lexicon JSON not found: $LEXICON_JSON"
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

mkdir -p "$LOG_DIR"

FAILED_LIST="$LOG_DIR/failed_grammars.tsv"
SKIPPED_LIST="$LOG_DIR/skipped_grammars.tsv"
SUCCESS_LIST="$LOG_DIR/success_grammars.tsv"
PATCH_LIST="$LOG_DIR/patch_anc_wo.tsv"

: > "$FAILED_LIST"
: > "$SKIPPED_LIST"
: > "$SUCCESS_LIST"
: > "$PATCH_LIST"

printf "language\treason\n" > "$FAILED_LIST"
printf "language\treason\n" > "$SKIPPED_LIST"
printf "language\treason\n" > "$SUCCESS_LIST"
printf "language\tstatus\tancwo_replacements\topt_comp_replacements\tmessage\n" > "$PATCH_LIST"

run_cmd() {
  echo "+ $*"
  if [[ "$DRY_RUN" == false ]]; then
    "$@"
  fi
}

make_compile_args() {
  local dat_path="$1"
  COMPILE_ARGS=("$dat_path")

  if [[ -n "$FREEZER_MEGABYTES" ]]; then
    COMPILE_ARGS+=(--freezer-megabytes "$FREEZER_MEGABYTES")
  fi
}

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

record_patch() {
  local lang_id="$1"
  local status="$2"
  local ancwo="$3"
  local optcomp="$4"
  local message="$5"

  message="$(echo "$message" | tr '\t' ' ' | tr '\n' ' ')"
  printf "%s\t%s\t%s\t%s\t%s\n" "$lang_id" "$status" "$ancwo" "$optcomp" "$message" >> "$PATCH_LIST"
}

extract_patch_number() {
  local text="$1"
  local key="$2"
  local value

  value="$(echo "$text" | grep -oE "${key}=[0-9]+" | head -n 1 | cut -d= -f2 || true)"

  if [[ -z "$value" ]]; then
    echo "0"
  else
    echo "$value"
  fi
}

run_patch_and_record() {
  local lang_id="$1"
  local tdl_path="$2"

  if [[ "$DRY_RUN" == true ]]; then
    echo "+ python grammar_build/patch_anc_wo.py --tdl $tdl_path"
    record_patch "$lang_id" "dry_run" "NA" "NA" "dry run only"
    return 0
  fi

  if [[ ! -f "$tdl_path" ]]; then
    echo "[warn] TDL file not found, skipping ANC-WO patch: $tdl_path"
    record_patch "$lang_id" "tdl_missing" "NA" "NA" "TDL file not found"
    return 0
  fi

  local patch_output
  local patch_status

  set +e
  patch_output="$(python grammar_build/patch_anc_wo.py --tdl "$tdl_path" 2>&1)"
  patch_status=$?
  set -e

  echo "$patch_output"

  if [[ "$patch_status" -ne 0 ]]; then
    record_patch "$lang_id" "patch_failed" "NA" "NA" "$patch_output"
    return "$patch_status"
  fi

  local ancwo
  local optcomp
  ancwo="$(extract_patch_number "$patch_output" "ANC-WO replacements")"
  optcomp="$(extract_patch_number "$patch_output" "anc-head-opt-comp-phrase replacements")"

  if echo "$patch_output" | grep -q "^\[skip\] no ANC-WO"; then
    record_patch "$lang_id" "no_anc_wo" "$ancwo" "$optcomp" "$patch_output"
  elif echo "$patch_output" | grep -q "^\[patched\]"; then
    record_patch "$lang_id" "patched" "$ancwo" "$optcomp" "$patch_output"
  elif echo "$patch_output" | grep -q "^\[warn\] ANC-WO found but no patch applied"; then
    record_patch "$lang_id" "not_needed_or_no_change" "$ancwo" "$optcomp" "$patch_output"
  else
    record_patch "$lang_id" "unknown_patch_output" "$ancwo" "$optcomp" "$patch_output"
  fi

  return 0
}

echo "========== Build All Target Grammars =========="
echo "Project root:     $PROJECT_ROOT"
echo "Lexicon JSON:     $LEXICON_JSON"
echo "Choices dir:      $CHOICES_DIR"
echo "Grammars dir:     $GRAMMARS_DIR"
echo "Matrix root:      $MATRIX_ROOT"
echo "Matrix gmcs root: $MATRIX_GMCS_ROOT"
echo "Log dir:          $LOG_DIR"
echo "Freezer MB:       ${FREEZER_MEGABYTES:-default}"
echo

echo "[0] Generating all target choice files..."
run_cmd python grammar_build/generate_choices.py \
  --all \
  --out-dir "$CHOICES_DIR"

echo
echo "[1] Building target grammars from numbered choice files..."

count=0
skipped=0
failed=0
seen=0

shopt -s nullglob
choice_files=("$CHOICES_DIR"/[0-9][0-9]_*.choice)
shopt -u nullglob

if [[ "${#choice_files[@]}" -eq 0 ]]; then
  echo "Error: no numbered target .choice files found in $CHOICES_DIR"
  echo "Expected files like: $CHOICES_DIR/62_svo_ng_er_d_ep.choice"
  exit 1
fi

for choice_path in "${choice_files[@]}"; do
  lang_id="$(basename "$choice_path" .choice)"
  grammar_root="$GRAMMARS_DIR/$lang_id"
  tdl_path="$grammar_root/$lang_id.tdl"
  dat_path="$grammar_root/$lang_id.dat"
  grammar_log="$LOG_DIR/$lang_id.log"

  seen=$((seen + 1))

  echo
  echo "---------- $lang_id ----------"

  if [[ "$SKIP_EXISTING" == true && -f "$dat_path" ]]; then
    echo "[skip] compiled grammar already exists: $dat_path"
    record_skipped "$lang_id" "compiled_dat_exists"
    record_patch "$lang_id" "skipped_existing" "NA" "NA" "compiled .dat already exists"
    skipped=$((skipped + 1))
    continue
  fi

  if [[ "$DRY_RUN" == true ]]; then
    run_cmd python "$MATRIX_ROOT/matrix.py" \
      --customizationroot "$MATRIX_GMCS_ROOT" \
      customize-to-destination \
      "$choice_path" \
      "$grammar_root"

    run_cmd python grammar_build/update_grammar_lexicon.py \
      --lexicon-json "$LEXICON_JSON" \
      --grammar-root "$grammar_root"

    run_patch_and_record "$lang_id" "$tdl_path"

    make_compile_args "$dat_path"
    run_cmd ./grammar_build/compile_grammar.sh "${COMPILE_ARGS[@]}"

    record_success "$lang_id" "dry_run"
    count=$((count + 1))
    continue
  fi

  {
    echo "========== $lang_id =========="
    echo "Choice: $choice_path"
    echo "Grammar root: $grammar_root"
    echo "TDL: $tdl_path"
    echo "DAT: $dat_path"
    echo

    echo "[1/4] Customize grammar"
    python "$MATRIX_ROOT/matrix.py" \
      --customizationroot "$MATRIX_GMCS_ROOT" \
      customize-to-destination \
      "$choice_path" \
      "$grammar_root"

    echo
    echo "[2/4] Update grammar lexicon"
    python grammar_build/update_grammar_lexicon.py \
      --lexicon-json "$LEXICON_JSON" \
      --grammar-root "$grammar_root"

    echo
    echo "[3/4] Patch ANC-WO"
    run_patch_and_record "$lang_id" "$tdl_path"

    echo
    echo "[4/4] Compile grammar"
    make_compile_args "$dat_path"
    ./grammar_build/compile_grammar.sh "${COMPILE_ARGS[@]}"
  } > "$grammar_log" 2>&1 || {
    reason="unknown_failure"

    if grep -qi "Error: matrix.py not found" "$grammar_log"; then
      reason="matrix_py_not_found"
    elif grep -qi "No choices file found" "$grammar_log"; then
      reason="choice_file_not_found"
    elif grep -qi "Traceback" "$grammar_log"; then
      reason="python_traceback"
    elif grep -qi "ACE config not found" "$grammar_log"; then
      reason="ace_config_not_found"
    elif grep -qi "syntax error" "$grammar_log"; then
      reason="tdl_or_shell_syntax_error"
    elif grep -qi "could not parse" "$grammar_log"; then
      reason="compile_parse_error"
    elif grep -qi "no such type as" "$grammar_log"; then
      reason="tdl_missing_type"
    elif grep -qi "ran out of room in the freezer" "$grammar_log"; then
      reason="freezer_too_small"
    elif grep -qi "ERROR" "$grammar_log"; then
      reason="reported_error"
    fi

    echo "[failed] $lang_id ($reason)"
    echo "Log: $grammar_log"
    record_failed "$lang_id" "$reason"
    failed=$((failed + 1))
    continue
  }

  if [[ ! -f "$dat_path" ]]; then
    echo "[failed] $lang_id (dat_not_created)"
    echo "Log: $grammar_log"
    record_failed "$lang_id" "dat_not_created"
    failed=$((failed + 1))
    continue
  fi

  echo "[ok] $lang_id"
  echo "Log: $grammar_log"
  record_success "$lang_id" "built"
  count=$((count + 1))
done

echo
echo "========== Done =========="
echo "Target choice files seen: $seen"
echo "Built:                  $count"
echo "Skipped:                $skipped"
echo "Failed:                 $failed"
echo
echo "Success list: $SUCCESS_LIST"
echo "Skipped list: $SKIPPED_LIST"
echo "Failed list:  $FAILED_LIST"
echo "Patch log:    $PATCH_LIST"

echo
echo "Patch summary:"
if [[ -s "$PATCH_LIST" ]]; then
  awk -F'\t' 'NR > 1 {count[$2]++} END {for (status in count) print "  " status ": " count[status]}' "$PATCH_LIST" | sort
fi

if [[ "$failed" -gt 0 ]]; then
  echo
  echo "Failed grammars:"
  tail -n +2 "$FAILED_LIST"
  exit 1
fi