#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

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


JsonDict = Dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--train-input", required=True)
    parser.add_argument("--dev-input", required=True)

    # Used for default output path:
    # models/<language>/seed_<seed>/
    parser.add_argument("--language", required=True)

    # Optional output overrides.
    parser.add_argument("--output-root", default="models")
    parser.add_argument("--output-dir", default=None)

    # Optional config overrides.
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--resume-from-checkpoint", default=None)

    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def read_jsonl(path: str, text_field: str) -> Dataset:
    rows: List[JsonDict] = []
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


def tokenize_and_group(dataset: Dataset, tokenizer: AutoTokenizer, block_size: int) -> Dataset:
    def tokenize_fn(batch: JsonDict) -> JsonDict:
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

    def group_texts(examples: JsonDict) -> JsonDict:
        concatenated = {k: sum(examples[k], []) for k in examples.keys()}
        total_length = len(concatenated["input_ids"])
        total_length = (total_length // block_size) * block_size

        if total_length == 0:
            return {"input_ids": [], "labels": []}

        result = {
            k: [t[i : i + block_size] for i in range(0, total_length, block_size)]
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


def default_output_dir(output_root: str, language: str, seed: int) -> str:
    return str(Path(output_root) / language / f"seed_{seed}")


def find_latest_checkpoint(output_dir: str) -> Optional[str]:
    path = Path(output_dir)
    if not path.exists():
        return None

    checkpoints = []
    for child in path.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("checkpoint-"):
            continue
        try:
            step = int(child.name.split("-")[-1])
        except ValueError:
            continue
        checkpoints.append((step, child))

    if not checkpoints:
        return None

    checkpoints.sort(key=lambda x: x[0])
    return str(checkpoints[-1][1])


def save_json(path: Path, obj: JsonDict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def save_log_history(output_dir: Path, log_history: List[JsonDict]) -> None:
    save_json(output_dir / "log_history.json", {"log_history": log_history})


def save_dev_loss_curve(output_dir: Path, log_history: List[JsonDict]) -> None:
    path = output_dir / "dev_loss_curve.tsv"

    with path.open("w", encoding="utf-8") as f:
        f.write("step\teval_loss\tperplexity\n")
        for row in log_history:
            if "eval_loss" not in row:
                continue

            step = row.get("step", "")
            eval_loss = row["eval_loss"]
            try:
                ppl = math.exp(eval_loss)
            except OverflowError:
                ppl = float("inf")

            f.write(f"{step}\t{eval_loss}\t{ppl}\n")


def save_train_loss_curve(output_dir: Path, log_history: List[JsonDict]) -> None:
    path = output_dir / "train_loss_curve.tsv"

    with path.open("w", encoding="utf-8") as f:
        f.write("step\tloss\tlearning_rate\n")
        for row in log_history:
            if "loss" not in row:
                continue

            step = row.get("step", "")
            loss = row.get("loss", "")
            lr = row.get("learning_rate", "")
            f.write(f"{step}\t{loss}\t{lr}\n")


def main() -> None:
    args = parse_args()
    cfg = dict(TRAINING_CONFIG)

    seed = args.seed if args.seed is not None else cfg["seed"]
    max_steps = args.max_steps if args.max_steps is not None else cfg["max_steps"]

    if max_steps <= 0:
        raise ValueError("--max-steps must be > 0")

    cfg["seed"] = seed
    cfg["max_steps"] = max_steps

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = default_output_dir(args.output_root, args.language, seed)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    set_seed(seed)

    model_name = cfg["model_name"]
    text_field = cfg["text_field"]
    block_size = cfg["block_size"]

    print("========== Train LM ==========")
    print(f"Language:       {args.language}")
    print(f"Train input:    {args.train_input}")
    print(f"Dev input:      {args.dev_input}")
    print(f"Output dir:     {output_dir}")
    print(f"Model config:   {model_name}")
    print(f"Text field:     {text_field}")
    print(f"Block size:     {block_size}")
    print(f"Seed:           {seed}")
    print(f"Max steps:      {max_steps}")
    print(f"Eval steps:     {cfg['eval_steps']}")
    print(f"Save steps:     {cfg['save_steps']}")
    print(f"Save limit:     {cfg['save_total_limit']}")
    print()

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

    num_gpus = max(1, torch.cuda.device_count())
    effective_batch_size = (
        cfg["per_device_train_batch_size"]
        * cfg["gradient_accumulation_steps"]
        * num_gpus
    )
    approx_blocks_seen = effective_batch_size * max_steps

    print(f"GPUs:                   {num_gpus}")
    print(f"Effective batch size:   {effective_batch_size}")
    print(f"Approx train blocks seen: {approx_blocks_seen:,}")
    print()

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

    train_config = {
        **cfg,
        "language": args.language,
        "train_input": args.train_input,
        "dev_input": args.dev_input,
        "output_dir": output_dir,
        "num_gpus": num_gpus,
        "effective_batch_size": effective_batch_size,
        "approx_train_blocks_seen": approx_blocks_seen,
        "saved_model": "final_step_model",
        "resume_from_checkpoint_arg": args.resume_from_checkpoint,
    }
    save_json(output_path / "train_config.json", train_config)

    training_args = TrainingArguments(
        output_dir=output_dir,

        # Fixed-step training.
        max_steps=max_steps,

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

        # Keep only the latest checkpoint. This supports resume while keeping disk usage low.
        save_total_limit=cfg["save_total_limit"],

        # Save final 70k-step model, not best-dev checkpoint.
        load_best_model_at_end=False,

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

    resume_checkpoint = args.resume_from_checkpoint
    if resume_checkpoint is None:
        resume_checkpoint = find_latest_checkpoint(output_dir)

    if resume_checkpoint is not None:
        print(f"Resuming from checkpoint: {resume_checkpoint}")
    else:
        print("Starting from scratch.")

    print("Start training...")
    trainer.train(resume_from_checkpoint=resume_checkpoint)

    print("Saving final model...")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("Saving training curves...")
    log_history = trainer.state.log_history
    save_log_history(output_path, log_history)
    save_dev_loss_curve(output_path, log_history)
    save_train_loss_curve(output_path, log_history)

    print("Final evaluation on dev...")
    metrics = trainer.evaluate(eval_dataset=dev_dataset)

    if "eval_loss" in metrics:
        try:
            metrics["perplexity"] = math.exp(metrics["eval_loss"])
        except OverflowError:
            metrics["perplexity"] = float("inf")

    metrics["language"] = args.language
    metrics["seed"] = seed
    metrics["max_steps"] = max_steps

    metrics_path = output_path / "dev_metrics.json"
    save_json(metrics_path, metrics)

    # Save final trainer state too.
    trainer_state_path = output_path / "trainer_state.json"
    trainer.state.save_to_json(str(trainer_state_path))

    print(metrics)
    print(f"Saved final model to: {output_dir}")
    print(f"Saved metrics to: {metrics_path}")
    print(f"Saved log history to: {output_path / 'log_history.json'}")
    print(f"Saved dev loss curve to: {output_path / 'dev_loss_curve.tsv'}")
    print(f"Saved train loss curve to: {output_path / 'train_loss_curve.tsv'}")


if __name__ == "__main__":
    main()