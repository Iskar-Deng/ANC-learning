#!/usr/bin/env bash

python3 /home/dengh/workspace/ANC-learning/scripts/run_matrix_tests.py \
    --ace /home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace \
    --grammar /home/dengh/workspace/ANC-learning/grammars/test-korean_20260226_164550/test-korean.dat  \
    --tests /home/dengh/workspace/ANC-learning/grammars/test-korean_20260226_164550/test_sentences \
    --max-parses 50

python3 scripts/inspect_one.py \
  --ace /home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace \
  --grammar /home/dengh/workspace/ANC-learning/grammars/test-korean_20260226_165854/test-korean.dat \
  --sent "n1-nom n2-gen n3-acc tv1-fin" \
  --mrs