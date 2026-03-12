#!/usr/bin/env bash

python3 /home/dengh/workspace/ANC-learning/scripts/run_matrix_tests.py \
    --ace /home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace \
    --grammar /home/dengh/workspace/ANC-learning/grammars/test-korean_20260310_141705/test-korean.dat  \
    --tests /home/dengh/workspace/ANC-learning/grammars/test-korean_20260310_141705/test_sentences \
    --max-parses 50

python3 scripts/inspect_one.py \
  --ace /home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace \
  --grammar /home/dengh/workspace/ANC-learning/grammars/test-korean_20260310_141705/test-korean.dat \
  --sent "n1-nom iv1-fin" \
  --mrs