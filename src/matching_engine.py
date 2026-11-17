"""
SkillPath AI — matching_engine.py
Algoritmo di scoring deterministico CV ↔ Occupation.

Output:
  - score percentuale di compatibilità (0-100%)
  - gap analysis: skill/cert/lingue mancanti
  - ranking top-N occupation per un CV

Uso standalone:
    python matching_engine.py --cv cv.json --profile profile.json
    python matching_engine.py --cv cv.json --top 5 --profiles occupation_profiles.json
"""

import json
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field


# ─── Strutture dati ──────────────────────────────────────────────────────────

@dataclass
class SkillGap:
    missing_essential: list[dict] = field(default_factory=list)
    missing_optional:  list[dict] = field(default_factory=list)
    matched_essential: list[dict] = field(default_factory=list)
    matched_optional:  list[dict] = field(default_factory=list)

@dataclass
class EducationGap:
    required_cycle:  str  = ""
    candidate_cycle: str  = ""
    area_match:      bool = False

@dataclass
class LanguageGap:
    missing:     list[dict] = field(default_factory=list)  # lingue richieste non presenti
    insufficient: list[dict] = field(default_factory=list)  # presenti ma livello troppo basso

@dataclass
class CertGap:
    missing: list[dict] = field(default_factory=list)

@dataclass
class MatchResult:
    occupation_id:    str
    occupation_label: str
    isco_code:        str

    # Score globale 0.0-1.0
    total_score:      float = 0.0
    percentage:       float = 0.0   # total_score * 100

    # Score per dimensione 0.0-1.0
    skill_score:      float = 0.0
    experience_score: float = 0.0
    education_score:  float = 0.0
    language_score:   float = 0.0
    cert_score:       float = 0.0

    # Gap analysis
    skill_gap:    SkillGap    = field(default_factory=SkillGap)
    edu_gap:      EducationGap = field(default_factory=EducationGap)
    lang_gap:     LanguageGap = field(default_factory=LanguageGap)
    cert_gap:     CertGap     = field(default_factory=CertGap)

    def summary(self) -> dict:
        return {
            "occupation_id":    self.occupation_id,
            "occupation_label": self.occupation_label,
            "isco_code":        self.isco_code,
            "percentage":       round(self.percentage, 1),
            "scores": {
                "skills":         round(self.skill_score * 100, 1),
                "experience":     round(self.experience_score * 100, 1),
                "education":      round(self.education_score * 100, 1),
                "languages":      round(self.language_score * 100, 1),
                "certifications": round(self.cert_score * 100, 1),
            },
            "gap_analysis": {
                "missing_essential_skills": [
                    {"id": s["id"], "label": s["label"]}
                    for s in self.skill_gap.missing_essential
                ],
                "missing_optional_skills": [
                    {"id": s["id"], "label": s["label"]}
                    for s in self.skill_gap.missing_optional[:5]  # max 5
                ],
                "missing_certifications": [
                    {"id": c["id"], "label": c["label"]}
                    for c in self.cert_gap.missing
                ],
                "language_gaps": [
                    {"language": l.get("language"), "required_cefr": l.get("required_cefr"),
                     "candidate_cefr": l.get("candidate_cefr")}
                    for l in self.lang_gap.insufficient
                ] + [
                    {"language": l.get("language"), "required_cefr": l.get("required_cefr"),
                     "candidate_cefr": None}
                    for l in self.lang_gap.missing
                ],
                "education_gap": {
                    "required_cycle":  self.edu_gap.required_cycle,
                    "candidate_cycle": self.edu_gap.candidate_cycle,
                    "area_match":      self.edu_gap.area_match,
                } if self.edu_gap.required_cycle else None,
            }
        }


# ─── Motore di matching ──────────────────────────────────────────────────────

class MatchingEngine:

    def __init__(
        self,
        weights_path:  str | Path,
        profiles_path: str | Path,
        supp_dir:      str | Path,
    ):
        self.w    = self._load_weights(weights_path)
        self.profiles = self._load_profiles(profiles_path)
        self.supp = self._load_supplementary(supp_dir)

    # ── Caricamento ──────────────────────────────────────────────────────────

    def _load_weights(self, path: str | Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_profiles(self, path: str | Path) -> dict:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Supporta sia lista che dict
        if isinstance(data, list):
            return {p["id"]: p for p in data}
        return data

    def _load_supplementary(self, supp_dir: str | Path) -> dict:
        supp_dir = Path(supp_dir)
        result = {}
        for fname in ["degree_programs.json", "language_levels.json", "certifications.json"]:
            path = supp_dir / fname
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    result[fname.replace(".json","")] = json.load(f)
        return result

    # ── Score Skill ──────────────────────────────────────────────────────────

    def _score_skills(self, cv: dict, profile: dict) -> tuple[float, SkillGap]:
        """
        Confronta le skill del CV con quelle richieste dall'occupation.
        Score = essential_weight * (matched_ess/total_ess)
              + optional_weight  * (matched_opt/total_opt)
        """
        w_ess = self.w["skills"]["essential_weight"]
        w_opt = self.w["skills"]["optional_weight"]

        cv_skills = set(cv.get("skills", {}).get("essential_ids", []) +
                        cv.get("skills", {}).get("optional_ids", []))

        ess_skills = profile.get("essential_skills", [])
        opt_skills = profile.get("optional_skills",  [])

        ess_ids = {s["id"] for s in ess_skills}
        opt_ids = {s["id"] for s in opt_skills}

        matched_ess = cv_skills & ess_ids
        matched_opt = cv_skills & opt_ids

        ess_score = len(matched_ess) / len(ess_ids) if ess_ids else 1.0
        opt_score = len(matched_opt) / len(opt_ids) if opt_ids else 1.0

        score = w_ess * ess_score + w_opt * opt_score

        gap = SkillGap(
            missing_essential = [s for s in ess_skills if s["id"] not in matched_ess],
            missing_optional  = [s for s in opt_skills  if s["id"] not in matched_opt],
            matched_essential = [s for s in ess_skills if s["id"] in matched_ess],
            matched_optional  = [s for s in opt_skills  if s["id"] in matched_opt],
        )
        return min(score, 1.0), gap

    # ── Score Experience ─────────────────────────────────────────────────────

    def _score_experience(self, cv: dict, profile: dict) -> float:
        """
        Valuta gli anni di esperienza e la seniority del candidato.
        Considera anche la rilevanza ISCO del percorso lavorativo.
        """
        w_years = self.w["experience"]["years_weight"]
        w_rel   = self.w["experience"]["relevance_weight"]

        years_exp = cv.get("persona", {}).get("years_experience", 0)
        seniority = cv.get("persona", {}).get("seniority", "junior")
        profile_isco = (profile.get("isco_code") or "")[:1]

        # Score anni: scala logaritmica (0=0%, 2=40%, 5=70%, 10=90%, 15+=100%)
        import math
        years_score = min(1.0, math.log1p(years_exp) / math.log1p(15))

        # Score rilevanza: quante WE sono nello stesso settore ISCO
        we = cv.get("work_experience", [])
        if we:
            relevant = sum(1 for e in we
                          if e.get("seniority") in ("mid","senior","executive"))
            relevance_score = min(1.0, relevant / len(we) * 1.5)
        else:
            relevance_score = 0.3  # nessuna WE = punteggio base basso

        # Bonus seniority
        seniority_bonus = self.w["experience"]["seniority_bonus"].get(seniority, 0.0)

        score = w_years * years_score + w_rel * relevance_score + seniority_bonus
        return min(score, 1.0)

    # ── Score Education ──────────────────────────────────────────────────────

    def _score_education(self, cv: dict, profile: dict) -> tuple[float, EducationGap]:
        """
        Valuta il titolo di studio rispetto al livello tipico del ruolo.
        Bonus se l'area disciplinare è coerente con il settore ISCO.
        """
        cycle_scores  = self.w["education"]["cycle_scores"]
        area_bonus    = self.w["education"]["area_match_bonus"]

        edu          = cv.get("education", {})
        cv_cycle     = (edu.get("cycle") or "none").lower()
        cv_area      = (edu.get("area")  or "").lower()
        profile_isco = (profile.get("isco_code") or "")[:1]

        # Score base dal ciclo
        base_score = cycle_scores.get(cv_cycle, cycle_scores["none"])

        # Determina ciclo atteso in base all'ISCO major
        expected_cycles = {
            "1": "magistrale", "2": "magistrale",
            "3": "triennale",  "4": "triennale",
            "5": "secondario", "6": "secondario",
            "7": "secondario", "8": "secondario",
            "9": "none",
        }
        expected = expected_cycles.get(profile_isco, "triennale")

        # Bonus area disciplinare
        isco_areas = {
            "1": ["economico","giuridico","sociale"],
            "2": ["stem","sanitario","economico","giuridico","umanistico","sociale"],
            "3": ["stem","sanitario"],
            "4": ["economico","sociale","umanistico"],
            "5": ["sociale","umanistico"],
            "6": ["stem"],
            "7": ["stem"],
            "8": ["stem"],
            "9": [],
        }
        relevant_areas = isco_areas.get(profile_isco, [])
        area_match = any(a in cv_area for a in relevant_areas)
        score = base_score + (area_bonus if area_match else 0.0)

        gap = EducationGap(
            required_cycle  = expected,
            candidate_cycle = cv_cycle,
            area_match      = area_match,
        )
        return min(score, 1.0), gap

    # ── Score Languages ──────────────────────────────────────────────────────

    def _score_languages(self, cv: dict, profile: dict) -> tuple[float, LanguageGap]:
        """
        Valuta le competenze linguistiche.
        L'inglese è valorizzato per ruoli ISCO 1-2.
        La lingua madre conta come livello massimo.
        """
        cefr_scores  = self.w["languages"]["cefr_scores"]
        profile_isco = (profile.get("isco_code") or "")[:1]

        cv_langs = cv.get("languages", [])
        lang_gap = LanguageGap()

        # Mappa lingua → miglior livello del candidato
        candidate_levels: dict[str, float] = {}
        for l in cv_langs:
            lang  = l.get("language", "").lower()
            cefr  = l.get("cefr", "A1")
            score = cefr_scores.get(cefr, 0.0)
            candidate_levels[lang] = max(candidate_levels.get(lang, 0.0), score)

        if not candidate_levels:
            return 0.2, lang_gap

        # Score base: media delle lingue del candidato
        avg_score = sum(candidate_levels.values()) / len(candidate_levels)

        # Bonus inglese per ISCO 1 e 2
        english_score = candidate_levels.get("english", 0.0)
        if profile_isco in ("1","2"):
            # Inglese pesato di più per professionisti e manager
            score = avg_score * 0.5 + english_score * 0.5
            if english_score < cefr_scores.get("B2", 0.65):
                lang_gap.insufficient.append({
                    "language": "English",
                    "required_cefr": "B2",
                    "candidate_cefr": next(
                        (l.get("cefr") for l in cv_langs
                         if l.get("language","").lower() == "english"), None
                    )
                })
        else:
            score = avg_score

        return min(score, 1.0), lang_gap

    # ── Score Certifications ─────────────────────────────────────────────────

    def _score_certifications(self, cv: dict, profile: dict) -> tuple[float, CertGap]:
        """
        Valuta le certificazioni del candidato.
        Non esiste una lista di cert richieste nell'occupation ESCO,
        quindi valutiamo la qualità delle cert possedute rispetto al settore.
        """
        level_scores = self.w["certifications"]["level_scores"]
        profile_isco = (profile.get("isco_code") or "")[:1]
        cert_gap     = CertGap()

        cv_certs = cv.get("certifications", [])
        if not cv_certs:
            # Nessuna certificazione: score dipende dal settore
            # Settori dove le cert sono importanti: 1,2,3
            base = 0.3 if profile_isco in ("1","2","3") else 0.6
            return base, cert_gap

        # Carica dizionario certificazioni
        cert_db = self.supp.get("certifications", {}).get("certifications", {})

        scores = []
        for c in cv_certs:
            cert_id = c.get("cert_id","")
            cert_info = cert_db.get(cert_id, {})
            level = cert_info.get("level", "foundation")
            # Verifica pertinenza settore
            relevant_sectors = cert_info.get("isco_relevant", [])
            is_relevant = profile_isco in relevant_sectors or not relevant_sectors
            level_score = level_scores.get(level, 0.40)
            # Penalità lieve se cert non pertinente al settore
            scores.append(level_score * (1.0 if is_relevant else 0.5))

        return min(sum(scores) / max(len(scores), 1), 1.0), cert_gap

    # ── Score Totale ─────────────────────────────────────────────────────────

    def score(self, cv: dict, occupation_id: str) -> MatchResult:
        """
        Calcola lo score completo di un CV rispetto a un'occupation.
        Restituisce un MatchResult con score percentuale e gap analysis.
        """
        profile = self.profiles.get(occupation_id)
        if not profile:
            raise ValueError(f"Occupation '{occupation_id}' non trovata nei profili")

        # Normalizza: accetta sia CV grezzo che wrapped in {"cv": {...}}
        if "cv" in cv and isinstance(cv["cv"], dict):
            cv_data = cv["cv"]
        else:
            cv_data = cv

        w = self.w["weights"]

        skill_score,  skill_gap  = self._score_skills(cv_data, profile)
        exp_score                 = self._score_experience(cv_data, profile)
        edu_score,   edu_gap     = self._score_education(cv_data, profile)
        lang_score,  lang_gap    = self._score_languages(cv_data, profile)
        cert_score,  cert_gap    = self._score_certifications(cv_data, profile)

        total = (
            w["skills"]         * skill_score  +
            w["experience"]     * exp_score     +
            w["education"]      * edu_score     +
            w["languages"]      * lang_score    +
            w["certifications"] * cert_score
        )

        result = MatchResult(
            occupation_id    = occupation_id,
            occupation_label = profile.get("label", ""),
            isco_code        = profile.get("isco_code", ""),
            total_score      = round(total, 4),
            percentage       = round(total * 100, 1),
            skill_score      = skill_score,
            experience_score = exp_score,
            education_score  = edu_score,
            language_score   = lang_score,
            cert_score       = cert_score,
            skill_gap        = skill_gap,
            edu_gap          = edu_gap,
            lang_gap         = lang_gap,
            cert_gap         = cert_gap,
        )
        return result

    # ── Ranking ──────────────────────────────────────────────────────────────

    def rank(self, cv: dict, top_n: int = 10) -> list[MatchResult]:
        """
        Calcola lo score del CV contro tutte le occupation e restituisce
        il ranking delle top_n più compatibili.
        """
        results = []
        for occ_id in self.profiles:
            try:
                results.append(self.score(cv, occ_id))
            except Exception:
                continue
        results.sort(key=lambda r: r.total_score, reverse=True)
        return results[:top_n]

    def rank_summary(self, cv: dict, top_n: int = 10) -> list[dict]:
        """Come rank() ma restituisce dict serializzabili."""
        return [r.summary() for r in self.rank(cv, top_n)]


# ─── Validazione algoritmo sul dataset sintetico ─────────────────────────────

def validate_on_dataset(
    engine:       MatchingEngine,
    cvs_path:     str | Path,
    top_n:        int = 5,
    max_cvs:      int | None = None,
) -> dict:
    """
    Valida l'algoritmo sul dataset sintetico.
    Metriche calcolate:
      - Precision@1: il ruolo corretto è al primo posto?
      - Precision@3: il ruolo corretto è nei primi 3?
      - Precision@5: il ruolo corretto è nei primi 5?
      - MRR: Mean Reciprocal Rank
      - Avg score per ruolo corretto
      - Avg score per negative samples (deve essere basso)
    """
    with open(cvs_path, encoding="utf-8") as f:
        cvs = json.load(f)

    if max_cvs:
        cvs = cvs[:max_cvs]

    p1 = p3 = p5 = mrr_sum = 0
    correct_scores   = []
    negative_scores  = []
    score_by_sen     = {"junior":[], "mid":[], "senior":[]}
    n_evaluated      = 0

    for cv in cvs:
        gt       = cv.get("ground_truth", {})
        target   = gt.get("target_occupation_id")
        negatives= [n["occupation_id"] for n in gt.get("negative_samples", [])]
        sen      = cv.get("cv",{}).get("persona",{}).get("seniority","?")

        if not target:
            continue

        ranking = engine.rank(cv, top_n=max(top_n, 10))
        ranked_ids = [r.occupation_id for r in ranking]

        # Precision@K
        if ranked_ids and ranked_ids[0] == target:
            p1 += 1
        if target in ranked_ids[:3]:
            p3 += 1
        if target in ranked_ids[:5]:
            p5 += 1

        # MRR
        if target in ranked_ids:
            rank_pos = ranked_ids.index(target) + 1
            mrr_sum += 1.0 / rank_pos
        else:
            rank_pos = None

        # Score per ruolo corretto
        correct_result = next((r for r in ranking if r.occupation_id == target), None)
        if correct_result:
            correct_scores.append(correct_result.percentage)
            if sen in score_by_sen:
                score_by_sen[sen].append(correct_result.percentage)

        # Score per negative samples
        for neg_id in negatives:
            neg_result = next((r for r in ranking if r.occupation_id == neg_id), None)
            if neg_result:
                negative_scores.append(neg_result.percentage)

        n_evaluated += 1

    n = n_evaluated or 1
    return {
        "n_evaluated":      n_evaluated,
        "precision_at_1":   round(p1 / n * 100, 1),
        "precision_at_3":   round(p3 / n * 100, 1),
        "precision_at_5":   round(p5 / n * 100, 1),
        "mrr":              round(mrr_sum / n, 3),
        "avg_correct_score":  round(sum(correct_scores) / len(correct_scores), 1) if correct_scores else 0,
        "avg_negative_score": round(sum(negative_scores) / len(negative_scores), 1) if negative_scores else 0,
        "score_by_seniority": {
            s: round(sum(v)/len(v), 1) if v else 0
            for s, v in score_by_sen.items()
        }
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SkillPath AI — Matching Engine")
    parser.add_argument("--weights",  default="./config/weights.json",
                        help="File pesi configurazione")
    parser.add_argument("--profiles", default="./dataset/materialized/occupation_profiles.json",
                        help="Profili occupation (materialized view)")
    parser.add_argument("--supp",     default="./dataset/supplementary",
                        help="Cartella dizionari supplementari")

    sub = parser.add_subparsers(dest="command")

    # Comando: score singolo
    sc = sub.add_parser("score", help="Score CV vs occupation specifica")
    sc.add_argument("--cv",      required=True, help="File CV JSON")
    sc.add_argument("--occ",     required=True, help="Occupation ID")

    # Comando: ranking
    rk = sub.add_parser("rank", help="Ranking top-N occupation per un CV")
    rk.add_argument("--cv",    required=True, help="File CV JSON")
    rk.add_argument("--top",   type=int, default=5, help="Numero risultati")

    # Comando: validazione dataset
    vl = sub.add_parser("validate", help="Valida algoritmo sul dataset sintetico")
    vl.add_argument("--cvs",   required=True, help="File cvs.json del dataset sintetico")
    vl.add_argument("--top",   type=int, default=5)
    vl.add_argument("--max",   type=int, default=None, help="Limita a N CV (test rapido)")

    args = parser.parse_args()

    engine = MatchingEngine(args.weights, args.profiles, args.supp)

    if args.command == "score":
        with open(args.cv, encoding="utf-8") as f:
            cv = json.load(f)
        result = engine.score(cv, args.occ)
        print(json.dumps(result.summary(), indent=2, ensure_ascii=False))

    elif args.command == "rank":
        with open(args.cv, encoding="utf-8") as f:
            cv = json.load(f)
        results = engine.rank_summary(cv, args.top)
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "validate":
        print("Validazione in corso...")
        metrics = validate_on_dataset(engine, args.cvs, args.top, args.max)
        print("\n" + "═"*45)
        print("  Metriche di validazione")
        print("═"*45)
        print(f"  CV valutati:         {metrics['n_evaluated']}")
        print(f"  Precision@1:         {metrics['precision_at_1']}%")
        print(f"  Precision@3:         {metrics['precision_at_3']}%")
        print(f"  Precision@5:         {metrics['precision_at_5']}%")
        print(f"  MRR:                 {metrics['mrr']}")
        print(f"  Avg score corretto:  {metrics['avg_correct_score']}%")
        print(f"  Avg score negative:  {metrics['avg_negative_score']}%")
        print(f"  Score per seniority: {metrics['score_by_seniority']}")
        print("═"*45)

    else:
        parser.print_help()


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 — Matching CV ↔ Job Description (output job_parser.py)
# ══════════════════════════════════════════════════════════════════════════════

import numpy as np
from sentence_transformers import SentenceTransformer
from skill_graph import SkillGraph

_E5_MODEL      = "intfloat/multilingual-e5-base"
_SEM_THRESHOLD = 0.82   # soglia cosine per skill "coperta" semanticamente

# Istanza globale del grafo (costruita una volta sola al primo uso)
_SKILL_GRAPH: SkillGraph | None = None

def _get_skill_graph() -> SkillGraph:
    global _SKILL_GRAPH
    if _SKILL_GRAPH is None:
        base = Path(__file__).resolve().parent.parent
        _SKILL_GRAPH = SkillGraph()
        _SKILL_GRAPH.build(
            relations_path=base / "dataset" / "source" / "occupation_skill_relations.json",
            skills_path   =base / "dataset" / "source" / "skills.json",
        )
    return _SKILL_GRAPH


def _match_grade(score: float) -> str:
    if score >= 0.80: return "ottimo"
    if score >= 0.60: return "buono"
    if score >= 0.40: return "discreto"
    return "insufficiente"


class JobMatchingEngine:
    """
    Confronta il profilo CV (output main_parser.py) con una job description
    già parsata (output job_parser.py) e produce:
      - match_score  : copertura delle skill richieste  (0.0–1.0)
      - grade        : ottimo / buono / discreto / insufficiente
      - matched_skills : skill coperte (exact o semantic)
      - skill_gap    : skill mancanti, ordinate per priorità apprendimento
      - occupation_match : similarità tra ruolo candidato e ruolo cercato

    Il gap è ordinato tramite SkillGraph (co-occorrenza ESCO + reuse_level):
    la skill mancante più fondamentale e correlata a quelle note ha priorità 1.
    """

    def __init__(
        self,
        seniority_weight: float = 0.1,
        count_weight: float = 0.15,
        count_k: float = 10.0,
    ):
        """
        Parametri di correzione (disattivi di default, così il comportamento
        storico resta riproducibile e ogni contributo è misurabile a parte):

        seniority_weight
            Peso del termine che confronta l'esperienza del candidato con il
            livello richiesto dall'annuncio. A 0 la seniority è ignorata, che
            è il comportamento originale.

            Predefinito 0.1. Il termine deve funzionare da SPAREGGIO fra
            annunci altrimenti equivalenti, non da criterio dominante.

            Con 0.3 — il valore inizialmente scelto — un abbinamento perfetto
            per contenuto ma con livello disallineato veniva superato da un
            annuncio di tutt'altro settore con il livello giusto. Nei casi
            tracciati: copertura 0.967 e similarità di ruolo 1.000 davano
            punteggio 0.646, mentre un annuncio da "mask maker" con copertura
            0.881 arrivava a 0.711. Il difetto era sfuggito perché il peso era
            stato tarato sul solo test della seniority, dove tutti gli annunci
            appartengono alla stessa occupazione e il contenuto è quindi
            costante: lì un peso alto non ha contropartite.

            Misurato su entrambe le dimensioni insieme:

                peso   sovrapp. occ↔settore   accuratezza livello
                0.30           40,0%                97,0%
                0.10            2,5%                97,0%

            Il valore basso è migliore sulla monotonia e identico sul livello:
            per distinguere annunci quasi uguali basta una spinta minima.

            Con questo valore la scelta del livello corretto passa comunque dal
            37% al 97% su 100 CV (baseline casuale 33,3%).
            ATTENZIONE a come si legge quel 97%: il livello non è dedotto dal
            motore, gli viene passato dal job parser che lo estrae dal testo
            con il 92,3% di accuratezza. Il merito è dell'estrattore; il test
            dimostra che il collegamento regge ed è robusto agli errori sul
            singolo annuncio, perché ogni occupazione ha due annunci per
            livello e ne basta uno etichettato bene.

            Perché serve: il punteggio è una copertura delle skill richieste,
            e gli annunci junior ne elencano molte meno (10,8 in media contro
            16,2 dei senior). Coprirne una quota alta è quindi più facile a
            prescindere dal candidato. Misurato su 100 CV, il motore sceglieva
            un annuncio junior 47 volte su 100 contro le 33 attese per caso, e
            l'accuratezza sul livello era 37% contro una baseline di 33,3%.

        count_weight
            Miscela alla copertura (una frazione) un termine basato sul numero
            ASSOLUTO di skill coperte, saturante: n / (n + count_k). Serve a
            togliere il vantaggio strutturale degli annunci con pochi
            requisiti, per i quali la frazione è alta anche con poche
            corrispondenze reali.

            Predefinito 0.15, scelto misurando su 100 CV quale valore elimina
            la distorsione senza introdurne una opposta. Le colonne indicano
            quante volte il motore sceglie un annuncio di ciascun livello,
            dove il valore atteso senza distorsioni è 33/33/33:

                peso    accuratezza   junior/mid/senior scelti
                0.00       37,0%          47 / 29 / 24
                0.15       44,0%          33 / 33 / 34
                0.25       44,0%          25 / 36 / 39
                0.40       43,0%          19 / 36 / 45

            A 0.15 e 0.25 l'accuratezza coincide, ma solo a 0.15 le scelte
            sono equilibrate: a parità di errori è preferibile che siano
            rumore anziché una tendenza sistematica.

        count_k
            Punto di saturazione del termine assoluto: con count_k=10, coprire
            10 skill vale 0.5. Va tenuto vicino al numero tipico di requisiti.
        """
        self.seniority_weight = float(seniority_weight)
        self.count_weight = float(count_weight)
        self.count_k = float(count_k)
        print(f"[JobMatchingEngine] Carico modello '{_E5_MODEL}'...")
        self._model = SentenceTransformer(_E5_MODEL)
        # Dizionario id → label per le skill ESCO
        self._skill_labels: dict[str, str] = {}
        skills_path = Path(__file__).resolve().parent.parent / "dataset" / "source" / "skills.json"
        if skills_path.exists():
            with open(skills_path, encoding="utf-8") as f:
                data = json.load(f)
            # skills.json è un dict {id: {id, label, ...}}
            if isinstance(data, dict):
                for item in data.values():
                    self._skill_labels[item["id"]] = item["label"]
            else:
                for item in data:
                    self._skill_labels[item["id"]] = item["label"]
        print(f"[JobMatchingEngine] Pronto — {len(self._skill_labels)} skill ESCO")

    # ── Encoding ─────────────────────────────────────────────────────────────

    def _encode(self, labels: list[str]) -> np.ndarray:
        """Encode con prefisso 'query: ' per E5 STS (similarity tra entità)."""
        if not labels:
            return np.zeros((0, 768), dtype=np.float32)
        return self._model.encode(
            [f"query: {l}" for l in labels],
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def _lbl(self, skill_id: str) -> str:
        return self._skill_labels.get(skill_id, skill_id)

    # ── Seniority ─────────────────────────────────────────────────────────────

    _LIVELLI = ("junior", "mid", "senior")

    @staticmethod
    def _livello_cv(cv_data: dict) -> str | None:
        """Livello del candidato: dichiarato, altrimenti dedotto dagli anni."""
        persona = cv_data.get("persona", {}) or {}
        liv = persona.get("seniority")
        if liv in JobMatchingEngine._LIVELLI:
            return liv
        anni = persona.get("years_of_experience", persona.get("years_experience"))
        if isinstance(anni, (int, float)):
            return "junior" if anni < 2 else ("mid" if anni <= 5 else "senior")
        return None

    @staticmethod
    def _livello_job(job_profile: dict) -> str | None:
        """
        Livello richiesto dall'annuncio.

        Priorità al campo prodotto dal job_parser (_detect_seniority), che
        funziona su annunci reali; `meta.seniority` esiste solo nel dataset
        sintetico, dove è iniettato dal generatore, e serve da riserva.
        """
        liv = (job_profile.get("seniority") or {}).get("level")
        if liv in JobMatchingEngine._LIVELLI:
            return liv
        liv = (job_profile.get("meta") or {}).get("seniority")
        return liv if liv in JobMatchingEngine._LIVELLI else None

    @classmethod
    def _allineamento_seniority(cls, cv_data: dict, job_profile: dict) -> float | None:
        """
        1.0 se i livelli coincidono, 0.5 se adiacenti, 0.0 se distanti due
        passi. None se uno dei due è ignoto: in quel caso il termine viene
        escluso dal punteggio invece di penalizzare l'annuncio, perché
        l'assenza del dato non è colpa della corrispondenza.
        """
        a, b = cls._livello_cv(cv_data), cls._livello_job(job_profile)
        if a is None or b is None:
            return None
        distanza = abs(cls._LIVELLI.index(a) - cls._LIVELLI.index(b))
        return 1.0 - distanza / 2.0

    # ── Match ─────────────────────────────────────────────────────────────────

    def match(self, cv_profile: dict, job_profile: dict) -> dict:
        """
        Args:
            cv_profile : output di main_parser.py
            job_profile: output di job_parser.py
        Returns:
            Dizionario con match_score, grade, matched_skills, skill_gap
        """
        candidate_id = cv_profile.get("cv_id", "candidato")
        job_id       = job_profile.get("job_id", "job")

        # ── Skill del candidato ──────────────────────────────────────────────
        cv_data      = cv_profile.get("cv", cv_profile)      # wrapper opzionale
        cv_skills    = cv_data.get("skills", {})
        cand_matches = cv_skills.get("all_matches", [])
        cand_ids     = list({m["id"] for m in cand_matches})
        cand_labels  = [self._lbl(sid) for sid in cand_ids]

        # ── Skill richieste dalla job ────────────────────────────────────────
        job_skills    = job_profile.get("skills", {})
        required_ids  = job_skills.get("required_ids",  [])
        preferred_ids = job_skills.get("preferred_ids", [])
        job_label_map = {m["id"]: m["label"]
                         for m in job_skills.get("all_matches", [])}

        if not required_ids:
            print("[JobMatchingEngine] Nessuna skill richiesta nel profilo job.")
            return self._empty(candidate_id, job_id)

        req_labels  = [job_label_map.get(sid, self._lbl(sid)) for sid in required_ids]
        pref_labels = [job_label_map.get(sid, self._lbl(sid)) for sid in preferred_ids]

        # ── Embedding ────────────────────────────────────────────────────────
        cand_emb = self._encode(cand_labels)    # (n_cand, 768)
        req_emb  = self._encode(req_labels)     # (n_req,  768)
        pref_emb = self._encode(pref_labels)    # (n_pref, 768)
        has_cand = cand_emb.shape[0] > 0

        # ── Matching skill richieste ─────────────────────────────────────────
        matched: list[dict] = []
        gap:     list[dict] = []

        for i, req_id in enumerate(required_ids):
            req_label = req_labels[i]

            # 1. Exact match (stesso ID ESCO)
            if req_id in cand_ids:
                matched.append({
                    "id": req_id, "label": req_label,
                    "match_type": "exact", "score": 1.0,
                })
                continue

            # 2. Semantic match
            if has_cand:
                sims     = cand_emb @ req_emb[i]
                best_idx = int(np.argmax(sims))
                best_sim = float(sims[best_idx])
            else:
                best_idx, best_sim = -1, 0.0

            if best_sim >= _SEM_THRESHOLD:
                matched.append({
                    "id": req_id, "label": req_label,
                    "match_type": "semantic",
                    "score":      round(best_sim, 4),
                    "matched_by": cand_labels[best_idx],
                })
            else:
                gap.append({
                    "id":    req_id,
                    "label": req_label,
                    "closest_known": {
                        "label":      cand_labels[best_idx] if best_idx >= 0 else "",
                        "similarity": round(best_sim, 4),
                    },
                })

        # ── Ranking gap con SkillGraph ────────────────────────────────────────
        # Ordina le skill mancanti per priorità di apprendimento usando:
        #   40% occupation_frequency (skill richieste da molte occupazioni → fondamentali)
        #   40% reuse_level          (cross-sector/transversal → imparare prima)
        #   20% prossimità           (skill vicine a quelle già note → più accessibili)
        # Questo sostituisce il semplice ranking per cosine similarity usato in precedenza.
        # La prossimità viene dalla gerarchia ufficiale ESCO quando
        # dataset/source/skill_relations.json è presente, altrimenti dalla
        # co-occorrenza ricostruita: la voce `fonte_prossimita` restituita da
        # rank_gap dichiara quale delle due è stata usata.
        if gap:
            sg = _get_skill_graph()
            gap_ids = [g["id"] for g in gap]
            ranked  = sg.rank_gap(gap_ids, cand_ids)
            # Arricchisci ogni entry del gap con i metadati del grafo
            rank_map = {r["id"]: r for r in ranked}
            for g in gap:
                info = rank_map.get(g["id"], {})
                g["priority"]          = info.get("priority", 0)
                g["priority_score"]    = info.get("priority_score", 0.0)
                g["occupation_freq"]   = info.get("occupation_freq", 0)
                g["reuse_level"]       = info.get("reuse_level", "")
                g["co_occurrence"]     = info.get("co_occurrence_score", 0.0)
                g["fonte_prossimita"]  = info.get("fonte_prossimita", "")
            gap.sort(key=lambda x: x["priority"])

        # ── Match score ──────────────────────────────────────────────────────
        # Required: peso 1.0 | Preferred: peso 0.5
        score_sum    = sum(m["score"] for m in matched)
        total_weight = float(len(required_ids))

        for i, pref_id in enumerate(preferred_ids):
            if pref_id in cand_ids:
                pref_s = 1.0
            elif has_cand and pref_emb.shape[0] > i:
                s = float(np.max(cand_emb @ pref_emb[i]))
                pref_s = s if s >= _SEM_THRESHOLD else 0.0
            else:
                pref_s = 0.0
            score_sum    += 0.5 * pref_s
            total_weight += 0.5

        skill_coverage = round(score_sum / total_weight, 4) if total_weight > 0 else 0.0

        # ── Correzione del vantaggio degli annunci corti ─────────────────────
        # La copertura è una frazione: con pochi requisiti al denominatore
        # basta poco per ottenere un valore alto. Si miscela quindi un termine
        # sul numero assoluto di skill coperte, saturante per non premiare
        # all'infinito gli annunci lunghi.
        skill_score = skill_coverage
        if self.count_weight > 0.0:
            n_coperte = float(len(matched))
            termine_assoluto = n_coperte / (n_coperte + self.count_k)
            skill_score = round(
                (1.0 - self.count_weight) * skill_coverage
                + self.count_weight * termine_assoluto,
                4,
            )

        # ── Occupation similarity ────────────────────────────────────────────
        work_exp     = cv_data.get("work_experience", [])
        cand_occ_lbl = work_exp[0]["label"] if work_exp else ""
        job_occ_lbl  = job_profile.get("occupation", {}).get("label", "")
        occ_sim      = 0.0
        if cand_occ_lbl and job_occ_lbl:
            occ_emb = self._encode([cand_occ_lbl, job_occ_lbl])
            occ_sim = round(float(occ_emb[0] @ occ_emb[1]), 4)

        # ── Score finale composito ───────────────────────────────────────────
        # 75% copertura skill richieste  +  25% similarità occupazione
        # Se occupation non è disponibile (CV senza WE o job senza occ), usa solo skill coverage
        if occ_sim > 0.0:
            match_score = round(0.75 * skill_score + 0.25 * occ_sim, 4)
        else:
            match_score = skill_score

        # ── Allineamento del livello di esperienza ───────────────────────────
        # Applicato per ultimo sul punteggio composito: se il livello di una
        # delle due parti è ignoto il termine viene omesso, così un annuncio
        # senza indicazioni non risulta penalizzato rispetto a uno esplicito.
        sen_align = self._allineamento_seniority(cv_data, job_profile)
        if self.seniority_weight > 0.0 and sen_align is not None:
            match_score = round(
                (1.0 - self.seniority_weight) * match_score
                + self.seniority_weight * sen_align,
                4,
            )

        return {
            "candidate_id":    candidate_id,
            "job_id":          job_id,
            "match_score":     match_score,
            "skill_coverage":  skill_coverage,
            "grade":           _match_grade(match_score),
            "occupation_match": {
                "candidate_label": cand_occ_lbl,
                "job_label":       job_occ_lbl,
                "similarity":      occ_sim,
            },
            "matched_skills":  matched,
            "skill_gap":       gap,
        }

    def _empty(self, candidate_id: str, job_id: str) -> dict:
        return {
            "candidate_id": candidate_id, "job_id": job_id,
            "match_score": 0.0, "skill_coverage": 0.0, "grade": "insufficiente",
            "occupation_match": {"candidate_label":"","job_label":"","similarity":0.0},
            "matched_skills": [], "skill_gap": [],
        }


# ── CLI Scenario 2 ────────────────────────────────────────────────────────────

def main_job_match():
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Matching CV ↔ Job Description")
    ap.add_argument("--cv",  required=True,
                    help="JSON output di main_parser.py")
    ap.add_argument("--job", required=True,
                    help="JSON output di job_parser.py")
    ap.add_argument("--out", default="outputs/match_result.json",
                    help="File output JSON (default: outputs/match_result.json)")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent.parent
    cv_path  = Path(args.cv)  if Path(args.cv).is_absolute()  else base / args.cv
    job_path = Path(args.job) if Path(args.job).is_absolute() else base / args.job

    with open(cv_path,  encoding="utf-8") as f: cv_profile  = json.load(f)
    with open(job_path, encoding="utf-8") as f: job_profile = json.load(f)

    engine = JobMatchingEngine()
    result = engine.match(cv_profile, job_profile)

    out_path = base / args.out
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[matching_engine] → {out_path}")
    print(f"  Candidato    : {result['candidate_id']}")
    print(f"  Job          : {result['job_id']}")
    print(f"  Match score  : {result['match_score']:.1%}  ({result['grade']})")
    print(f"  Skill coperte: {len(result['matched_skills'])}")
    print(f"  Skill gap    : {len(result['skill_gap'])}")
    occ = result["occupation_match"]
    if occ["candidate_label"] and occ["job_label"]:
        print(f"  Occ candidato: {occ['candidate_label']}")
        print(f"  Occ richiesta: {occ['job_label']}  (sim {occ['similarity']:.2f})")
    if result["skill_gap"]:
        print(f"\n  Roadmap apprendimento (top 5):")
        for g in result["skill_gap"][:5]:
            near = g.get("closest_known", {})
            freq  = g.get("occupation_freq", 0)
            reuse = g.get("reuse_level", "")
            score = g.get("priority_score", 0.0)
            print(f"    [{g['priority']}] {g['label']}")
            print(f"          freq={freq} occ | {reuse} | priority_score={score:.3f}")
            if near.get("label"):
                print(f"          ← skill correlata: '{near['label']}'"
                      f" (sim {near['similarity']:.2f})")


if __name__ == "__main__":
    # Se il primo argomento è 'job', usa il motore Scenario 2
    if len(sys.argv) > 1 and sys.argv[1] == "job":
        sys.argv.pop(1)
        main_job_match()
    else:
        main()
