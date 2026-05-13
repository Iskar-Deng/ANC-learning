# Training Pipeline

Train one language model per target grammar output.

## Single run

```bash
python -m training.train_lm \
  --language 62_svo_ng_er_d_ep \
  --train-input data/train/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --dev-input data/dev/generated/selected/62_svo_ng_er_d_ep.jsonl
```

Default output:

```text
models/62_svo_ng_er_d_ep/seed_42/
```

## Multiple seeds

```bash
python -m training.train_lm \
  --language 62_svo_ng_er_d_ep \
  --train-input data/train/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --dev-input data/dev/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --seed 43
```

Default output:

```text
models/62_svo_ng_er_d_ep/seed_43/
```

## Resume

Resume is automatic if a checkpoint exists in the output directory.

```bash
python -m training.train_lm \
  --language 62_svo_ng_er_d_ep \
  --train-input data/train/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --dev-input data/dev/generated/selected/62_svo_ng_er_d_ep.jsonl
```

Or specify a checkpoint explicitly:

```bash
python -m training.train_lm \
  --language 62_svo_ng_er_d_ep \
  --train-input data/train/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --dev-input data/dev/generated/selected/62_svo_ng_er_d_ep.jsonl \
  --resume-from-checkpoint models/62_svo_ng_er_d_ep/seed_42/checkpoint-65000
```

## Defaults

Training defaults are defined in `utils.py`.

```text
max_steps: 70000
eval_steps: 5000
save_steps: 5000
save_total_limit: 1
block_size: 32
batch_size: 16
gradient_accumulation_steps: 2
```

The saved model is the final model at `max_steps`, not the best dev-loss checkpoint.

## Outputs

```text
models/<language>/seed_<seed>/
  train_config.json
  log_history.json
  dev_loss_curve.tsv
  train_loss_curve.tsv
  dev_metrics.json
  checkpoint-*
  model files
```
