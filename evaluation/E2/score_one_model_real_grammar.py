#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {path} line {line_no}: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"Line {line_no} in {path} is not a JSON object")
            yield obj


def load_selected(path: Path):
    data = {}
    for row in iter_jsonl(path):
        row_id = row.get("id")
        sent = row.get("sent")
        if row_id is None or not isinstance(sent, str) or not sent.strip():
            continue
        if row_id in data:
            raise ValueError(f"Duplicate id {row_id!r} in {path}")
        data[row_id] = sent.strip()
    return data


def load_common_ids(path: Path):
    ids = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            x = line.strip()
            if not x:
                continue
            try:
                ids.append(int(x))
            except ValueError:
                ids.append(x)
    return ids


def parse_language_id(lang: str):
    parts = lang.split("_")
    keys = ["num_id", "clause_wo", "np_wo", "alignment", "comp_system", "strategy"]
    if len(parts) != 6:
        return {"language": lang, **{k: "" for k in keys}}
    return {"language": lang, **dict(zip(keys, parts))}


def get_device(device_arg: str):
    if device_arg == "cuda" and not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device(device_arg)


def boundary_token(tokenizer):
    tok = tokenizer.bos_token or tokenizer.eos_token
    if tok is None:
        raise ValueError("Tokenizer has neither bos_token nor eos_token.")
    return tok


def prepare_for_scoring(tokenizer, sentence: str, score_mode: str):
    sentence = sentence.strip()
    if score_mode == "legacy":
        return sentence
    bos = boundary_token(tokenizer)
    if score_mode == "bos":
        return bos + sentence
    if score_mode == "bos_eos":
        if tokenizer.eos_token is None:
            raise ValueError("Tokenizer has no eos_token; cannot use bos_eos.")
        return bos + sentence + tokenizer.eos_token
    raise ValueError(f"Unknown score mode: {score_mode}")


def model_max_positions(model):
    for attr in ("n_positions", "max_position_embeddings", "n_ctx"):
        value = getattr(model.config, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    raise ValueError("Could not determine model maximum position length.")


def score_batch_input_ids(model, input_ids, attention_mask):
    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
    logits = outputs.logits
    shift_logits = logits[:, :-1, :].contiguous()
    shift_labels = input_ids[:, 1:].contiguous()
    shift_mask = attention_mask[:, 1:].contiguous()

    log_probs = torch.nn.functional.log_softmax(shift_logits, dim=-1)
    token_log_probs = log_probs.gather(-1, shift_labels.unsqueeze(-1)).squeeze(-1)
    token_log_probs = token_log_probs * shift_mask
    lengths = shift_mask.sum(dim=1)
    return token_log_probs.sum(dim=1) / lengths.clamp(min=1)


def score_long_input_ids(model, input_ids, device, max_positions):
    if len(input_ids) <= 1:
        return 0.0
    total_log_prob = 0.0
    total_tokens = 0
    start = 0

    while start < len(input_ids) - 1:
        end = min(len(input_ids), start + max_positions)
        chunk = torch.tensor([input_ids[start:end]], dtype=torch.long, device=device)
        mask = torch.ones_like(chunk)
        score = score_batch_input_ids(model, chunk, mask)
        n_scored = chunk.shape[1] - 1
        total_log_prob += float(score.item()) * n_scored
        total_tokens += n_scored
        if end == len(input_ids):
            break
        start = end - 1

    return total_log_prob / max(total_tokens, 1)


def score_sentences(model, tokenizer, sentences, device, batch_size, score_mode):
    if not sentences:
        return []

    scores = []
    max_positions = model_max_positions(model)
    model.eval()

    with torch.no_grad():
        for start in range(0, len(sentences), batch_size):
            raw_batch = sentences[start:start + batch_size]
            batch = [prepare_for_scoring(tokenizer, s, score_mode) for s in raw_batch]
            encoded = tokenizer(batch, add_special_tokens=False, truncation=False)["input_ids"]

            batch_scores = [None] * len(encoded)
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
                    model, encoded[i], device, max_positions
                )

            scores.extend(float(x) for x in batch_scores if x is not None)

    return scores


def safe_tsv(text):
    return str(text).replace("\t", " ").replace("\n", " ").replace("\r", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--selected-dir", required=True)
    ap.add_argument("--common-ids", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--max-ids", type=int, default=None)
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu", "mps"])
    ap.add_argument("--tol", type=float, default=1e-8)
    ap.add_argument(
        "--score-mode",
        default="bos_eos",
        choices=["legacy", "bos", "bos_eos"],
        help="legacy=old E2; bos=scores first token; bos_eos=scores first token and final EOS.",
    )
    ap.add_argument("--write-details", action="store_true")
    args = ap.parse_args()

    model_path = Path(args.model)
    selected_dir = Path(args.selected_dir)
    common_ids_path = Path(args.common_ids)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected_files = sorted(selected_dir.glob("[0-9][0-9]_*.jsonl"))
    if not selected_files:
        raise FileNotFoundError(f"No selected files found in {selected_dir}")

    languages = [p.stem for p in selected_files]
    if args.model_id not in languages:
        raise ValueError(f"--model-id {args.model_id!r} not found among selected languages.")

    print(f"Loading selected outputs from {selected_dir}...")
    selected_by_lang = {}
    for path in tqdm(selected_files, desc="selected files"):
        selected_by_lang[path.stem] = load_selected(path)

    common_ids = load_common_ids(common_ids_path)
    if args.max_ids is not None:
        common_ids = common_ids[:args.max_ids]

    print(f"Selected languages: {len(languages)}")
    print(f"Common ids to score: {len(common_ids)}")
    print(f"Model id: {args.model_id}")
    print(f"Model path: {model_path}")
    print(f"Score mode: {args.score_mode}")

    device = get_device(args.device)
    print(f"Device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        if tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
        else:
            tokenizer.add_special_tokens({"pad_token": "<|pad|>"})

    model = AutoModelForCausalLM.from_pretrained(model_path)
    if len(tokenizer) != model.get_input_embeddings().weight.shape[0]:
        model.resize_token_embeddings(len(tokenizer))
    model.to(device)
    model.eval()

    print(f"Model max positions: {model_max_positions(model)}")

    summary_path = out_dir / f"{args.model_id}.summary.json"
    predictions_path = out_dir / f"{args.model_id}.predictions.tsv"
    details_path = out_dir / f"{args.model_id}.details.tsv"

    own_dims = parse_language_id(args.model_id)

    total = 0
    correct_tie_ok = 0
    strict_unique_top1 = 0
    top5 = 0
    mrr_sum = 0.0
    rank_sum = 0.0
    n_unique_sent_sum = 0
    own_group_size_sum = 0
    max_group_size_sum = 0
    max_sent_group_size_sum = 0
    dimension_correct = {
        "clause_wo": 0,
        "np_wo": 0,
        "alignment": 0,
        "comp_system": 0,
        "strategy": 0,
    }

    with predictions_path.open("w", encoding="utf-8") as f_pred:
        f_pred.write(
            "model_id\tid\town_language\town_score\tmax_score\town_rank\t"
            "correct_tie_ok\tstrict_unique_top1\ttop5\tmrr\t"
            "n_candidate_languages\tn_unique_sentences\t"
            "own_sentence_group_size\tmax_languages_count\tmax_unique_sentences_count\t"
            "max_languages\town_sentence\tbest_sentences\n"
        )

        f_detail = None
        if args.write_details:
            f_detail = details_path.open("w", encoding="utf-8")
            f_detail.write(
                "model_id\tid\tcandidate_language\tscore\trank\t"
                "is_own\tis_max\tsentence_group_size\tsent\n"
            )

        try:
            for row_id in tqdm(common_ids, desc="scoring ids"):
                lang_to_sent = {lang: selected_by_lang[lang][row_id] for lang in languages}

                sent_to_langs = defaultdict(list)
                for lang, sent in lang_to_sent.items():
                    sent_to_langs[sent].append(lang)

                unique_sents = list(sent_to_langs.keys())
                unique_scores = score_sentences(
                    model, tokenizer, unique_sents, device, args.batch_size, args.score_mode
                )

                sent_to_score = dict(zip(unique_sents, unique_scores))
                lang_to_score = {
                    lang: sent_to_score[sent]
                    for lang, sent in lang_to_sent.items()
                }

                own_sent = lang_to_sent[args.model_id]
                own_score = sent_to_score[own_sent]
                max_score = max(sent_to_score.values())

                best_sents = [
                    sent for sent, score in sent_to_score.items()
                    if score >= max_score - args.tol
                ]

                max_langs = []
                for sent in best_sents:
                    max_langs.extend(sent_to_langs[sent])
                max_langs = sorted(max_langs)

                own_rank = 1 + sum(score > own_score + args.tol for score in lang_to_score.values())
                is_correct_tie_ok = own_score >= max_score - args.tol
                is_strict_unique_top1 = is_correct_tie_ok and len(max_langs) == 1
                is_top5 = own_rank <= 5
                mrr = 1.0 / own_rank

                total += 1
                correct_tie_ok += int(is_correct_tie_ok)
                strict_unique_top1 += int(is_strict_unique_top1)
                top5 += int(is_top5)
                mrr_sum += mrr
                rank_sum += own_rank

                n_unique_sent = len(unique_sents)
                own_group_size = len(sent_to_langs[own_sent])
                max_languages_count = len(max_langs)
                max_unique_sentences_count = len(best_sents)

                n_unique_sent_sum += n_unique_sent
                own_group_size_sum += own_group_size
                max_group_size_sum += max_languages_count
                max_sent_group_size_sum += max_unique_sentences_count

                best_dims = [parse_language_id(lang) for lang in max_langs]
                for dim in dimension_correct:
                    if any(d[dim] == own_dims[dim] for d in best_dims):
                        dimension_correct[dim] += 1

                f_pred.write(
                    f"{args.model_id}\t{row_id}\t{args.model_id}\t"
                    f"{own_score:.8f}\t{max_score:.8f}\t{own_rank}\t"
                    f"{int(is_correct_tie_ok)}\t{int(is_strict_unique_top1)}\t"
                    f"{int(is_top5)}\t{mrr:.8f}\t"
                    f"{len(languages)}\t{n_unique_sent}\t"
                    f"{own_group_size}\t{max_languages_count}\t{max_unique_sentences_count}\t"
                    f"{','.join(max_langs)}\t{safe_tsv(own_sent)}\t"
                    f"{' ||| '.join(safe_tsv(s) for s in best_sents)}\n"
                )

                if f_detail is not None:
                    for lang in languages:
                        sent = lang_to_sent[lang]
                        score = lang_to_score[lang]
                        rank = 1 + sum(other > score + args.tol for other in lang_to_score.values())
                        f_detail.write(
                            f"{args.model_id}\t{row_id}\t{lang}\t"
                            f"{score:.8f}\t{rank}\t{int(lang == args.model_id)}\t"
                            f"{int(score >= max_score - args.tol)}\t"
                            f"{len(sent_to_langs[sent])}\t{safe_tsv(sent)}\n"
                        )
        finally:
            if f_detail is not None:
                f_detail.close()

    summary = {
        "model_id": args.model_id,
        "model_path": str(model_path),
        "selected_dir": str(selected_dir),
        "common_ids": str(common_ids_path),
        "score_mode": args.score_mode,
        "boundary_token": boundary_token(tokenizer) if args.score_mode != "legacy" else None,
        "includes_initial_token": args.score_mode in {"bos", "bos_eos"},
        "includes_final_eos": args.score_mode == "bos_eos",
        "n_languages": len(languages),
        "n_ids": total,
        "accuracy_tie_ok": correct_tie_ok / total if total else None,
        "correct_tie_ok": correct_tie_ok,
        "strict_unique_top1_accuracy": strict_unique_top1 / total if total else None,
        "strict_unique_top1": strict_unique_top1,
        "top5_accuracy": top5 / total if total else None,
        "top5": top5,
        "mrr": mrr_sum / total if total else None,
        "mean_rank": rank_sum / total if total else None,
        "mean_unique_sentences_per_id": n_unique_sent_sum / total if total else None,
        "mean_own_sentence_group_size": own_group_size_sum / total if total else None,
        "mean_max_languages_count": max_group_size_sum / total if total else None,
        "mean_max_unique_sentences_count": max_sent_group_size_sum / total if total else None,
        "dimension_accuracy_tie_ok": {
            dim: count / total if total else None
            for dim, count in dimension_correct.items()
        },
        "predictions_path": str(predictions_path),
        "details_path": str(details_path) if args.write_details else None,
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()