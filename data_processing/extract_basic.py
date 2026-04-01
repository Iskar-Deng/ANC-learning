#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
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
    sid: int,
    sentence: str,
    reason: str,
    nominal_modifiers: Optional[List[JsonDict]] = None,
) -> JsonDict:
    return {
        "sid": sid,
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
    sid: int,
    sentence: str,
    construction: str,
    predicate: str,
    arguments: JsonDict,
    object_info: Optional[JsonDict] = None,
    complement: Optional[JsonDict] = None,
    nominal_modifiers: Optional[List[JsonDict]] = None,
) -> JsonDict:
    return {
        "sid": sid,
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
                "particle": extract_particle(pred),
            } if extract_particle(pred) is not None else None,
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
                "particle": extract_particle(root),
            } if extract_particle(root) is not None else None,
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
                "particle": extract_particle(root),
            } if extract_particle(root) is not None else None,
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


def extract_from_sentence(sent: Span, sid: int, max_depth: int = 2) -> JsonDict:
    sentence = sent.text.strip()
    nominal_modifiers = extract_nominal_modifiers(sent)

    if not sentence:
        return reject_record(sid, sentence, "empty_sentence", nominal_modifiers=nominal_modifiers)

    root = next((tok for tok in sent if tok.dep_ == "ROOT"), None)
    if root is None:
        return reject_record(sid, sentence, "no_root", nominal_modifiers=nominal_modifiers)

    if has_child_dep(root, {"nsubjpass", "auxpass"}):
        return reject_record(sid, sentence, "passive", nominal_modifiers=nominal_modifiers)

    subj = first_child_by_dep(root, {"nsubj"})
    attr = first_child_by_dep(root, {"attr"})
    acomp = first_child_by_dep(root, {"acomp"})

    if root.lemma_ == "be" and root.pos_ == "AUX":
        if acomp is not None:
            return reject_record(sid, sentence, "copula_adjective", nominal_modifiers=nominal_modifiers)

        if subj is not None and attr is not None and attr.pos_ in {"NOUN", "PROPN", "PRON"}:
            return keep_record(
                sid,
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

        return reject_record(sid, sentence, "bad_copula", nominal_modifiers=nominal_modifiers)

    if root.pos_ == "VERB":
        if has_multiple_object_candidates(root):
            return reject_record(sid, sentence, "multiple_objects", nominal_modifiers=nominal_modifiers)

        result = extract_clause(root, forced_subject=None, depth=0, max_depth=max_depth)
        if result is not None:
            return keep_record(
                sid,
                sentence,
                result["construction"],
                result["predicate"],
                result["arguments"],
                object_info=result.get("object_info"),
                complement=result.get("complement"),
                nominal_modifiers=nominal_modifiers,
            )

        if has_child_dep(root, {"xcomp", "ccomp"}):
            return reject_record(sid, sentence, "bad_clausal_complement", nominal_modifiers=nominal_modifiers)

        return reject_record(sid, sentence, "bad_simple_clause", nominal_modifiers=nominal_modifiers)

    return reject_record(sid, sentence, "unhandled", nominal_modifiers=nominal_modifiers)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input txt file")
    parser.add_argument("--output", required=True, help="Output jsonl file")
    parser.add_argument("--model", default="en_core_web_md", help="spaCy model name")
    parser.add_argument("--max-depth", type=int, default=2, help="Max recursive depth for clausal complement")
    parser.add_argument("--batch-size", type=int, default=1000, help="spaCy pipe batch size")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    nlp = load_nlp(args.model)

    records: List[JsonDict] = []
    total = 0
    kept = 0
    sid = 1

    lines = list(iter_nonempty_lines(input_path))

    for doc in tqdm(
        nlp.pipe(lines, batch_size=args.batch_size),
        total=len(lines),
        desc="Processing",
    ):
        assert isinstance(doc, Doc)
        for sent in doc.sents:
            rec = extract_from_sentence(sent, sid=sid, max_depth=args.max_depth)
            records.append(rec)
            total += 1
            if rec["status"] == "keep":
                kept += 1
            sid += 1

    write_jsonl(records, output_path)

    extraction_rate = kept / total if total > 0 else 0.0

    print(f"Total sentences: {total}")
    print(f"Extracted: {kept}")
    print(f"Rejected: {total - kept}")
    print(f"Extraction rate: {extraction_rate:.4f} ({extraction_rate * 100:.2f}%)")


if __name__ == "__main__":
    main()