"""
valida_recruiter.py  —  SkillPath AI
=====================================
Valuta la direzione INVERSA del matching: dato un annuncio, ordinare i
candidati.

PERCHÉ SERVE UN TEST A PARTE
────────────────────────────
analysis/valida_matching_engine.py misura il verso candidato → offerta: un CV
contro molti annunci. Il verso opposto — un annuncio contro molti CV — usa la
stessa funzione di punteggio ma NON è equivalente, perché la formula non è
simmetrica.

Nel verso candidato → offerta il denominatore della copertura cambia a ogni
annuncio, ed è da lì che nasceva la preferenza per le posizioni junior
corretta con `count_weight` (vedi la docstring di JobMatchingEngine).

Nel verso annuncio → candidati il denominatore è fisso, quindi quel problema
non si pone. Ma il termine introdotto per correggerlo — il numero ASSOLUTO di
competenze coperte — qui cambia natura: premia chi ne copre di più in valore
assoluto, e chi ha un curriculum più ricco ne copre di più anche solo per
ampiezza. Nel dataset la variabilità è consistente: un CV del 90° percentile
ha 23 competenze estratte contro le 7 del 10°, più del triplo.

Il rischio da verificare è quindi che il sistema favorisca i curriculum lunghi
invece dei più pertinenti — una distorsione di segno opposto a quella
corretta, e generata proprio dalla correzione.

METRICHE
────────
Per ogni annuncio si ordinano tutti i CV del campione e si osserva:

  Precision@k        quota di annunci con almeno un candidato dell'occupazione
                     giusta nelle prime k posizioni
  MRR                posizione reciproca media del primo candidato corretto
  Baseline casuale   quota attesa pescando candidati a caso

  Skill medie top-10 numero medio di competenze estratte dai CV in cima alla
                     classifica, confrontato con la media del campione. Se i
                     primi dieci hanno molte più competenze della media, il
                     motore sta premiando l'ampiezza del curriculum invece
                     della pertinenza: è questo il segnale da cercare.

  Correlazione       coefficiente fra il punteggio assegnato e il numero di
                     competenze del CV, calcolato sui soli candidati
                     dell'occupazione SBAGLIATA. Fra i non pertinenti, il
                     punteggio dovrebbe essere basso a prescindere dalla
                     lunghezza: una correlazione alta indica che la lunghezza
                     da sola guadagna posizioni.

Uso (dalla radice del progetto):
    python analysis/valida_recruiter.py
    python analysis/valida_recruiter.py --max-jobs 30 --max-cvs 300
    python analysis/valida_recruiter.py --count-weight 0.0   # confronto A/B
"""

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

CVS_FILE = BASE_DIR / "outputs" / "cv_batch_results.json"
JOBS_FILE = BASE_DIR / "outputs" / "job_gt_batch_results.json"
OUT_FILE = BASE_DIR / "outputs" / "recruiter_eval.json"

SEP = "─" * 65


def n_skill(cv: dict) -> int:
    s = (cv.get("cv") or {}).get("skills", {})
    return len(set(s.get("essential_ids", []) + s.get("optional_ids", [])))


def correlazione(xs: list[float], ys: list[float]) -> float:
    """Coefficiente di Pearson, senza dipendenze esterne."""
    if len(xs) < 3:
        return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def run(max_jobs: int, max_cvs: int, top_k: int, seed: int,
        sen_w: float | None, cnt_w: float | None) -> dict:
    from matching_engine import JobMatchingEngine

    if not CVS_FILE.exists() or not JOBS_FILE.exists():
        print(f"[ERRORE] Servono {CVS_FILE.name} e {JOBS_FILE.name}")
        sys.exit(1)

    cvs = json.loads(CVS_FILE.read_text(encoding="utf-8"))
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    rng = random.Random(seed)

    # Solo annunci per cui esiste almeno un candidato della stessa occupazione
    occ_cv: dict[str, list] = {}
    for c in cvs:
        o = (c.get("ground_truth") or {}).get("target_occupation_id", "")
        if o:
            occ_cv.setdefault(o, []).append(c)

    jobs_ok = [j for j in jobs
               if (j.get("ground_truth") or {}).get("target_occupation_id", "") in occ_cv]
    campione_jobs = (jobs_ok if len(jobs_ok) <= max_jobs
                     else rng.sample(jobs_ok, max_jobs))

    campione_cvs = cvs if len(cvs) <= max_cvs else rng.sample(cvs, max_cvs)
    # Garantisce che i candidati corretti degli annunci scelti siano nel pool
    presenti = {c.get("cv_id") for c in campione_cvs}
    for j in campione_jobs:
        o = j["ground_truth"]["target_occupation_id"]
        for c in occ_cv[o]:
            if c.get("cv_id") not in presenti:
                campione_cvs.append(c)
                presenti.add(c.get("cv_id"))

    kw = {}
    if sen_w is not None:
        kw["seniority_weight"] = sen_w
    if cnt_w is not None:
        kw["count_weight"] = cnt_w
    engine = JobMatchingEngine(**kw)
    print(f"[config] seniority_weight={engine.seniority_weight}  "
          f"count_weight={engine.count_weight}")
    print(f"[valida_recruiter] {len(campione_jobs)} annunci × "
          f"{len(campione_cvs)} candidati\n")

    media_pool = st.mean([n_skill(c) for c in campione_cvs])

    hit1 = hit3 = hitk = 0
    mrr = 0.0
    base_sum = 0.0
    skill_top: list[float] = []
    corr_valori: list[float] = []

    for i, job in enumerate(campione_jobs, 1):
        target = job["ground_truth"]["target_occupation_id"]

        punteggi = []
        for cv in campione_cvs:
            try:
                m = engine.match(cv, job)
            except Exception:
                continue
            punteggi.append((m["match_score"], cv))
        if not punteggi:
            continue
        punteggi.sort(key=lambda x: x[0], reverse=True)

        occ_ordinate = [
            (c.get("ground_truth") or {}).get("target_occupation_id", "")
            for _, c in punteggi
        ]
        rango = next((k + 1 for k, o in enumerate(occ_ordinate) if o == target), None)
        if rango == 1:
            hit1 += 1
        if rango is not None and rango <= 3:
            hit3 += 1
        if rango is not None and rango <= top_k:
            hitk += 1
        if rango is not None:
            mrr += 1.0 / rango

        n_corretti = sum(1 for o in occ_ordinate if o == target)
        base_sum += n_corretti / len(punteggi)

        skill_top.append(st.mean([n_skill(c) for _, c in punteggi[:10]]))

        # Correlazione punteggio ↔ lunghezza del CV fra i NON pertinenti
        sbagliati = [(s, n_skill(c)) for s, c in punteggi
                     if (c.get("ground_truth") or {}).get("target_occupation_id", "") != target]
        if len(sbagliati) >= 20:
            corr_valori.append(correlazione([s for s, _ in sbagliati],
                                            [float(n) for _, n in sbagliati]))

        print(f"  [{i}/{len(campione_jobs)}] {job.get('job_id','?')[:28]:<30} "
              f"rango primo candidato corretto = {rango}")

    n = len(campione_jobs)
    p1, p3, pk = hit1 / n, hit3 / n, hitk / n
    base = base_sum / n
    media_top = st.mean(skill_top) if skill_top else 0.0
    corr = st.mean(corr_valori) if corr_valori else 0.0

    print(f"\n{SEP}")
    print("  RISULTATI — direzione annuncio → candidati")
    print(SEP)
    print(f"  Annunci valutati            : {n}")
    print(f"  Candidati nel pool          : {len(campione_cvs)}")
    print(SEP)
    print(f"  Precision@1                 : {p1*100:.1f}%")
    print(f"  Precision@3                 : {p3*100:.1f}%")
    print(f"  Precision@{top_k:<3}               : {pk*100:.1f}%")
    print(f"  MRR                         : {mrr/n:.3f}")
    print(f"  Baseline casuale            : {base*100:.1f}%")
    print(SEP)
    print("  CONTROLLO DISTORSIONE PER LUNGHEZZA DEL CV")
    print(f"  Skill medie nel pool        : {media_pool:.1f}")
    print(f"  Skill medie nei primi 10    : {media_top:.1f}")
    print(f"  Rapporto                    : {media_top/media_pool:.2f}x")
    print(f"  Correlazione punteggio↔lunghezza")
    print(f"    fra candidati NON pertinenti: {corr:+.3f}")
    print(SEP)

    if media_top / media_pool > 1.35 or corr > 0.4:
        print("  LETTURA: il motore premia i curriculum più lunghi.")
        print("  La lunghezza guadagna posizioni indipendentemente dalla")
        print("  pertinenza — va ridotto count_weight.")
    elif media_top / media_pool > 1.15 or corr > 0.25:
        print("  LETTURA: distorsione lieve verso i curriculum più ricchi,")
        print("  probabilmente accettabile ma da dichiarare.")
    else:
        print("  LETTURA: nessuna distorsione apprezzabile per lunghezza.")
        print("  I candidati in cima lo sono per pertinenza, non per ampiezza.")
    print(SEP)

    return {
        "n_annunci": n,
        "n_candidati_pool": len(campione_cvs),
        "seniority_weight": engine.seniority_weight,
        "count_weight": engine.count_weight,
        "precision_at_1": round(p1 * 100, 1),
        "precision_at_3": round(p3 * 100, 1),
        f"precision_at_{top_k}": round(pk * 100, 1),
        "mrr": round(mrr / n, 3),
        "baseline_casuale": round(base * 100, 1),
        "skill_medie_pool": round(media_pool, 1),
        "skill_medie_top10": round(media_top, 1),
        "rapporto_lunghezza": round(media_top / media_pool, 2),
        "correlazione_punteggio_lunghezza_non_pertinenti": round(corr, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — validazione della direzione annuncio → candidati")
    ap.add_argument("--max-jobs", type=int, default=20,
                    help="Numero di annunci da valutare (default 20)")
    ap.add_argument("--max-cvs", type=int, default=300,
                    help="Numero di candidati nel pool (default 300)")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seniority-weight", dest="sen_w", type=float, default=None)
    ap.add_argument("--count-weight", dest="cnt_w", type=float, default=None,
                    help="Override del peso sul conteggio assoluto "
                         "(0.0 per il confronto A/B)")
    ap.add_argument("--out", dest="out_file", default=str(OUT_FILE))
    args = ap.parse_args()

    r = run(args.max_jobs, args.max_cvs, args.top_k, args.seed,
            args.sen_w, args.cnt_w)
    Path(args.out_file).write_text(
        json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[valida_recruiter] Risultati salvati in {args.out_file}")


if __name__ == "__main__":
    main()
