#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=/home/dengh/workspace/ANC-learning
GRAMMAR_ROOT="$PROJECT_ROOT/grammars"
LID=test-english
TARBALL="$GRAMMAR_ROOT/$LID.tar.gz"

ACE_BIN=$(python3 -c 'from utils import ACE_BIN; print(ACE_BIN)')

STAMP=$(date +"%Y%m%d_%H%M%S")
OUTDIR="$GRAMMAR_ROOT/${LID}_$STAMP"
DAT_NAME="$LID.dat"

echo "========== ANC ITERATION =========="
echo "Language: $LID"
echo "Timestamp: $STAMP"
echo

echo "[1/3] Extracting grammar..."
mkdir -p "$OUTDIR"

tar -xzf "$TARBALL" \
  -C "$OUTDIR" \
  --strip-components=1

echo "Extracted → $OUTDIR"
echo

echo "[2/3] Compiling with ACE..."
cd "$OUTDIR"

"$ACE_BIN" \
  -g ace/config.tdl \
  -G "$DAT_NAME"

echo "Compiled → $OUTDIR/$DAT_NAME"
echo

echo "[3/3] Running test suite..."

cd "$PROJECT_ROOT"

python3 -m scripts.run_matrix_tests \
  --grammar "$OUTDIR/$DAT_NAME" \
  --tests "$OUTDIR/test_sentences" \
  --max-parses 50

echo
echo "========== DONE =========="
echo "Grammar directory:"
echo "  $OUTDIR"