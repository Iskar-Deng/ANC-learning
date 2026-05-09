#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计 jsonl 语料大小，并粗略估算 GPT-2 训练时间。

输入文件格式示例：
{"id": 1, "sent": "They gets"}
{"id": 2, "sent": "You haves that you worrys"}

用法：
python training/corpus_stats_and_gpt2_estimate.py \
  --input /home/dengh/workspace/ANC-learning/data/train_mrs-test-english-selected.jsonl \
  --epochs 3 \
  --batch-size 8 \
  --seq-len 32 \
  --tokens-per-sec 50000

说明：
- 默认按空格分词统计 token 数。
- tokens_per_sec 是一个粗略速度参数，用来估训练时长。
- 这个脚本只做估算，不真的训练模型。
"""

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median


def format_seconds(seconds: float) -> str:
    seconds = int(round(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON 解析失败: line {line_no}: {e}") from e


def tokenize_whitespace(text: str):
    return text.strip().split()


def compute_corpus_stats(path: Path):
    num_sent = 0
    total_tokens = 0
    sent_lengths = []
    vocab = Counter()

    bad_rows = 0
    missing_sent = 0

    for line_no, row in iter_jsonl(path):
        if "sent" not in row:
            missing_sent += 1
            continue

        sent = row["sent"]

        if not isinstance(sent, str):
            bad_rows += 1
            continue

        tokens = tokenize_whitespace(sent)

        num_sent += 1
        sent_len = len(tokens)
        total_tokens += sent_len
        sent_lengths.append(sent_len)
        vocab.update(tokens)

    if num_sent == 0:
        raise ValueError("没有读到有效句子，请检查输入文件。")

    sorted_lengths = sorted(sent_lengths)

    def pct(p: float) -> int:
        idx = min(len(sorted_lengths) - 1, max(0, math.ceil(len(sorted_lengths) * p) - 1))
        return sorted_lengths[idx]

    stats = {
        "sentences": num_sent,
        "total_tokens": total_tokens,
        "avg_len": total_tokens / num_sent,
        "median_len": median(sent_lengths),
        "max_len": max(sent_lengths),
        "min_len": min(sent_lengths),
        "p90_len": pct(0.90),
        "p95_len": pct(0.95),
        "p99_len": pct(0.99),
        "vocab_size": len(vocab),
        "top_50_tokens": vocab.most_common(50),
        "bad_rows": bad_rows,
        "missing_sent": missing_sent,
    }
    return stats


def estimate_training(
    total_tokens: int,
    epochs: float,
    batch_size: int,
    seq_len: int,
    tokens_per_sec: float,
):
    if batch_size <= 0 or seq_len <= 0 or epochs <= 0 or tokens_per_sec <= 0:
        raise ValueError("epochs, batch_size, seq_len, tokens_per_sec 都必须 > 0")

    tokens_per_step = batch_size * seq_len
    steps_per_epoch = math.ceil(total_tokens / tokens_per_step)
    total_steps = math.ceil(steps_per_epoch * epochs)

    # 粗略估算：每个 epoch 看一遍所有 token
    total_train_tokens = total_tokens * epochs
    total_time_sec = total_train_tokens / tokens_per_sec

    return {
        "tokens_per_step": tokens_per_step,
        "steps_per_epoch": steps_per_epoch,
        "total_steps": total_steps,
        "total_train_tokens": int(total_train_tokens),
        "total_time_sec": total_time_sec,
        "total_time_human": format_seconds(total_time_sec),
    }


def print_stats(stats: dict):
    print("==== Corpus Stats ====")
    print(f"Sentences      : {stats['sentences']}")
    print(f"Total tokens   : {stats['total_tokens']}")
    print(f"Avg length     : {stats['avg_len']:.2f}")
    print(f"Median length  : {stats['median_len']}")
    print(f"Min length     : {stats['min_len']}")
    print(f"Max length     : {stats['max_len']}")
    print(f"P90 length     : {stats['p90_len']}")
    print(f"P95 length     : {stats['p95_len']}")
    print(f"P99 length     : {stats['p99_len']}")
    print(f"Vocab size     : {stats['vocab_size']}")
    print(f"Bad rows       : {stats['bad_rows']}")
    print(f"Missing 'sent' : {stats['missing_sent']}")
    print()

    print("Top 50 tokens:")
    for tok, cnt in stats["top_50_tokens"]:
        print(f"  {tok!r}: {cnt}")
    print()


def print_estimate(est: dict, epochs: float, batch_size: int, seq_len: int, tokens_per_sec: float):
    print("==== GPT-2 Training Estimate ====")
    print(f"Epochs             : {epochs}")
    print(f"Batch size         : {batch_size}")
    print(f"Seq len            : {seq_len}")
    print(f"Tokens / sec       : {tokens_per_sec}")
    print(f"Tokens / step      : {est['tokens_per_step']}")
    print(f"Steps / epoch      : {est['steps_per_epoch']}")
    print(f"Total steps        : {est['total_steps']}")
    print(f"Total train tokens : {est['total_train_tokens']}")
    print(f"Estimated time     : {est['total_time_human']}")
    print()


def save_json(output_path: Path, stats: dict, estimate: dict, args: argparse.Namespace):
    payload = {
        "input": str(args.input),
        "corpus_stats": stats,
        "training_estimate": estimate,
        "config": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "seq_len": args.seq_len,
            "tokens_per_sec": args.tokens_per_sec,
        },
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"结果已写入: {output_path}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="输入 jsonl 文件路径",
    )
    parser.add_argument(
        "--epochs",
        type=float,
        default=3.0,
        help="训练轮数，默认 3",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="batch size，默认 8",
    )
    parser.add_argument(
        "--seq-len",
        type=int,
        default=32,
        help="序列长度，默认 32",
    )
    parser.add_argument(
        "--tokens-per-sec",
        type=float,
        default=50000,
        help="估算吞吐速度，默认 50000 tokens/s",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        default=None,
        help="可选：把结果写到 json 文件",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"输入文件不存在: {args.input}")

    stats = compute_corpus_stats(args.input)
    estimate = estimate_training(
        total_tokens=stats["total_tokens"],
        epochs=args.epochs,
        batch_size=args.batch_size,
        seq_len=args.seq_len,
        tokens_per_sec=args.tokens_per_sec,
    )

    print_stats(stats)
    print_estimate(
        estimate,
        epochs=args.epochs,
        batch_size=args.batch_size,
        seq_len=args.seq_len,
        tokens_per_sec=args.tokens_per_sec,
    )

    # 顺手给一个很粗的提示
    print("==== Notes ====")
    print("- 这里 token 是按空格切分，不是 GPT-2 tokenizer 的 subword token。")
    print("- 所以 total_tokens 会比真实 GPT-2 训练 token 数略小或略不一样。")
    print("- 但对你现在做训练规模预估，已经够用了。")
    print("- 如果句子都很短、vocab 很小，GPT-2 往往训练很快，也很容易过拟合。")
    print()

    if args.save_json is not None:
        save_json(args.save_json, stats, estimate, args)


if __name__ == "__main__":
    main()