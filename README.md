# ANC-learning

## Project structure

```text
data_processing/
  download.py
  split.py

semantic_extraction/
  run_semantic_extraction.sh
  extract_basic.py
  generate_pseudo_english.py
  parse_pseudo_with_grammar.py
  SEMANTIC_PIPELINE.md

grammar_build/
  generate_choices.py
  update_grammar_lexicon.py
  patch_anc_wo.py
  compile_grammar.sh
  build_all_grammars.sh
  GRAMMAR_PIPELINE.md

language_generation/
  generate_from_mrs_bank.py
  select_overgen.py
  run_all_language_generation.sh
  GENERATION_PIPELINE.md

training/
  train_lm.py
  run_all_lm_training.sh
  TRAINING_PIPELINE.md

evaluation/
  E1/
    E1_PIPELINE.md
    phenomena/
  E2/
    README.md

choices/
  *.choice
  manifest.tsv

data/
  train.txt
  dev.txt
  test.txt
  train/
  dev/
  test/

grammars/
  pseudo-english/
  <language>/

models/
  <language>/seed_<seed>/

results/
logs/
archive/
```

## Full runnable pipeline

Run commands from the repository root.

The full experiment has three derived layers:

1. English corpus -> controlled pseudo-English MRS banks.
2. Pseudo-English MRS banks -> 96 generated target-language corpora.
3. Target-language corpora -> trained LMs -> E1/E2 evaluation.

For step-by-step details, see the linked pipeline documents:

- [Semantic extraction pipeline](semantic_extraction/SEMANTIC_PIPELINE.md)
- [Grammar build pipeline](grammar_build/GRAMMAR_PIPELINE.md)
- [Language generation pipeline](language_generation/GENERATION_PIPELINE.md)
- [Training pipeline](training/TRAINING_PIPELINE.md)
- [E1 minimal-pair pipeline](evaluation/E1/E1_PIPELINE.md)
- [E2 real-grammar pipeline](evaluation/E2/README.md)

### 1. Prepare corpus splits

```bash
python data_processing/download.py

python data_processing/split.py
```

Main outputs:

```text
data/train.txt
data/dev.txt
data/test.txt
```

### 2. Generate the 96 choice files

```bash
python grammar_build/generate_choices.py \
  --all \
  --out-dir choices \
  --manifest manifest.tsv
```

Main outputs:

```text
choices/*.choice
choices/manifest.tsv
```

### 3. Extract semantics and build the pseudo-English grammar

Train split updates and compiles the pseudo-English grammar:

```bash
bash semantic_extraction/run_semantic_extraction.sh \
  --input data/train.txt \
  --update-grammar
```

Dev/test reuse the train-built pseudo-English grammar:

```bash
bash semantic_extraction/run_semantic_extraction.sh \
  --input data/dev.txt

bash semantic_extraction/run_semantic_extraction.sh \
  --input data/test.txt
```

Main outputs:

```text
data/train/train_extract.jsonl
data/train/train_pseudo.jsonl
data/train/train_lexicon.json
data/train/train_mrs.jsonl

data/dev/dev_mrs.jsonl
data/test/test_mrs.jsonl

grammars/pseudo-english/pseudo-english.dat
```

Important: after changing semantic extraction or pseudo-English realization,
rerun from `extract_basic.py`, not only from `generate_pseudo_english.py`.

### 4. Build the 96 target grammars

```bash
bash grammar_build/build_all_grammars.sh \
  --lexicon-json data/train/train_lexicon.json \
  --freezer-megabytes 4096
```

Main outputs:

```text
grammars/<language>/<language>.dat
logs/grammar_build/
```

### 5. Generate target-language corpora

```bash
bash language_generation/run_all_language_generation.sh \
  --mrs data/train/train_mrs.jsonl \
  --log-dir logs/generation/train

bash language_generation/run_all_language_generation.sh \
  --mrs data/dev/dev_mrs.jsonl \
  --log-dir logs/generation/dev

bash language_generation/run_all_language_generation.sh \
  --mrs data/test/test_mrs.jsonl \
  --log-dir logs/generation/test
```

Main outputs:

```text
data/train/generated/raw/
data/train/generated/selected/
data/train/generated/details/

data/dev/generated/selected/
data/test/generated/selected/
```

### 6. Train the 96 language models

```bash
bash training/run_all_lm_training.sh \
  --train-dir data/train/generated/selected \
  --dev-dir data/dev/generated/selected \
  --seed 42
```

Main outputs:

```text
models/<language>/seed_42/
logs/training/
```

### 7. Run E1 controlled minimal-pair evaluation

E1 is phenomenon-specific. Each phenomenon lives under:

```text
evaluation/E1/phenomena/<PHENOMENON>/
  source.txt
  rules.py
```

For the full runnable E1 sequence, follow
[evaluation/E1/E1_PIPELINE.md](evaluation/E1/E1_PIPELINE.md).

Typical output layout:

```text
e1_materials/<PHENOMENON>/
  <PHENOMENON>_extract.jsonl
  <PHENOMENON>_pseudo.jsonl
  <PHENOMENON>_mrs.jsonl
  generated/
  pairs/
  scores/
  analysis/
```

### 8. Run E2 real-grammar preference evaluation

The recommended E2 order is documented in
[evaluation/E2/README.md](evaluation/E2/README.md).

Smoke test:

```bash
python evaluation/E2/check_selected_coverage.py \
  --selected-dir data/test/generated/selected \
  --write-common-ids

python evaluation/E2/classify_e2_top_anc_items.py \
  --out-dir evaluation/E2/generated/item_classification/top_anc_detail

bash evaluation/E2/run_e2_models.sh \
  --score-mode bos_eos \
  --out-dir results/e2_real_grammar_preference/smoke_bos_eos \
  --max-ids 1000 \
  04_sov_gn_ac_d_se
```

Full E2 model scoring:

```bash
bash evaluation/E2/run_e2_models.sh \
  --score-mode bos_eos \
  --out-dir results/e2_real_grammar_preference/all_models_bos_eos
```

Main outputs:

```text
results/e2_real_grammar_preference/
evaluation/E2/generated/analysis/
evaluation/E2/generated/item_classification/
```

## Quick rerun guide

If only E1 `source.txt` or `rules.py` changes, rerun the E1 pipeline for that
phenomenon.

If semantic extraction, pseudo-English realization, or the train lexicon
changes, rerun:

```text
semantic extraction -> grammar build -> language generation -> training -> E1/E2
```

If only the E2 scorer or analysis changes, regenerate E2 predictions/analysis;
the grammars, generated corpora, and LMs do not need to be rebuilt.
