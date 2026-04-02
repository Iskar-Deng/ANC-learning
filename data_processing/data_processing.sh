#!/usr/bin/env bash

python data_processing/extract_basic.py \
    --input data/babylm_1pct.txt \
    --output data/babylm_1pct.jsonl \
    --stats-output data/babylm_1pct_stats.json

python data_processing/generate_pseudo_english.py \
    --input data/babylm_1pct.jsonl \
    --out-jsonl data/babylm_1pct_pseudo.jsonl \
    --out-lexicon data/babylm_1pct_lexicon.json

python data_processing/update_grammar_lexicon.py \
    --lexicon-json data/babylm_1pct_lexicon.json \
    --grammar-root grammars/test-english \
    --no-trigger

grammar_build/recompile_grammar.sh grammars/test-english/test-english.dat

python -m data_processing.parse_pseudo_with_grammar \
    --grammar grammars/test-english/test-english.dat \
    --input data/babylm_1pct_pseudo.jsonl \
    --out data/babylm_1pct_mrs.jsonl \
    --max-parses 20

------------------------------------------------------------------------------------------
grammar_build/iterate.sh c-random  

python data_processing/update_grammar_lexicon.py \
    --lexicon-json data/sample_lexicon.json \
    --grammar-root grammars/c-random \
    --no-trigger

grammar_build/recompile_grammar.sh grammars/c-random/c-random.dat

python3 -m scripts.generate_from_mrs_bank \
    --grammar grammars/c-random/c-random.dat \
    --input data/pseudo_parsed.jsonl \
    --out data/sample_c-random_output.jsonl \
    --no-mre

------------------------------------------------------------------------------------------

