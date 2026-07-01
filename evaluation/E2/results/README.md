# E2 Result Tables

This directory contains the small, tracked E2 aggregate tables used for
analysis and paper writing.

The full E2 model-scoring outputs remain untracked:

```text
results/e2_real_grammar_preference/
evaluation/E2/generated/
```

Those directories contain large prediction files, logs, selected-coverage
diagnostics, item labels, and detailed confusion edges. They can be regenerated
from the E2 pipeline.

## Main Tables

Overall cross-grammar competition results:

```text
analysis/bos_eos/model_summary.tsv
analysis/bos_eos/by_dimension.tsv
analysis/bos_eos/comp_by_strategy.tsv
analysis/bos_eos/subset_by_dimension.tsv
analysis/bos_eos/subset_by_model.tsv
analysis/bos_eos/counters.json
analysis/bos_eos/top_error_examples.tsv
```

ANC/item-category summaries:

```text
item_classification/top_anc_detail/top_anc_summary.tsv
item_classification/top_anc_detail/quick_report.txt
item_classification/per_language_behavior/metadata_focus_summary.tsv
item_classification/per_language_behavior/per_language_focus_categories.tsv
item_classification/per_language_behavior/per_language_strong_weak_categories.tsv
item_classification/per_language_behavior/per_language_category_accuracy_wide.tsv
item_classification/per_language_behavior/quick_report.txt
```

Language-confusion summaries:

```text
item_classification/language_confusions/language_confusion_type_parameter_mass.tsv
item_classification/language_confusions/quick_report.txt
```

Large detailed files such as `item_top_anc_labels.tsv`,
`language_confusion_top_targets.tsv`, and all `*.predictions.tsv` files are not
tracked.

## Metric

The main E2 metric is `accuracy_tie_ok`: a model is counted as correct if its
own grammar's sentence is tied for highest score among the 96 candidate
sentences for the same test id.

The scoring mode is `bos_eos`, which scores:

```text
log p(w1 | BOS) ... log p(EOS | wn)
```

This includes both the first true token and final EOS.
