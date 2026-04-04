#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <LID> [--timestamp]"
  exit 1
fi

LID=""
USE_TIMESTAMP=false

for arg in "$@"; do
  case "$arg" in
    --timestamp)
      USE_TIMESTAMP=true
      ;;
    -*)
      echo "Error: unknown option: $arg"
      echo "Usage: $0 <LID> [--timestamp]"
      exit 1
      ;;
    *)
      if [ -z "$LID" ]; then
        LID="$arg"
      else
        echo "Error: unexpected argument: $arg"
        echo "Usage: $0 <LID> [--timestamp]"
        exit 1
      fi
      ;;
  esac
done

if [ -z "$LID" ]; then
  echo "Usage: $0 <LID> [--timestamp]"
  exit 1
fi

PROJECT_ROOT=/home/dengh/workspace/ANC-learning
GRAMMAR_ROOT="$PROJECT_ROOT/grammars"
TARBALL="$GRAMMAR_ROOT/$LID.tar.gz"

if [ ! -f "$TARBALL" ]; then
  echo "Error: tarball not found: $TARBALL"
  exit 1
fi

ACE_BIN=$(python3 -c 'from utils import ACE_BIN; print(ACE_BIN)')

if [ "$USE_TIMESTAMP" = true ]; then
  STAMP=$(date +"%Y%m%d_%H%M%S")
  OUTDIR="$GRAMMAR_ROOT/${LID}_$STAMP"
else
  STAMP=""
  OUTDIR="$GRAMMAR_ROOT/$LID"
fi

DAT_NAME="$LID.dat"
TDL_FILE="$OUTDIR/$LID.tdl"

echo "========== ANC ITERATION =========="
echo "Language: $LID"
if [ "$USE_TIMESTAMP" = true ]; then
  echo "Timestamp: $STAMP"
else
  echo "Timestamp: disabled"
fi
echo

echo "[1/4] Extracting grammar..."
mkdir -p "$OUTDIR"

tar -xzf "$TARBALL" \
  -C "$OUTDIR" \
  --strip-components=1

echo "Extracted → $OUTDIR"
echo

echo "[2/4] Compiling with ACE..."
cd "$OUTDIR"

"$ACE_BIN" \
  -g ace/config.tdl \
  -G "$DAT_NAME"

echo "Compiled → $OUTDIR/$DAT_NAME"
echo

echo "[3/4] Running test suite..."

cd "$PROJECT_ROOT"

set +e

python3 -m grammar_build.run_matrix_tests \
  --grammar "$OUTDIR/$DAT_NAME" \
  --tests "$OUTDIR/test_sentences" \
  --max-parses 50

set -e

echo
echo "[4/4] Checking for ANC-WO in $TDL_FILE ..."

if [ ! -f "$TDL_FILE" ]; then
  echo "Warning: TDL file not found: $TDL_FILE"
else
  if grep -q 'ANC-WO' "$TDL_FILE"; then
    echo
    echo "ANC-WO found in:"
    echo "  $TDL_FILE"
    echo
    echo "Next step: manual repair is needed."
    echo "Please patch the ANC-WO-related rules by hand."
  else
    echo "No ANC-WO found."
  fi
fi

echo
echo "========== DONE =========="
echo "Grammar directory:"
echo "  $OUTDIR"