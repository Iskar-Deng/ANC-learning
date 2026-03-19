#!/usr/bin/env bash
set -euo pipefail

DAT_PATH="/home/dengh/workspace/ANC-learning/grammars/c-alignment/c-alignment.dat"

GRAMMAR_DIR="$(dirname "$DAT_PATH")"
CONFIG_FILE="$GRAMMAR_DIR/ace/config.tdl"

ACE_BIN=$(python3 -c 'from utils import ACE_BIN; print(ACE_BIN)')

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Error: cannot find $CONFIG_FILE"
  exit 1
fi

cd "$GRAMMAR_DIR"

if [ -f "trigger.mtr" ] && ! grep -q 'trigger.mtr' "$CONFIG_FILE"; then
  echo ':= include "trigger.mtr".' >> "$CONFIG_FILE"
fi

echo "Compiling: $DAT_PATH"

"$ACE_BIN" \
  -g "$CONFIG_FILE" \
  -G "$(basename "$DAT_PATH")"

echo "Done."