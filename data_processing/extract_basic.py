#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tqdm import tqdm
import spacy
from spacy.language import Language
from spacy.tokens import Doc, Span, Token


JsonDict = Dict[str, Any]


def first_child_by_dep(token: Token, deps: Sequence[str]) -> Optional[Token]:
    for child in token.children:
        if child.dep_ in deps:
            return child
    return None


def children_by_dep(token: Token, deps: Sequence[str]) -> List[Token]:
    return [child for child in token.children if child.dep_ in deps]


def has_child_dep(token: Token, deps: Sequence[str]) -> bool:
    return any(child.dep_ in deps for child in token.children)


def extract_head_lemma(token: Optional[Token]) -> Optional[str]:
    if token is None:
        return None
    return token.lemma_


def subtree_text(token: Optional[Token]) -> Optional[str]:
    if token is None:
        return None
    left = min(t.i for t in token.subtree)
    right = max(t.i for t in token.subtree)
    return token.doc[left : right + 1].text


def extract_poss_modifiers(noun: Token) -> List[JsonDict]:
    results: List[JsonDict] = []
    for child in noun.children:
        if child.dep_ == "poss":
            results.append(
                {
                    "relation": "poss",
                    "text": subtree_text(child),
                    "head_text": child.text,
                    "head_lemma": child.lemma_,
                    "dep": child.dep_,
                }
            )
    return results


def extract_pp_modifiers(noun: Token, prep_lemma: str) -> List[JsonDict]:
    results: List[JsonDict] = []

    for child in noun.children:
        if child.dep_ == "prep" and child.lemma_.lower() == prep_lemma:
            pobjs = [gc for gc in child.children if gc.dep_ == "pobj"]

            if pobjs:
                for pobj in pobjs:
                    results.append(
                        {
                            "relation": f"{prep_lemma}_pp",
                            "text": subtree_text(child),
                            "prep_text": child.text,
                            "prep_lemma": child.lemma_,
                            "object_text": subtree_text(pobj),
                            "object_head_text": pobj.text,
                            "object_head_lemma": pobj.lemma_,
                        }
                    )
            else:
                results.append(
                    {
                        "relation": f"{prep_lemma}_pp",
                        "text": subtree_text(child),
                        "prep_text": child.text,
                        "prep_lemma": child.lemma_,
                        "object_text": None,
                        "object_head_text": None,
                        "object_head_lemma": None,
                    }
                )

    return results


def extract_nominal_modifiers(sent: Span) -> List[JsonDict]:
    records: List[JsonDict] = []

    for tok in sent:
        if tok.pos_ not in {"NOUN", "PROPN"}:
            continue

        poss_mods = extract_poss_modifiers(tok)
        of_mods = extract_pp_modifiers(tok, "of")
        by_mods = extract_pp_modifiers(tok, "by")

        records.append(
            {
                "noun_text": tok.text,
                "noun_lemma": tok.lemma_,
                "noun_dep": tok.dep_,
                "noun_head": tok.head.text,
                "modifiers": {
                    "poss": poss_mods,
                    "of": of_mods,
                    "by": by_mods,
                },
            }
        )

    return records


def reject_record(
    id: int,
    sentence: str,
    reason: str,
    nominal_modifiers: Optional[List[JsonDict]] = None,
) -> JsonDict:
    return {
        "id": id,
        "sentence": sentence,
        "status": "reject",
        "construction": None,
        "predicate": None,
        "arguments": None,
        "object_info": None,
        "complement": None,
        "nominal_modifiers": nominal_modifiers if nominal_modifiers is not None else [],
        "reject_reason": reason,
    }


def keep_record(
    id: int,
    sentence: str,
    construction: str,
    predicate: str,
    arguments: JsonDict,
    object_info: Optional[JsonDict] = None,
    complement: Optional[JsonDict] = None,
    nominal_modifiers: Optional[List[JsonDict]] = None,
) -> JsonDict:
    return {
        "id": id,
        "sentence": sentence,
        "status": "keep",
        "construction": construction,
        "predicate": predicate,
        "arguments": arguments,
        "object_info": object_info,
        "complement": complement,
        "nominal_modifiers": nominal_modifiers if nominal_modifiers is not None else [],
        "reject_reason": None,
    }


def extract_particle(pred: Token) -> Optional[JsonDict]:
    prt = first_child_by_dep(pred, {"prt"})
    if prt is None:
        return None
    return {
        "particle_text": prt.text,
        "particle_lemma": prt.lemma_,
        "particle_dep": prt.dep_,
    }


def collect_object_candidates(pred: Token) -> List[JsonDict]:
    candidates: List[JsonDict] = []

    direct_obj = first_child_by_dep(pred, {"dobj", "obj"})
    if direct_obj is not None:
        candidates.append(
            {
                "object_type": "direct_obj",
                "token": direct_obj,
                "adposition": None,
                "adposition_dep": None,
            }
        )

    for child in pred.children:
        # Bare dative NP, e.g. "Mary gave me a book."
        if child.dep_ == "dative" and child.pos_ != "ADP":
            candidates.append(
                {
                    "object_type": "indirect_obj",
                    "token": child,
                    "adposition": None,
                    "adposition_dep": "dative",
                }
            )
            continue

        # Prepositional/dative object, e.g. "Mary gave a book to me."
        if child.dep_ in {"prep", "dative"}:
            pobj = first_child_by_dep(child, {"pobj"})
            if pobj is not None:
                candidates.append(
                    {
                        "object_type": "pp_obj",
                        "token": pobj,
                        "adposition": child.lemma_.lower(),
                        "adposition_dep": child.dep_,
                    }
                )

    return candidates


def build_object_info(pred: Token, obj_info: JsonDict) -> JsonDict:
    obj_tok = obj_info["token"]
    particle_info = extract_particle(pred)

    return {
        "object_type": obj_info["object_type"],
        "adposition": obj_info["adposition"],
        "adposition_dep": obj_info["adposition_dep"],
        "object_form": extract_head_lemma(obj_tok),
        "object_text": subtree_text(obj_tok),
        "particle": particle_info,
    }


def extract_simple_clause(pred: Optional[Token], forced_subject: Optional[Token] = None) -> Optional[JsonDict]:
    if pred is None:
        return None

    if has_child_dep(pred, {"nsubjpass", "auxpass"}):
        return None

    if has_child_dep(pred, {"xcomp", "ccomp"}):
        return None

    if pred.pos_ != "VERB":
        return None

    subj = forced_subject if forced_subject is not None else first_child_by_dep(pred, {"nsubj"})
    if subj is None:
        return None

    obj_candidates = collect_object_candidates(pred)

    if len(obj_candidates) == 0:
        particle_info = extract_particle(pred)
        return {
            "construction": "iv",
            "predicate": pred.lemma_,
            "arguments": {
                "S": extract_head_lemma(subj),
            },
            "object_info": {
                "object_type": None,
                "adposition": None,
                "adposition_dep": None,
                "object_form": None,
                "object_text": None,
                "particle": particle_info,
            } if particle_info is not None else None,
            "complement": None,
        }

    if len(obj_candidates) == 1:
        obj_info = obj_candidates[0]
        obj_tok = obj_info["token"]

        return {
            "construction": "tv",
            "predicate": pred.lemma_,
            "arguments": {
                "A": extract_head_lemma(subj),
                "P": extract_head_lemma(obj_tok),
            },
            "object_info": build_object_info(pred, obj_info),
            "complement": None,
        }

    return None


def extract_cv(
    root: Optional[Token],
    forced_subject: Optional[Token] = None,
    depth: int = 0,
    max_depth: int = 2,
) -> Optional[JsonDict]:
    if root is None or root.pos_ != "VERB":
        return None

    if depth >= max_depth:
        return None

    if has_child_dep(root, {"nsubjpass", "auxpass"}):
        return None

    matrix_subj = forced_subject if forced_subject is not None else first_child_by_dep(root, {"nsubj"})
    if matrix_subj is None:
        return None

    comps = children_by_dep(root, {"xcomp", "ccomp"})
    if len(comps) != 1:
        return None

    comp = comps[0]
    comp_type = comp.dep_

    if comp_type == "xcomp":
        embedded = extract_clause(
            comp,
            forced_subject=matrix_subj,
            depth=depth + 1,
            max_depth=max_depth,
        )
        if embedded is None:
            return None

        particle_info = extract_particle(root)
        return {
            "construction": "cv",
            "predicate": root.lemma_,
            "arguments": {
                "A": extract_head_lemma(matrix_subj),
            },
            "object_info": {
                "object_type": None,
                "adposition": None,
                "adposition_dep": None,
                "object_form": None,
                "object_text": None,
                "particle": particle_info,
            } if particle_info is not None else None,
            "complement": {
                "comp_type": "xcomp",
                "construction": embedded["construction"],
                "predicate": embedded["predicate"],
                "arguments": embedded["arguments"],
                "object_info": embedded.get("object_info"),
                "complement": embedded.get("complement"),
            },
        }

    if comp_type == "ccomp":
        embedded = extract_clause(
            comp,
            forced_subject=None,
            depth=depth + 1,
            max_depth=max_depth,
        )
        if embedded is None:
            return None

        particle_info = extract_particle(root)
        return {
            "construction": "cv",
            "predicate": root.lemma_,
            "arguments": {
                "A": extract_head_lemma(matrix_subj),
            },
            "object_info": {
                "object_type": None,
                "adposition": None,
                "adposition_dep": None,
                "object_form": None,
                "object_text": None,
                "particle": particle_info,
            } if particle_info is not None else None,
            "complement": {
                "comp_type": "ccomp",
                "construction": embedded["construction"],
                "predicate": embedded["predicate"],
                "arguments": embedded["arguments"],
                "object_info": embedded.get("object_info"),
                "complement": embedded.get("complement"),
            },
        }

    return None


def extract_clause(
    pred: Optional[Token],
    forced_subject: Optional[Token] = None,
    depth: int = 0,
    max_depth: int = 5,
) -> Optional[JsonDict]:
    cv = extract_cv(pred, forced_subject=forced_subject, depth=depth, max_depth=max_depth)
    if cv is not None:
        return cv

    simple = extract_simple_clause(pred, forced_subject=forced_subject)
    if simple is not None:
        return simple

    return None


def has_multiple_object_candidates(root: Token) -> bool:
    return len(collect_object_candidates(root)) > 1


def extract_from_sentence(sent: Span, id: int, max_depth: int = 2) -> JsonDict:
    sentence = sent.text.strip()
    nominal_modifiers = extract_nominal_modifiers(sent)

    if not sentence:
        return reject_record(id, sentence, "empty_sentence", nominal_modifiers=nominal_modifiers)

    root = next((tok for tok in sent if tok.dep_ == "ROOT"), None)
    if root is None:
        return reject_record(id, sentence, "no_root", nominal_modifiers=nominal_modifiers)

    if has_child_dep(root, {"nsubjpass", "auxpass"}):
        return reject_record(id, sentence, "passive", nominal_modifiers=nominal_modifiers)

    subj = first_child_by_dep(root, {"nsubj"})
    attr = first_child_by_dep(root, {"attr"})
    acomp = first_child_by_dep(root, {"acomp"})

    if root.lemma_ == "be" and root.pos_ == "AUX":
        if acomp is not None:
            return reject_record(id, sentence, "copula_adjective", nominal_modifiers=nominal_modifiers)

        if subj is not None and attr is not None and attr.pos_ in {"NOUN", "PROPN", "PRON"}:
            return keep_record(
                id,
                sentence,
                "cop_n",
                "be",
                {
                    "A": extract_head_lemma(subj),
                    "PRED": extract_head_lemma(attr),
                },
                object_info=None,
                nominal_modifiers=nominal_modifiers,
            )

        return reject_record(id, sentence, "bad_copula", nominal_modifiers=nominal_modifiers)

    if root.pos_ == "VERB":
        if has_multiple_object_candidates(root):
            return reject_record(id, sentence, "multiple_objects", nominal_modifiers=nominal_modifiers)

        result = extract_clause(root, forced_subject=None, depth=0, max_depth=max_depth)
        if result is not None:
            return keep_record(
                id,
                sentence,
                result["construction"],
                result["predicate"],
                result["arguments"],
                object_info=result.get("object_info"),
                complement=result.get("complement"),
                nominal_modifiers=nominal_modifiers,
            )

        if has_child_dep(root, {"xcomp", "ccomp"}):
            return reject_record(id, sentence, "bad_clausal_complement", nominal_modifiers=nominal_modifiers)

        return reject_record(id, sentence, "bad_simple_clause", nominal_modifiers=nominal_modifiers)

    return reject_record(id, sentence, "unhandled", nominal_modifiers=nominal_modifiers)


def iter_nonempty_lines(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8") as infile:
        for line in infile:
            stripped = line.strip()
            if stripped:
                yield stripped


def load_nlp(model_name: str) -> Language:
    return spacy.load(model_name, disable=["ner"])


def write_jsonl(records: List[JsonDict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as outfile:
        for rec in records:
            outfile.write(json.dumps(rec, ensure_ascii=False) + "\n")


def get_complement_depth(comp: Optional[JsonDict]) -> int:
    if comp is None:
        return 0
    return 1 + get_complement_depth(comp.get("complement"))


def collect_stats(records: List[JsonDict], top_n_predicates: int = 20) -> JsonDict:
    total = len(records)
    kept_records = [r for r in records if r["status"] == "keep"]
    rejected_records = [r for r in records if r["status"] == "reject"]

    kept = len(kept_records)
    rejected = len(rejected_records)

    construction_counts = Counter(
        r["construction"] for r in kept_records if r["construction"] is not None
    )
    reject_counts = Counter(
        r["reject_reason"] for r in rejected_records if r["reject_reason"] is not None
    )

    object_type_counts = Counter()
    comp_type_counts = Counter()
    comp_depth_counts = Counter()
    predicate_counts = Counter()
    particle_counts = Counter()

    nominal_modifier_totals = Counter()
    sentences_with_modifier = Counter()
    noun_records_total = 0

    for rec in kept_records:
        predicate = rec.get("predicate")
        if predicate:
            predicate_counts[predicate] += 1

        obj = rec.get("object_info")
        if obj:
            obj_type = obj.get("object_type")
            if obj_type:
                object_type_counts[obj_type] += 1
            particle = obj.get("particle")
            if particle:
                particle_lemma = particle.get("particle_lemma")
                if particle_lemma:
                    particle_counts[particle_lemma] += 1

        comp = rec.get("complement")
        if comp:
            comp_type = comp.get("comp_type")
            if comp_type:
                comp_type_counts[comp_type] += 1
            comp_depth_counts[get_complement_depth(comp)] += 1

        current = comp
        while current:
            obj2 = current.get("object_info")
            if obj2 and obj2.get("particle"):
                particle_lemma = obj2["particle"].get("particle_lemma")
                if particle_lemma:
                    particle_counts[particle_lemma] += 1
            current = current.get("complement")

    for rec in records:
        nm_list = rec.get("nominal_modifiers", [])
        noun_records_total += len(nm_list)

        has_poss = False
        has_of = False
        has_by = False

        for noun_rec in nm_list:
            mods = noun_rec.get("modifiers", {})
            poss_n = len(mods.get("poss", []))
            of_n = len(mods.get("of", []))
            by_n = len(mods.get("by", []))

            nominal_modifier_totals["poss"] += poss_n
            nominal_modifier_totals["of"] += of_n
            nominal_modifier_totals["by"] += by_n

            if poss_n > 0:
                has_poss = True
            if of_n > 0:
                has_of = True
            if by_n > 0:
                has_by = True

        if has_poss:
            sentences_with_modifier["poss"] += 1
        if has_of:
            sentences_with_modifier["of"] += 1
        if has_by:
            sentences_with_modifier["by"] += 1
        if has_poss or has_of or has_by:
            sentences_with_modifier["any"] += 1

    def pct(n: int, d: int) -> float:
        return (n / d * 100.0) if d > 0 else 0.0

    top_predicates = predicate_counts.most_common(top_n_predicates)
    top_particles = particle_counts.most_common(top_n_predicates)

    return {
        "total_sentences": total,
        "kept": kept,
        "rejected": rejected,
        "kept_rate_percent": pct(kept, total),
        "rejected_rate_percent": pct(rejected, total),

        "construction_counts": dict(construction_counts),
        "construction_percent_of_kept": {
            k: pct(v, kept) for k, v in construction_counts.items()
        },
        "construction_percent_of_total": {
            k: pct(v, total) for k, v in construction_counts.items()
        },

        "copula_count": construction_counts.get("cop_n", 0),
        "copula_percent_of_kept": pct(construction_counts.get("cop_n", 0), kept),
        "copula_percent_of_total": pct(construction_counts.get("cop_n", 0), total),

        "reject_reason_counts": dict(reject_counts),
        "reject_reason_percent_of_rejected": {
            k: pct(v, rejected) for k, v in reject_counts.items()
        },
        "reject_reason_percent_of_total": {
            k: pct(v, total) for k, v in reject_counts.items()
        },

        "object_type_counts": dict(object_type_counts),
        "object_type_percent_of_kept": {
            k: pct(v, kept) for k, v in object_type_counts.items()
        },

        "complement_type_counts": dict(comp_type_counts),
        "complement_depth_counts": dict(comp_depth_counts),

        "predicate_top_n": top_predicates,
        "particle_top_n": top_particles,
        "sentences_with_particle": sum(particle_counts.values()),
        "particle_token_total": sum(particle_counts.values()),

        "nominal_modifier_totals": dict(nominal_modifier_totals),
        "sentences_with_modifier_counts": dict(sentences_with_modifier),
        "sentences_with_modifier_percent_of_total": {
            k: pct(v, total) for k, v in sentences_with_modifier.items()
        },
        "noun_records_total": noun_records_total,
        "avg_noun_records_per_sentence": (noun_records_total / total) if total > 0 else 0.0,
    }


def print_stats(stats: JsonDict) -> None:
    print("\n=== Overall ===")
    print(f"Total sentences: {stats['total_sentences']}")
    print(f"Kept: {stats['kept']} ({stats['kept_rate_percent']:.2f}%)")
    print(f"Rejected: {stats['rejected']} ({stats['rejected_rate_percent']:.2f}%)")

    print("\n=== Constructions ===")
    for k, v in sorted(stats["construction_counts"].items()):
        pct_kept = stats["construction_percent_of_kept"].get(k, 0.0)
        pct_total = stats["construction_percent_of_total"].get(k, 0.0)
        print(f"{k}: {v} ({pct_kept:.2f}% of kept, {pct_total:.2f}% of total)")

    print("\n=== Copula ===")
    print(
        f"cop_n: {stats['copula_count']} "
        f"({stats['copula_percent_of_kept']:.2f}% of kept, "
        f"{stats['copula_percent_of_total']:.2f}% of total)"
    )

    print("\n=== Reject reasons ===")
    for k, v in sorted(stats["reject_reason_counts"].items()):
        pct_rej = stats["reject_reason_percent_of_rejected"].get(k, 0.0)
        pct_total = stats["reject_reason_percent_of_total"].get(k, 0.0)
        print(f"{k}: {v} ({pct_rej:.2f}% of rejected, {pct_total:.2f}% of total)")

    print("\n=== Object types ===")
    for k, v in sorted(stats["object_type_counts"].items()):
        pct_kept = stats["object_type_percent_of_kept"].get(k, 0.0)
        print(f"{k}: {v} ({pct_kept:.2f}% of kept)")

    print("\n=== Complement types ===")
    for k, v in sorted(stats["complement_type_counts"].items()):
        print(f"{k}: {v}")

    print("\n=== Complement depth ===")
    for k, v in sorted(stats["complement_depth_counts"].items()):
        print(f"depth_{k}: {v}")

    print("\n=== Top predicates ===")
    for pred, count in stats["predicate_top_n"]:
        print(f"{pred}: {count}")

    print("\n=== Top particles ===")
    for particle, count in stats["particle_top_n"]:
        print(f"{particle}: {count}")

    print("\n=== Nominal modifiers (totals) ===")
    for k, v in sorted(stats["nominal_modifier_totals"].items()):
        print(f"{k}: {v}")

    print("\n=== Sentences with nominal modifiers ===")
    for k, v in sorted(stats["sentences_with_modifier_counts"].items()):
        pct_total = stats["sentences_with_modifier_percent_of_total"].get(k, 0.0)
        print(f"{k}: {v} ({pct_total:.2f}% of total)")

    print("\n=== Noun record density ===")
    print(f"noun_records_total: {stats['noun_records_total']}")
    print(f"avg_noun_records_per_sentence: {stats['avg_noun_records_per_sentence']:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input txt file")
    parser.add_argument("--output", required=True, help="Output jsonl file")
    parser.add_argument("--model", default="en_core_web_md", help="spaCy model name")
    parser.add_argument("--max-depth", type=int, default=2, help="Max recursive depth for clausal complement")
    parser.add_argument("--batch-size", type=int, default=1000, help="spaCy pipe batch size")
    parser.add_argument("--stats-output", help="Optional path to write corpus statistics as json")
    parser.add_argument("--top-n-predicates", type=int, default=20, help="Top N predicates/particles to report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    nlp = load_nlp(args.model)

    records: List[JsonDict] = []
    id = 1

    lines = list(iter_nonempty_lines(input_path))

    for doc in tqdm(
        nlp.pipe(lines, batch_size=args.batch_size),
        total=len(lines),
        desc="Processing",
    ):
        assert isinstance(doc, Doc)
        for sent in doc.sents:
            rec = extract_from_sentence(sent, id=id, max_depth=args.max_depth)
            records.append(rec)
            id += 1

    write_jsonl(records, output_path)

    stats = collect_stats(records, top_n_predicates=args.top_n_predicates)
    print_stats(stats)

    if args.stats_output:
        stats_path = Path(args.stats_output)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        with stats_path.open("w", encoding="utf-8") as outfile:
            json.dump(stats, outfile, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()