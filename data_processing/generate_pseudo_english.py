#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):  # type: ignore
        return iterable


JsonDict = Dict[str, Any]


class PseudoEnglishGenerator:
    def __init__(self, similarity_threshold: float = 0.65) -> None:
        self.noun_lemmas: Set[str] = set()

        # 按 construction 区分动词库存
        self.iv_verbs: Set[str] = set()
        self.tv_verbs: Set[str] = set()
        self.cv_verbs: Set[str] = set()
        self.cop_n_verbs: Set[str] = set()

        # 仍然记录哪些 noun 被识别成 ANC source，但不再从 noun lexicon 里移除
        self.anc_source_nouns: Set[str] = set()

        self.similarity_threshold = similarity_threshold

    def process_records(self, records: List[JsonDict]) -> Tuple[List[JsonDict], JsonDict]:
        self._collect_base_lexicon(records)

        outputs: List[JsonDict] = []
        new_sid = 1

        for rec in tqdm(records, desc="Realizing pseudo-English"):
            pseudo = self._realize_record(rec)
            if pseudo is None:
                continue

            outputs.append(
                {
                    "id": new_sid,
                    "sentence": rec.get("sentence"),
                    "pseudo_english": pseudo,
                }
            )
            new_sid += 1

        lexicon = self._build_lexicon()
        return outputs, lexicon

    def _collect_base_lexicon(self, records: List[JsonDict]) -> None:
        for rec in tqdm(records, desc="Collecting base lexicon"):
            self._collect_from_record(rec, top_level=True)

    def _collect_from_record(self, rec: JsonDict, top_level: bool = False) -> None:
        """
        top_level=True:
            只收 status == keep 的顶层记录
        top_level=False:
            用于递归补语，不要求显式带 status == keep
        """
        if top_level and rec.get("status") != "keep":
            return

        construction = rec.get("construction")
        predicate = rec.get("predicate")
        object_info = rec.get("object_info")

        if construction in {"iv", "tv", "cv", "cop_n"} and predicate:
            verb_form = self._verb_surface(predicate, object_info)
            self._add_verb_by_construction(construction, verb_form)

        for arg in (rec.get("arguments") or {}).values():
            if isinstance(arg, str):
                self.noun_lemmas.add(arg)

        nominal_modifiers = rec.get("nominal_modifiers") or []
        for nm in nominal_modifiers:
            noun_lemma = nm.get("noun_lemma")
            if noun_lemma:
                self.noun_lemmas.add(noun_lemma)

            modifiers = nm.get("modifiers") or {}

            for poss in (modifiers.get("poss") or []):
                head_lemma = poss.get("head_lemma")
                if isinstance(head_lemma, str) and head_lemma:
                    self.noun_lemmas.add(head_lemma)

            for of_mod in (modifiers.get("of") or []):
                obj_lemma = of_mod.get("object_head_lemma")
                if isinstance(obj_lemma, str) and obj_lemma:
                    self.noun_lemmas.add(obj_lemma)

            for by_mod in (modifiers.get("by") or []):
                obj_lemma = by_mod.get("object_head_lemma")
                if isinstance(obj_lemma, str) and obj_lemma:
                    self.noun_lemmas.add(obj_lemma)

        comp = rec.get("complement")
        if isinstance(comp, dict):
            self._collect_from_record(comp, top_level=False)

    def _add_verb_by_construction(self, construction: str, verb_form: str) -> None:
        if construction == "iv":
            self.iv_verbs.add(verb_form)
        elif construction == "tv":
            self.tv_verbs.add(verb_form)
        elif construction == "cv":
            self.cv_verbs.add(verb_form)
        elif construction == "cop_n":
            self.cop_n_verbs.add(verb_form)

    def _realize_record(self, rec: JsonDict) -> Optional[str]:
        if rec.get("status") != "keep":
            return None
        return self._realize_clause(rec)

    def _realize_clause(self, rec: JsonDict) -> Optional[str]:
        construction = rec.get("construction")

        if construction == "iv":
            return self._realize_iv(rec)
        if construction == "tv":
            return self._realize_tv(rec)
        if construction == "cv":
            return self._realize_cv(rec)
        if construction == "cop_n":
            return self._realize_cop_n(rec)

        return None

    def _realize_iv(self, rec: JsonDict) -> str:
        args = rec.get("arguments") or {}
        subj = args.get("S")
        pred = rec.get("predicate")

        if not subj or not pred:
            return "[BAD_IV]"

        return f"{subj} {self._verb_surface(pred, rec.get('object_info'))}s"

    def _realize_tv(self, rec: JsonDict) -> str:
        args = rec.get("arguments") or {}
        a = args.get("A")
        p = args.get("P")

        if not a or not p or not rec.get("predicate"):
            return "[BAD_TV]"

        matrix_verb = self._verb_surface(rec["predicate"], rec.get("object_info")) + "s"

        anc = self._extract_anc_info(rec)
        if anc is not None:
            parts: List[str] = []
            if anc["agent"]:
                parts.append(f"{anc['agent']}gs")
            parts.append(f"{anc['verb']}tion")
            if anc["patient"]:
                parts.append(f"{anc['patient']}ob")
            return f"{' '.join(parts)} {matrix_verb} {p}"

        ordinary_np_subj = self._realize_ordinary_noun_with_gen(a, rec)
        return f"{ordinary_np_subj} {matrix_verb} {p}"

    def _realize_cv(self, rec: JsonDict) -> str:
        args = rec.get("arguments") or {}
        a = args.get("A")
        pred = rec.get("predicate")
        comp = rec.get("complement")

        if not a or not pred or not isinstance(comp, dict):
            return "[BAD_CV]"

        embedded = self._realize_clause(comp)
        if embedded is None:
            return "[BAD_CV]"

        return f"{a} {self._verb_surface(pred, rec.get('object_info'))}s that {embedded}"

    def _realize_cop_n(self, rec: JsonDict) -> str:
        args = rec.get("arguments") or {}
        a = args.get("A")
        pred_nom = args.get("PRED")
        pred = rec.get("predicate")

        if not a or not pred_nom or not pred:
            return "[BAD_COP_N]"

        subj = self._realize_ordinary_noun_with_gen(a, rec)
        verb = self._verb_surface(pred, rec.get("object_info")) + "s"
        return f"{subj} {verb} {pred_nom}"

    def _realize_ordinary_noun_with_gen(self, noun_lemma: str, rec: JsonDict) -> str:
        nominal_modifiers = rec.get("nominal_modifiers") or []
        for nm in nominal_modifiers:
            if nm.get("noun_lemma") != noun_lemma:
                continue

            modifiers = nm.get("modifiers") or {}
            poss_mods = modifiers.get("poss") or []
            if poss_mods:
                possessor = poss_mods[0].get("head_lemma") or poss_mods[0].get("head_text")
                if possessor:
                    return f"{possessor}gs {noun_lemma}"

        return noun_lemma

    def _extract_anc_info(self, rec: JsonDict) -> Optional[Dict[str, Optional[str]]]:
        args = rec.get("arguments") or {}
        a = args.get("A")
        if not isinstance(a, str):
            return None

        nominal_modifiers = rec.get("nominal_modifiers") or []
        target_nm = None
        for nm in nominal_modifiers:
            if nm.get("noun_lemma") == a:
                target_nm = nm
                break

        if target_nm is None:
            return None

        modifiers = target_nm.get("modifiers") or {}
        poss_mods = modifiers.get("poss") or []
        of_mods = modifiers.get("of") or []
        by_mods = modifiers.get("by") or []

        if not (poss_mods or of_mods or by_mods):
            return None

        base_verb = self._find_base_verb(
            a,
            expected_constructions=("tv", "iv", "cv"),
        )
        if not base_verb:
            return None

        self.anc_source_nouns.add(a)

        agent = None
        patient = None

        if poss_mods:
            agent = poss_mods[0].get("head_lemma") or poss_mods[0].get("head_text")
        elif by_mods:
            agent = by_mods[0].get("object_head_lemma") or by_mods[0].get("object_head_text")

        if of_mods:
            patient = of_mods[0].get("object_head_lemma") or of_mods[0].get("object_head_text")

        return {"verb": base_verb, "agent": agent, "patient": patient}

    def _verb_surface(self, pred: str, obj: Optional[JsonDict]) -> str:
        if obj and obj.get("object_type") == "pp_obj":
            prep = obj.get("adposition")
            if prep:
                return f"{pred}_{prep}"

        if obj and obj.get("particle"):
            particle = obj["particle"].get("particle_lemma")
            if particle:
                return f"{pred}_{particle}"

        return pred

    def _get_verb_inventory(self, constructions: Tuple[str, ...]) -> Set[str]:
        inventory: Set[str] = set()
        for c in constructions:
            if c == "iv":
                inventory.update(self.iv_verbs)
            elif c == "tv":
                inventory.update(self.tv_verbs)
            elif c == "cv":
                inventory.update(self.cv_verbs)
            elif c == "cop_n":
                inventory.update(self.cop_n_verbs)
        return inventory

    def _common_prefix_len(self, a: str, b: str) -> int:
        limit = min(len(a), len(b))
        i = 0
        while i < limit and a[i] == b[i]:
            i += 1
        return i

    def _prefix_match_score(self, noun: str, verb: str) -> float:
        if not noun:
            return 0.0
        prefix_len = self._common_prefix_len(noun, verb)
        return prefix_len / len(noun)

    def _find_base_verb(
        self,
        noun: str,
        expected_constructions: Tuple[str, ...] = ("tv", "iv", "cv", "cop_n"),
    ) -> Optional[str]:
        noun_lower = noun.lower()
        candidate_verbs = self._get_verb_inventory(expected_constructions)

        if noun_lower in candidate_verbs:
            return noun_lower

        best_match: Optional[str] = None
        best_score = 0.0

        for verb in candidate_verbs:
            score = self._prefix_match_score(noun_lower, verb)
            if score > best_score:
                best_score = score
                best_match = verb

        if best_match is not None and best_score >= self.similarity_threshold:
            return best_match

        return None

    def _build_lexicon(self) -> JsonDict:
        return {
            "nouns": sorted(self.noun_lemmas),
            "iv_verbs": sorted(self.iv_verbs),
            "tv_verbs": sorted(self.tv_verbs),
            "cv_verbs": sorted(self.cv_verbs),
            "cop_n_verbs": sorted(self.cop_n_verbs),
            "comp": ["that"],
        }


def load_jsonl(path: str) -> List[JsonDict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(data: List[JsonDict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(data: JsonDict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-lexicon", required=True)
    parser.add_argument("--similarity-threshold", type=float, default=0.65)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    records = load_jsonl(args.input)

    gen = PseudoEnglishGenerator(similarity_threshold=args.similarity_threshold)
    out, lex = gen.process_records(records)

    write_jsonl(out, args.out_jsonl)
    write_json(lex, args.out_lexicon)


if __name__ == "__main__":
    main()