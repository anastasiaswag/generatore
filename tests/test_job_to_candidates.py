"""
test_job_to_candidates.py  —  SkillPath AI
===========================================
Scenario recruiter: dato un annuncio di lavoro, trova i candidati
più compatibili tra tutti i CV parsati in cv_batch_results.json.

Uso (dalla radice del progetto):
    # Lista gli annunci disponibili con indice
    python tests/test_job_to_candidates.py --list

    # Matcha il job #4 (IoT Platform Engineer) contro tutti i CV
    python tests/test_job_to_candidates.py --job 4

    # Filtra per seniority del candidato
    python tests/test_job_to_candidates.py --job 4 --seniority senior

    # Top 20 candidati
    python tests/test_job_to_candidates.py --job 4 --top 20
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent  # radice progetto (tests/ è un livello sotto)
SRC_DIR   = BASE_DIR / "src"
JOBS_FILE = BASE_DIR / "outputs" / "batch_job_results.json"
CVS_FILE  = BASE_DIR / "outputs" / "cv_batch_results.json"


def list_jobs(jobs: list[dict], n: int = 30) -> None:
    print(f"\n  {'#':>4}  {'Area':<14}  {'Ruolo':<42}  {'Skill req':>9}")
    print(f"  {'-'*75}")
    for i, j in enumerate(jobs[:n]):
        m = j.get("meta", {})
        n_req = len(j["skills"]["required_ids"])
        ruolo = (m.get("ruolo") or j.get("raw_title") or "")[:42]
        print(f"  {i:>4}.  {m.get('area','?'):<14}  {ruolo:<42}  {n_req:>9}")
    if len(jobs) > n:
        print(f"  ... e altri {len(jobs)-n} annunci. Usa --list-all per vederli tutti.")


def main():
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Ranking candidati per una job description")
    ap.add_argument("--job",      type=int, default=None,
                    help="Indice del job in batch_job_results.json (usa --list per vederli)")
    ap.add_argument("--list",     action="store_true",
                    help="Mostra la lista degli annunci disponibili")
    ap.add_argument("--list-all", action="store_true",
                    help="Mostra tutti gli annunci")
    ap.add_argument("--top",      type=int, default=10,
                    help="Numero di top candidati (default 10)")
    ap.add_argument("--seniority",default=None,
                    help="Filtra candidati per seniority: junior | mid | senior")
    ap.add_argument("--out",      default="outputs/job_to_candidates_results.json",
                    help="File output JSON")
    args = ap.parse_args()

    # ── Carica job descriptions ────────────────────────────────────────────────
    if not JOBS_FILE.exists():
        print(f"[recruiter] ERRORE: {JOBS_FILE} non trovato.")
        print("  Esegui prima: python batch_test_job_parser.py")
        sys.exit(1)

    with open(JOBS_FILE, encoding="utf-8") as f:
        all_jobs = json.load(f)

    # ── Modalità lista ─────────────────────────────────────────────────────────
    if args.list or args.list_all:
        n = len(all_jobs) if args.list_all else 50
        list_jobs(all_jobs, n)
        print(f"\n  Usa --job N per selezionare un annuncio.")
        sys.exit(0)

    if args.job is None:
        print("[recruiter] Specifica un annuncio con --job N  (usa --list per vederli)")
        list_jobs(all_jobs, 20)
        sys.exit(1)

    if args.job < 0 or args.job >= len(all_jobs):
        print(f"[recruiter] ERRORE: indice {args.job} fuori range (0–{len(all_jobs)-1})")
        sys.exit(1)

    job = all_jobs[args.job]
    job_meta  = job.get("meta", {})
    job_title = job_meta.get("ruolo") or job.get("raw_title") or f"job_{args.job}"

    print(f"\n{'═'*62}")
    print(f"  SkillPath AI — Ranking Candidati")
    print(f"{'═'*62}")
    print(f"\n  Annuncio selezionato  : {job_title}")
    print(f"  Area                  : {job_meta.get('area','?')}")
    print(f"  Azienda               : {job_meta.get('azienda','?')}")
    print(f"  Skill richieste       : {len(job['skills']['required_ids'])}")
    print(f"  Skill preferibili     : {len(job['skills']['preferred_ids'])}")
    if job["skills"]["all_matches"]:
        print("  Skill cercate:")
        for m in sorted(job["skills"]["all_matches"],
                        key=lambda x: x["score"], reverse=True)[:6]:
            tag = "[REQ]" if m["id"] in job["skills"]["required_ids"] else "[PREF]"
            print(f"    {tag} {m['label']}")

    # ── Carica CV parsati ──────────────────────────────────────────────────────
    if not CVS_FILE.exists():
        print(f"\n[recruiter] ERRORE: {CVS_FILE} non trovato.")
        print("  Esegui prima: python batch_parse_cvs.py")
        sys.exit(1)

    print(f"\n  Carico CV da {CVS_FILE.name}...")
    with open(CVS_FILE, encoding="utf-8") as f:
        all_cvs = json.load(f)

    # Filtro seniority
    if args.seniority:
        all_cvs = [
            cv for cv in all_cvs
            if cv.get("cv", {}).get("persona", {}).get("seniority") == args.seniority
        ]
        print(f"  Filtro seniority '{args.seniority}': {len(all_cvs)} CV")
    else:
        print(f"  CV disponibili: {len(all_cvs)}")

    if not all_cvs:
        print("[recruiter] Nessun CV dopo il filtro.")
        sys.exit(1)

    # ── Matching ───────────────────────────────────────────────────────────────
    print(f"\n  Calcolo match score per {len(all_cvs)} candidati...")
    sys.path.insert(0, str(SRC_DIR))
    from matching_engine import JobMatchingEngine
    engine = JobMatchingEngine()

    results = []
    t0 = time.time()

    for i, cv in enumerate(all_cvs, 1):
        try:
            result = engine.match(cv, job)
        except Exception:
            continue

        # Aggiungi info candidato
        cv_data   = cv.get("cv", cv)
        persona   = cv_data.get("persona", {})
        work_exp  = cv_data.get("work_experience", [])
        gt        = cv.get("ground_truth", {})

        result["candidato"] = {
            "cv_id":     cv.get("cv_id", f"cv_{i}"),
            "seniority": persona.get("seniority", "?"),
            "anni_exp":  persona.get("years_of_experience", 0),
            "ruolo_cv":  work_exp[0]["label"] if work_exp else "",
            "template":  cv.get("template", ""),
            "gt_occupation": gt.get("target_occupation_label", ""),
        }
        results.append(result)

        if i % 100 == 0:
            elapsed = time.time() - t0
            eta = elapsed / i * (len(all_cvs) - i)
            print(f"    [{i}/{len(all_cvs)}]  {elapsed:.0f}s  ETA {eta:.0f}s")

    elapsed_tot = time.time() - t0
    print(f"  ✓ Completato in {elapsed_tot:.1f}s")

    # ── Ranking ────────────────────────────────────────────────────────────────
    results.sort(key=lambda r: r["match_score"], reverse=True)

    # ── Output console ─────────────────────────────────────────────────────────
    print(f"\n{'═'*62}")
    print(f"  TOP {args.top} CANDIDATI  —  {job_title}")
    print(f"{'═'*62}")

    for rank, r in enumerate(results[:args.top], 1):
        c       = r["candidato"]
        score   = r["match_score"]
        grade   = r["grade"]
        matched = len(r.get("matched_skills", []))
        gap     = len(r.get("skill_gap", []))
        occ_sim = r.get("occupation_match", {}).get("similarity", 0.0)

        print(f"\n  #{rank}  {score:.1%}  ({grade})  —  {c['seniority'].upper()}  "
              f"{c['anni_exp']:.0f}aa exp")
        print(f"      Ruolo nel CV    : {c['ruolo_cv'][:55]}")
        print(f"      Occupazione GT  : {c['gt_occupation'][:55]}")
        print(f"      Skill coperte   : {matched}  |  Gap: {gap}  "
              f"|  Occ similarity: {occ_sim:.2f}")
        if r.get("matched_skills"):
            skills_str = ", ".join(m["label"] for m in r["matched_skills"][:3])
            print(f"      Match skill     : {skills_str}")
        if r.get("skill_gap") and rank <= 3:
            gap_str = ", ".join(g["label"] for g in r["skill_gap"][:3])
            print(f"      Skill mancanti  : {gap_str}")

    # ── Distribuzione score ────────────────────────────────────────────────────
    scores = [r["match_score"] for r in results]
    grade_counts: dict[str, int] = {}
    for r in results:
        grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

    print(f"\n{'─'*62}")
    print(f"  Statistiche su {len(results)} candidati:")
    print(f"    Score medio  : {sum(scores)/len(scores):.1%}")
    print(f"    Score max    : {max(scores):.1%}")
    print(f"    Score mediano: {sorted(scores)[len(scores)//2]:.1%}")
    print("    Distribuzione grade:")
    for g in ["ottimo", "buono", "discreto", "insufficiente"]:
        n = grade_counts.get(g, 0)
        bar = "█" * (n * 25 // max(len(results), 1))
        print(f"      {g:<14} {n:>4}  {bar}")

    # ── Salva risultati ────────────────────────────────────────────────────────
    out_path = BASE_DIR / args.out
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  → Risultati salvati in {out_path.name}")
    print(f"{'═'*62}\n")


if __name__ == "__main__":
    main()
