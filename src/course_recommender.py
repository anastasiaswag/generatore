"""
course_recommender.py  —  SkillPath AI
=======================================
Modulo di raccomandazione corsi basato sul gap analysis.

Dato l'output di JobMatchingEngine.match() (campo "skill_gap"),
suggerisce corsi Coursera per colmare le skill mancanti,
seguendo la priorità calcolata da SkillGraph.

PREREQUISITO:
    Eseguire prima build_course_index.py per generare course_index.json

USO STANDALONE (dalla radice del progetto):
    python src/course_recommender.py --gap outputs/end_to_end_results.json
    python src/course_recommender.py --gap outputs/end_to_end_results.json --top-skills 5

INTEGRAZIONE:
    from course_recommender import CourseRecommender
    rec = CourseRecommender("config/course_index.json")
    roadmap = rec.recommend(match_result["skill_gap"])
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)
DEFAULT_INDEX = BASE_DIR / "config" / "course_index.json"


class CourseRecommender:
    """
    Raccomanda corsi per colmare il gap di skill identificato da JobMatchingEngine.

    Il gap è già ordinato per priorità di apprendimento da SkillGraph:
    prima le skill fondamentali e trasversali, poi quelle più specifiche.
    Il recommender rispetta quell'ordine.
    """

    def __init__(self, index_path: str | Path = DEFAULT_INDEX):
        index_path = Path(index_path)
        if not index_path.exists():
            raise FileNotFoundError(
                f"course_index.json non trovato: {index_path}\n"
                f"  Esegui prima: python src/build_course_index.py --csv config/Coursera.csv"
            )
        with open(index_path, encoding="utf-8") as f:
            self._index: dict[str, list[dict]] = json.load(f)
        self._n_skills = len(self._index)

    # ── API pubblica ──────────────────────────────────────────────────────────

    def recommend(
        self,
        skill_gap:        list[dict],
        top_skills:       int = 5,
        courses_per_skill: int = 3,
        min_rating:       float = 4.0,
        level_filter:     str | None = None,
    ) -> list[dict]:
        """
        Per ogni skill mancante (ordinata per priorità SkillGraph),
        restituisce i corsi più pertinenti.

        Args:
            skill_gap:         lista di skill mancanti da JobMatchingEngine.match()
            top_skills:        quante skill considerare (default 5)
            courses_per_skill: max corsi per skill (default 3)
            min_rating:        filtra corsi con rating ≥ soglia (default 4.0)
            level_filter:      "beginner"|"intermediate"|"advanced"|None

        Returns:
            Lista di dict {skill_id, skill_label, priority, courses: [...]}
        """
        result = []

        for skill in skill_gap[:top_skills]:
            skill_id = skill.get("id", "")
            courses  = self._index.get(skill_id, [])

            # Filtra per rating minimo
            if min_rating > 0:
                courses = [c for c in courses if c.get("rating", 0) >= min_rating]

            # Filtra per livello se specificato
            if level_filter:
                courses = [c for c in courses
                           if c.get("level", "") == level_filter.lower()]

            # Già ordinati per rating desc in fase di build
            courses = courses[:courses_per_skill]

            result.append({
                "skill_id":       skill_id,
                "skill_label":    skill.get("label", skill_id),
                "priority":       skill.get("priority", 0),
                "priority_score": skill.get("priority_score", 0.0),
                "reuse_level":    skill.get("reuse_level", ""),
                "courses":        courses,
                "n_available":    len(self._index.get(skill_id, [])),
            })

        return result

    def coverage(self, skill_gap: list[dict]) -> dict:
        """
        Statistiche di copertura: quante skill del gap hanno almeno un corso.
        """
        total   = len(skill_gap)
        covered = sum(1 for s in skill_gap if s.get("id") in self._index)
        return {
            "gap_size":     total,
            "covered":      covered,
            "not_covered":  total - covered,
            "coverage_pct": round(covered / total * 100, 1) if total else 0.0,
        }

    def stats(self) -> dict:
        """Statistiche generali sull'indice."""
        n_courses = sum(len(v) for v in self._index.values())
        return {
            "skill_esco_coperte": self._n_skills,
            "corsi_totali":       n_courses,
            "media_per_skill":    round(n_courses / self._n_skills, 1) if self._n_skills else 0,
        }


# ── Funzione di stampa roadmap ────────────────────────────────────────────────

def print_roadmap(roadmap: list[dict], job_title: str = "") -> None:
    """Stampa la roadmap di apprendimento in formato leggibile."""
    if not roadmap:
        print("  Nessuna raccomandazione disponibile.")
        return

    header = f"Roadmap di apprendimento"
    if job_title:
        header += f"  —  {job_title}"
    print(f"\n{'═'*62}")
    print(f"  {header}")
    print(f"{'═'*62}")

    for item in roadmap:
        found = len(item["courses"])
        avail = item["n_available"]
        reuse = item.get("reuse_level", "")
        reuse_tag = f"  [{reuse}]" if reuse else ""
        cov_tag   = f"  ({avail} corsi disponibili)" if avail > 0 else "  (nessun corso)"

        print(f"\n  [{item['priority']}] {item['skill_label']}{reuse_tag}{cov_tag}")

        if not item["courses"]:
            print(f"      ⚠  Nessun corso trovato per questa skill")
            continue

        for c in item["courses"]:
            stars = f"★{c['rating']:.1f}" if c.get("rating") else ""
            level = c.get("level", "")
            prov  = c.get("provider", "")
            url   = c.get("url", "")
            tag   = f"[{level}]" if level else ""
            print(f"      → {c['title'][:55]}")
            if prov or stars or tag:
                print(f"         {prov}  {stars}  {tag}")
            if url:
                print(f"         {url}")


# ── CLI standalone ────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Raccomandazione corsi da skill gap")
    ap.add_argument("--gap",    required=True,
                    help="File JSON con risultati matching (es. end_to_end_results.json)")
    ap.add_argument("--index",  default=str(DEFAULT_INDEX),
                    help=f"course_index.json (default: {DEFAULT_INDEX})")
    ap.add_argument("--top-skills",       type=int,   default=5,
                    help="Numero max di skill da coprire (default 5)")
    ap.add_argument("--courses-per-skill",type=int,   default=3,
                    help="Corsi per skill (default 3)")
    ap.add_argument("--min-rating",       type=float, default=4.0,
                    help="Rating minimo corsi (default 4.0)")
    ap.add_argument("--level",            default=None,
                    help="Filtra per livello: beginner|intermediate|advanced")
    ap.add_argument("--job-idx",          type=int,   default=0,
                    help="Indice del risultato nel JSON (default 0 = primo job)")
    args = ap.parse_args()

    gap_path = Path(args.gap) if Path(args.gap).is_absolute() \
               else BASE_DIR / args.gap
    if not gap_path.exists():
        print(f"[recommender] ERRORE: file non trovato: {gap_path}")
        sys.exit(1)

    with open(gap_path, encoding="utf-8") as f:
        results = json.load(f)

    # Supporta sia lista che singolo oggetto
    if isinstance(results, list):
        if args.job_idx >= len(results):
            print(f"[recommender] ERRORE: indice {args.job_idx} fuori range "
                  f"(0–{len(results)-1})")
            sys.exit(1)
        result = results[args.job_idx]
    else:
        result = results

    skill_gap = result.get("skill_gap", [])
    job_title = (result.get("meta", {}).get("ruolo")
                 or result.get("raw_title")
                 or result.get("job_id", ""))

    rec = CourseRecommender(args.index)

    # Statistiche indice
    s = rec.stats()
    print(f"\n[recommender] Indice: {s['skill_esco_coperte']} skill ESCO "
          f"→ {s['corsi_totali']} corsi  (avg {s['media_per_skill']} per skill)")

    # Copertura gap
    cov = rec.coverage(skill_gap)
    print(f"[recommender] Gap:    {cov['gap_size']} skill mancanti  "
          f"→ copertura {cov['covered']}/{cov['gap_size']} ({cov['coverage_pct']}%)")

    # Raccomandazioni
    roadmap = rec.recommend(
        skill_gap,
        top_skills        = args.top_skills,
        courses_per_skill = args.courses_per_skill,
        min_rating        = args.min_rating,
        level_filter      = args.level,
    )

    print_roadmap(roadmap, job_title)


if __name__ == "__main__":
    main()
