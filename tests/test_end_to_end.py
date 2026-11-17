"""
test_end_to_end.py  —  SkillPath AI
=====================================
Test end-to-end: parsa un CV e lo abbina alle 1000 job description
già elaborate in batch_job_results.json.

Uso (dalla radice del progetto):
    python tests/test_end_to_end.py                          # usa samples/cv_test.pdf
    python tests/test_end_to_end.py --cv samples/015_MISTHIR_Ing_Mecc_Senior.pdf
    python tests/test_end_to_end.py --cv mio_cv.pdf --top 20
    python tests/test_end_to_end.py --cv mio_cv.pdf --area Informatica
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (tests/ è un livello sotto)
SRC_DIR  = BASE_DIR / "src"


def main():
    ap = argparse.ArgumentParser(description="SkillPath AI — Test end-to-end CV ↔ Job")
    ap.add_argument("--cv",   default="samples/cv_test.pdf",
                    help="File CV da parsare (PDF/DOCX, relativo alla radice del progetto)")
    ap.add_argument("--jobs", default="outputs/batch_job_results.json",
                    help="File JSON con le job description già parsate")
    ap.add_argument("--top",  type=int, default=10,
                    help="Numero di top match da mostrare (default 10)")
    ap.add_argument("--area", default=None,
                    help="Filtra job per area (Informatica | Meccanica | Elettronica)")
    ap.add_argument("--out",  default="outputs/end_to_end_results.json",
                    help="File output JSON con tutti i match (default: outputs/end_to_end_results.json)")
    args = ap.parse_args()

    # ── 1. Parsa il CV ─────────────────────────────────────────────────────────
    cv_path = Path(args.cv) if Path(args.cv).is_absolute() else BASE_DIR / args.cv
    if not cv_path.exists():
        print(f"[e2e] ERRORE: CV non trovato: {cv_path}")
        sys.exit(1)

    print(f"\n{'═'*60}")
    print(f"  SkillPath AI — Test end-to-end")
    print(f"{'═'*60}")
    print(f"\n[1/3] Parsing CV: {cv_path.name}")
    t0 = time.time()

    sys.path.insert(0, str(SRC_DIR))
    from main_parser import MainParser
    parser = MainParser()
    cv_profile = parser.parse_cv(str(cv_path))

    cv_skills = cv_profile.get("cv", {}).get("skills", {})
    cv_occ    = cv_profile.get("cv", {}).get("work_experience", [])
    print(f"  ✓ Parsing completato in {time.time()-t0:.1f}s")
    print(f"  Occupazione rilevata : {cv_occ[0]['label'] if cv_occ else 'nessuna'}")
    print(f"  Skill trovate        : {len(cv_skills.get('all_matches', []))}")
    print(f"    Essential          : {len(cv_skills.get('essential_ids', []))}")
    print(f"    Optional           : {len(cv_skills.get('optional_ids', []))}")

    if cv_skills.get("all_matches"):
        print("  Top skill del candidato:")
        for m in sorted(cv_skills["all_matches"], key=lambda x: x["score"], reverse=True)[:6]:
            print(f"    {m['score']:.3f}  {m['label']}")

    # ── 2. Carica job descriptions già parsate ─────────────────────────────────
    jobs_path = Path(args.jobs) if Path(args.jobs).is_absolute() else BASE_DIR / args.jobs
    if not jobs_path.exists():
        print(f"\n[e2e] ERRORE: {jobs_path} non trovato.")
        print("  Esegui prima: python batch_test_job_parser.py")
        sys.exit(1)

    print(f"\n[2/3] Carico job descriptions da {jobs_path.name}...")
    with open(jobs_path, encoding="utf-8") as f:
        all_jobs = json.load(f)

    # Filtra per area se richiesto
    if args.area:
        all_jobs = [j for j in all_jobs
                    if j.get("meta", {}).get("area", "") == args.area]
        print(f"  Filtro area '{args.area}': {len(all_jobs)} job")
    else:
        print(f"  Job disponibili: {len(all_jobs)}")

    if not all_jobs:
        print("[e2e] Nessuna job description dopo il filtro.")
        sys.exit(1)

    # ── 3. Matching ────────────────────────────────────────────────────────────
    print(f"\n[3/3] Matching CV ↔ {len(all_jobs)} job descriptions...")
    from matching_engine import JobMatchingEngine
    engine = JobMatchingEngine()

    results = []
    t1 = time.time()

    for i, job in enumerate(all_jobs, 1):
        # Salta job senza skill (nessun criterio di match)
        if not job["skills"].get("required_ids"):
            continue

        try:
            result = engine.match(cv_profile, job)
        except Exception as e:
            continue

        result["meta"] = job.get("meta", {})
        result["raw_title"] = job.get("raw_title", "")
        results.append(result)

        if i % 100 == 0:
            elapsed = time.time() - t1
            eta = elapsed / i * (len(all_jobs) - i)
            print(f"  [{i}/{len(all_jobs)}]  {elapsed:.0f}s  ETA {eta:.0f}s")

    elapsed_total = time.time() - t1
    print(f"  ✓ Matching completato in {elapsed_total:.1f}s")

    # ── Ranking ────────────────────────────────────────────────────────────────
    results.sort(key=lambda r: r["match_score"], reverse=True)

    # ── Output console ─────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  TOP {args.top} MATCH  —  {cv_path.name}")
    print(f"{'═'*60}")
    print(f"  {'#':>3}  {'Score':>6}  {'Grade':<12}  {'Ruolo / Titolo'}")
    print(f"  {'-'*57}")

    for rank, r in enumerate(results[:args.top], 1):
        meta   = r.get("meta", {})
        ruolo  = meta.get("ruolo") or r.get("raw_title") or r.get("job_id", "")
        area   = meta.get("area", "")
        score  = r["match_score"]
        grade  = r["grade"]
        n_match = len(r.get("matched_skills", []))
        n_gap   = len(r.get("skill_gap", []))
        area_tag = f"[{area}]" if area else ""
        print(f"  {rank:>3}.  {score:>5.1%}  {grade:<12}  {ruolo[:45]}  {area_tag}")
        print(f"       skill coperte: {n_match}  |  gap: {n_gap}")
        if r.get("matched_skills"):
            top_sk = [m["label"] for m in r["matched_skills"][:3]]
            print(f"       match: {', '.join(top_sk)}")
        if r.get("skill_gap") and rank <= 3:
            top_gap = [g["label"] for g in r["skill_gap"][:3]]
            print(f"       gap:   {', '.join(top_gap)}")
        print()

    # ── Statistiche aggregate ──────────────────────────────────────────────────
    if results:
        scores = [r["match_score"] for r in results]
        grade_counts = {}
        for r in results:
            grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

        print(f"{'─'*60}")
        print(f"  Statistiche su {len(results)} job con skill:")
        print(f"    Score medio  : {sum(scores)/len(scores):.1%}")
        print(f"    Score max    : {max(scores):.1%}")
        print(f"    Score mediano: {sorted(scores)[len(scores)//2]:.1%}")
        print("    Distribuzione grade:")
        for g, n in sorted(grade_counts.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * (n * 20 // len(results))
            print(f"      {g:<14} {n:>4}  {bar}")

    # ── Salva JSON completo ────────────────────────────────────────────────────
    out_path = BASE_DIR / args.out
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  → Risultati completi salvati in {out_path.name}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
