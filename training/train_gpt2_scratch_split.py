#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import math
import os
import random
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

from utils import TRAINING_CONFIG


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-input", type=str, required=True)
    parser.add_argument("--dev-input", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default=None)
    return parser.parse_args()


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def read_jsonl(path: str, text_field: str):
    rows = []
    bad_rows = 0

    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON parse error in {path} line {line_no}: {e}") from e

            if text_field not in obj:
                bad_rows += 1
                continue

            text = obj[text_field]
            if not isinstance(text, str):
                bad_rows += 1
                continue

            text = text.strip()
            if not text:
                bad_rows += 1
                continue

            rows.append({"text": text})

    if not rows:
        raise ValueError(f"No valid data loaded from {path}")

    if bad_rows > 0:
        print(f"[Warning] skipped {bad_rows} bad rows from {path}")

    return Dataset.from_list(rows)


def tokenize_and_group(dataset, tokenizer, block_size: int):
    def tokenize_fn(batch):
        texts = [x + tokenizer.eos_token for x in batch["text"]]
        return tokenizer(
            texts,
            add_special_tokens=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )

    tokenized = dataset.map(
        tokenize_fn,
        batched=True,
        remove_columns=dataset.column_names,
        desc="Tokenizing",
    )

    def group_texts(examples):
        concatenated = {k: sum(examples[k], []) for k in examples.keys()}
        total_length = len(concatenated["input_ids"])
        total_length = (total_length // block_size) * block_size

        if total_length == 0:
            return {"input_ids": [], "labels": []}

        result = {
            k: [t[i:i + block_size] for i in range(0, total_length, block_size)]
            for k, t in concatenated.items()
        }
        result["labels"] = [ids.copy() for ids in result["input_ids"]]
        return result

    lm_dataset = tokenized.map(
        group_texts,
        batched=True,
        desc="Packing",
    )

    if len(lm_dataset) == 0:
        raise ValueError("Dataset became empty after packing. Try a smaller block_size.")

    return lm_dataset


def main():
    args = parse_args()
    cfg = TRAINING_CONFIG

    model_name = cfg["model_name"]
    text_field = cfg["text_field"]
    output_dir = args.output_dir
    block_size = cfg["block_size"]
    seed = cfg["seed"]

    os.makedirs(output_dir, exist_ok=True)
    set_seed(seed)

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("Loading datasets...")
    train_raw = read_jsonl(args.train_input, text_field)
    dev_raw = read_jsonl(args.dev_input, text_field)

    print(f"Train examples: {len(train_raw):,}")
    print(f"Dev examples  : {len(dev_raw):,}")

    print("Tokenizing and packing train...")
    train_dataset = tokenize_and_group(train_raw, tokenizer, block_size)

    print("Tokenizing and packing dev...")
    dev_dataset = tokenize_and_group(dev_raw, tokenizer, block_size)

    print(f"Packed train blocks: {len(train_dataset):,}")
    print(f"Packed dev blocks  : {len(dev_dataset):,}")

    print("Building config...")
    config = AutoConfig.from_pretrained(model_name)
    config.vocab_size = len(tokenizer)
    config.n_positions = block_size
    config.n_ctx = block_size

    print("Initializing model from scratch...")
    model = AutoModelForCausalLM.from_config(config)
    model.resize_token_embeddings(len(tokenizer))

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total params: {total_params:,}")

    training_args = TrainingArguments(
        output_dir=output_dir,

        num_train_epochs=cfg["num_train_epochs"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=cfg["per_device_eval_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],

        learning_rate=cfg["learning_rate"],
        warmup_steps=cfg["warmup_steps"],
        weight_decay=cfg["weight_decay"],

        logging_steps=cfg["logging_steps"],
        eval_steps=cfg["eval_steps"],
        save_steps=cfg["save_steps"],

        eval_strategy="steps",
        save_strategy="steps",
        logging_strategy="steps",

        save_total_limit=cfg["save_total_limit"],
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,

        fp16=torch.cuda.is_available(),
        report_to="none",
        remove_unused_columns=False,

        seed=seed,
        data_seed=seed,
        dataloader_num_workers=cfg["dataloader_num_workers"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=dev_dataset,
        processing_class=tokenizer,
    )

    print("Start training...")
    trainer.train()

    print("Saving model...")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("Final evaluation on dev...")
    metrics = trainer.evaluate(eval_dataset=dev_dataset)

    if "eval_loss" in metrics:
        try:
            metrics["perplexity"] = math.exp(metrics["eval_loss"])
        except OverflowError:
            metrics["perplexity"] = float("inf")

    metrics_path = Path(output_dir) / "dev_metrics.json"
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(metrics)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()