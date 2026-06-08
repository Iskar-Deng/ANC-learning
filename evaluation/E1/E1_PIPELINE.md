# E1 Basic Grammar Minimal-Pair Pipeline

E1 evaluates whether each model has learned local grammar dimensions using
controlled minimal pairs.

Each phenomenon owns its source sentences and perturbation rule:

```text
evaluation/E1/phenomena/<PHENOMENON>/
  source.txt
  rules.py
  README.md
```

All generated E1 materials should stay outside tracked evaluation code:

```text
e1_materials/<PHENOMENON>/
```

## Assumptions

Before running E1, the main experiment resources already exist:

```text
grammars/pseudo-english/pseudo-english.dat
grammars/<language>/<language>.dat
models/<language>/seed_42/checkpoint-70000
```

Use the same `<PHENOMENON>` name throughout, for example:

```text
1_1_intran_S_marker
```

## 1. Extract English Sources

```bash
mkdir -p e1_materials/<PHENOMENON>

python semantic_extraction/extract_basic.py \
  --input evaluation/E1/phenomena/<PHENOMENON>/source.txt \
  --output e1_materials/<PHENOMENON>/<PHENOMENON>_extract.jsonl \
  --stats-output e1_materials/<PHENOMENON>/<PHENOMENON>_extract_stats.json
```

Check the extraction summary:

```bash
cat e1_materials/<PHENOMENON>/<PHENOMENON>_extract_stats.json
```

## 2. Generate Pseudo-English

```bash
python semantic_extraction/generate_pseudo_english.py \
  --input e1_materials/<PHENOMENON>/<PHENOMENON>_extract.jsonl \
  --out-jsonl e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo.jsonl \
  --out-lexicon e1_materials/<PHENOMENON>/<PHENOMENON>_lexicon.json \
  --out-stats e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo_stats.json
```

Inspect:

```bash
head -20 e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo.jsonl
cat e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo_stats.json
```

## 3. Parse Pseudo-English To MRS

```bash
python -m semantic_extraction.parse_pseudo_with_grammar \
  --grammar grammars/pseudo-english/pseudo-english.dat \
  --input e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo.jsonl \
  --out e1_materials/<PHENOMENON>/<PHENOMENON>_mrs.jsonl \
  --max-parses 20 \
  --first-parse-only \
  --skip-failed \
  --workers 8 \
  --chunksize 50 \
  --restart-every 5000
```

Check counts:

```bash
wc -l e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo.jsonl \
      e1_materials/<PHENOMENON>/<PHENOMENON>_mrs.jsonl
```

## 4. Generate GOOD Sentences With 96 Grammars

```bash
bash language_generation/run_all_language_generation.sh \
  --mrs e1_materials/<PHENOMENON>/<PHENOMENON>_mrs.jsonl \
  --out-base e1_materials/<PHENOMENON>/generated \
  --log-dir e1_materials/<PHENOMENON>/logs/generation \
  --workers 12 \
  --chunksize 50 \
  --max-gen 20
```

Main outputs:

```text
e1_materials/<PHENOMENON>/generated/raw/
e1_materials/<PHENOMENON>/generated/selected/
e1_materials/<PHENOMENON>/generated/details/
```

## 5. Smoke Test One Language: GOOD To Minimal Pairs

Use one language first to verify `rules.py`.

```bash
python evaluation/E1/apply_perturbation.py \
  --phenomenon-dir evaluation/E1/phenomena/<PHENOMENON> \
  --good-items e1_materials/<PHENOMENON>/generated/selected/32_svo_gn_ac_b_se.jsonl \
  --out e1_materials/<PHENOMENON>/pairs/32_svo_gn_ac_b_se.pairs.jsonl \
  --sample-size 100 \
  --seed 42
```

Inspect:

```bash
head -20 e1_materials/<PHENOMENON>/pairs/32_svo_gn_ac_b_se.pairs.jsonl
```

Confirm that:

```text
GOOD is grammar-generated.
BAD is generated only by the external perturbation rule.
BAD uses only existing grammar resources.
The perturbation hits the intended target token.
```

## 6. Smoke Test One Language: Score GOOD vs BAD

```bash
python evaluation/E1/score_e1_pairs.py \
  --model models/32_svo_gn_ac_b_se/seed_42/checkpoint-70000 \
  --pairs e1_materials/<PHENOMENON>/pairs/32_svo_gn_ac_b_se.pairs.jsonl \
  --out e1_materials/<PHENOMENON>/scores/32_svo_gn_ac_b_se.scores.tsv \
  --summary e1_materials/<PHENOMENON>/scores/32_svo_gn_ac_b_se.summary.json \
  --batch-size 64 \
  --device cuda \
  --score-mode bos_eos
```

Inspect:

```bash
cat e1_materials/<PHENOMENON>/scores/32_svo_gn_ac_b_se.summary.json
head -10 e1_materials/<PHENOMENON>/scores/32_svo_gn_ac_b_se.scores.tsv
```

`bos_eos` scores:

```text
log p(w1 | BOS) ... log p(EOS | wn)
```

## 7. Batch Generate Minimal Pairs For 96 Languages

```bash
mkdir -p e1_materials/<PHENOMENON>/pairs

for f in e1_materials/<PHENOMENON>/generated/selected/[0-9][0-9]_*.jsonl; do
  lang="$(basename "$f" .jsonl)"

  python evaluation/E1/apply_perturbation.py \
    --phenomenon-dir evaluation/E1/phenomena/<PHENOMENON> \
    --good-items "$f" \
    --out "e1_materials/<PHENOMENON>/pairs/${lang}.pairs.jsonl" \
    --sample-size 100 \
    --seed 42
done
```

Check:

```bash
ls e1_materials/<PHENOMENON>/pairs/*.pairs.jsonl | wc -l
wc -l e1_materials/<PHENOMENON>/pairs/*.pairs.jsonl | tail
```

## 8. Optional: Check Sampled Ids Are Parallel

This verifies that all languages kept the same source/MRS ids after shuffling
and sampling.

```bash
python - <<'PY'
import json
from pathlib import Path

base = Path("e1_materials/<PHENOMENON>/pairs")
files = sorted(base.glob("*.pairs.jsonl"))

ref = None
bad = []

for p in files:
    ids = []
    with p.open() as f:
        for line in f:
            ids.append(json.loads(line)["id"])

    if ref is None:
        ref = ids
        ref_name = p.name
    elif ids != ref:
        bad.append(p.name)

print("files", len(files))
print("ref", ref_name if files else "")
print("same_id_sequence", len(bad) == 0)
if bad:
    print("different:", bad[:20])
PY
```

## 9. Batch Score 96 Models

```bash
mkdir -p e1_materials/<PHENOMENON>/scores

for f in e1_materials/<PHENOMENON>/pairs/*.pairs.jsonl; do
  lang="$(basename "$f" .pairs.jsonl)"
  model="models/${lang}/seed_42/checkpoint-70000"

  if [ ! -d "$model" ]; then
    echo "[skip] missing model: $model"
    continue
  fi

  python evaluation/E1/score_e1_pairs.py \
    --model "$model" \
    --pairs "$f" \
    --out "e1_materials/<PHENOMENON>/scores/${lang}.scores.tsv" \
    --summary "e1_materials/<PHENOMENON>/scores/${lang}.summary.json" \
    --batch-size 64 \
    --device cuda \
    --score-mode bos_eos
done
```

## 10. Quick Aggregate

```bash
python evaluation/E1/analyze_e1_scores.py \
  --score-dir e1_materials/<PHENOMENON>/scores \
  --out-dir e1_materials/<PHENOMENON>/analysis \
  --manifest choices/manifest.tsv \
  --lowest-n 20
```

Main analysis outputs:

```text
e1_materials/<PHENOMENON>/analysis/quick_report.json
e1_materials/<PHENOMENON>/analysis/model_summary.tsv
e1_materials/<PHENOMENON>/analysis/by_dimension.tsv
e1_materials/<PHENOMENON>/analysis/clause_np_alignment.tsv
e1_materials/<PHENOMENON>/analysis/lowest_models.tsv
```

## Main Outputs

```text
e1_materials/<PHENOMENON>/<PHENOMENON>_extract.jsonl
e1_materials/<PHENOMENON>/<PHENOMENON>_pseudo.jsonl
e1_materials/<PHENOMENON>/<PHENOMENON>_mrs.jsonl
e1_materials/<PHENOMENON>/generated/selected/*.jsonl
e1_materials/<PHENOMENON>/pairs/*.pairs.jsonl
e1_materials/<PHENOMENON>/scores/*.scores.tsv
e1_materials/<PHENOMENON>/scores/*.summary.json
```

## Clean-Repo Policy

E1 source definitions live in:

```text
evaluation/E1/phenomena/<PHENOMENON>/
```

Large or regenerated materials live in:

```text
e1_materials/
```

Keep `e1_materials/` untracked.
