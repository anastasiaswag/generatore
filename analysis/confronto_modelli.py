"""
confronto_modelli.py  —  SkillPath AI
======================================
Confronta encoder di embedding diversi sullo stesso compito, stessi dati,
stessa pipeline.

LA DOMANDA
──────────
Quanto del risultato dipende dal modello e quanto dalla pipeline costruita
attorno? È una distinzione che le metriche finali da sole non permettono di
fare, e ha una conseguenza pratica: se un encoder più grande guadagna poco,
allora investire in un fine-tuning renderà probabilmente poco, e conviene
lavorare altrove.

PREREQUISITO GIÀ RISOLTO
────────────────────────
Le cache degli embedding sono separate per modello (vedi `_tag_modello` in
semantic_mapper). Prima non lo erano: cambiando encoder si sarebbero
ricaricati silenziosamente gli embedding del precedente, producendo numeri
plausibili e privi di senso.

LA CORREZIONE HUBNESS VA DISATTIVATA
────────────────────────────────────
Il confronto gira con --no-hubness, e la ragione è la stessa di sopra vista da
un'altra angolatura. Il profilo di background è un vettore di deviazioni per
etichetta, calcolato nello spazio vettoriale di UN encoder preciso. La sua
lunghezza dipende però dal solo numero di etichette, identico fra modelli:
un profilo calibrato su un altro encoder si carica quindi senza errori e
falsa i punteggi in silenzio.

È esattamente ciò che è accaduto alla prima esecuzione con MiniLM: il profilo
di e5-base, applicato a uno spazio vettoriale diverso, ha portato i punteggi
delle competenze sopra 1,0 — valore impossibile per un coseno — e ha depresso
quelli delle occupazioni sotto la soglia di accettazione, azzerando il
riconoscimento dell'occupazione in 765 annunci su 810. Il file adesso porta il
tag del modello, quindi l'errore non può ripetersi; resterebbe però l'onere di
calibrare un profilo per ciascuno dei sette encoder.

Non ne vale la pena: la correzione hubness è già stata misurata come
ininfluente sui risultati. Disattivarla toglie una variabile di confondimento
dal confronto senza costare nulla. Va però detto in tesi, perché la riga di
e5-base in questa tabella può discostarsi lievemente dalla configurazione di
produzione, dove la correzione è attiva.

COSTO
─────
Per ogni modello mai usato prima serve costruire due indici di embedding —
circa 118.000 etichette per le competenze e 49.000 per le occupazioni. Su CPU
sono decine di minuti, una tantum. Il parsing degli 810 annunci aggiunge circa
venti minuti. Conviene lanciarlo e lasciarlo lavorare.

I MODELLI SUGGERITI
───────────────────
  paraphrase-multilingual-MiniLM-L12-v2   384 dim — il modello usato all'inizio
                                          del progetto, utile come riferimento
                                          storico
  intfloat/multilingual-e5-small          384 dim — stessa famiglia dell'attuale
                                          ma più piccolo: isola l'effetto della
                                          dimensione dall'effetto della famiglia
  intfloat/multilingual-e5-base           768 dim — quello in uso
  intfloat/multilingual-e5-large         1024 dim — il più grande della famiglia,
                                          lento su CPU

Il confronto fra e5-small, e5-base ed e5-large misura il rendimento della
dimensione a parità di addestramento; il confronto con MiniLM misura la
differenza fra famiglie.

Uso (dalla radice del progetto):
    python analysis/confronto_modelli.py --lista
    python analysis/confronto_modelli.py --modelli intfloat/multilingual-e5-small
    python analysis/confronto_modelli.py --tutti --max 200
    python analysis/confronto_modelli.py --solo-riepilogo
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Su Windows la console usa UTF-8, ma quando l'output viene rediretto o passato
# in pipe Python ricade sulla codifica di sistema (cp1252), che non contiene i
# caratteri di riquadro usati qui: lo script muore con UnicodeEncodeError prima
# ancora di fare il suo lavoro. Si forza UTF-8 sull'uscita.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "outputs" / "confronto_modelli"
RIEPILOGO = BASE_DIR / "outputs" / "confronto_modelli.json"

# Ordinati per costo crescente su CPU. I primi cinque bastano a rispondere
# alla domanda; gli ultimi due sono utili ma pesanti.
MODELLI = [
    # famiglia sentence-transformers: due taglie
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",   # 384 dim
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",   # 768 dim
    # famiglia E5: tre taglie, isolano l'effetto della dimensione
    "intfloat/multilingual-e5-small",                                # 384 dim
    "intfloat/multilingual-e5-base",                                 # 768 dim
    "intfloat/multilingual-e5-large",                                # 1024 dim
    # encoder recenti, più costosi
    "Alibaba-NLP/gte-multilingual-base",   # 768 dim, richiede codice remoto
    "BAAI/bge-m3",                         # 1024 dim, ~2,2 GB: molto lento su CPU
]

# Modelli su cui non conviene insistere se il tempo è limitato
COSTOSI = {"intfloat/multilingual-e5-large", "BAAI/bge-m3"}

SEP = "─" * 74


def tag(nome: str) -> str:
    return nome.split("/")[-1]


def metriche(percorso: Path) -> dict:
    """Precision, recall e F1 macro sulle skill, come analisi_job_parser."""
    res = json.loads(percorso.read_text(encoding="utf-8"))
    P = R = F = 0.0
    n = tp = fp = 0
    occ_ok = occ_tot = 0
    # Sentinelle. Un coseno non può superare 1,0: se accade, ai punteggi è
    # stato sommato qualcosa che non appartiene a questo spazio vettoriale.
    # Un'occupazione assente in quasi tutti i documenti indica invece una
    # soglia tarata su un altro encoder. Entrambi i casi si sono già
    # verificati: meglio che lo script se ne accorga da solo.
    punteggi_impossibili = 0
    occ_assenti = 0
    for e in res:
        for m in (e.get("skills", {}) or {}).get("all_matches", []) or []:
            if (m.get("score") or 0) > 1.0:
                punteggi_impossibili += 1
        if not ((e.get("occupation") or {}).get("id")):
            occ_assenti += 1
        ex = e.get("expected_skills", {})
        gt = set(ex.get("required_ids", []) + ex.get("preferred_ids", []))
        s = e.get("skills", {})
        trovate = set(s.get("required_ids", []) + s.get("preferred_ids", []))

        gt_occ = (e.get("ground_truth") or {}).get("target_occupation_id", "")
        if gt_occ:
            occ_tot += 1
            occ_ok += (e.get("occupation") or {}).get("id", "") == gt_occ

        if not gt and not trovate:
            continue
        n += 1
        a, b, c = len(trovate & gt), len(trovate - gt), len(gt - trovate)
        tp += a
        fp += b
        p = a / (a + b) if a + b else 0.0
        r = a / (a + c) if a + c else 0.0
        P += p
        R += r
        F += (2 * p * r / (p + r)) if p + r else 0.0

    return {
        "n": n,
        "precision": round(P / n, 4),
        "recall": round(R / n, 4),
        "f1": round(F / n, 4),
        "tp": tp,
        "fp": fp,
        "accuracy_occupazione": round(occ_ok / occ_tot, 4) if occ_tot else 0.0,
        "punteggi_impossibili": punteggi_impossibili,
        "quota_senza_occupazione": round(occ_assenti / len(res), 4) if res else 0.0,
    }


def esegui(modello: str, max_annunci: int | None,
           con_hubness: bool = False) -> Path | None:
    """Lancia il batch parse con l'encoder indicato."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{tag(modello)}.json"

    if out.exists():
        print(f"  già presente: {out.name} — salto il parsing")
        return out

    cmd = [sys.executable, str(BASE_DIR / "tests" / "batch_parse_jobs_gt.py"),
           "--modello", modello, "--classificatore", "--out", str(out)]
    # Vedi la docstring: senza un profilo calibrato per QUESTO encoder la
    # correzione hubness falsa i punteggi in silenzio.
    if not con_hubness:
        cmd += ["--no-hubness"]
    if max_annunci:
        cmd += ["--max", str(max_annunci)]

    print(f"  comando: {' '.join(cmd[1:])}\n")
    t0 = time.time()
    esito = subprocess.run(cmd, cwd=str(BASE_DIR))
    if esito.returncode != 0:
        print(f"  [ERRORE] il parsing con {tag(modello)} è fallito")
        return None
    print(f"  completato in {(time.time()-t0)/60:.1f} min")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — confronto fra encoder di embedding")
    ap.add_argument("--modelli", nargs="+", default=None,
                    help="Modelli da valutare (default: quello in uso)")
    ap.add_argument("--tutti", action="store_true",
                    help="Valuta tutti i modelli suggeriti")
    ap.add_argument("--max", type=int, default=None,
                    help="Limita a N annunci per velocizzare la prova")
    ap.add_argument("--lista", action="store_true",
                    help="Mostra i modelli suggeriti ed esce")
    ap.add_argument("--solo-riepilogo", action="store_true",
                    help="Ricalcola il riepilogo dai file già prodotti")
    ap.add_argument("--con-hubness", action="store_true",
                    help="Mantiene attiva la correzione hubness. Da usare SOLO "
                         "se esiste un profilo calibrato per ciascun encoder "
                         "confrontato (vedi analysis/costruisci_profilo_background.py "
                         "--modello). Altrimenti i punteggi risultano falsati.")
    args = ap.parse_args()

    if args.lista:
        print("\nModelli suggeriti:\n")
        for m in MODELLI:
            print(f"  {m}")
        print("\nUno per volta:")
        print("  python analysis/confronto_modelli.py --modelli "
              "intfloat/multilingual-e5-small\n")
        return

    if args.solo_riepilogo:
        modelli = [m for m in MODELLI if (OUT_DIR / f"{tag(m)}.json").exists()]
        if not modelli:
            print(f"[ERRORE] Nessun risultato in {OUT_DIR}")
            return
    else:
        modelli = MODELLI if args.tutti else (args.modelli or [MODELLI[3]])
        for m in modelli:
            if m in COSTOSI:
                print(f"\n  Nota: {tag(m)} è pesante su CPU — "
                      "attendersi tempi lunghi per la costruzione dell'indice.")
        if args.con_hubness:
            print("\n  ATTENZIONE: correzione hubness attiva. Verificare che "
                  "esista un\n  profilo calibrato per ciascun encoder, "
                  "altrimenti i punteggi sono falsati.")
        for i, m in enumerate(modelli, 1):
            print(f"\n{SEP}\n  [{i}/{len(modelli)}]  {m}\n{SEP}")
            esegui(m, args.max, con_hubness=args.con_hubness)

    # ── Riepilogo ────────────────────────────────────────────────────────────
    righe = []
    for m in modelli:
        f = OUT_DIR / f"{tag(m)}.json"
        if f.exists():
            righe.append((m, metriche(f)))

    if not righe:
        print("[ERRORE] Nessun risultato da confrontare.")
        return

    print(f"\n{SEP}\n  CONFRONTO FRA ENCODER — stessa pipeline, stessi dati\n{SEP}")
    print(f"  {'modello':<40}{'Prec':>8}{'Rec':>8}{'F1':>8}{'occ.':>8}")
    print(f"  {'-'*72}")
    for m, x in sorted(righe, key=lambda t: -t[1]["f1"]):
        print(f"  {tag(m):<40}{x['precision']:>8.3f}{x['recall']:>8.3f}"
              f"{x['f1']:>8.3f}{x['accuracy_occupazione']:>8.3f}")

    # ── Controlli di sanità, prima di qualunque lettura dei numeri ───────────
    allarmi = []
    for m, x in righe:
        if x["punteggi_impossibili"]:
            allarmi.append(
                f"  {tag(m)}: {x['punteggi_impossibili']} punteggi sopra 1,0. "
                "Un coseno\n    non può superare 1: quasi certamente è attiva "
                "una correzione hubness\n    calibrata su un altro encoder. "
                "Rilanciare con --no-hubness.")
        if x["quota_senza_occupazione"] > 0.5:
            allarmi.append(
                f"  {tag(m)}: nessuna occupazione riconosciuta nel "
                f"{x['quota_senza_occupazione']:.1%} dei documenti.\n"
                "    Le soglie sono tarate su un altro encoder, oppure i "
                "punteggi sono falsati.")
    if allarmi:
        print(f"\n{SEP}\n  ANOMALIE — questi numeri NON sono confrontabili\n{SEP}")
        for a in allarmi:
            print(a)
        print(SEP)

    if len(righe) > 1:
        f1 = [x["f1"] for _, x in righe]
        scarto = max(f1) - min(f1)
        print(f"\n  Scarto fra il migliore e il peggiore: {scarto:.3f} di F1")
        print(f"\n{SEP}\n  LETTURA\n{SEP}")
        if scarto < 0.05:
            print("  Gli encoder si equivalgono. Il risultato dipende dalla")
            print("  pipeline, non dal modello: investire in un encoder più")
            print("  grande o in un fine-tuning renderebbe poco.")
        elif scarto < 0.12:
            print("  La scelta dell'encoder incide moderatamente. Vale la pena")
            print("  usare il migliore fra quelli disponibili, ma il margine")
            print("  non giustifica da solo un lavoro di adattamento.")
        else:
            print("  L'encoder incide in modo sostanziale: qui un fine-tuning")
            print("  sul dominio avrebbe ragionevoli probabilità di rendere.")
        print(SEP)

    RIEPILOGO.write_text(
        json.dumps({tag(m): x for m, x in righe}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"\n  Riepilogo salvato in {RIEPILOGO}")


if __name__ == "__main__":
    main()
