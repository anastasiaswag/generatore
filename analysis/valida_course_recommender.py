"""
valida_course_recommender.py  —  SkillPath AI
=================================================
Valuta CourseRecommender riusando gli skill_gap già calcolati nelle run
precedenti del matching engine (outputs/end_to_end_results.json e
outputs/job_to_candidates_results.json) — nessun nuovo parsing, nessun
modello semantico da caricare, gira in pochi secondi.

Due metriche, entrambe automatiche:

  1. COPERTURA — per tutte le skill mancanti osservate nel dataset,
     quante hanno almeno un corso disponibile nell'indice Coursera?
     (CourseRecommender.coverage(), già presente nel codice ma non
     ancora usata sistematicamente)

  2. SKILL SCOPERTE PIÙ FREQUENTI — classifica delle skill mancanti
     più comuni che NON hanno nessun corso associato: utile per capire
     dove l'indice Coursera è debole (stesso stile di analisi di
     estrai_fn.py per il CV parser).

NOTA: questo script NON valuta la pertinenza qualitativa dei corsi
suggeriti (serve controllo manuale — vedi la sezione "Problemi aperti"
della relazione).

Uso (dalla radice del progetto):
    python analysis/valida_course_recommender.py
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (analysis/ è un livello sotto)
SRC_DIR  = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

# File storici di risultati (test end-to-end di maggio 2026). Sono precedenti
# a tutte le correzioni ai parser e al matching engine, e nascono dal vecchio
# dataset di annunci limitato a 3 aree professionali: producevano appena 15
# skill mancanti distinte, troppo poche per una stima sensata della copertura.
# Restano leggibili per confronto storico, ma la modalità predefinita ora
# calcola i gap sul dataset corrente.
RESULT_FILES = [
    BASE_DIR / "outputs" / "end_to_end_results.json",
    BASE_DIR / "outputs" / "job_to_candidates_results.json",
]
CVS_FILE  = BASE_DIR / "outputs" / "cv_batch_results.json"
JOBS_FILE = BASE_DIR / "outputs" / "job_gt_batch_results.json"
OUT_FILE  = BASE_DIR / "outputs" / "course_recommender_eval.json"

SEP = "─" * 65


def _load_all_gaps() -> list[dict]:
    """Raccoglie tutte le voci skill_gap da tutti i file di risultati disponibili."""
    all_gaps = []
    for path in RESULT_FILES:
        if not path.exists():
            print(f"[valida_course] Attenzione: {path.name} non trovato, salto.")
            continue
        with open(path, encoding="utf-8") as f:
            results = json.load(f)
        n_gaps = 0
        for r in results:
            for g in r.get("skill_gap", []):
                all_gaps.append(g)
                n_gaps += 1
        print(f"[valida_course] {path.name}: {len(results)} confronti, {n_gaps} skill mancanti raccolte")
    return all_gaps


def _genera_gap(n_cv: int, seed: int, scenario: str = "avanzamento") -> list[dict]:
    """
    Calcola gli skill gap sul dataset corrente secondo tre scenari d'uso.

    SCELTA DELLO SCENARIO — è la decisione che determina se la valutazione
    abbia senso. Confrontare un candidato con un annuncio del lavoro che già
    svolge non produce quasi nulla da colmare: misurato su 300 confronti,
    appena 0,17 skill mancanti ciascuno, perché CV e annuncio della stessa
    occupazione attingono alla stessa lista ESCO e la soglia semantica copre
    il resto. Su quei numeri la copertura dei corsi non è stimabile.

    Chi cerca formazione, però, lo fa per un lavoro che ancora non può
    ottenere. Da qui gli scenari:

      stesso        CV contro annunci della propria occupazione e livello.
                    Utile solo come riferimento: mostra che il gap è nullo.

      avanzamento   CV junior o mid contro annunci SENIOR della stessa
                    occupazione. È la progressione di carriera: stesso
                    mestiere, requisiti più alti. Predefinito.

      transizione   CV contro annunci di un'occupazione DIVERSA dello stesso
                    macro-settore ISCO. È il cambio di ruolo verso un ambito
                    affine, il caso in cui la formazione pesa di più.
    """
    from matching_engine import JobMatchingEngine

    if not CVS_FILE.exists() or not JOBS_FILE.exists():
        print(f"[valida_course] ERRORE: servono {CVS_FILE.name} e {JOBS_FILE.name}")
        sys.exit(1)

    cvs  = json.loads(CVS_FILE.read_text(encoding="utf-8"))
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))

    per_occ: dict[str, list] = {}
    settore_di: dict[str, str] = {}
    for j in jobs:
        gt = j.get("ground_truth") or {}
        o = gt.get("target_occupation_id", "")
        if o:
            per_occ.setdefault(o, []).append(j)
            settore_di[o] = str(gt.get("isco_major", ""))

    per_settore: dict[str, list] = {}
    for o, sett in settore_di.items():
        per_settore.setdefault(sett, []).append(o)

    validi = [c for c in cvs
              if (c.get("ground_truth") or {}).get("target_occupation_id", "") in per_occ]
    if scenario == "avanzamento":
        validi = [c for c in validi
                  if (c.get("cv") or {}).get("persona", {}).get("seniority")
                  in ("junior", "mid")]

    rng = random.Random(seed)
    campione = validi if len(validi) <= n_cv else rng.sample(validi, n_cv)
    print(f"[valida_course] Scenario '{scenario}': {len(campione)} CV")

    def annunci_per(cv: dict) -> list:
        o = cv["ground_truth"]["target_occupation_id"]
        if scenario == "avanzamento":
            return [j for j in per_occ[o]
                    if (j.get("meta") or {}).get("seniority") == "senior"]
        if scenario == "transizione":
            altre = [x for x in per_settore.get(settore_di.get(o, ""), []) if x != o]
            if not altre:
                return []
            scelta = rng.choice(altre)
            return per_occ[scelta]
        return per_occ[o]

    engine = JobMatchingEngine()
    gaps: list[dict] = []
    for i, cv in enumerate(campione, 1):
        for job in annunci_per(cv):
            try:
                m = engine.match(cv, job)
            except Exception:
                continue
            gaps.extend(m.get("skill_gap", []))
        if i % 10 == 0:
            print(f"  [{i}/{len(campione)}] {len(gaps)} skill mancanti raccolte")
    return gaps


def main():
    from course_recommender import CourseRecommender

    ap = argparse.ArgumentParser(
        description="SkillPath AI — validazione CourseRecommender")
    ap.add_argument("--storico", action="store_true",
                    help="Usa i vecchi file di risultati invece di ricalcolare "
                         "i gap sul dataset corrente")
    ap.add_argument("--n-cv", type=int, default=50,
                    help="Numero di CV su cui calcolare i gap (default 50)")
    ap.add_argument("--scenario", choices=["stesso", "avanzamento", "transizione"],
                    default="avanzamento",
                    help="Situazione d'uso simulata (vedi docstring di _genera_gap)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", dest="out_file", default=str(OUT_FILE))
    args = ap.parse_args()

    all_gaps = (_load_all_gaps() if args.storico
                else _genera_gap(args.n_cv, args.seed, args.scenario))
    if not all_gaps:
        print("[valida_course] ERRORE: nessuno skill_gap trovato. Esegui prima i test end-to-end.")
        sys.exit(1)

    print(f"\n[valida_course] Totale occorrenze skill mancanti (con ripetizioni): {len(all_gaps)}")

    # Skill uniche (per id) — evita di contare N volte la stessa skill mancante in job diversi
    unique_by_id: dict[str, dict] = {g["id"]: g for g in all_gaps if g.get("id")}
    unique_gaps = list(unique_by_id.values())
    print(f"[valida_course] Skill mancanti distinte: {len(unique_gaps)}")

    rec = CourseRecommender(str(BASE_DIR / "config" / "course_index.json"))

    coverage_unique   = rec.coverage(unique_gaps)
    coverage_weighted = rec.coverage(all_gaps)

    # Skill mancanti più frequenti SENZA corsi disponibili
    counter = Counter(g["id"] for g in all_gaps if g.get("id"))
    uncovered_ids = {g["id"] for g in unique_gaps if g["id"] not in rec._index}
    uncovered_ranked = [
        {"id": sid, "label": unique_by_id[sid].get("label", sid), "occorrenze": cnt}
        for sid, cnt in counter.most_common()
        if sid in uncovered_ids
    ]

    result = {
        "skill_mancanti_totali_con_ripetizioni": len(all_gaps),
        "skill_mancanti_distinte":               len(unique_gaps),
        "copertura_su_skill_distinte":           coverage_unique,
        "copertura_pesata_su_occorrenze":        coverage_weighted,
        "top_skill_scoperte":                    uncovered_ranked[:20],
    }

    print(f"\n{SEP}")
    print("  RISULTATI — CourseRecommender")
    print(SEP)
    print(f"  Skill mancanti distinte osservate : {coverage_unique['gap_size']}")
    print(f"  ...con almeno un corso disponibile: {coverage_unique['covered']}  "
          f"({coverage_unique['coverage_pct']}%)")
    print(f"  ...senza nessun corso             : {coverage_unique['not_covered']}")
    print(SEP)
    print(f"  Stesso calcolo pesato per frequenza (quante volte capitano nei match reali):")
    print(f"  Copertura pesata                  : {coverage_weighted['coverage_pct']}%")
    print(SEP)
    if uncovered_ranked:
        print("  Skill scoperte più frequenti (nessun corso trovato):")
        for u in uncovered_ranked[:10]:
            print(f"    {u['occorrenze']:>4}×  {u['label']}")
    else:
        print("  Nessuna skill scoperta — copertura completa.")
    print(SEP)

    result["origine_gap"] = "storico" if args.storico else "dataset corrente"
    result["scenario"] = None if args.storico else args.scenario
    result["n_cv"] = None if args.storico else args.n_cv
    with open(args.out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[valida_course] Risultati salvati in {args.out_file}")
    print("[valida_course] NOTA: la pertinenza dei corsi suggeriti va comunque")
    print("                 verificata a occhio su un campione — questo script")
    print("                 misura solo se un corso esiste, non se è quello giusto.")


if __name__ == "__main__":
    main()
