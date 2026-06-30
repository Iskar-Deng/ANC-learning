# E1 Result Tables

This directory contains the small, tracked E1 aggregate result tables used for
analysis and paper writing.

The full generated E1 working directory is `e1_materials/` and remains
untracked. It contains generated sentences, minimal pairs, scores, ACE
parseability checks, and large pair-level diagnostics.

## Main Tables

- `e1_language_phenomenon_weighted_summary.tsv`
  - main table: one row per language and phenomenon
  - includes raw accuracy, BAD parse rate, and weighted accuracy
- `e1_phenomenon_weighted_summary.tsv`
  - one row per phenomenon
- `e1_language_weighted_summary.tsv`
  - one row per language

## Metric

The weighted score is an aggregate-level diagnostic:

```text
weighted_accuracy = raw_accuracy * (1 - bad_parse_rate)
```

It does not replace raw accuracy. It is used to separate low model preference
from low minimal-pair cleanliness when BAD sentences can still be parsed by the
grammar.

## Regeneration

These tables are copied from:

```text
e1_materials/analysis/
```

The pair-level file `e1_bad_parse_by_pair.tsv` is intentionally not tracked
because it is large and fully regenerable.
