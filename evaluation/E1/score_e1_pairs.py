#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import torch
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer


JsonDict = Dict[str, Any]


def iter_jsonl(path: Path) -> Iterator[JsonDict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"Line {line_no} is not a JSON object")
            yield obj


def get_device(device_arg: str) -> torch.device:
    if device_arg == "cuda" and not torch.cuda.is_available():
        print("[warn] cuda requested but unavailable; using cpu")
        return torch.device("cpu")
    return torch.device(device_arg)


def boundary_token(tokenizer) -> str:
    tok = tokenizer.bos_token or tokenizer.eos_token
    if tok is None:
        raise ValueError("Tokenizer has neither bos_token nor eos_token")
    return tok


def prepare_for_scoring(tokenizer, sentence: str, score_mode: str) -> str:
    sentence = sentence.strip()

    if score_mode == "legacy":
        return sentence

    bos = boundary_token(tokenizer)

    if score_mode == "bos":
        return bos + sentence

    if score_mode == "bos_eos":
        if tokenizer.eos_token is None:
            raise ValueError("Tokenizer has no eos_token; cannot use bos_eos")
        return bos + sentence + tokenizer.eos_token

    raise ValueError(score_mode)


def model_max_positions(model) -> int:
    for attr in ("n_positions", "max_position_embeddings", "n_ctx"):
        value = getattr(model.config, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    raise ValueError("Could not determine model max positions")


def score_batch_input_ids(model, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
    logits = outputs.logits

    shift_logits = logits[:, :-1, :].contiguous()
    shift_labels = input_ids[:, 1:].contiguous()
    shift_mask = attention_mask[:, 1:].contiguous()

    log_probs = torch.nn.functional.log_softmax(shift_logits, dim=-1)
    token_log_probs = log_probs.gather(
        dim=-1,
        index=shift_labels.unsqueeze(-1),
    ).squeeze(-1)

    token_log_probs = token_log_probs * shift_mask
    lengths = shift_mask.sum(dim=1)

    # Average log probability per scored token.
    return token_log_probs.sum(dim=1) / lengths.clamp(min=1)


def score_long_input_ids(
    model,
    input_ids: List[int],
    device: torch.device,
    max_positions: int,
) -> float:
    if len(input_ids) <= 1:
        return 0.0

    total_log_prob = 0.0
    total_tokens = 0
    start = 0

    while start < len(input_ids) - 1:
        end = min(len(input_ids), start + max_positions)
        chunk = torch.tensor([input_ids[start:end]], dtype=torch.long, device=device)
        mask = torch.ones_like(chunk, device=device)

        seq_score = score_batch_input_ids(model, chunk, mask)
        n_scored = chunk.shape[1] - 1
        total_log_prob += float(seq_score.item()) * n_scored
        total_tokens += n_scored

        if end == len(input_ids):
            break
        start = end - 1

    return total_log_prob / max(total_tokens, 1)


def score_sentences(
    model,
    tokenizer,
    sentences: List[str],
    device: torch.device,
    batch_size: int,
    score_mode: str,
) -> List[float]:
    scores: List[float] = []
    max_positions = model_max_positions(model)

    model.eval()
    with torch.no_grad():
        for start in tqdm(range(0, len(sentences), batch_size), desc="Scoring batches"):
            raw_batch = sentences[start:start + batch_size]
            batch = [prepare_for_scoring(tokenizer, s, score_mode) for s in raw_batch]

            encoded = tokenizer(
                batch,
                add_special_tokens=False,
                truncation=False,
            )["input_ids"]

            batch_scores: List[float | None] = [None] * len(encoded)

            short_indices = [i for i, ids in enumerate(encoded) if len(ids) <= max_positions]
            long_indices = [i for i, ids in enumerate(encoded) if len(ids) > max_positions]

            if short_indices:
                short_batch = [batch[i] for i in short_indices]
                enc = tokenizer(
                    short_batch,
                    add_special_tokens=False,
                    return_tensors="pt",
                    padding=True,
                    truncation=False,
                )
                input_ids = enc["input_ids"].to(device)
                attention_mask = enc["attention_mask"].to(device)

                seq_scores = score_batch_input_ids(model, input_ids, attention_mask)
                for i, score in zip(short_indices, seq_scores.detach().cpu().tolist()):
                    batch_scores[i] = float(score)

            for i in long_indices:
                batch_scores[i] = score_long_input_ids(
                    model=model,
                    input_ids=encoded[i],
                    device=device,
                    max_positions=max_positions,
                )

            scores.extend(float(s) for s in batch_scores if s is not None)

    return scores


def safe_tsv(x: Any) -> str:
    return str(x).replace("\t", " ").replace("\n", " ").replace("\r", " ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--pairs", required=True, help="JSONL with good and bad fields")
    ap.add_argument("--out", required=True, help="Output TSV")
    ap.add_argument("--summary", default=None, help="Optional summary JSON")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu", "mps"])
    ap.add_argument(
        "--score-mode",
        default="bos_eos",
        choices=["legacy", "bos", "bos_eos"],
    )
    args = ap.parse_args()

    model_path = Path(args.model)
    pairs_path = Path(args.pairs)
    out_path = Path(args.out)
    summary_path = Path(args.summary) if args.summary else out_path.with_suffix(".summary.json")

    rows = list(iter_jsonl(pairs_path))
    if not rows:
        raise ValueError(f"No rows loaded from {pairs_path}")

    goods = []
    bads = []
    for row in rows:
        good = row.get("good")
        bad = row.get("bad")
        if not isinstance(good, str) or not good.strip():
            raise ValueError(f"Missing good sentence: {row}")
        if not isinstance(bad, str) or not bad.strip():
            raise ValueError(f"Missing bad sentence: {row}")
        goods.append(good.strip())
        bads.append(bad.strip())

    device = get_device(args.device)

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or boundary_token(tokenizer)

    model = AutoModelForCausalLM.from_pretrained(model_path)
    if len(tokenizer) != model.get_input_embeddings().weight.shape[0]:
        model.resize_token_embeddings(len(tokenizer))

    model.to(device)
    model.eval()

    print(f"Model:      {model_path}")
    print(f"Pairs:      {pairs_path}")
    print(f"N pairs:    {len(rows)}")
    print(f"Device:     {device}")
    print(f"Score mode: {args.score_mode}")

    good_scores = score_sentences(
        model=model,
        tokenizer=tokenizer,
        sentences=goods,
        device=device,
        batch_size=args.batch_size,
        score_mode=args.score_mode,
    )
    bad_scores = score_sentences(
        model=model,
        tokenizer=tokenizer,
        sentences=bads,
        device=device,
        batch_size=args.batch_size,
        score_mode=args.score_mode,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    correct = 0
    ties = 0
    delta_sum = 0.0

    with out_path.open("w", encoding="utf-8") as f:
        f.write(
            "pair_index\tid\tlanguage\tphenomenon_id\tgood_score\tbad_score\t"
            "delta\tcorrect\ttie\tgood\tbad\n"
        )

        for i, (row, gs, bs) in enumerate(zip(rows, good_scores, bad_scores), start=1):
            delta = gs - bs
            is_tie = abs(delta) <= 1e-8
            is_correct = delta > 1e-8

            correct += int(is_correct)
            ties += int(is_tie)
            delta_sum += delta

            f.write(
                f"{row.get('pair_index', i)}\t"
                f"{row.get('id', '')}\t"
                f"{row.get('language', '')}\t"
                f"{row.get('phenomenon_id', '')}\t"
                f"{gs:.8f}\t{bs:.8f}\t{delta:.8f}\t"
                f"{int(is_correct)}\t{int(is_tie)}\t"
                f"{safe_tsv(row.get('good', ''))}\t"
                f"{safe_tsv(row.get('bad', ''))}\n"
            )

    summary = {
        "model": str(model_path),
        "pairs": str(pairs_path),
        "out": str(out_path),
        "n_pairs": len(rows),
        "score_mode": args.score_mode,
        "accuracy_strict": correct / len(rows),
        "ties": ties,
        "tie_rate": ties / len(rows),
        "mean_delta_good_minus_bad": delta_sum / len(rows),
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()