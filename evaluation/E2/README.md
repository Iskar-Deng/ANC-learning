# E2 Real Grammar Pipeline

This folder contains the rerunnable E2 pipeline after the scoring fix.

Run commands from the repository root.

## What Changed

Old E2 scoring used causal-LM shifted labels without a sentence-start token, so
the first true token of each sentence was not scored.

The new default is:

```text
--score-mode bos_eos
score = average log p(w1 | BOS) ... p(EOS | wn)
```

This makes short `SV`/`VS` comparisons fairer because the initial true token is
included in the sentence probability.

`--score-mode legacy` is still available only for reproducing the archived E2
results.

## Output Policy

Fast derived files go under:

```text
evaluation/E2/generated/
```

Large model-scoring outputs go under:

```text
results/e2_real_grammar_preference/
```

This keeps regenerated helper artifacts out of `results/`, while preserving
the expensive E2 predictions/summaries in `results/`.

## Scripts

```text
check_selected_coverage.py
```

Checks that all 96 selected generation files contain the same ids. Writes
`common_ids.txt`, coverage summaries, bad-row diagnostics, and duplicate-id
diagnostics under `evaluation/E2/generated/selected_coverage/test/`.

```text
score_one_model_real_grammar.py
```

Scores one trained model against the 96 candidate sentences for each common id.
The default score mode is `bos_eos`.

```text
run_e2_models.sh
```

Runs `score_one_model_real_grammar.py` over all languages found in
`data/test/generated/selected`, or over languages supplied on the command line.
Writes predictions and summaries to
`results/e2_real_grammar_preference/all_models_bos_eos` by default.

```text
analyze_e2_results.py
```

Aggregates model-level and subset-level E2 metrics from the prediction files.
Writes tables under `evaluation/E2/generated/analysis/bos_eos/`.

```text
classify_e2_top_anc_items.py
```

Builds item labels such as `top_construction`, `anc_bucket`, `anc_subtype`,
`top_x_anc`, `complexity_bucket`, and detailed ANC/construction combinations.
Writes labels and summary reports under
`evaluation/E2/generated/item_classification/top_anc_detail/`.

The recommended main-table `complexity_bucket` values are:

```text
tv_plain_obj
iv_plain
cop_n
pp_or_particle
cv_depth1
cv_depth2plus
anc_bare
anc_overt_arg
```

ANC overrides other categories: a transitive item with overt-argument ANC is
classified as `anc_overt_arg`, not `tv_plain_obj`.

It also writes classified E2 id sets from the same ANC logic:

```text
anc_ids.txt
anc_bare_ids.txt
anc_arg_ids.txt
anc_ge_only_ids.txt
anc_ob_only_ids.txt
anc_ge_ob_ids.txt
```

```text
analyze_e2_language_item_behavior.py
```

Computes per-language accuracy by item category and metadata fields. Useful for
checking whether `iv|none`, `tv|arg`, `iv|arg`, and `cv|bare` changed under the
new scorer. Writes under
`evaluation/E2/generated/item_classification/per_language_behavior/`.

```text
analyze_e2_language_confusions.py
```

Computes source-to-target error attractions and parameter-mass summaries. This
is the key script for checking whether the old `SOV/SVO -> VOS` attraction in
`iv|none` survives the BOS/EOS scoring fix. Writes under
`evaluation/E2/generated/item_classification/language_confusions/`.

## Recommended Run Order

### 1. Generate common ids

```bash
python evaluation/E2/check_selected_coverage.py \
  --selected-dir data/test/generated/selected \
  --write-common-ids
```

Default output:

```text
evaluation/E2/generated/selected_coverage/test/common_ids.txt
```

### 2. Classify items and generate ANC id sets

```bash
python evaluation/E2/classify_e2_top_anc_items.py \
  --out-dir evaluation/E2/generated/item_classification/top_anc_detail
```

Default output:

```text
evaluation/E2/generated/item_classification/top_anc_detail/item_top_anc_labels.tsv
evaluation/E2/generated/item_classification/top_anc_detail/anc_ids.txt
```

This step can run before model scoring. If prediction files do not exist yet,
the item labels and id sets are still generated; accuracy columns in the summary
are left blank.

### 3. Smoke-test one model

```bash
bash evaluation/E2/run_e2_models.sh \
  --score-mode bos_eos \
  --out-dir results/e2_real_grammar_preference/smoke_bos_eos \
  --max-ids 1000 \
  04_sov_gn_ac_d_se
```

### 4. Run all models

```bash
bash evaluation/E2/run_e2_models.sh \
  --score-mode bos_eos \
  --out-dir results/e2_real_grammar_preference/all_models_bos_eos
```

### 5. Refresh item classification summaries

```bash
python evaluation/E2/classify_e2_top_anc_items.py \
  --pred-dir results/e2_real_grammar_preference/all_models_bos_eos \
  --out-dir evaluation/E2/generated/item_classification/top_anc_detail
```

### 6. Aggregate overall E2 results

```bash
python evaluation/E2/analyze_e2_results.py \
  --pred-dir results/e2_real_grammar_preference/all_models_bos_eos \
  --out-dir evaluation/E2/generated/analysis/bos_eos
```

### 7. Analyze per-language item behavior

```bash
python evaluation/E2/analyze_e2_language_item_behavior.py \
  --pred-dir results/e2_real_grammar_preference/all_models_bos_eos \
  --item-labels evaluation/E2/generated/item_classification/top_anc_detail/item_top_anc_labels.tsv \
  --out-dir evaluation/E2/generated/item_classification/per_language_behavior
```

### 8. Analyze language confusions

```bash
python evaluation/E2/analyze_e2_language_confusions.py \
  --pred-dir results/e2_real_grammar_preference/all_models_bos_eos \
  --item-labels evaluation/E2/generated/item_classification/top_anc_detail/item_top_anc_labels.tsv \
  --out-dir evaluation/E2/generated/item_classification/language_confusions
```

## Minimal Files Needed

For a clean rerun, these are the essential inputs:

```text
data/test/generated/selected/*.jsonl
data/test/test_pseudo.jsonl
test_extract.jsonl
choices/manifest.tsv
models/<language>/seed_42/checkpoint-70000/
```

The coverage files, classified ANC ids, item labels, and analysis tables can
all be regenerated quickly under `evaluation/E2/generated/`.
