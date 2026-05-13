#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs/training

languages=(
  42_svo_gn_er_b_ep
  50_svo_ng_ac_b_ep
  82_vos_ng_ac_b_ep
  94_vos_ng_er_d_ep
)

for lang in "${languages[@]}"; do
  out_dir="models/${lang}/seed_42"
  log_file="logs/training/train_${lang}_seed42.log"
  train_file="data/train/generated/selected/${lang}.jsonl"
  dev_file="data/dev/generated/selected/${lang}.jsonl"

  echo "[$(date)] CHECK ${lang}"

  if [[ ! -f "${train_file}" ]]; then
    echo "[$(date)] ERROR ${lang}: missing train file: ${train_file}"
    exit 1
  fi

  if [[ ! -f "${dev_file}" ]]; then
    echo "[$(date)] ERROR ${lang}: missing dev file: ${dev_file}"
    exit 1
  fi

  if [[ -f "${out_dir}/dev_metrics.json" && -f "${out_dir}/model.safetensors" ]]; then
    echo "[$(date)] SKIP ${lang}: already completed."
    continue
  fi

  echo "[$(date)] START ${lang}"

  python -m training.train_lm \
    --language "${lang}" \
    --train-input "${train_file}" \
    --dev-input "${dev_file}" \
    > "${log_file}" 2>&1

  echo "[$(date)] DONE ${lang}"
done

echo "[$(date)] ALL DONE"
