#!/usr/bin/env bash
set -euo pipefail

FREEZER_MEGABYTES=""

usage() {
  echo "Usage: $0 <GRAMMAR_DAT> [options]"
  echo
  echo "Options:"
  echo "  --freezer-megabytes N     Set ACE freezer-megabytes in ace/config.tdl before compiling"
  echo
  echo "Example:"
  echo "  $0 grammars/62_svo_ng_er_d_ep/62_svo_ng_er_d_ep.dat"
  echo "  $0 grammars/pseudo-english/pseudo-english.dat --freezer-megabytes 4096"
}

if [[ "$#" -lt 1 ]]; then
  usage
  exit 1
fi

DAT_PATH="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --freezer-megabytes)
      FREEZER_MEGABYTES="$2"
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

if [[ "$DAT_PATH" != *.dat ]]; then
  echo "Error: expected a .dat path: $DAT_PATH"
  usage
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACE_BIN="$(cd "$PROJECT_ROOT" && python3 -c 'from utils import ACE_BIN; print(ACE_BIN)')"

GRAMMAR_DIR="$(dirname "$DAT_PATH")"
DAT_NAME="$(basename "$DAT_PATH")"

if [[ ! -d "$GRAMMAR_DIR" ]]; then
  echo "Error: grammar directory not found: $GRAMMAR_DIR"
  exit 1
fi

GRAMMAR_DIR_ABS="$(cd "$GRAMMAR_DIR" && pwd)"
CONFIG_PATH="$GRAMMAR_DIR_ABS/ace/config.tdl"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Error: ACE config not found: $CONFIG_PATH"
  exit 1
fi

if [[ -n "$FREEZER_MEGABYTES" ]]; then
  if ! [[ "$FREEZER_MEGABYTES" =~ ^[0-9]+$ ]]; then
    echo "Error: --freezer-megabytes must be an integer: $FREEZER_MEGABYTES"
    exit 1
  fi

  if grep -q '^freezer-megabytes' "$CONFIG_PATH"; then
    sed -i "s/^freezer-megabytes.*/freezer-megabytes := ${FREEZER_MEGABYTES}./" "$CONFIG_PATH"
  else
    printf "\nfreezer-megabytes := %s.\n" "$FREEZER_MEGABYTES" >> "$CONFIG_PATH"
  fi
fi

echo "========== Compile Grammar =========="
echo "Grammar dir:        $GRAMMAR_DIR_ABS"
echo "Output dat:         $GRAMMAR_DIR_ABS/$DAT_NAME"
echo "ACE binary:         $ACE_BIN"
if [[ -n "$FREEZER_MEGABYTES" ]]; then
  echo "Freezer megabytes:  $FREEZER_MEGABYTES"
else
  echo "Freezer megabytes:  default"
fi
echo

cd "$GRAMMAR_DIR_ABS"

"$ACE_BIN" \
  -g ace/config.tdl \
  -G "$DAT_NAME"

echo
echo "========== Done =========="
echo "Compiled:"
echo "  $GRAMMAR_DIR_ABS/$DAT_NAME" 