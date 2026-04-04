#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: $0 <path_to_dat_file> [freezer_megabytes]"
  exit 1
fi

DAT_PATH="$(realpath "$1")"
FREEZER_MB="${2:-8192}"

if ! [[ "$FREEZER_MB" =~ ^[0-9]+$ ]]; then
  echo "Error: freezer_megabytes must be an integer"
  exit 1
fi

if [ ! -f "$DAT_PATH" ]; then
  echo "Error: file not found: $DAT_PATH"
  exit 1
fi

GRAMMAR_DIR="$(dirname "$DAT_PATH")"
CONFIG_FILE="$GRAMMAR_DIR/ace/config.tdl"

ACE_BIN="$(python3 -c 'from utils import ACE_BIN; print(ACE_BIN)')"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Error: cannot find $CONFIG_FILE"
  exit 1
fi

if [ ! -x "$ACE_BIN" ]; then
  echo "Error: ACE binary is not executable: $ACE_BIN"
  exit 1
fi

cd "$GRAMMAR_DIR"

if [ -f "trigger.mtr" ] && ! grep -q 'trigger.mtr' "$CONFIG_FILE"; then
  printf '\n:= include "trigger.mtr".\n' >> "$CONFIG_FILE"
fi

TMP_CONFIG="$(mktemp)"

awk -v freezer="$FREEZER_MB" '
BEGIN { replaced = 0 }
{
  if ($0 ~ /^[[:space:]]*freezer-megabytes[[:space:]]*:=/) {
    print "freezer-megabytes := " freezer "."
    replaced = 1
  } else {
    print
  }
}
END {
  if (!replaced) {
    print ""
    print "freezer-megabytes := " freezer "."
  }
}
' "$CONFIG_FILE" > "$TMP_CONFIG"

mv "$TMP_CONFIG" "$CONFIG_FILE"

echo "Compiling: $DAT_PATH"
echo "Using freezer-megabytes := $FREEZER_MB"

"$ACE_BIN" \
  -g "$CONFIG_FILE" \
  -G "$(basename "$DAT_PATH")"

echo "Done."