"""
valuta_annotazione.py  —  SkillPath AI
=======================================
Calcola precisione, richiamo e F1 del parser dei curriculum su DATI REALI,
usando la ground truth raccolta a mano con `app/annota_cv.py`.

È l'unico punto dell'intero progetto in cui le metriche del parser non
dipendono da un dataset generato dal progetto stesso.

COME VANNO LETTI I NUMERI
─────────────────────────
PRECISIONE — piena. Fra le competenze che la configurazione di produzione ha
estratto, quante sono state giudicate corrette. Non c'è nulla di relativo: il
denominatore è esattamente ciò che il parser ha prodotto.

RICHIAMO — relativo al pool. Il denominatore sono le competenze giudicate
presenti, ma «presenti» significa qui «proposte da almeno una configurazione,
oppure aggiunte a mano durante l'annotazione». Una competenza che nessuna
configurazione ha proposto e che l'annotatore non ha notato resta invisibile.
Il richiamo vero è quindi minore o uguale a quello riportato, ed è una
sovrastima per costruzione. Va scritto così in tesi, non arrotondato a
«richiamo».

INCERTI — esclusi da entrambi i conteggi. La loro quota viene riportata
perché, se fosse alta, indicherebbe che la ground truth stessa è fragile.

INTERVALLI DI CONFIDENZA — di Wilson al 95%, gli stessi usati per la
revisione dei corsi. Su quindici documenti sono larghi, e vanno mostrati:
un numero puntuale su un campione simile suggerirebbe una precisione che il
campione non ha.

Uso (dalla radice del progetto):
    python analysis/valuta_annotazione.py
    python analysis/valuta_annotazione.py --parsato outputs/cv_reali_finale.json
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
ANNOT_FILE = BASE_DIR / "outputs" / "annotazione_cv_reali.json"
POOL_FILE = BASE_DIR / "outputs" / "pool_annotazione.json"
PARSATO_FILE = BASE_DIR / "outputs" / "cv_reali_finale.json"
OUT_FILE = BASE_DIR / "outputs" / "valutazione_cv_reali.json"

SEP = "─" * 74
RIF_PRECISION_SINTETICO = 0.907
RIF_RECALL_SINTETICO = 0.860
RIF_F1_SINTETICO = 0.878


def wilson(successi: int, totale: int, z: float = 1.96) -> tuple:
    """Intervallo di Wilson al 95%. Su campioni piccoli è preferibile a quello
    normale, che può uscire dall'intervallo [0, 1]."""
    if totale == 0:
        return (0.0, 0.0)
    p = successi / totale
    d = 1 + z * z / totale
    centro = (p + z * z / (2 * totale)) / d
    mezza = z * math.sqrt(p * (1 - p) / totale
                          + z * z / (4 * totale * totale)) / d
    return (max(0.0, centro - mezza), min(1.0, centro + mezza))


def f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if (p + r) else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — metriche del parser CV su dati reali")
    ap.add_argument("--annotazione", default=str(ANNOT_FILE))
    ap.add_argument("--parsato", default=str(PARSATO_FILE),
                    help="Output della configurazione di produzione")
    ap.add_argument("--out", default=str(OUT_FILE))
    args = ap.parse_args()

    p_annot = Path(args.annotazione)
    if not p_annot.exists():
        print(f"[ERRORE] Annotazione non trovata: {p_annot}\n"
              f"         Eseguire prima: python -m streamlit run app/annota_cv.py")
        sys.exit(1)
    giudizi = json.loads(p_annot.read_text(encoding="utf-8")).get("giudizi", {})
    if not giudizi:
        print("[ERRORE] Nessun giudizio registrato.")
        sys.exit(1)

    p_pars = Path(args.parsato)
    if not p_pars.exists():
        print(f"[ERRORE] File parsato non trovato: {p_pars}")
        sys.exit(1)

    # Competenze estratte dalla configurazione di produzione, per documento.
    estratte = defaultdict(set)
    for e in json.loads(p_pars.read_text(encoding="utf-8")):
        cid = e.get("cv_id")
        for m in ((e.get("cv", {}).get("skills") or {}).get("all_matches") or []):
            estratte[cid].add(m["id"])

    # Ground truth e giudizi, per documento.
    vere = defaultdict(set)       # giudicate presenti
    negate = defaultdict(set)     # giudicate assenti
    incerte = defaultdict(set)
    aggiunte = defaultdict(set)
    for g in giudizi.values():
        cid, sid = g["cv_id"], g["skill_id"]
        if g["giudizio"] == "si":
            vere[cid].add(sid)
            if g.get("aggiunta"):
                aggiunte[cid].add(sid)
        elif g["giudizio"] == "no":
            negate[cid].add(sid)
        else:
            incerte[cid].add(sid)

    documenti = sorted(set(estratte) | set(vere) | set(negate) | set(incerte))

    print(f"\n{SEP}\n  PARSER DEI CURRICULUM — METRICHE SU DATI REALI\n{SEP}")

    # ── Copertura dell'annotazione ───────────────────────────────────────────
    # Se una parte del pool non è stata giudicata, le metriche sarebbero
    # calcolate su un insieme parziale: meglio fermarsi che riportarle.
    if Path(POOL_FILE).exists():
        pool = json.loads(Path(POOL_FILE).read_text(encoding="utf-8"))
        tot_pool = sum(len(d["candidati"]) for d in pool.get("documenti", []))
        n_giudicati = sum(1 for g in giudizi.values() if not g.get("aggiunta"))
        quota = n_giudicati / tot_pool if tot_pool else 0.0
        print(f"  pool annotato: {n_giudicati}/{tot_pool} ({quota*100:.1f}%)")
        if quota < 0.995:
            print("\n  [ATTENZIONE] L'annotazione non è completa. I numeri qui\n"
                  "               sotto sono calcolati sul solo sottoinsieme\n"
                  "               giudicato e non vanno riportati in tesi.")
    print()

    # ── Conteggi globali ─────────────────────────────────────────────────────
    tp = fp = fn = 0
    per_doc = []
    for cid in documenti:
        est = estratte.get(cid, set())
        ok = vere.get(cid, set())
        ko = negate.get(cid, set())
        inc = incerte.get(cid, set())

        # Gli incerti escono da ogni conteggio, sia al numeratore sia al
        # denominatore: non sono né successi né errori.
        d_tp = len(est & ok)
        d_fp = len(est & ko)
        d_fn = len(ok - est)
        tp += d_tp
        fp += d_fp
        fn += d_fn

        p = d_tp / (d_tp + d_fp) if (d_tp + d_fp) else 0.0
        r = d_tp / (d_tp + d_fn) if (d_tp + d_fn) else 0.0
        per_doc.append({
            "cv_id": cid, "tp": d_tp, "fp": d_fp, "fn": d_fn,
            "incerti": len(est & inc),
            "aggiunte": len(aggiunte.get(cid, set())),
            "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(f1(p, r), 4),
        })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1_tot = f1(precision, recall)
    ic_p = wilson(tp, tp + fp)
    ic_r = wilson(tp, tp + fn)

    print(f"  {'':<26}{'valore':>10}{'IC 95%':>20}{'sintetico':>12}")
    print(f"  {'-'*68}")
    print(f"  {'Precisione':<26}{precision:>10.3f}"
          f"{f'{ic_p[0]:.3f}–{ic_p[1]:.3f}':>20}{RIF_PRECISION_SINTETICO:>12.3f}")
    print(f"  {'Richiamo (rel. al pool)':<26}{recall:>10.3f}"
          f"{f'{ic_r[0]:.3f}–{ic_r[1]:.3f}':>20}{RIF_RECALL_SINTETICO:>12.3f}")
    print(f"  {'F1':<26}{f1_tot:>10.3f}{'':>20}{RIF_F1_SINTETICO:>12.3f}")
    print()
    print(f"  veri positivi {tp} · falsi positivi {fp} · falsi negativi {fn}")

    n_inc = sum(d["incerti"] for d in per_doc)
    n_agg = sum(d["aggiunte"] for d in per_doc)
    print(f"  incerti esclusi dal conteggio: {n_inc}")
    print(f"  competenze aggiunte a mano (mai proposte da nessuna "
          f"configurazione): {n_agg}")

    if n_inc > (tp + fp) * 0.15:
        print("\n  [ATTENZIONE] Oltre il 15% dei candidati è stato giudicato\n"
              "               incerto: la ground truth è fragile e va detto.")

    # ── Quanto ha pesato l'indizio ───────────────────────────────────────────
    # L'interfaccia tiene nascosta la frase da cui nasce ogni proposta e
    # registra quando viene rivelata. Se la quota di accettazione fosse molto
    # più alta fra i giudizi presi dopo averla vista, l'annotazione starebbe
    # misurando in parte la plausibilità dell'abbinamento invece della
    # presenza della competenza nel documento. È un effetto noto in
    # letteratura come ancoraggio, e qui è osservabile invece che presunto.
    decisi = [g for g in giudizi.values()
              if not g.get("aggiunta") and g["giudizio"] in ("si", "no")]
    con_aiuto = [g for g in decisi if g.get("rivelato")]
    senza_aiuto = [g for g in decisi if not g.get("rivelato")]

    print(f"\n{SEP}\n  QUANTO HA PESATO L'INDIZIO\n{SEP}")
    if not decisi:
        print("  Nessun giudizio binario registrato.")
        acc_con = acc_senza = None
    else:
        quota_riv = len(con_aiuto) / len(decisi)
        acc_con = (sum(1 for g in con_aiuto if g["giudizio"] == "si")
                   / len(con_aiuto)) if con_aiuto else None
        acc_senza = (sum(1 for g in senza_aiuto if g["giudizio"] == "si")
                     / len(senza_aiuto)) if senza_aiuto else None
        print(f"  frase di origine rivelata in {len(con_aiuto)}/{len(decisi)} "
              f"giudizi ({quota_riv*100:.1f}%)")
        if acc_con is not None:
            print(f"  quota di accettazione CON indizio    {acc_con*100:.1f}%"
                  f"   (n={len(con_aiuto)})")
        if acc_senza is not None:
            print(f"  quota di accettazione SENZA indizio  {acc_senza*100:.1f}%"
                  f"   (n={len(senza_aiuto)})")
        if acc_con is not None and acc_senza is not None:
            delta = acc_con - acc_senza
            print(f"  differenza                           {delta*100:+.1f} punti")
            if abs(delta) > 0.15 and min(len(con_aiuto), len(senza_aiuto)) >= 20:
                print("\n  [ATTENZIONE] Divario superiore a 15 punti: l'indizio\n"
                      "               ha influenzato il giudizio in modo non\n"
                      "               trascurabile. Va riportato in tesi\n"
                      "               insieme alle metriche, non omesso.")
            elif min(len(con_aiuto), len(senza_aiuto)) < 20:
                print("  (uno dei due gruppi ha meno di 20 casi: differenza\n"
                      "   non interpretabile)")

    # ── Lo scarto, che è il risultato ────────────────────────────────────────
    print(f"\n{SEP}\n  LO SCARTO FRA SINTETICO E REALE\n{SEP}")
    d_p = precision - RIF_PRECISION_SINTETICO
    d_f = f1_tot - RIF_F1_SINTETICO
    print(f"  precisione {RIF_PRECISION_SINTETICO:.3f} → {precision:.3f}   "
          f"({d_p:+.3f})")
    print(f"  F1         {RIF_F1_SINTETICO:.3f} → {f1_tot:.3f}   ({d_f:+.3f})")
    print()
    if ic_p[1] < RIF_PRECISION_SINTETICO:
        print("  L'intervallo di confidenza sui reali NON contiene il valore\n"
              "  misurato sul sintetico: la differenza non è attribuibile al\n"
              "  caso. È la quantificazione diretta di quanto il dataset\n"
              "  sintetico sia ottimistico.")
    elif ic_p[0] > RIF_PRECISION_SINTETICO:
        print("  Il parser va MEGLIO sui reali che sul sintetico. È il caso\n"
              "  scomodo: va spiegato, non festeggiato. Possibili cause da\n"
              "  verificare prima di riportarlo — un pool troppo stretto, o\n"
              "  curriculum reali più semplici di quelli generati.")
    else:
        print("  L'intervallo di confidenza contiene il valore del sintetico:\n"
              "  con quindici documenti non si può concludere che i due\n"
              "  insiemi differiscano. Va detto così, senza forzare.")

    # ── Per documento ────────────────────────────────────────────────────────
    print(f"\n{SEP}\n  DETTAGLIO PER DOCUMENTO\n{SEP}")
    print(f"  {'documento':<16}{'TP':>5}{'FP':>5}{'FN':>5}"
          f"{'P':>8}{'R':>8}{'F1':>8}")
    print(f"  {'-'*55}")
    for d in per_doc:
        print(f"  {d['cv_id']:<16}{d['tp']:>5}{d['fp']:>5}{d['fn']:>5}"
              f"{d['precision']:>8.3f}{d['recall']:>8.3f}{d['f1']:>8.3f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_documenti": len(documenti),
        "precision": round(precision, 4), "ic_precision": [round(x, 4) for x in ic_p],
        "recall_relativo_al_pool": round(recall, 4),
        "ic_recall": [round(x, 4) for x in ic_r],
        "f1": round(f1_tot, 4),
        "tp": tp, "fp": fp, "fn": fn,
        "incerti_esclusi": n_inc, "aggiunte_manuali": n_agg,
        "ancoraggio": {
            "giudizi_binari": len(decisi),
            "con_indizio": len(con_aiuto),
            "accettazione_con_indizio": (round(acc_con, 4)
                                         if acc_con is not None else None),
            "accettazione_senza_indizio": (round(acc_senza, 4)
                                           if acc_senza is not None else None),
        },
        "riferimento_sintetico": {"precision": RIF_PRECISION_SINTETICO,
                                  "recall": RIF_RECALL_SINTETICO,
                                  "f1": RIF_F1_SINTETICO},
        "per_documento": per_doc,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {out}\n{SEP}\n")


if __name__ == "__main__":
    main()
