"""
valida_matching_engine.py  —  SkillPath AI
=============================================
Valuta JobMatchingEngine (Scenario 2, CV ↔ job description) riusando
i dati già disponibili nel dataset sintetico, senza bisogno di annotare
nulla a mano:

  - ogni CV sintetico ha un ground_truth.target_occupation_label noto
    (outputs/cv_batch_results.json)
  - ogni annuncio ha sia l'occupazione con cui è stato generato sia
    quella rilevata dal job_parser
    (outputs/job_gt_batch_results.json)

METODOLOGIA
-----------
Il dataset di annunci con ground truth (dataset/synthetic/jobs_gt/) copre
le stesse 135 occupazioni ESCO dei CV, sei annunci ciascuna. Praticamente
ogni CV ha quindi almeno un annuncio "corretto" da trovare, e la
valutazione è statisticamente significativa.

Storicamente non era così: il primo dataset di annunci copriva solo tre
aree (Informatica / Meccanica / Elettronica), quindi appena 3 occupazioni
su 135 erano verificabili e il risultato era puramente indicativo. Da qui
la necessità di generare il dataset con ground truth.

ORIGINE DELL'OCCUPAZIONE DELL'ANNUNCIO (--occ-source)
-----------------------------------------------------
  ground_truth  l'occupazione con cui l'annuncio è stato generato. È
                un'etichetta indipendente e corretta per costruzione:
                misura il matching engine ISOLATO. Default.
  parser        l'occupazione stimata dal job_parser. Misura la catena
                job_parser + matching_engine insieme, cioè il
                comportamento reale del sistema su un annuncio mai visto.

Vale la pena riportarle entrambe: la differenza fra le due quantifica
quanto gli errori del parser si propagano a valle.

Lo script quindi:
  1. individua quali CV hanno un'occupazione target che compare anche
     tra le occupazioni rilevate negli annunci (i CV "testabili")
  2. per ciascun CV testabile, ordina gli annunci per match_score e
     controlla se un annuncio con la stessa occupazione compare nei
     primi K risultati (Precision@1/3/10, MRR — stessa logica già
     usata da matching_engine.py validate_on_dataset(), qui applicata
     allo Scenario 2 invece che allo Scenario 1)
  3. confronta il risultato con una baseline casuale (quanto sarebbe
     facile trovarlo per puro caso, dato quanti annunci hanno
     quell'occupazione)

LIMITE METODOLOGICO (da dichiarare nella tesi):
CV e annunci sono entrambi sintetici e generati dallo stesso modello di
linguaggio a partire dalla stessa ontologia. Il lessico condiviso rende
l'abbinamento più facile di quanto sarebbe su documenti reali: i valori
vanno letti come limite superiore, e il confronto con la baseline casuale
è più informativo del valore assoluto.

Uso (dalla radice del progetto):
    python analysis/valida_matching_engine.py
    python analysis/valida_matching_engine.py --occ-source parser
    python analysis/valida_matching_engine.py --max-cvs 30 --max-jobs 300
"""

import argparse
import json
import random
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (analysis/ è un livello sotto)
SRC_DIR  = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

CVS_FILE  = BASE_DIR / "outputs" / "cv_batch_results.json"
# Dataset di annunci con ground truth ESCO (135 occupazioni × 6).
# Il vecchio outputs/batch_job_results.json copriva solo 3 occupazioni.
JOBS_FILE = BASE_DIR / "outputs" / "job_gt_batch_results.json"
OUT_FILE  = BASE_DIR / "outputs" / "matching_engine_eval.json"

SEP = "─" * 65


def _norm(label: str) -> str:
    return (label or "").strip().lower()


def job_occ_id(job: dict, source: str) -> str:
    """
    ID ESCO dell'occupazione di un annuncio.

    source="ground_truth" usa l'occupazione con cui l'annuncio è stato
    generato (etichetta indipendente); "parser" usa quella stimata dal
    job_parser. Se la ground truth è richiesta ma assente, ricade sul
    parser, così lo script funziona anche sui dataset più vecchi.
    """
    if source == "ground_truth":
        gt = (job.get("ground_truth") or {}).get("target_occupation_id", "")
        if gt:
            return gt
    return (job.get("occupation") or {}).get("id", "")


def build_testable_set(cvs: list[dict], jobs: list[dict],
                       occ_source: str = "ground_truth") -> tuple[list[dict], dict[str, list[dict]]]:
    """
    Ritorna:
      - lista dei CV "testabili" (il cui target_occupation_id ESCO compare
        anche tra le occupazioni rilevate negli annunci)
      - dizionario {occupation_id: [annunci con quella occupazione]}

    NOTA: il confronto avviene per ID ESCO, non per etichetta testuale —
    i CV hanno l'occupazione target in inglese (dataset ESCO originale),
    gli annunci hanno l'occupazione rilevata dal job_parser in italiano
    (dataset bilingue attivo). Le due etichette per la stessa occupazione
    non coincidono mai come stringhe, ma condividono lo stesso ID ESCO.
    """
    jobs_by_occ: dict[str, list[dict]] = {}
    for j in jobs:
        occ_id = job_occ_id(j, occ_source)
        if occ_id:
            jobs_by_occ.setdefault(occ_id, []).append(j)

    testable = []
    for cv in cvs:
        target_id = cv.get("ground_truth", {}).get("target_occupation_id", "")
        if target_id and target_id in jobs_by_occ:
            testable.append(cv)

    return testable, jobs_by_occ


def run_eval(max_cvs: int, max_jobs: int, top_k: int, seed: int = 42,
             occ_source: str = "ground_truth", jobs_file: Path | None = None,
             sen_w: float | None = None, cnt_w: float | None = None) -> dict:
    from matching_engine import JobMatchingEngine

    jobs_path = jobs_file or JOBS_FILE
    with open(CVS_FILE, encoding="utf-8") as f:
        cvs = json.load(f)
    with open(jobs_path, encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"[valida_matching] {len(cvs)} CV, {len(jobs)} annunci caricati "
          f"({jobs_path.name}, occupazione da '{occ_source}')")

    testable, jobs_by_occ = build_testable_set(cvs, jobs, occ_source)
    print(f"[valida_matching] CV testabili (occupazione target presente tra gli annunci, per ID ESCO): "
          f"{len(testable)}/{len(cvs)}")
    if len(testable) < 10:
        print(f"[valida_matching] ATTENZIONE: solo {len(testable)} CV testabili. I due dataset sintetici "
              f"(CV e annunci) coprono occupazioni ESCO in gran parte diverse — il risultato è puramente "
              f"indicativo, non statisticamente robusto. Vedi la nota metodologica in cima al file.")

    if not testable:
        print("[valida_matching] ERRORE: nessun CV testabile — controlla i due file di input.")
        sys.exit(1)

    rng = random.Random(seed)
    sample_cvs = testable if len(testable) <= max_cvs else rng.sample(testable, max_cvs)

    # Sottocampiona gli annunci per velocità, ma garantisce che tutti gli annunci
    # "corretti" per i CV campionati restino inclusi.
    target_ids = {cv["ground_truth"]["target_occupation_id"] for cv in sample_cvs}
    must_keep_ids = {j["job_id"] for tid in target_ids for j in jobs_by_occ.get(tid, [])}
    if len(jobs) > max_jobs:
        pool = [j for j in jobs if j["job_id"] not in must_keep_ids]
        extra = rng.sample(pool, max(0, max_jobs - len(must_keep_ids)))
        sample_jobs = [j for j in jobs if j["job_id"] in must_keep_ids] + extra
    else:
        sample_jobs = jobs

    print(f"[valida_matching] Valuto {len(sample_cvs)} CV contro {len(sample_jobs)} annunci "
          f"(top-{top_k})...\n")

    kw = {}
    if sen_w is not None: kw["seniority_weight"] = sen_w
    if cnt_w is not None: kw["count_weight"] = cnt_w
    engine = JobMatchingEngine(**kw)
    print(f"[config] seniority_weight={engine.seniority_weight}  "
          f"count_weight={engine.count_weight}")

    p1 = p3 = pk = mrr_sum = 0
    baseline_p1_sum = 0.0
    details = []

    for i, cv in enumerate(sample_cvs, 1):
        target_id = cv["ground_truth"]["target_occupation_id"]
        # quanti annunci "giusti" (stessa occupazione ESCO) sono nel pool campionato per questo CV
        n_correct_in_pool = sum(
            1 for j in sample_jobs if job_occ_id(j, occ_source) == target_id
        )

        scored = []
        for job in sample_jobs:
            try:
                m = engine.match(cv, job)
            except Exception:
                continue
            scored.append((m["match_score"], job))
        scored.sort(key=lambda x: x[0], reverse=True)

        ranked_ids = [job_occ_id(j, occ_source) for _, j in scored]

        hit_rank = next((idx + 1 for idx, oid in enumerate(ranked_ids) if oid == target_id), None)

        if hit_rank == 1:
            p1 += 1
        if hit_rank is not None and hit_rank <= 3:
            p3 += 1
        if hit_rank is not None and hit_rank <= top_k:
            pk += 1
        if hit_rank is not None:
            mrr_sum += 1.0 / hit_rank

        baseline = n_correct_in_pool / len(sample_jobs) if sample_jobs else 0.0
        baseline_p1_sum += baseline

        details.append({
            "cv_id": cv.get("cv_id"),
            "target_occupation": cv["ground_truth"]["target_occupation_label"],
            "hit_rank": hit_rank,
            "n_correct_in_pool": n_correct_in_pool,
            "baseline_p1": round(baseline, 4),
        })

        print(f"  [{i}/{len(sample_cvs)}]  {cv.get('cv_id','?'):<25}  target={cv['ground_truth']['target_occupation_label'][:35]:<35}  "
              f"hit_rank={hit_rank}")

    n = len(sample_cvs)
    result = {
        "occ_source":        occ_source,
        "jobs_file":         jobs_path.name,
        "n_cv_totali":       len(cvs),
        "n_cv_testabili":    len(testable),
        "n_cv_valutati":     n,
        "n_jobs_pool":       len(sample_jobs),
        "top_k":             top_k,
        "precision_at_1":    round(p1 / n * 100, 1),
        "precision_at_3":    round(p3 / n * 100, 1),
        f"precision_at_{top_k}": round(pk / n * 100, 1),
        "mrr":               round(mrr_sum / n, 3),
        "baseline_precision_at_1_media": round(baseline_p1_sum / n * 100, 1),
        "dettaglio_per_cv":  details,
    }
    return result


def main():
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Validazione JobMatchingEngine (Scenario 2)")
    ap.add_argument("--max-cvs",  type=int, default=15,
                     help="Numero di CV testabili da valutare (default 15 — ogni CV richiede N match, è lento)")
    ap.add_argument("--max-jobs", type=int, default=300,
                     help="Numero di annunci nel pool di confronto per CV (default 300)")
    ap.add_argument("--top-k",    type=int, default=10,
                     help="Soglia K per Precision@K (default 10)")
    ap.add_argument("--seed",     type=int, default=42)
    ap.add_argument("--occ-source", dest="occ_source",
                    choices=["ground_truth", "parser"], default="ground_truth",
                    help="Origine dell'occupazione dell'annuncio (vedi docstring)")
    ap.add_argument("--jobs", default=None,
                    help="File di annunci parsati (default job_gt_batch_results.json)")
    # Configurazioni diverse devono salvare su file diversi, altrimenti la
    # seconda esecuzione cancella i risultati della prima.
    ap.add_argument("--seniority-weight", dest="sen_w", type=float, default=None,
                    help="Override del peso seniority (omesso = predefinito del motore)")
    ap.add_argument("--count-weight", dest="cnt_w", type=float, default=None,
                    help="Override del peso sul conteggio assoluto")
    ap.add_argument("--out", dest="out_file", default=None,
                    help="File su cui salvare le metriche "
                         "(default: matching_engine_eval_<occ-source>.json)")
    args = ap.parse_args()

    result = run_eval(args.max_cvs, args.max_jobs, args.top_k, args.seed,
                      args.occ_source, Path(args.jobs) if args.jobs else None,
                      args.sen_w, args.cnt_w)

    print(f"\n{SEP}")
    print("  RISULTATI — JobMatchingEngine (Scenario 2)")
    print(SEP)
    print(f"  Occupazione annunci da      : {result['occ_source']}")
    print(f"  CV totali nel dataset       : {result['n_cv_totali']}")
    print(f"  CV testabili (occ. presente): {result['n_cv_testabili']}")
    print(f"  CV effettivamente valutati  : {result['n_cv_valutati']}")
    print(f"  Pool annunci per CV         : {result['n_jobs_pool']}")
    print(SEP)
    print(f"  Precision@1                 : {result['precision_at_1']}%")
    print(f"  Precision@3                 : {result['precision_at_3']}%")
    pk_key = f"precision_at_{result['top_k']}"
    print(f"  Precision@{result['top_k']:<3}                : {result[pk_key]}%")
    print(f"  MRR                         : {result['mrr']}")
    print(f"  Baseline Precision@1 (caso) : {result['baseline_precision_at_1_media']}%")
    print(SEP)
    print("  Se Precision@1 è nettamente sopra la baseline casuale, il matching")
    print("  engine sta effettivamente premiando gli annunci del ruolo giusto")
    print("  e non ordinando a caso.")
    print(SEP)

    out_path = Path(args.out_file) if args.out_file else (
        BASE_DIR / "outputs" / f"matching_engine_eval_{args.occ_source}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[valida_matching] Risultati salvati in {out_path}")


if __name__ == "__main__":
    main()
