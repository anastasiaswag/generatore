"""
valida_monotonia.py  —  SkillPath AI
=====================================
Verifica che il punteggio del matching engine sia una misura GRADUATA e non
soltanto un ordinamento, e produce alcuni casi tracciati per intero.

DUE DOMANDE DISTINTE
────────────────────
Le validazioni esistenti misurano se il candidato giusto finisce in cima alla
classifica. Non dicono però se il VALORE del punteggio significhi qualcosa. È
una differenza che conta: se l'interfaccia mostra "compatibilità 72%",
quel numero deve corrispondere a un grado di affinità, non essere un artefatto
dell'ordinamento.

  1. MONOTONIA
     Il punteggio dovrebbe decrescere in modo ordinato lungo tre livelli di
     affinità decrescente:
         stessa occupazione  >  stesso settore ISCO  >  settore diverso
     Se le tre distribuzioni si separano nettamente, il valore assoluto è
     informativo. Se si sovrappongono, il punteggio va usato solo per
     ordinare, e in tesi va detto.

  2. CASI TRACCIATI
     Cinque coppie CV↔annuncio mostrate per intero: competenze estratte da
     ciascun lato, quali coincidono, come si scompone il punteggio finale nei
     suoi quattro termini. Servono a rendere i numeri verificabili a mano da
     un lettore, cosa che nessuna metrica aggregata permette. Contro
     l'obiezione "questi risultati sono costruiti", un esempio ispezionabile
     vale più di una tabella.

METRICHE DI SEPARAZIONE
───────────────────────
Oltre alle medie si calcola la sovrapposizione fra distribuzioni contigue —
la quota di coppie del livello inferiore che ottiene comunque un punteggio
superiore alla mediana del livello superiore. Una sovrapposizione alta
significa che il punteggio da solo non permette di distinguere i due casi.

Uso (dalla radice del progetto):
    python analysis/valida_monotonia.py
    python analysis/valida_monotonia.py --n-cv 40 --esempi 5
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
OCC_FILE = BASE_DIR / "dataset" / "source" / "occupations.json"
OUT_FILE = BASE_DIR / "outputs" / "monotonia_eval.json"
OUT_CASI = BASE_DIR / "docs" / "casi_tracciati.md"

SEP = "─" * 68
LIVELLI = ["stessa occupazione", "stesso settore ISCO", "settore diverso"]


def sovrapposizione(alto: list[float], basso: list[float]) -> float:
    """Quota del gruppo inferiore che supera la mediana di quello superiore."""
    if not alto or not basso:
        return 0.0
    med = st.median(alto)
    return sum(1 for v in basso if v > med) / len(basso)


# ══════════════════════════════════════════════════════════════════════════════

def run(n_cv: int, n_esempi: int, seed: int,
        sen_w: float | None = None, cnt_w: float | None = None) -> dict:
    from matching_engine import JobMatchingEngine

    for f in (CVS_FILE, JOBS_FILE, OCC_FILE):
        if not f.exists():
            print(f"[ERRORE] File mancante: {f}")
            sys.exit(1)

    cvs = json.loads(CVS_FILE.read_text(encoding="utf-8"))
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    occ_db = json.loads(OCC_FILE.read_text(encoding="utf-8"))
    settore = {k: (v.get("isco_code") or "")[:1] for k, v in occ_db.items()}

    per_occ: dict[str, list] = {}
    for j in jobs:
        o = (j.get("ground_truth") or {}).get("target_occupation_id", "")
        if o:
            per_occ.setdefault(o, []).append(j)

    validi = [c for c in cvs
              if (c.get("ground_truth") or {}).get("target_occupation_id", "") in per_occ]
    rng = random.Random(seed)
    campione = validi if len(validi) <= n_cv else rng.sample(validi, n_cv)

    kw = {}
    if sen_w is not None: kw["seniority_weight"] = sen_w
    if cnt_w is not None: kw["count_weight"] = cnt_w
    engine = JobMatchingEngine(**kw)
    print(f"[config] seniority_weight={engine.seniority_weight}  "
          f"count_weight={engine.count_weight}")
    print(f"[monotonia] {len(campione)} CV, tre confronti ciascuno\n")

    punteggi: dict[str, list] = {l: [] for l in LIVELLI}
    tracciati: list[dict] = []

    for i, cv in enumerate(campione, 1):
        o = cv["ground_truth"]["target_occupation_id"]
        sett = settore.get(o, "")

        stesse = per_occ[o]
        stesso_sett = [j for j in jobs
                       if settore.get((j.get("ground_truth") or {}).get(
                           "target_occupation_id", ""), "") == sett
                       and (j.get("ground_truth") or {}).get(
                           "target_occupation_id", "") != o]
        altro_sett = [j for j in jobs
                      if settore.get((j.get("ground_truth") or {}).get(
                          "target_occupation_id", ""), "") not in ("", sett)]

        scelte = {
            LIVELLI[0]: rng.choice(stesse) if stesse else None,
            LIVELLI[1]: rng.choice(stesso_sett) if stesso_sett else None,
            LIVELLI[2]: rng.choice(altro_sett) if altro_sett else None,
        }

        riga = {"cv_id": cv.get("cv_id"),
                "occupazione": cv["ground_truth"].get("target_occupation_label"),
                "confronti": {}}

        for liv, job in scelte.items():
            if job is None:
                continue
            try:
                m = engine.match(cv, job)
            except Exception:
                continue
            punteggi[liv].append(m["match_score"])
            riga["confronti"][liv] = {
                "job_id": job.get("job_id"),
                "occupazione_annuncio": (job.get("ground_truth") or {}).get(
                    "target_occupation_label"),
                "match_score": m["match_score"],
                "skill_coverage": m.get("skill_coverage"),
                "occupation_similarity": (m.get("occupation_match") or {}).get(
                    "similarity"),
                "n_skill_coperte": len(m.get("matched_skills", [])),
                "n_skill_mancanti": len(m.get("skill_gap", [])),
            }

        if len(tracciati) < n_esempi and len(riga["confronti"]) == 3:
            riga["dettaglio"] = _dettaglio(engine, cv, scelte[LIVELLI[0]])
            tracciati.append(riga)

        if i % 10 == 0:
            print(f"  [{i}/{len(campione)}]")

    # ── Risultati ────────────────────────────────────────────────────────────
    print(f"\n{SEP}\n  MONOTONIA DEL PUNTEGGIO\n{SEP}")
    print(f"  {'livello di affinità':<24}{'n':>6}{'media':>9}{'mediana':>9}"
          f"{'min':>8}{'max':>8}")
    print(f"  {'-'*64}")
    riassunto = {}
    for liv in LIVELLI:
        v = punteggi[liv]
        if not v:
            continue
        riassunto[liv] = {
            "n": len(v), "media": round(st.mean(v), 4),
            "mediana": round(st.median(v), 4),
            "min": round(min(v), 4), "max": round(max(v), 4),
        }
        print(f"  {liv:<24}{len(v):>6}{st.mean(v):>9.3f}{st.median(v):>9.3f}"
              f"{min(v):>8.3f}{max(v):>8.3f}")

    ok_mono = (riassunto.get(LIVELLI[0], {}).get("media", 0)
               > riassunto.get(LIVELLI[1], {}).get("media", 0)
               > riassunto.get(LIVELLI[2], {}).get("media", 0))

    s1 = sovrapposizione(punteggi[LIVELLI[0]], punteggi[LIVELLI[1]])
    s2 = sovrapposizione(punteggi[LIVELLI[1]], punteggi[LIVELLI[2]])

    print(f"\n  Sovrapposizione fra livelli contigui")
    print(f"    stesso settore che supera la mediana di stessa occupazione : {s1:.1%}")
    print(f"    settore diverso che supera la mediana di stesso settore    : {s2:.1%}")

    print(f"\n{SEP}\n  LETTURA\n{SEP}")
    if not ok_mono:
        print("  Le medie NON decrescono nell'ordine atteso: il punteggio non")
        print("  riflette il grado di affinità e va usato solo per ordinare.")
    elif max(s1, s2) > 0.25:
        print("  L'ordine delle medie è corretto ma le distribuzioni si")
        print("  sovrappongono in modo consistente. Il punteggio distingue i")
        print("  casi in media, non sul singolo confronto: mostrarlo come")
        print("  percentuale di compatibilità sarebbe fuorviante.")
    else:
        print("  Il punteggio decresce in modo ordinato e le distribuzioni")
        print("  sono ben separate: il valore assoluto è informativo, non solo")
        print("  l'ordinamento. Può essere mostrato all'utente come grado di")
        print("  compatibilità.")
    print(SEP)

    _scrivi_casi(tracciati)
    print(f"\n  Casi tracciati scritti in {OUT_CASI}")

    return {"riassunto": riassunto,
            "monotonia_rispettata": bool(ok_mono),
            "sovrapposizione_occ_settore": round(s1, 4),
            "sovrapposizione_settore_altro": round(s2, 4),
            "n_cv": len(campione)}


def _dettaglio(engine, cv: dict, job: dict) -> dict:
    """Scomposizione del punteggio per un singolo confronto."""
    m = engine.match(cv, job)
    return {
        "skill_coverage": m.get("skill_coverage"),
        "occupation_similarity": (m.get("occupation_match") or {}).get("similarity"),
        "match_score": m.get("match_score"),
        "grade": m.get("grade"),
        "coperte": [s.get("label") for s in m.get("matched_skills", [])][:10],
        "mancanti": [s.get("label") for s in m.get("skill_gap", [])][:10],
        "pesi": {
            "count_weight": engine.count_weight,
            "seniority_weight": engine.seniority_weight,
        },
    }


def _scrivi_casi(tracciati: list[dict]) -> None:
    """Genera il documento dei casi tracciati, ispezionabile a mano."""
    r = ["# Casi tracciati — matching engine", "",
         "Cinque confronti CV↔annuncio mostrati per intero, con la",
         "scomposizione del punteggio. Servono a rendere i risultati",
         "verificabili a mano: le metriche aggregate dicono quanto spesso il",
         "sistema ha ragione, questi esempi mostrano *come* arriva alla",
         "risposta.", "",
         "Per ogni CV sono riportati tre confronti con affinità decrescente,",
         "così si vede il punteggio degradare al diminuire della pertinenza.",
         "", "---", ""]

    for i, t in enumerate(tracciati, 1):
        r += [f"## Caso {i} — {t['occupazione']}", "",
              f"CV: `{t['cv_id']}`", "",
              "| confronto | occupazione dell'annuncio | punteggio | copertura skill | similarità ruolo |",
              "|---|---|---|---|---|"]
        for liv in LIVELLI:
            c = t["confronti"].get(liv)
            if not c:
                continue
            r.append(f"| {liv} | {c['occupazione_annuncio']} | "
                     f"**{c['match_score']:.3f}** | {c['skill_coverage']:.3f} | "
                     f"{c['occupation_similarity']:.3f} |")
        d = t.get("dettaglio", {})
        if d:
            r += ["", "Dettaglio del confronto con la stessa occupazione:", "",
                  f"- punteggio finale **{d['match_score']:.3f}** "
                  f"(giudizio: {d.get('grade','—')})",
                  f"- copertura delle competenze richieste: {d['skill_coverage']:.3f}",
                  f"- similarità fra i ruoli: {d['occupation_similarity']:.3f}",
                  f"- pesi in uso: conteggio assoluto {d['pesi']['count_weight']}, "
                  f"seniority {d['pesi']['seniority_weight']}", ""]
            if d.get("coperte"):
                r += ["Competenze coperte dal candidato:", ""]
                r += [f"- {s}" for s in d["coperte"]]
                r.append("")
            if d.get("mancanti"):
                r += ["Competenze mancanti (il gap formativo):", ""]
                r += [f"- {s}" for s in d["mancanti"]]
                r.append("")
        r += ["---", ""]

    OUT_CASI.parent.mkdir(parents=True, exist_ok=True)
    OUT_CASI.write_text("\n".join(r), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — monotonia del punteggio e casi tracciati")
    ap.add_argument("--n-cv", type=int, default=40)
    ap.add_argument("--esempi", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seniority-weight", dest="sen_w", type=float, default=None,
                    help="Override del peso seniority (0.3 è il predefinito attuale)")
    ap.add_argument("--count-weight", dest="cnt_w", type=float, default=None)
    ap.add_argument("--out", dest="out_file", default=str(OUT_FILE))
    args = ap.parse_args()

    r = run(args.n_cv, args.esempi, args.seed, args.sen_w, args.cnt_w)
    r["seniority_weight"] = args.sen_w
    Path(args.out_file).write_text(
        json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Metriche salvate in {args.out_file}")


if __name__ == "__main__":
    main()
