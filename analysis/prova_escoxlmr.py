"""
prova_escoxlmr.py  —  SkillPath AI
===================================
Assaggio di `jjzha/escoxlmr_skill_extraction` sugli annunci sintetici.

CHE COSA È QUESTO MODELLO, E CHE COSA NON È
───────────────────────────────────────────
È un etichettatore di sequenze: dato un testo, marca le porzioni che
costituiscono menzioni di competenze. **Non restituisce identificativi
ESCO**, malgrado il nome — «ESCO» si riferisce al pre-addestramento
(adattazione di dominio sulla tassonomia), non all'uscita. La
normalizzazione su ESCO resta compito di `semantic_mapper.py`.

Occupa quindi lo stadio 2 dell'architettura di riferimento (Capitolo 2):
sostituisce l'estrazione dei candidati a regole, non il resto della pipeline.

PERCHÉ NON SI CONFRONTANO GLI F1
────────────────────────────────
Un confronto di F1 sul dataset sintetico sarebbe scorretto per tre motivi
cumulativi, e vanno dichiarati:

  1. il banco di prova è tarato sul parser di questo progetto — denylist e
     soglie sono state costruite osservando quegli stessi annunci;
  2. l'affinamento di questo modello è avvenuto su SkillSpan, in inglese,
     mentre gli annunci sono italiani: si misurerebbero insieme la qualità
     del modello e la perdita in trasferimento cross-lingua;
  3. la ground truth elenca le competenze che il generatore *doveva*
     inserire, non quelle che ha davvero scritto (Capitolo 4, Sezione 4.3):
     un estrattore che trova solo ciò che sta nel testo paga quel costo per
     intero, mentre le soglie del parser locale sono state ottimizzate
     proprio contro quel rumore.

Si misurano invece tre cose che non dipendono dalla ground truth, e che
quindi non ereditano nessuna di queste distorsioni:

  A. quota di span privi di contenuto — la domanda del Capitolo 6: un
     riconoscitore addestrato emette frammenti come «responsible»?
  B. numero e lunghezza degli span prodotti, contro i candidati del parser
     locale — il vincolo multi-parola elimina il 45,5% dei candidati; un
     modello addestrato ha bisogno di un vincolo simile?
  C. quanti span sono di una parola sola, che è la forma del rumore
     grammaticale individuato nel Capitolo 6.

CONDIZIONE DI ARRESTO
─────────────────────
Se il modello non carica, o se su testo italiano produce span palesemente
rotti, ci si ferma e lo si dichiara. «Provato, non utilizzabile in queste
condizioni» è un esito legittimo.

AMBIENTE
────────
Da eseguire in un ambiente virtuale separato: questo script installa nulla,
ma `transformers` e `torch` vanno tenuti fuori dall'ambiente che produce i
numeri della tesi.

Uso (dalla radice del progetto, nell'ambiente separato):
    python analysis/prova_escoxlmr.py
    python analysis/prova_escoxlmr.py --annunci 20 --mostra 5
"""

import argparse
import json
import re
import statistics as st
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = BASE_DIR / "job_descriptions"
JOBS_GT = BASE_DIR / "dataset" / "synthetic" / "jobs_gt" / "jobs.json"
OUT_FILE = BASE_DIR / "outputs" / "prova_escoxlmr.json"

MODELLO = "jjzha/escoxlmr_skill_extraction"
SEP = "─" * 74

# Frammenti grammaticali senza contenuto proprio: è la categoria di rumore
# diagnosticata nel Capitolo 6. Se il modello addestrato li evita, il difetto
# è strutturale dell'estrazione a regole e non del compito.
SENZA_CONTENUTO = {
    "responsible", "seeking", "using", "complying", "required", "looking",
    "provided", "including", "working", "related", "based", "available",
    "responsabile", "richiesto", "utilizzando", "previsto", "relativo",
}

# Frase di servizio presente in coda a tutti gli annunci sintetici: è stata
# osservata generare falsi positivi nel parser locale, quindi vale la pena
# sapere se il modello la ignora.
CODA = "Testo esportato in forma sintetica"


def leggi_annuncio(p: Path) -> tuple[str, str]:
    """Ritorna (ruolo, corpo). Le prime righe sono metadati chiave: valore."""
    righe = p.read_text(encoding="utf-8").splitlines()
    ruolo, corpo = p.stem, []
    for r in righe:
        if r.startswith("Ruolo:"):
            ruolo = r.split(":", 1)[1].strip()
        elif ":" in r[:12] and len(r) < 60 and not corpo:
            continue          # altri metadati di testa
        elif r.strip():
            corpo.append(r.strip())
    return ruolo, " ".join(corpo)


def carica_documenti(sorgente: str, quanti: int) -> list:
    """
    Ritorna [(id, ruolo, testo)] dalla sorgente richiesta.

    Le due sorgenti NON sono equivalenti e la scelta cambia cosa si misura:

      txt  `job_descriptions/*.txt`, gli annunci mostrati dal frontend.
      gt   `dataset/synthetic/jobs_gt/jobs.json`, gli annunci con ground
           truth su cui sono misurate tutte le metriche del Capitolo 6.

    È in questi ultimi che vive il fenomeno diagnosticato nella Sezione 6.3
    — la frase «The successful candidate will be responsible for…» da cui
    nascono i candidati-detrito. Cercare quei frammenti nella prima sorgente
    non prova nulla: lì non potrebbero comparire comunque.
    """
    if sorgente == "txt":
        files = sorted(JOBS_DIR.glob("job_*.txt"))[:quanti]
        fuori = []
        for f in files:
            ruolo, corpo = leggi_annuncio(f)
            if corpo:
                fuori.append((f.stem, ruolo, corpo))
        return fuori

    if not JOBS_GT.exists():
        print(f"[ERRORE] File non trovato: {JOBS_GT}")
        sys.exit(1)
    dati = json.loads(JOBS_GT.read_text(encoding="utf-8"))
    voci = dati if isinstance(dati, list) else list(dati.values())

    # Il testo sta in entry["job"]["raw_text"]: è lo stesso campo che legge
    # tests/batch_parse_jobs_gt.py per alimentare il parser locale. Usare
    # quello garantisce che i due sistemi ricevano input identico — senza,
    # qualunque differenza osservata potrebbe venire dal testo e non dai
    # metodi.
    fuori = []
    for i, v in enumerate(voci[:quanti]):
        if not isinstance(v, dict):
            continue
        testo = ((v.get("job") or {}).get("raw_text") or "").strip()
        if not testo:
            continue
        ruolo = ((v.get("ground_truth") or {}).get("target_occupation_label")
                 or (v.get("job") or {}).get("title") or "—")
        fuori.append((v.get("job_id", f"gt_{i:04d}"), ruolo, testo))

    if not fuori:
        esempio = next((x for x in voci if isinstance(x, dict)), {})
        print("[ERRORE] Nessun raw_text trovato in jobs.json.\n"
              f"         Chiavi di primo livello: {sorted(esempio)}\n"
              f"         Chiavi di 'job': {sorted(esempio.get('job', {}))}")
        sys.exit(1)
    return fuori


def _testo(tokens: list) -> str:
    """
    Ricostruisce il testo da token SentencePiece.

    Il marcatore `▁` indica inizio di parola: diventa uno spazio. I token che
    ne sono privi sono continuazioni della parola precedente e si attaccano
    senza spazio — «▁coordinat» + «ing» = «coordinating». Il prefisso `##`
    dei tokenizzatori stile BERT è gestito per sicurezza, anche se questo
    modello non lo usa.
    """
    s = ""
    for t in tokens:
        if t.startswith("▁"):
            s += " " + t[1:]
        elif t.startswith("##"):
            s += t[2:]
        else:
            s += t
    return re.sub(r"\s+", " ", s).strip()


def ricomponi(spans: list) -> list:
    """
    Ricompone le competenze dai token etichettati.

    Due complicazioni si sommano, ed entrambe vanno gestite qui.

    La PRIMA è lo schema di etichettatura: il modello usa `B` e `I` puri, non
    `B-SKILL` e `I-SKILL`. L'aggregazione automatica di `transformers` li
    interpreta come due tipi di entità distinti e spezza ogni competenza in
    due tronconi, perciò si lavora sull'uscita grezza.

    La SECONDA è la tokenizzazione a sottoparole. Le etichette stanno sui
    token di SentencePiece, non sulle parole: «coordinating» si scompone in
    «▁coordinat» + «ing», e il modello può marcare la seconda come inizio di
    entità. Prendere ogni `B` alla lettera spezzerebbe le parole a metà.

    La regola che risolve entrambe: una nuova competenza comincia solo dove
    un token è marcato `B` **e** inizia una parola. Tutto il resto prolunga
    la competenza corrente.
    """
    fuori, corrente = [], None
    for s in spans:
        tok = s.get("word") or ""
        if not tok.strip():
            continue
        gruppo = (s.get("entity") or s.get("entity_group") or "").upper()
        inizio_parola = tok.startswith("▁") or not tok.startswith("##")
        nuova = gruppo.startswith("B") and tok.startswith("▁")

        if corrente is None or nuova:
            if corrente:
                fuori.append(corrente)
            corrente = {"tokens": [tok],
                        "score_min": float(s.get("score", 0.0))}
        else:
            corrente["tokens"].append(tok)
            corrente["score_min"] = min(corrente["score_min"],
                                        float(s.get("score", 0.0)))

    if corrente:
        fuori.append(corrente)

    puliti = []
    for v in fuori:
        testo = _testo(v["tokens"])
        if not testo:
            continue
        puliti.append({
            "testo": testo,
            "n_parole": len(testo.split()),
            "pezzi": len(v["tokens"]),
            "score_min": round(v["score_min"], 4),
        })
    return puliti


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — assaggio di ESCOXLM-R sugli annunci")
    ap.add_argument("--annunci", type=int, default=10,
                    help="Quanti annunci analizzare (default 10)")
    ap.add_argument("--sorgente", choices=("gt", "txt"), default="gt",
                    help="gt = annunci con ground truth del Capitolo 6 "
                         "(dove vive il fenomeno 'responsible'); "
                         "txt = job_descriptions/ usati dal frontend")
    ap.add_argument("--mostra", type=int, default=3,
                    help="Di quanti stampare gli span per esteso")
    ap.add_argument("--modello", default=MODELLO)
    ap.add_argument("--out", default=str(OUT_FILE))
    args = ap.parse_args()

    print(f"\n{SEP}\n  ASSAGGIO — {args.modello}\n{SEP}")

    # ── Caricamento, con la condizione di arresto ────────────────────────────
    try:
        from transformers import pipeline
    except ImportError:
        print("[ERRORE] transformers non installato in questo ambiente.\n"
              "         python -m venv .venv-esco && .venv-esco\\Scripts\\activate\n"
              "         pip install transformers torch")
        sys.exit(1)

    t0 = time.time()
    try:
        # Nessuna aggregazione automatica: le etichette sono `B` e `I` puri e
        # transformers le tratterebbe come entità diverse, spezzando ogni
        # competenza in due. La ricomposizione è fatta da ricomponi().
        ner = pipeline("token-classification", model=args.modello,
                       aggregation_strategy="none")
    except Exception as e:
        print(f"[ARRESTO] Il modello non si carica: {e}\n")
        print("  Esito legittimo da dichiarare: «provato, non utilizzabile\n"
              "  in queste condizioni». Non insistere.")
        sys.exit(2)
    print(f"  modello caricato in {time.time()-t0:.0f}s")

    documenti = carica_documenti(args.sorgente, args.annunci)
    if not documenti:
        print("[ERRORE] Nessun annuncio caricato.")
        sys.exit(1)
    print(f"  sorgente: {args.sorgente}   annunci: {len(documenti)}\n")

    risultati = []
    grezzi_totali = 0
    t0 = time.time()
    for i, (jid, ruolo, corpo) in enumerate(documenti, 1):
        try:
            spans = ner(corpo)
        except Exception as e:
            print(f"  [{i}] {jid}: ERRORE {e}")
            continue
        grezzi_totali += len(spans)
        voci = ricomponi(spans)
        risultati.append({"job_id": jid, "ruolo": ruolo,
                          "n_caratteri": len(corpo),
                          "span_grezzi": len(spans), "span": voci})
        print(f"  [{i}/{len(documenti)}] {str(jid)[:18]:<18} "
              f"{str(ruolo)[:30]:<30} {len(voci):>3} span "
              f"({len(spans)} grezzi)")

    if not risultati:
        print("\n[ARRESTO] Nessun annuncio analizzato con successo.")
        sys.exit(2)

    durata = time.time() - t0
    tutti = [v for r in risultati for v in r["span"]]

    # ══ A. Span privi di contenuto ═══════════════════════════════════════════
    print(f"\n{SEP}\n  A. IL MODELLO PRODUCE FRAMMENTI SENZA CONTENUTO?\n{SEP}")
    sospetti = [v for v in tutti
                if v["testo"].lower().strip(" ,.;:") in SENZA_CONTENUTO]
    quota = len(sospetti) / len(tutti) if tutti else 0.0
    print(f"  span totali                     {len(tutti)}")
    print(f"  span privi di contenuto         {len(sospetti)} "
          f"({quota*100:.1f}%)")
    if sospetti:
        for v in sospetti[:10]:
            print(f"      «{v['testo']}»  (score {v['score_min']:.3f})")
        print("\n  Il modello addestrato NON evita il rumore grammaticale:\n"
              "  il difetto del Capitolo 6 non è specifico dell'estrazione\n"
              "  a regole. È un risultato, e va riportato.")
    else:
        print("\n  Nessun frammento della lista. È l'indizio che il difetto\n"
              "  del Capitolo 6 è strutturale dell'estrazione a regole, e che\n"
              "  un riconoscitore addestrato lo eviterebbe per costruzione.")

    # ══ B. Numero e lunghezza ════════════════════════════════════════════════
    print(f"\n{SEP}\n  B. QUANTI SPAN, E DI CHE LUNGHEZZA\n{SEP}")
    per_doc = [len(r["span"]) for r in risultati]
    lung = [v["n_parole"] for v in tutti]
    una_parola = sum(1 for n in lung if n == 1)
    print(f"  span ricomposti        {len(tutti)}  "
          f"(da {grezzi_totali} token etichettati)")
    print(f"  span per annuncio      media {st.mean(per_doc):.1f}  "
          f"mediana {st.median(per_doc):.0f}  "
          f"min {min(per_doc)}  max {max(per_doc)}")

    # Gli annunci ripetono le stesse competenze in punti diversi del testo:
    # senza deduplicare, il numero di candidati risulta gonfiato rispetto a
    # quello che arriverebbe davvero al mappatore.
    unici = [len({v["testo"].lower() for v in r["span"]}) for r in risultati]
    print(f"  span distinti per annuncio   media {st.mean(unici):.1f}  "
          f"(ripetizioni: {(1 - sum(unici)/len(tutti))*100:.0f}%)")
    print(f"  parole per span        media {st.mean(lung):.2f}  "
          f"mediana {st.median(lung):.0f}")
    print(f"  span di una sola parola {una_parola}/{len(tutti)} "
          f"({una_parola/len(tutti)*100:.1f}%)")
    print(f"\n  Riferimento: nel parser locale il vincolo multi-parola elimina")
    print(f"  il 45,5% dei candidati prodotti dalla prosa (Capitolo 6).")

    # ══ C. La frase di servizio ══════════════════════════════════════════════
    print(f"\n{SEP}\n  C. LA FRASE DI SERVIZIO IN CODA\n{SEP}")
    print(f"  Tutti gli annunci sintetici terminano con «{CODA}…»,")
    print(f"  che nel parser locale genera il falso positivo «tradurre testi».")
    tocca_coda = [v for v in tutti
                  if v["testo"].lower() in ("testo", "testo esportato",
                                            "screening", "screening candidature")]
    print(f"\n  span che la intercettano: {len(tocca_coda)}")
    for v in tocca_coda[:5]:
        print(f"      «{v['testo']}»  ({v['score']})")

    # ══ Esempi per esteso ════════════════════════════════════════════════════
    print(f"\n{SEP}\n  ESEMPI PER ESTESO\n{SEP}")
    for r in risultati[:args.mostra]:
        print(f"\n  {r['job_id']} — {r['ruolo']}")
        for v in r["span"]:
            print(f"      {v['score_min']:.3f}  ({v['pezzi']} frammenti)  "
                  f"«{v['testo']}»")

    print(f"\n{SEP}")
    print(f"  tempo di analisi: {durata:.0f}s per {len(risultati)} annunci "
          f"({durata/len(risultati):.1f}s ciascuno)")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "modello": args.modello,
        "sorgente": args.sorgente,
        "span_grezzi_totali": grezzi_totali,
        "n_annunci": len(risultati),
        "secondi_per_annuncio": round(durata / len(risultati), 2),
        "span_totali": len(tutti),
        "quota_senza_contenuto": round(quota, 4),
        "quota_una_parola": round(una_parola / len(tutti), 4),
        "media_span_per_annuncio": round(st.mean(per_doc), 2),
        "media_parole_per_span": round(st.mean(lung), 2),
        "documenti": risultati,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {out}")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
