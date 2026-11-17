"""
valuta_escoxlmr.py  —  SkillPath AI
====================================
Misura il parser degli annunci con lo stadio di generazione dei candidati
sostituito: al posto dell'estrazione a regole (segmentazione sui confini
delle parole funzionali, ispirata a RAKE) si usano gli span prodotti da
`jjzha/escoxlmr_skill_extraction`.

Tutto il resto della pipeline resta identico: stesso indice ESCO bilingue,
stesso mappatore semantico, stesse tre soglie calibrate. È l'unica forma di
confronto che isola lo stadio 2 dell'architettura del Capitolo 2 — se
cambiasse anche altro, la differenza non sarebbe attribuibile.

QUANTO È LEALE QUESTO CONFRONTO
───────────────────────────────
Va dichiarato con precisione, perché il lettore se lo chiede.

  NON è un problema la lingua. Gli annunci con ground truth sono in inglese,
  e SkillSpan — su cui questo modello è affinato — pure. Il trasferimento
  cross-lingua non entra in gioco.

  È un problema la taratura. Denylist e soglie del parser locale sono state
  costruite osservando questi stessi 810 annunci; il modello non li ha mai
  visti. Il confronto parte quindi in salita per lui, e per questo lo script
  riporta la configurazione locale sia con sia senza denylist.

  È un problema la ground truth. Elenca le competenze che il generatore
  DOVEVA inserire, non quelle che ha davvero scritto (Capitolo 4, Sezione
  4.3). Un estrattore che trova solo ciò che sta nel testo paga quel costo
  per intero; le soglie locali sono invece state ottimizzate contro quel
  rumore. È la distorsione residua, e non si elimina: si dichiara.

Conclusione onesta: un vantaggio del modello sarebbe un risultato forte,
perché ottenuto in condizioni sfavorevoli. Uno svantaggio va letto insieme
alle due asimmetrie sopra e non dimostra granché.

PREREQUISITO
────────────
Gli span vanno estratti prima, nell'ambiente separato:

    python analysis/prova_escoxlmr.py --sorgente gt --annunci 810 \\
           --out outputs/span_escoxlmr.json

Poi questo script gira nell'ambiente normale del progetto, dove c'è
sentence-transformers. I due passi sono separati apposta: nessun ambiente
deve avere le dipendenze dell'altro.

Uso (dalla radice del progetto):
    python analysis/valuta_escoxlmr.py
"""

import argparse
import json
import statistics as st
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
DATA_IT = BASE_DIR / "dataset" / "source_it"
DATA_EN = BASE_DIR / "dataset" / "source_en"
DATA_SRC = BASE_DIR / "dataset" / "source"
JOBS_GT = BASE_DIR / "dataset" / "synthetic" / "jobs_gt" / "jobs.json"
SPAN_FILE = BASE_DIR / "outputs" / "span_escoxlmr.json"
OUT_FILE = BASE_DIR / "outputs" / "valuta_escoxlmr.json"

SEP = "─" * 74

# Soglie del parser degli annunci, quelle calibrate e in uso.
SOGLIE = {"sw": 0.82, "mw": 0.88, "acr": 0.84}

# Riferimenti dalla Tabella 6.6, per il confronto finale.
ABLAZIONE = [
    ("Nessun rimedio",                       0.297, 0.615, 0.391),
    ("Denylist (232 etichette)",             0.529, 0.607, 0.551),
    ("Vincolo multi-parola",                 0.540, 0.581, 0.546),
    ("Multi-parola + denylist (64)",         0.614, 0.577, 0.580),
    ("Multi-parola + classificatore",        0.807, 0.539, 0.629),
]


def f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if (p + r) else 0.0


def tipo_candidato(testo: str) -> str:
    """
    Classifica uno span come il parser locale classifica i suoi candidati:
    una parola, più parole, oppure acronimo. Serve ad applicare la stessa
    soglia allo stesso tipo di candidato — applicarne una sola renderebbe il
    confronto disomogeneo.
    """
    t = testo.strip()
    if len(t.split()) == 1:
        if t.isupper() and 2 <= len(t) <= 6:
            return "acr"
        return "sw"
    return "mw"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — parser degli annunci con riconoscitore appreso")
    ap.add_argument("--span", default=str(SPAN_FILE))
    ap.add_argument("--out", default=str(OUT_FILE))
    ap.add_argument("--soglia-sw", type=float, default=SOGLIE["sw"])
    ap.add_argument("--soglia-mw", type=float, default=SOGLIE["mw"])
    ap.add_argument("--soglia-acr", type=float, default=SOGLIE["acr"])
    args = ap.parse_args()

    p_span = Path(args.span)
    if not p_span.exists():
        print(f"[ERRORE] Span non trovati: {p_span}\n"
              f"         Estrarli prima nell'ambiente separato:\n"
              f"         python analysis/prova_escoxlmr.py --sorgente gt "
              f"--annunci 810 --out {p_span}")
        sys.exit(1)

    dati_span = json.loads(p_span.read_text(encoding="utf-8"))
    per_job = {d["job_id"]: d["span"] for d in dati_span.get("documenti", [])}
    print(f"\n{SEP}\n  PARSER DEGLI ANNUNCI CON RICONOSCITORE APPRESO\n{SEP}")
    print(f"  annunci con span estratti   {len(per_job)}")
    print(f"  modello                     {dati_span.get('modello','?')}")

    if not JOBS_GT.exists():
        print(f"[ERRORE] File non trovato: {JOBS_GT}")
        sys.exit(1)
    voci = json.loads(JOBS_GT.read_text(encoding="utf-8"))
    voci = voci if isinstance(voci, list) else list(voci.values())

    attese = {}
    for v in voci:
        if not isinstance(v, dict):
            continue
        exp = v.get("expected_skills") or {}
        ids = set((exp.get("required_ids") or []) + (exp.get("preferred_ids") or []))
        if ids:
            attese[v.get("job_id")] = ids

    comuni = [j for j in per_job if j in attese]
    print(f"  annunci con ground truth    {len(comuni)}")
    if not comuni:
        print("\n[ERRORE] Nessun annuncio confrontabile.")
        sys.exit(1)

    # ── Mappatore, configurato come il parser degli annunci ──────────────────
    sys.path.insert(0, str(SRC_DIR))
    from semantic_mapper import SemanticMapper

    print("\n  Carico l'indice ESCO bilingue…")
    mapper = SemanticMapper()
    if (DATA_IT / "skills.json").exists() and (DATA_EN / "skills.json").exists():
        mapper.load_databases_bilingual(str(DATA_IT / "skills.json"),
                                        str(DATA_EN / "skills.json"))
    else:
        mapper.load_database(str(DATA_SRC / "skills.json"))

    soglie = {"sw": args.soglia_sw, "mw": args.soglia_mw, "acr": args.soglia_acr}
    print(f"  soglie: {soglie}\n")

    tp = fp = fn = 0
    n_span = n_mappati = 0
    per_doc = []
    for i, jid in enumerate(sorted(comuni), 1):
        span = per_job[jid]
        n_span += len(span)

        # Gli span identici ripetuti nello stesso annuncio sono lo stesso
        # candidato: il parser locale non li conterebbe due volte.
        testi = {}
        for s in span:
            t = (s.get("testo") or "").strip()
            if t:
                testi.setdefault(tipo_candidato(t), set()).add(t)

        trovati = {}
        for tipo, insieme in testi.items():
            m = mapper.find_matches(sorted(insieme), threshold=soglie[tipo],
                                    top_k=1, max_results=30,
                                    return_scores=True)
            for x in m:
                if x["score"] > trovati.get(x["id"], 0.0):
                    trovati[x["id"]] = x["score"]
        n_mappati += len(trovati)

        gt = attese[jid]
        d_tp = len(set(trovati) & gt)
        d_fp = len(set(trovati) - gt)
        d_fn = len(gt - set(trovati))
        tp += d_tp
        fp += d_fp
        fn += d_fn
        per_doc.append({"job_id": jid, "tp": d_tp, "fp": d_fp, "fn": d_fn,
                        "span": len(span), "mappati": len(trovati)})

        if i % 100 == 0:
            print(f"    {i}/{len(comuni)} annunci…")

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1_tot = f1(precision, recall)

    print(f"\n{SEP}\n  RISULTATO\n{SEP}")
    print(f"  span in ingresso, media per annuncio   "
          f"{n_span/len(comuni):.1f}")
    print(f"  competenze ESCO dopo la mappatura      "
          f"{n_mappati/len(comuni):.1f}")
    print(f"  attese dalla ground truth              "
          f"{sum(len(attese[j]) for j in comuni)/len(comuni):.1f}")
    print()
    print(f"  Precision {precision:.3f}   Recall {recall:.3f}   F1 {f1_tot:.3f}")
    print(f"  veri positivi {tp} · falsi positivi {fp} · falsi negativi {fn}")

    print(f"\n{SEP}\n  CONFRONTO CON L'ABLAZIONE DEL CAPITOLO 6\n{SEP}")
    print(f"  {'configurazione':<36}{'Prec':>8}{'Rec':>8}{'F1':>8}")
    print(f"  {'-'*60}")
    for nome, p, r, f in ABLAZIONE:
        print(f"  {nome:<36}{p:>8.3f}{r:>8.3f}{f:>8.3f}")
    print(f"  {'-'*60}")
    print(f"  {'Riconoscitore appreso + mappatore':<36}"
          f"{precision:>8.3f}{recall:>8.3f}{f1_tot:>8.3f}")

    finale_f1 = ABLAZIONE[-1][3]
    multiword_f1 = ABLAZIONE[2][3]
    print()
    if f1_tot > finale_f1:
        print("  Il riconoscitore appreso supera la configurazione finale del\n"
              "  parser locale, e lo fa in condizioni sfavorevoli — soglie e\n"
              "  denylist locali sono tarate su questi stessi annunci, il\n"
              "  modello non li ha mai visti. È un risultato forte.")
    elif f1_tot > multiword_f1:
        print("  Il riconoscitore appreso supera il vincolo multi-parola ma\n"
              "  non la configurazione finale, che include il classificatore\n"
              "  addestrato. Confronto coerente con l'architettura a due\n"
              "  stadi: la generazione dei candidati non basta da sola.")
    else:
        print("  Il riconoscitore appreso non supera l'estrazione a regole su\n"
              "  questo banco di prova. Va letto insieme alle due asimmetrie\n"
              "  dichiarate in testa allo script: soglie tarate localmente e\n"
              "  ground truth che elenca competenze non sempre presenti nel\n"
              "  testo. Non dimostra che il metodo sia peggiore.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "modello": dati_span.get("modello"),
        "soglie": soglie,
        "n_annunci": len(comuni),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1_tot, 4),
        "tp": tp, "fp": fp, "fn": fn,
        "span_medi": round(n_span / len(comuni), 2),
        "mappati_medi": round(n_mappati / len(comuni), 2),
        "ablazione_riferimento": [
            {"configurazione": n, "precision": p, "recall": r, "f1": f}
            for n, p, r, f in ABLAZIONE
        ],
        "per_documento": per_doc,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {out}\n{SEP}\n")


if __name__ == "__main__":
    main()
