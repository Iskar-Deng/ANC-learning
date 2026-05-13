#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def load_selected(path: Path) -> Dict[Any, str]:
    data: Dict[Any, str] = {}

    for row in iter_jsonl(path):
        row_id = row.get("id")
        sent = row.get("sent")

        if row_id is None:
            continue
        if not isinstance(sent, str) or not sent.strip():
            continue

        if row_id in data:
            raise ValueError(f"Duplicate id {row_id!r} in {path}")

        data[row_id] = sent

    return data


def load_common_ids(path: Path) -> List[Any]:
    ids: List[Any] = []

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


def parse_language_id(lang: str) -> Dict[str, str]:
    parts = lang.split("_")

    if len(parts) != 6:
        return {
            "language": lang,
            "num_id": "",
            "clause_wo": "",
            "np_wo": "",
            "alignment": "",
            "comp_system": "",
            "strategy": "",
        }

    num_id, clause_wo, np_wo, alignment, comp_system, strategy = parts

    return {
        "language": lang,
        "num_id": num_id,
        "clause_wo": clause_wo,
        "np_wo": np_wo,
        "alignment": alignment,
        "comp_system": comp_system,
        "strategy": strategy,
    }


def get_device(device_arg: str) -> torch.device:
    if device_arg == "cuda" and not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device(device_arg)


def score_sentences(
    model,
    tokenizer,
    sentences: List[str],
    device: torch.device,
    batch_size: int,
    add_bos: bool = False,
) -> List[float]:
    """
    Return length-normalized causal LM log probability for each sentence.

    Score = average log p(token_t | previous tokens), excluding padding.
    If add_bos=True and tokenizer has bos_token, prepend it to each sentence.
    """
    if not sentences:
        return []

    scores: List[float] = []
    model.eval()

    with torch.no_grad():
        for start in range(0, len(sentences), batch_size):
            batch = sentences[start : start + batch_size]

            if add_bos and tokenizer.bos_token is not None:
                batch = [tokenizer.bos_token + s for s in batch]

            enc = tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=False,
            )

            input_ids = enc["input_ids"].to(device)
            attention_mask = enc["attention_mask"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits

            # Predict token t from positions t-1.
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
            seq_scores = token_log_probs.sum(dim=1) / lengths.clamp(min=1)

            scores.extend(seq_scores.detach().cpu().tolist())

    return scores


def safe_tsv(text: Any) -> str:
    return str(text).replace("\t", " ").replace("\n", " ").replace("\r", " ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path to HF model checkpoint")
    ap.add_argument("--model-id", required=True, help="Grammar id for this model, e.g. 02_sov_gn_ac_b_ep")
    ap.add_argument("--selected-dir", required=True, help="Directory with 96 selected JSONL files")
    ap.add_argument("--common-ids", required=True, help="File with one common id per line")
    ap.add_argument("--out-dir", required=True)

    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--max-ids", type=int, default=None)
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu", "mps"])
    ap.add_argument("--tol", type=float, default=1e-8)
    ap.add_argument("--add-bos", action="store_true")

    ap.add_argument(
        "--write-details",
        action="store_true",
        help="Write 96 candidate rows per id. This can be very large.",
    )

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
        raise ValueError(
            f"--model-id {args.model_id!r} not found among selected languages. "
            f"Found examples: {languages[:5]}"
        )

    print(f"Loading selected outputs from {selected_dir}...")
    selected_by_lang: Dict[str, Dict[Any, str]] = {}

    for path in tqdm(selected_files, desc="selected files"):
        selected_by_lang[path.stem] = load_selected(path)

    common_ids = load_common_ids(common_ids_path)
    if args.max_ids is not None:
        common_ids = common_ids[: args.max_ids]

    print(f"Selected languages: {len(languages)}")
    print(f"Common ids to score: {len(common_ids)}")
    print(f"Model id: {args.model_id}")
    print(f"Model path: {model_path}")

    device = get_device(args.device)
    print(f"Device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if tokenizer.pad_token is None:
        if tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
        else:
            tokenizer.add_special_tokens({"pad_token": "<|pad|>"})

    model = AutoModelForCausalLM.from_pretrained(model_path)

    # If we added a new pad token, resize embeddings.
    if len(tokenizer) != model.get_input_embeddings().weight.shape[0]:
        model.resize_token_embeddings(len(tokenizer))

    model.to(device)
    model.eval()

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
                # lang -> sent
                lang_to_sent: Dict[str, str] = {
                    lang: selected_by_lang[lang][row_id]
                    for lang in languages
                }

                # sent -> languages producing it
                sent_to_langs: Dict[str, List[str]] = defaultdict(list)
                for lang, sent in lang_to_sent.items():
                    sent_to_langs[sent].append(lang)

                unique_sents = list(sent_to_langs.keys())

                unique_scores = score_sentences(
                    model=model,
                    tokenizer=tokenizer,
                    sentences=unique_sents,
                    device=device,
                    batch_size=args.batch_size,
                    add_bos=args.add_bos,
                )

                sent_to_score = {
                    sent: score
                    for sent, score in zip(unique_sents, unique_scores)
                }

                lang_to_score = {
                    lang: sent_to_score[sent]
                    for lang, sent in lang_to_sent.items()
                }

                own_sent = lang_to_sent[args.model_id]
                own_score = sent_to_score[own_sent]
                max_score = max(sent_to_score.values())

                best_sents = [
                    sent
                    for sent, score in sent_to_score.items()
                    if score >= max_score - args.tol
                ]

                max_langs: List[str] = []
                for sent in best_sents:
                    max_langs.extend(sent_to_langs[sent])
                max_langs = sorted(max_langs)

                # Rank of own grammar candidate:
                # 1 + number of candidate languages whose score is strictly better.
                own_rank = 1 + sum(
                    score > own_score + args.tol
                    for lang, score in lang_to_score.items()
                )

                is_correct_tie_ok = own_score >= max_score - args.tol

                # Strict unique top-1 means own grammar is the only language at max.
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

                best_sents_safe = " ||| ".join(safe_tsv(s) for s in best_sents)
                max_langs_safe = ",".join(max_langs)

                f_pred.write(
                    f"{args.model_id}\t{row_id}\t{args.model_id}\t"
                    f"{own_score:.8f}\t{max_score:.8f}\t{own_rank}\t"
                    f"{int(is_correct_tie_ok)}\t{int(is_strict_unique_top1)}\t"
                    f"{int(is_top5)}\t{mrr:.8f}\t"
                    f"{len(languages)}\t{n_unique_sent}\t"
                    f"{own_group_size}\t{max_languages_count}\t{max_unique_sentences_count}\t"
                    f"{max_langs_safe}\t{safe_tsv(own_sent)}\t{best_sents_safe}\n"
                )

                if f_detail is not None:
                    for lang in languages:
                        sent = lang_to_sent[lang]
                        score = lang_to_score[lang]
                        rank = 1 + sum(
                            other_score > score + args.tol
                            for other_score in lang_to_score.values()
                        )
                        is_own = lang == args.model_id
                        is_max = score >= max_score - args.tol
                        group_size = len(sent_to_langs[sent])

                        f_detail.write(
                            f"{args.model_id}\t{row_id}\t{lang}\t"
                            f"{score:.8f}\t{rank}\t{int(is_own)}\t"
                            f"{int(is_max)}\t{group_size}\t{safe_tsv(sent)}\n"
                        )
        finally:
            if f_detail is not None:
                f_detail.close()

    summary = {
        "model_id": args.model_id,
        "model_path": str(model_path),
        "selected_dir": str(selected_dir),
        "common_ids": str(common_ids_path),
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