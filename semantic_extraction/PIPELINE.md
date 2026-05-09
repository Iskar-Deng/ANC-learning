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
# 3. Run semantic extraction
bash semantic_extraction/run_semantic_extraction.sh \
  --input data/train.txt \
  --freezer-megabytes 4096
```

## Debug: step-by-step equivalent

```bash
python external/matrix/matrix.py \
  --customizationroot external/matrix/gmcs \
  customize-to-destination \
  choices/pseudo-english.choice \
  grammars/pseudo-english

python semantic_extraction/extract_basic.py \
  --input data/train.txt \
  --output data/train/train_extract.jsonl \
  --stats-output data/train/train_extract_stats.json

python semantic_extraction/generate_pseudo_english.py \
  --input data/train/train_extract.jsonl \
  --out-jsonl data/train/train_pseudo.jsonl \
  --out-lexicon data/train/train_lexicon.json \
  --out-stats data/train/train_pseudo_stats.json

python grammar_build/update_grammar_lexicon.py \
  --lexicon-json data/train/train_lexicon.json \
  --grammar-root grammars/pseudo-english \
  --with-trigger \
  --default-comp-trigger that

./grammar_build/compile_grammar.sh \
  grammars/pseudo-english/pseudo-english.dat \
  --freezer-megabytes 4096

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
