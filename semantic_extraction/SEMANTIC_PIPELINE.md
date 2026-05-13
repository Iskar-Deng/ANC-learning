# Semantic Extraction Pipeline

```bash
# 1. Download corpus
python data_processing/download.py
```

```bash
# 2. Split corpus into train/dev/test
python data_processing/split.py
```

```bash
# 3. Train split: run extraction and update pseudo-English grammar
bash semantic_extraction/run_semantic_extraction.sh \
  --input data/train.txt \
  --update-grammar
```

```bash
# 4. Dev/test splits: reuse the train-built pseudo-English grammar
bash semantic_extraction/run_semantic_extraction.sh \
  --input data/dev.txt

bash semantic_extraction/run_semantic_extraction.sh \
  --input data/test.txt
```

## Debug: step-by-step equivalent

```bash
python semantic_extraction/extract_basic.py \
  --input data/train.txt \
  --output data/train/train_extract.jsonl \
  --stats-output data/train/train_extract_stats.json

python semantic_extraction/generate_pseudo_english.py \
  --input data/train/train_extract.jsonl \
  --out-jsonl data/train/train_pseudo.jsonl \
  --out-lexicon data/train/train_lexicon.json \
  --out-stats data/train/train_pseudo_stats.json

# ---- BEGIN: only needed with --update-grammar ----
python external/matrix/matrix.py \
  --customizationroot external/matrix/gmcs \
  customize-to-destination \
  choices/pseudo-english.choice \
  grammars/pseudo-english

python grammar_build/update_grammar_lexicon.py \
  --lexicon-json data/train/train_lexicon.json \
  --grammar-root grammars/pseudo-english \
  --with-trigger \
  --default-comp-trigger that

./grammar_build/compile_grammar.sh \
  grammars/pseudo-english/pseudo-english.dat

# ---- END: only needed with --update-grammar ----

python -m semantic_extraction.parse_pseudo_with_grammar \
  --grammar grammars/pseudo-english/pseudo-english.dat \
  --input data/train/train_pseudo.jsonl \
  --out data/train/train_mrs.jsonl \
  --max-parses 20 \
  --workers 8 \
  --chunksize 100 \
  --restart-every 5000
```

```text
# Main downstream outputs
data/train/train_lexicon.json
data/train/train_mrs.jsonl
```
