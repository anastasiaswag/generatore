"""
valida_seniority.py  —  SkillPath AI
=====================================
Valuta se JobMatchingEngine sa distinguere il livello di esperienza, non
solo l'area professionale.

PERCHÉ SERVE UN TEST DIVERSO
────────────────────────────
La validazione principale (analysis/valida_matching_engine.py) chiede al
motore di ritrovare, in un pool di centinaia di annunci, quelli
dell'occupazione giusta. Il risultato è altissimo (Precision@1 ≈ 97%), ma
su questi dati il compito è quasi banale: CV e annunci della stessa
occupazione sono stati generati campionando dalla medesima lista di skill
ESCO, quindi condividono in media il 64% delle competenze, mentre coppie di
occupazioni diverse ne condividono lo 0,3% — e nel 93% dei casi nessuna.
Al motore basta rilevare "hanno qualcosa in comune" per vincere.

Restringere il pool non risolve: anche fra occupazioni dello stesso settore
ISCO la separazione resta di 39 volte e l'82% delle coppie non condivide
alcuna skill. Il limite è nella costruzione del dataset, non nel test.

L'IDEA DI QUESTO TEST
─────────────────────
La seniority è annotata su entrambi i lati ed è **indipendente** dal
campionamento delle skill: i sei annunci di una stessa occupazione hanno
competenze quasi identiche e differiscono per livello richiesto. Chiedere al
motore di scegliere, fra questi sei, quello del livello giusto isola una
capacità che il dataset non regala: il segnale non è replicato per
costruzione, va davvero estratto dal testo.

È quindi l'unica valutazione non circolare che questo dataset permette.

METRICHE
────────
Per ogni CV si ordinano i soli annunci della SUA occupazione e si guarda la
seniority del primo classificato:

  Accuracy esatta   quota di CV il cui primo annuncio ha la stessa seniority
  Accuracy adiacente quota in cui la seniority è uguale o adiacente
                     (junior↔mid, mid↔senior): errore lieve
  Baseline casuale  quota attesa scegliendo a caso fra gli annunci
                    disponibili di quella occupazione

Se l'accuracy esatta non supera la baseline, il motore ignora la seniority.

Uso (dalla radice del progetto):
    python analysis/valida_seniority.py
    python analysis/valida_seniority.py --max-cvs 200
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

CVS_FILE = BASE_DIR / "outputs" / "cv_batch_results.json"
JOBS_FILE = BASE_DIR / "outputs" / "job_gt_batch_results.json"
OUT_FILE = BASE_DIR / "outputs" / "seniority_eval.json"

SEP = "─" * 65
LIVELLI = ["junior", "mid", "senior"]


def adiacente(a: str, b: str) -> bool:
    """True se i due livelli coincidono o sono contigui."""
    if a not in LIVELLI or b not in LIVELLI:
        return False
    return abs(LIVELLI.index(a) - LIVELLI.index(b)) <= 1


def run(max_cvs: int, seed: int, sen_w: float = 0.0,
        cnt_w: float | None = None, cnt_k: float = 10.0) -> dict:
    from matching_engine import JobMatchingEngine

    if not CVS_FILE.exists() or not JOBS_FILE.exists():
        print("[ERRORE] Servono outputs/cv_batch_results.json e "
              "outputs/job_gt_batch_results.json")
        sys.exit(1)

    cvs = json.loads(CVS_FILE.read_text(encoding="utf-8"))
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))

    # Annunci raggruppati per occupazione VERA (non stimata dal parser:
    # qui non stiamo valutando il parser ma la discriminazione di livello)
    per_occ: dict[str, list] = {}
    for j in jobs:
        o = (j.get("ground_truth") or {}).get("target_occupation_id", "")
        if o and (j.get("meta") or {}).get("seniority") in LIVELLI:
            per_occ.setdefault(o, []).append(j)

    # Servono almeno due livelli diversi, altrimenti la scelta è obbligata
    valutabili = []
    for cv in cvs:
        o = (cv.get("ground_truth") or {}).get("target_occupation_id", "")
        sen = (cv.get("cv") or {}).get("persona", {}).get("seniority", "")
        cand = per_occ.get(o, [])
        if sen in LIVELLI and len({c["meta"]["seniority"] for c in cand}) >= 2:
            valutabili.append(cv)

    print(f"[valida_seniority] CV valutabili: {len(valutabili)}/{len(cvs)}")
    if not valutabili:
        print("[ERRORE] Nessun CV valutabile.")
        sys.exit(1)

    rng = random.Random(seed)
    campione = (valutabili if len(valutabili) <= max_cvs
                else rng.sample(valutabili, max_cvs))
    print(f"[valida_seniority] Ne valuto {len(campione)}\n")

    # cnt_w=None -> si usa il valore predefinito del motore (0.15), quello
    # effettivamente in produzione. Passare 0.0 esplicitamente disattiva la
    # correzione, utile solo per i confronti.
    kw = {"seniority_weight": sen_w, "count_k": cnt_k}
    if cnt_w is not None:
        kw["count_weight"] = cnt_w
    engine = JobMatchingEngine(**kw)
    cnt_eff = engine.count_weight
    print(f'[config] seniority_weight={sen_w}  count_weight={cnt_eff}  count_k={cnt_k}')
    esatti = adiacenti = 0
    baseline_sum = 0.0
    confusione: Counter = Counter()
    per_livello: dict[str, list] = {}

    for i, cv in enumerate(campione, 1):
        o = cv["ground_truth"]["target_occupation_id"]
        sen_cv = cv["cv"]["persona"]["seniority"]
        annunci = per_occ[o]

        punteggi = []
        for j in annunci:
            try:
                m = engine.match(cv, j)
            except Exception:
                continue
            punteggi.append((m["match_score"], j))
        if not punteggi:
            continue
        punteggi.sort(key=lambda x: x[0], reverse=True)
        sen_top = punteggi[0][1]["meta"]["seniority"]

        ok = (sen_top == sen_cv)
        esatti += ok
        adiacenti += adiacente(sen_top, sen_cv)
        confusione[(sen_cv, sen_top)] += 1
        per_livello.setdefault(sen_cv, []).append(ok)

        # baseline: probabilità di indovinare scegliendo a caso fra gli annunci
        n_giusti = sum(1 for j in annunci if j["meta"]["seniority"] == sen_cv)
        baseline_sum += n_giusti / len(annunci)

        if i % 25 == 0:
            print(f"  [{i}/{len(campione)}] accuracy corrente "
                  f"{esatti/i:.3f}")

    n = sum(len(v) for v in per_livello.values())
    if not n:
        print("[ERRORE] Nessun confronto riuscito.")
        sys.exit(1)

    acc = esatti / n
    acc_adj = adiacenti / n
    base = baseline_sum / n

    print(f"\n{SEP}")
    print("  RISULTATI — discriminazione della seniority")
    print(SEP)
    print(f"  CV valutati                 : {n}")
    print(f"  Accuracy esatta             : {acc*100:.1f}%")
    print(f"  Accuracy adiacente          : {acc_adj*100:.1f}%")
    print(f"  Baseline casuale            : {base*100:.1f}%")
    print(f"  Guadagno sulla baseline     : {acc/base if base else 0:.2f}x")
    print(SEP)

    print("\n  Accuracy per livello del CV:")
    out_liv = {}
    for liv in LIVELLI:
        v = per_livello.get(liv, [])
        if v:
            out_liv[liv] = {"n": len(v), "accuracy": round(sum(v)/len(v), 3)}
            print(f"    {liv:<8} (n={len(v):>3})  {sum(v)/len(v)*100:5.1f}%")

    print("\n  Matrice di confusione (riga = CV, colonna = annuncio scelto):")
    print(f"    {'':<8}" + "".join(f"{l:>9}" for l in LIVELLI))
    for vero in LIVELLI:
        riga = "".join(f"{confusione[(vero, p)]:>9}" for p in LIVELLI)
        print(f"    {vero:<8}" + riga)

    if acc <= base * 1.05:
        print(f"\n  LETTURA: l'accuracy non supera la baseline casuale.")
        print("  Il motore NON sta usando l'informazione sulla seniority.")
    elif acc < 0.5:
        print(f"\n  LETTURA: il segnale c'è ma è debole.")
        print("  La seniority influenza il punteggio solo marginalmente.")
    else:
        print(f"\n  LETTURA: il motore discrimina il livello di esperienza.")
        print("  A differenza del ritrovamento dell'occupazione, questo")
        print("  risultato non è replicato dalla costruzione del dataset.")
    print()

    risultato = {
        "n_cv_valutati": n,
        "accuracy_esatta": round(acc, 3),
        "accuracy_adiacente": round(acc_adj, 3),
        "baseline_casuale": round(base, 3),
        "guadagno_su_baseline": round(acc / base, 2) if base else None,
        "per_livello": out_liv,
        "confusione": {f"{a}->{b}": c for (a, b), c in confusione.items()},
    }
    return risultato


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — discriminazione della seniority nel matching")
    ap.add_argument("--max-cvs", type=int, default=100,
                    help="Numero di CV da valutare (default 100)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", dest="out_file", default=str(OUT_FILE),
                    help="File su cui salvare le metriche")
    # Correzioni del motore, disattive di default: vanno misurate una alla
    # volta prima di decidere se renderle predefinite.
    ap.add_argument("--seniority-weight", dest="sen_w", type=float, default=0.0,
                    help="Peso del termine di allineamento seniority (0 = disattivo)")
    ap.add_argument("--count-weight", dest="cnt_w", type=float, default=None,
                    help="Peso del termine sul numero assoluto di skill coperte "
                         "(omesso = valore predefinito del motore)")
    ap.add_argument("--count-k", dest="cnt_k", type=float, default=10.0,
                    help="Punto di saturazione del termine assoluto")
    args = ap.parse_args()

    r = run(args.max_cvs, args.seed, args.sen_w, args.cnt_w, args.cnt_k)
    r["config"] = {"seniority_weight": args.sen_w,
                   "count_weight": args.cnt_w, "count_k": args.cnt_k}
    out_path = Path(args.out_file)
    out_path.write_text(json.dumps(r, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"[valida_seniority] Risultati salvati in {out_path}")


if __name__ == "__main__":
    main()
