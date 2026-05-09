#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):  # type: ignore
        return iterable


JsonDict = Dict[str, Any]


class PseudoEnglishGenerator:
    # Conservative English ANC suffix whitelist.
    # Ordered roughly from longer/more specific to shorter/more general.
    ANC_SUFFIXES: Tuple[str, ...] = (
        "ation",
        "tion",
        "sion",
        "ment",
        "ance",
        "ence",
        "ure",
        "al",
        "ing",
    )

    def __init__(self, similarity_threshold: float = 0.70) -> None:
        self.noun_lemmas: Set[str] = set()

        self.iv_verbs: Set[str] = set()
        self.tv_verbs: Set[str] = set()
        self.cv_verbs: Set[str] = set()
        self.cop_n_verbs: Set[str] = set()

        # noun -> list of ANC candidates
        # each candidate:
        #   {"verb": str, "construction": "iv"|"tv", "score": float, "stem": str, "suffix": str}
        self.anc_noun_to_candidates: Dict[str, List[Dict[str, Any]]] = {}
        self.anc_source_nouns: Set[str] = set()

        # Bidirectional threshold:
        # common_prefix_len / len(stem) >= threshold
        # common_prefix_len / len(verb) >= threshold
        self.similarity_threshold = similarity_threshold

        # ========= stats =========
        self.total_input_records = 0
        self.total_keep_sentences = 0
        self.total_realized_sentences = 0
        self.anc_detected_sentences = 0

        self.keep_by_construction: Dict[str, int] = {
            "iv": 0,
            "tv": 0,
            "cv": 0,
            "cop_n": 0,
        }
        self.realized_by_construction: Dict[str, int] = {
            "iv": 0,
            "tv": 0,
            "cv": 0,
            "cop_n": 0,
        }
        self.anc_by_construction: Dict[str, int] = {
            "iv": 0,
            "tv": 0,
            "cv": 0,
            "cop_n": 0,
        }

        self.anc_lexicon_counts: Dict[str, int] = {
            "iv": 0,
            "tv": 0,
            "cv": 0,
            "multi_source": 0,
            "total_anc_nouns": 0,
        }

    # ========= token normalization =========

    def _canon_token(self, s: str) -> str:
        s = s.strip()
        if not s:
            return "x"

        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.lower()
        s = re.sub(r"[^a-z0-9]", "", s)

        if not s:
            return "x"
        if s[0].isdigit():
            s = f"tok{s}"
        return s

    # ========= streaming pipeline =========

    def collect_base_lexicon(self, records: Iterable[JsonDict], total: Optional[int] = None) -> None:
        for rec in tqdm(records, total=total, desc="Collecting base lexicon"):
            self._collect_from_record(rec, top_level=True)

    def _common_prefix_len(self, a: str, b: str) -> int:
        limit = min(len(a), len(b))
        i = 0
        while i < limit and a[i] == b[i]:
            i += 1
        return i

    def _match_suffix(self, noun: str) -> Optional[str]:
        for suf in self.ANC_SUFFIXES:
            if noun.endswith(suf) and len(noun) > len(suf):
                return suf
        return None

    def _stem_from_nominal(self, noun: str) -> Optional[Tuple[str, str]]:
        """
        Return (stem, suffix) if noun ends with a whitelisted ANC suffix.
        Otherwise return None.
        """
        suffix = self._match_suffix(noun)
        if suffix is None:
            return None

        stem = noun[:-len(suffix)]
        if not stem:
            return None
        return stem, suffix

    def _stem_match_score(self, stem: str, verb: str) -> float:
        """
        Bidirectional prefix threshold score.

        Score is the minimum of:
            common_prefix_len / len(stem)
            common_prefix_len / len(verb)

        This makes matching conservative:
        both stem coverage and verb coverage must be high.

        Examples with threshold=0.7:
            refusal -> refus vs refuse   => min(5/5, 5/6) = 0.8333
            running -> runn  vs run      => min(3/4, 3/3) = 0.75
            destruc vs destroy           => min(4/7, 4/7) = 0.5714
        """
        if not stem or not verb:
            return 0.0

        cpl = self._common_prefix_len(stem, verb)
        if cpl == 0:
            return 0.0

        stem_ratio = cpl / len(stem)
        verb_ratio = cpl / len(verb)
        return min(stem_ratio, verb_ratio)

    def _build_verb_buckets(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Speedup: only compare a stem against verbs sharing the first 2 chars
        of the stem. If stem is shorter than 2, use the whole stem.
        """
        # ANC source lookup intentionally ignores clausal verbs (cv).
        # cv verbs are still collected in self.cv_verbs for ordinary clausal
        # complement generation, but they are not used to identify action
        # nominal candidates.
        buckets: Dict[str, Dict[str, List[str]]] = {
            "iv": {},
            "tv": {},
        }

        for construction, verbs in [
            ("iv", self.iv_verbs),
            ("tv", self.tv_verbs),
        ]:
            for verb in verbs:
                key = verb[:2] if len(verb) >= 2 else verb
                buckets[construction].setdefault(key, []).append(verb)

        return buckets

    def build_anc_lexicon(self) -> None:
        """
        Build ANC noun lexicon conservatively:

        1. noun must end in a whitelisted nominal suffix
        2. remove suffix -> stem
        3. compare stem against IV/TV verbs using bidirectional prefix threshold
        4. keep only the closest match for each construction

        CV verbs are deliberately excluded from ANC source matching.
        """
        self.anc_noun_to_candidates = {}
        verb_buckets = self._build_verb_buckets()

        for noun in tqdm(sorted(self.noun_lemmas), desc="Building ANC lexicon"):
            if not noun:
                continue

            stem_info = self._stem_from_nominal(noun)
            if stem_info is None:
                continue

            stem, suffix = stem_info
            key = stem[:2] if len(stem) >= 2 else stem
            best_by_construction: Dict[str, Dict[str, Any]] = {}

            # 关键改动：这里只对比 iv 和 tv，不对比 cv。
            for construction in ["iv", "tv"]:
                best_match: Optional[str] = None
                best_score = 0.0
                best_cpl = -1

                candidate_verbs = verb_buckets[construction].get(key, [])
                for verb in candidate_verbs:
                    score = self._stem_match_score(stem, verb)
                    if score < self.similarity_threshold:
                        continue

                    cpl = self._common_prefix_len(stem, verb)

                    if score > best_score:
                        best_score = score
                        best_match = verb
                        best_cpl = cpl
                    elif score == best_score:
                        # tie-break 1: longer shared prefix
                        if cpl > best_cpl:
                            best_match = verb
                            best_cpl = cpl
                        # tie-break 2: longer verb
                        elif cpl == best_cpl and best_match is not None:
                            if len(verb) > len(best_match):
                                best_match = verb

                if best_match is not None:
                    best_by_construction[construction] = {
                        "verb": best_match,
                        "construction": construction,
                        "score": best_score,
                        "stem": stem,
                        "suffix": suffix,
                    }

            if best_by_construction:
                candidates = list(best_by_construction.values())
                candidates.sort(
                    key=lambda x: (
                        x["score"],
                        self._common_prefix_len(x["stem"], x["verb"]),
                        len(x["verb"]),
                        x["construction"],
                    ),
                    reverse=True,
                )
                self.anc_noun_to_candidates[noun] = candidates

        iv_count = 0
        tv_count = 0
        multi_source = 0

        for cands in self.anc_noun_to_candidates.values():
            seen = {c["construction"] for c in cands}
            if "iv" in seen:
                iv_count += 1
            if "tv" in seen:
                tv_count += 1
            if len(seen) > 1:
                multi_source += 1

        self.anc_lexicon_counts = {
            "iv": iv_count,
            "tv": tv_count,
            "cv": 0,
            "multi_source": multi_source,
            "total_anc_nouns": len(self.anc_noun_to_candidates),
        }

    def iter_outputs(self, records: Iterable[JsonDict], total: Optional[int] = None) -> Iterator[JsonDict]:
        new_sid = 1
        for rec in tqdm(records, total=total, desc="Realizing pseudo-English"):
            pseudo = self._realize_record(rec)
            if pseudo is None:
                continue

            yield {
                "id": new_sid,
                "sentence": rec.get("sentence"),
                "pseudo_english": pseudo,
            }
            new_sid += 1

    def build_lexicon(self) -> JsonDict:
        return self._build_lexicon()

    def build_stats(self) -> JsonDict:
        anc_ratio_all_keep = (
            self.anc_detected_sentences / self.total_keep_sentences
            if self.total_keep_sentences > 0 else 0.0
        )

        anc_ratio_iv_keep = (
            self.anc_by_construction["iv"] / self.keep_by_construction["iv"]
            if self.keep_by_construction["iv"] > 0 else 0.0
        )

        anc_ratio_tv_keep = (
            self.anc_by_construction["tv"] / self.keep_by_construction["tv"]
            if self.keep_by_construction["tv"] > 0 else 0.0
        )

        anc_ratio_cv_keep = (
            self.anc_by_construction["cv"] / self.keep_by_construction["cv"]
            if self.keep_by_construction["cv"] > 0 else 0.0
        )

        return {
            "records": {
                "total_input_records": self.total_input_records,
                "total_keep_sentences": self.total_keep_sentences,
                "total_realized_sentences": self.total_realized_sentences,
                "anc_detected_sentences": self.anc_detected_sentences,
            },
            "ratios": {
                "anc_ratio_among_all_keep_sentences": anc_ratio_all_keep,
                "anc_ratio_among_keep_iv_sentences": anc_ratio_iv_keep,
                "anc_ratio_among_keep_tv_sentences": anc_ratio_tv_keep,
                "anc_ratio_among_keep_cv_sentences": anc_ratio_cv_keep,
            },
            "construction_counts": {
                "keep_by_construction": self.keep_by_construction,
                "realized_by_construction": self.realized_by_construction,
                "anc_by_construction": self.anc_by_construction,
            },
            "lexicon_sizes": {
                "nouns": len(self.noun_lemmas),
                "iv_verbs": len(self.iv_verbs),
                "tv_verbs": len(self.tv_verbs),
                "cv_verbs": len(self.cv_verbs),
                "cop_n_verbs": len(self.cop_n_verbs),
                "anc_source_nouns": len(self.anc_source_nouns),
                "total_unique_verbs": len(
                    self.iv_verbs | self.tv_verbs | self.cv_verbs | self.cop_n_verbs
                ),
                "anc_nouns_in_lexicon": len(self.anc_noun_to_candidates),
            },
            "anc_lexicon_counts": self.anc_lexicon_counts,
            "anc_lexicon_samples": {
                "first_50": {
                    noun: cands
                    for noun, cands in list(sorted(self.anc_noun_to_candidates.items()))[:50]
                }
            },
            "lexicon_samples": {
                "nouns_first_50": sorted(self.noun_lemmas)[:50],
                "iv_verbs_first_50": sorted(self.iv_verbs)[:50],
                "tv_verbs_first_50": sorted(self.tv_verbs)[:50],
                "cv_verbs_first_50": sorted(self.cv_verbs)[:50],
                "cop_n_verbs_first_50": sorted(self.cop_n_verbs)[:50],
                "anc_source_nouns_first_50": sorted(self.anc_source_nouns)[:50],
            },
            "settings": {
                "similarity_threshold": self.similarity_threshold,
                "similarity_definition": (
                    "noun must end in whitelisted ANC suffix; "
                    "strip suffix -> stem; "
                    "score = min(common_prefix_len/len(stem), common_prefix_len/len(verb)); "
                    "only iv/tv verbs are considered as ANC sources"
                ),
                "anc_suffixes": list(self.ANC_SUFFIXES),
                "anc_source_constructions": ["iv", "tv"],
                "exclude_cv_as_anc_source": True,
            },
        }

    # ========= lexicon collection =========

    def _collect_from_record(self, rec: JsonDict, top_level: bool = False) -> None:
        if top_level:
            self.total_input_records += 1
            if rec.get("status") != "keep":
                return

        construction = rec.get("construction")
        predicate = rec.get("predicate")
        object_info = rec.get("object_info")

        if top_level and construction in self.keep_by_construction:
            self.keep_by_construction[construction] += 1

        if construction in {"iv", "tv", "cv", "cop_n"} and predicate:
            verb_form = self._verb_surface(predicate, object_info)
            self._add_verb_by_construction(construction, verb_form)

        for arg in (rec.get("arguments") or {}).values():
            if isinstance(arg, str) and arg:
                self.noun_lemmas.add(self._canon_token(arg))

        nominal_modifiers = rec.get("nominal_modifiers") or []
        for nm in nominal_modifiers:
            noun_lemma = nm.get("noun_lemma")
            if noun_lemma:
                self.noun_lemmas.add(self._canon_token(noun_lemma))

            modifiers = nm.get("modifiers") or {}

            for poss in (modifiers.get("poss") or []):
                head_lemma = poss.get("head_lemma")
                if isinstance(head_lemma, str) and head_lemma:
                    self.noun_lemmas.add(self._canon_token(head_lemma))

            for of_mod in (modifiers.get("of") or []):
                obj_lemma = of_mod.get("object_head_lemma")
                if isinstance(obj_lemma, str) and obj_lemma:
                    self.noun_lemmas.add(self._canon_token(obj_lemma))

            for by_mod in (modifiers.get("by") or []):
                obj_lemma = by_mod.get("object_head_lemma")
                if isinstance(obj_lemma, str) and obj_lemma:
                    self.noun_lemmas.add(self._canon_token(obj_lemma))

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

    # ========= realization =========

    def _realize_record(self, rec: JsonDict) -> Optional[str]:
        if rec.get("status") != "keep":
            return None

        self.total_keep_sentences += 1

        pseudo, has_anc = self._realize_clause(rec)
        if pseudo is None:
            return None

        self.total_realized_sentences += 1

        construction = rec.get("construction")
        if construction in self.realized_by_construction:
            self.realized_by_construction[construction] += 1

        if has_anc:
            self.anc_detected_sentences += 1
            if construction in self.anc_by_construction:
                self.anc_by_construction[construction] += 1

        return pseudo

    def _realize_clause(self, rec: JsonDict) -> Tuple[Optional[str], bool]:
        construction = rec.get("construction")

        if construction == "iv":
            return self._realize_iv(rec)
        if construction == "tv":
            return self._realize_tv(rec)
        if construction == "cv":
            return self._realize_cv(rec)
        if construction == "cop_n":
            return self._realize_cop_n(rec), False

        return None, False

    def _render_anc_np(self, anc: Dict[str, Optional[str]]) -> str:
        parts: List[str] = []

        mode = anc.get("realization_mode")

        if mode == "iv_single":
            sole_arg = anc.get("agent")
            if sole_arg:
                parts.append(f"{sole_arg}ge")
            parts.append(f"{anc['verb']}nmz")
            return " ".join(parts)

        if anc.get("agent"):
            parts.append(f"{anc['agent']}ge")
        parts.append(f"{anc['verb']}nmz")
        if anc.get("patient"):
            parts.append(f"{anc['patient']}ob")

        return " ".join(parts)

    def _realize_iv(self, rec: JsonDict) -> Tuple[str, bool]:
        args = rec.get("arguments") or {}
        subj = args.get("S")
        pred = rec.get("predicate")

        if not subj or not pred:
            return "[BAD_IV]", False

        anc = self._extract_anc_info_for_noun(
            rec=rec,
            noun_lemma=subj,
            expected_construction="iv",
        )
        if anc is not None:
            anc_np = self._render_anc_np(anc)
            verb_tok = self._verb_surface(pred, rec.get("object_info"))
            return f"{anc_np} {verb_tok}s", True

        subj_tok = self._realize_ordinary_noun_with_gen(subj, rec)
        verb_tok = self._verb_surface(pred, rec.get("object_info"))
        return f"{subj_tok} {verb_tok}s", False

    def _realize_tv(self, rec: JsonDict) -> Tuple[str, bool]:
        args = rec.get("arguments") or {}
        a = args.get("A")
        p = args.get("P")

        if not a or not p or not rec.get("predicate"):
            return "[BAD_TV]", False

        p_tok = self._canon_token(p)
        matrix_verb = self._verb_surface(rec["predicate"], rec.get("object_info")) + "s"

        anc = self._extract_anc_info_for_noun(
            rec=rec,
            noun_lemma=a,
            expected_construction="tv",
        )
        if anc is not None:
            anc_np = self._render_anc_np(anc)
            return f"{anc_np} {matrix_verb} {p_tok}", True

        ordinary_np_subj = self._realize_ordinary_noun_with_gen(a, rec)
        return f"{ordinary_np_subj} {matrix_verb} {p_tok}", False

    def _realize_cv(self, rec: JsonDict) -> Tuple[str, bool]:
        args = rec.get("arguments") or {}
        a = args.get("A")
        pred = rec.get("predicate")
        comp = rec.get("complement")

        if not a or not pred or not isinstance(comp, dict):
            return "[BAD_CV]", False

        embedded, embedded_has_anc = self._realize_clause(comp)
        if embedded is None:
            return "[BAD_CV]", False

        # 这里虽然还调用 expected_construction="cv"，
        # 但 _extract_anc_info_for_noun() 现在不会返回 cv ANC。
        # 所以 cv 句子会正常 realization，但不会 nominalized-cv。
        anc = self._extract_anc_info_for_noun(
            rec=rec,
            noun_lemma=a,
            expected_construction="cv",
        )
        if anc is not None:
            anc_np = self._render_anc_np(anc)
            verb_tok = self._verb_surface(pred, rec.get("object_info"))
            return f"{anc_np} {verb_tok}s that {embedded}", True

        a_tok = self._realize_ordinary_noun_with_gen(a, rec)
        verb_tok = self._verb_surface(pred, rec.get("object_info"))
        return f"{a_tok} {verb_tok}s that {embedded}", embedded_has_anc

    def _realize_cop_n(self, rec: JsonDict) -> str:
        args = rec.get("arguments") or {}
        a = args.get("A")
        pred_nom = args.get("PRED")
        pred = rec.get("predicate")

        if not a or not pred_nom or not pred:
            return "[BAD_COP_N]"

        subj = self._realize_ordinary_noun_with_gen(a, rec)
        verb = self._verb_surface(pred, rec.get("object_info")) + "s"
        pred_nom_tok = self._canon_token(pred_nom)
        return f"{subj} {verb} {pred_nom_tok}"

    def _realize_ordinary_noun_with_gen(self, noun_lemma: str, rec: JsonDict) -> str:
        noun_tok = self._canon_token(noun_lemma)

        nominal_modifiers = rec.get("nominal_modifiers") or []
        for nm in nominal_modifiers:
            if self._canon_token(nm.get("noun_lemma", "")) != noun_tok:
                continue

            modifiers = nm.get("modifiers") or {}
            poss_mods = modifiers.get("poss") or []
            if poss_mods:
                possessor = poss_mods[0].get("head_lemma") or poss_mods[0].get("head_text")
                if possessor:
                    possessor_tok = self._canon_token(possessor)
                    return f"{possessor_tok}ge {noun_tok}"

        return noun_tok

    # ========= ANC handling =========

    def _lookup_anc_candidate(
        self,
        noun_lemma: str,
        expected_construction: str,
    ) -> Optional[Dict[str, Any]]:
        noun_tok = self._canon_token(noun_lemma)
        candidates = self.anc_noun_to_candidates.get(noun_tok, [])
        for cand in candidates:
            if cand["construction"] == expected_construction:
                return cand
        return None

    def _extract_anc_info_for_noun(
        self,
        rec: JsonDict,
        noun_lemma: str,
        expected_construction: str,
    ) -> Optional[Dict[str, Optional[str]]]:
        noun_tok = self._canon_token(noun_lemma)

        cand = self._lookup_anc_candidate(noun_tok, expected_construction)
        if cand is None:
            return None

        nominal_modifiers = rec.get("nominal_modifiers") or []
        target_nm = None
        for nm in nominal_modifiers:
            if self._canon_token(nm.get("noun_lemma", "")) == noun_tok:
                target_nm = nm
                break

        poss_mods: List[JsonDict] = []
        of_mods: List[JsonDict] = []
        by_mods: List[JsonDict] = []

        if target_nm is not None:
            modifiers = target_nm.get("modifiers") or {}
            poss_mods = modifiers.get("poss") or []
            of_mods = modifiers.get("of") or []
            by_mods = modifiers.get("by") or []

        # shared sanity checks
        if len(poss_mods) > 1 or len(of_mods) > 1 or len(by_mods) > 1:
            return None
        if poss_mods and by_mods:
            return None

        subj_arg: Optional[str] = None
        obj_arg: Optional[str] = None

        if poss_mods:
            raw_subj = poss_mods[0].get("head_lemma") or poss_mods[0].get("head_text")
            if raw_subj:
                subj_arg = self._canon_token(raw_subj)
        elif by_mods:
            raw_subj = by_mods[0].get("object_head_lemma") or by_mods[0].get("object_head_text")
            if raw_subj:
                subj_arg = self._canon_token(raw_subj)

        if of_mods:
            raw_obj = of_mods[0].get("object_head_lemma") or of_mods[0].get("object_head_text")
            if raw_obj:
                obj_arg = self._canon_token(raw_obj)

        overt_arg_count = int(subj_arg is not None) + int(obj_arg is not None)

        if expected_construction == "iv":
            # iv:
            # 0 overt args -> bare verbtion is allowed
            # 1 overt arg  -> that sole arg is always realized as ge
            # 2 overt args -> reject this ANC analysis
            if overt_arg_count > 1:
                return None

            sole_arg = subj_arg if subj_arg is not None else obj_arg

            self.anc_source_nouns.add(noun_tok)
            return {
                "verb": cand["verb"],
                "agent": sole_arg,           # sole argument always rendered as ge
                "patient": None,
                "source_construction": cand["construction"],
                "realization_mode": "iv_single",
            }

        if expected_construction == "tv":
            # tv:
            # poss/by -> subject -> ge
            # of      -> object  -> ob
            if overt_arg_count > 2:
                return None

            self.anc_source_nouns.add(noun_tok)
            return {
                "verb": cand["verb"],
                "agent": subj_arg,
                "patient": obj_arg,
                "source_construction": cand["construction"],
                "realization_mode": "default",
            }

        # 关键改动：cv nominalization 不作为 ANC 抽取/实现。
        return None

    # ========= verb handling =========

    def _verb_surface(self, pred: str, obj: Optional[JsonDict]) -> str:
        if obj and obj.get("object_type") == "pp_obj":
            prep = obj.get("adposition")
            if prep:
                return self._canon_token(f"{pred}{prep}")

        if obj and obj.get("particle"):
            particle = obj["particle"].get("particle_lemma")
            if particle:
                return self._canon_token(f"{pred}{particle}")

        return self._canon_token(pred)

    # ========= outputs =========

    def _build_lexicon(self) -> JsonDict:
        return {
            "nouns": sorted(self.noun_lemmas),
            "iv_verbs": sorted(self.iv_verbs),
            "tv_verbs": sorted(self.tv_verbs),
            "cv_verbs": sorted(self.cv_verbs),
            "cop_n_verbs": sorted(self.cop_n_verbs),
            "anc_noun_to_candidates": self.anc_noun_to_candidates,
            "comp": ["that"],
        }


def iter_jsonl(path: str) -> Iterator[JsonDict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def count_nonempty_lines(path: str) -> int:
    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def write_jsonl_stream(data: Iterable[JsonDict], path: str) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(data: JsonDict, path: str) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-lexicon", required=True)
    parser.add_argument("--out-stats", default=None)
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.70,
        help=(
            "Bidirectional threshold on stripped nominal stem vs verb: "
            "common_prefix_len/len(stem) >= t and common_prefix_len/len(verb) >= t"
        ),
    )
    parser.add_argument(
        "--no-count",
        action="store_true",
        help="Do not pre-count input lines for tqdm total",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    total = None if args.no_count else count_nonempty_lines(args.input)

    gen = PseudoEnglishGenerator(similarity_threshold=args.similarity_threshold)

    # pass 1: collect nouns + verb inventories
    gen.collect_base_lexicon(iter_jsonl(args.input), total=total)

    # pass 2: build ANC noun lexicon
    gen.build_anc_lexicon()

    # pass 3: realize pseudo-English and collect ANC stats
    write_jsonl_stream(
        gen.iter_outputs(iter_jsonl(args.input), total=total),
        args.out_jsonl,
    )

    write_json(gen.build_lexicon(), args.out_lexicon)

    stats = gen.build_stats()

    print(f"total input records: {stats['records']['total_input_records']}")
    print(f"keep sentences: {stats['records']['total_keep_sentences']}")
    print(f"realized sentences: {stats['records']['total_realized_sentences']}")
    print(f"anc detected sentences: {stats['records']['anc_detected_sentences']}")
    print(
        "anc ratio among all keep sentences: "
        f"{stats['ratios']['anc_ratio_among_all_keep_sentences']:.4%}"
    )
    print(
        "anc ratio among keep iv sentences: "
        f"{stats['ratios']['anc_ratio_among_keep_iv_sentences']:.4%}"
    )
    print(
        "anc ratio among keep tv sentences: "
        f"{stats['ratios']['anc_ratio_among_keep_tv_sentences']:.4%}"
    )
    print(
        "anc ratio among keep cv sentences: "
        f"{stats['ratios']['anc_ratio_among_keep_cv_sentences']:.4%}"
    )
    print(
        "lexicon sizes: "
        f"nouns={stats['lexicon_sizes']['nouns']}, "
        f"iv={stats['lexicon_sizes']['iv_verbs']}, "
        f"tv={stats['lexicon_sizes']['tv_verbs']}, "
        f"cv={stats['lexicon_sizes']['cv_verbs']}, "
        f"cop_n={stats['lexicon_sizes']['cop_n_verbs']}, "
        f"anc_source_nouns={stats['lexicon_sizes']['anc_source_nouns']}, "
        f"anc_nouns={stats['lexicon_sizes']['anc_nouns_in_lexicon']}"
    )
    print(
        "anc lexicon counts: "
        f"iv={stats['anc_lexicon_counts']['iv']}, "
        f"tv={stats['anc_lexicon_counts']['tv']}, "
        f"cv={stats['anc_lexicon_counts']['cv']}, "
        f"multi_source={stats['anc_lexicon_counts']['multi_source']}, "
        f"total={stats['anc_lexicon_counts']['total_anc_nouns']}"
    )

    if args.out_stats:
        write_json(stats, args.out_stats)


if __name__ == "__main__":
    main()