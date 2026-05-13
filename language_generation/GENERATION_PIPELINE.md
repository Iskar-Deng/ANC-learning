# Language Generation Pipeline

```bash
# Generate all target-language corpora
bash language_generation/run_all_language_generation.sh \
  --mrs data/sample/sample_mrs.jsonl
```

## Single-grammar workflow

```bash
# 1. Generate raw target-language outputs from MRS bank
nohup python3 -m language_generation.generate_from_mrs_bank \
  --grammar grammars/62_svo_ng_er_d_ep/62_svo_ng_er_d_ep.dat \
  --input data/sample/sample_mrs.jsonl \
  --out data/sample/generated/raw/62_svo_ng_er_d_ep.jsonl \
  --no-mrs \
  --workers 12 \
  --chunksize 100 \
  --max-gen 20 \
  > logs/generation/generate_62_svo_ng_er_d_ep.log 2>&1 &
```

```bash
# 2. Select one generated sentence per MRS id
python language_generation/select_overgen.py \
  --input data/sample/generated/raw/62_svo_ng_er_d_ep.jsonl \
  --out data/sample/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --save-details data/sample/generated/details/62_svo_ng_er_d_ep.jsonl
```