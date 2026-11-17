"""
valuta_certificazioni.py  —  SkillPath AI
==========================================
Valuta il percorso delle certificazioni contro la ground truth dei CV
sintetici, e cerca la soglia migliore senza riparsare.

PERCHÉ QUESTO SCRIPT ESISTE
───────────────────────────
Il percorso delle certificazioni non era mai stato valutato. Le competenze sì,
le lingue sì, l'occupazione sì; le certificazioni no. Il difetto è emerso solo
provando il parser su 15 curriculum reali:

    Abilitazione PES/PAV (lavori elettrici)   assegnata a 14 persone su 15
    RSPP                                      assegnata a 12 su 15
    Abilitazione Muletto                      assegnata a 10 su 15

e 9 documenti su 15 avevano saturato il tetto di 10 certificazioni.

Sul dataset sintetico il difetto era invisibile per una ragione precisa: il
generatore pescava le certificazioni dalla stessa lista usata per il
riconoscimento, quindi i match risultavano corretti per costruzione. La ground
truth però esiste ed è verificabile — i CV sintetici hanno in media 1.34
certificazioni — mentre il parser ne estrae circa 4.6. La sovraproduzione c'era
anche lì: mancava solo qualcuno che la misurasse.

DUE DIFETTI DISTINTI
────────────────────
  1. LA SOGLIA. 0.75 contro lo 0.85 e 0.88 usati per le competenze. Non c'è
     ragione perché le certificazioni debbano essere più permissive: semmai il
     contrario, dato che sono un vocabolario chiuso e ben definito.

  2. DOVE SI CERCA. I candidati sono `cert_lines + skl_lines + edu_lines`:
     anche le righe di competenze e istruzione. Recupera qualcosa quando la
     sezione dedicata non viene riconosciuta, ma espone ogni riga di competenze
     al rischio di essere scambiata per una certificazione. Sui 15 curriculum
     reali la sezione dedicata è stata riconosciuta in UN solo documento: quasi
     tutti i candidati arrivavano quindi da righe che certificazioni non erano.

I due difetti si misurano separatamente, perché i rimedi sono indipendenti.

COME FUNZIONA LA RICERCA
────────────────────────
La soglia è un filtro applicato dopo il calcolo dei punteggi. Se il parsing
avviene una volta con una soglia bassa e un tetto alto, tutte le
certificazioni deboli restano nel file, e qualunque soglia più alta si applica
a posteriori. Non serve riparsare per ogni valore.

Uso (dalla radice del progetto):

  1) Parsing di calibrazione su un sottoinsieme di CV sintetici:
       python tests/batch_parse_cvs.py --max 150 --soglia-cert 0.55 \
              --cert-max 40 --out outputs/cal_cert.json

  2) Valutazione e ricerca della soglia:
       python analysis/valuta_certificazioni.py --in outputs/cal_cert.json

  3) Verifica dell'altro difetto, riparsando con la restrizione alla sezione:
       python tests/batch_parse_cvs.py --max 150 --cert-solo-sezione \
              --out outputs/cal_cert_sezione.json
       python analysis/valuta_certificazioni.py --in outputs/cal_cert_sezione.json
"""

import argparse
import json
import statistics as st
import sys
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
CVS_SORGENTE = BASE_DIR / "dataset" / "synthetic" / "cvs.json"

SEP = "─" * 74
SOGLIA_ATTUALE = 0.75


def griglia(lo: float, hi: float, passo: float) -> list[float]:
    n = int(round((hi - lo) / passo)) + 1
    return [round(lo + i * passo, 4) for i in range(n)]


def normalizza_id(cv_id: str) -> str:
    """
    Riconduce alla stessa forma gli identificativi dei due file.

    Il generatore scrive `cv_<uuid>_<livello>_<n>`; il batch di parsing scrive
    `parsed_cv_<uuid>_<livello>_<n>.pdf`, perché costruisce l'identificativo
    dal nome del file. Senza questa normalizzazione l'incrocio con la ground
    truth non trova nulla e tutte le metriche risultano zero — cosa che
    sembrerebbe un difetto del parser invece che dello script.
    """
    s = (cv_id or "").strip()
    if s.startswith("parsed_"):
        s = s[len("parsed_"):]
    for est in (".pdf", ".docx", ".doc", ".txt"):
        if s.lower().endswith(est):
            s = s[: -len(est)]
    return s


def ground_truth() -> dict[str, set]:
    """cv_id normalizzato → insieme degli id di certificazione del generatore."""
    if not CVS_SORGENTE.exists():
        print(f"[ERRORE] Sorgente dei CV sintetici non trovata: {CVS_SORGENTE}")
        sys.exit(1)
    gt = {}
    for e in json.loads(CVS_SORGENTE.read_text(encoding="utf-8")):
        certs = (e.get("cv") or {}).get("certifications") or []
        gt[normalizza_id(e["cv_id"])] = {
            c.get("cert_id") for c in certs if c.get("cert_id")}
    return gt


def metriche(dati: list[dict], gt: dict[str, set], soglia: float) -> dict:
    """Precision, recall e F1 macro sulle certificazioni a una data soglia."""
    P = R = F = 0.0
    n = tp_tot = fp_tot = 0
    estratte_tot = 0
    for e in dati:
        cv_id = normalizza_id(e.get("cv_id"))
        if cv_id not in gt:
            continue
        veri = gt[cv_id]
        trovate = {c["id"] for c in ((e.get("cv") or {}).get("certifications") or [])
                   if c.get("score", 0) >= soglia}
        estratte_tot += len(trovate)
        if not veri and not trovate:
            continue
        n += 1
        a, b, c = len(trovate & veri), len(trovate - veri), len(veri - trovate)
        tp_tot += a
        fp_tot += b
        p = a / (a + b) if a + b else 0.0
        r = a / (a + c) if a + c else 0.0
        P += p
        R += r
        F += (2 * p * r / (p + r)) if p + r else 0.0
    if not n:
        return {"n": 0, "precision": 0, "recall": 0, "f1": 0,
                "tp": 0, "fp": 0, "medie": 0}
    return {"n": n, "precision": P / n, "recall": R / n, "f1": F / n,
            "tp": tp_tot, "fp": fp_tot,
            "medie": estratte_tot / len(dati)}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — valutazione del percorso certificazioni")
    ap.add_argument("--in", dest="inp", required=True,
                    help="Risultati del parsing dei CV sintetici")
    ap.add_argument("--passo", type=float, default=0.01)
    ap.add_argument("--quota-taratura", type=float, default=0.30,
                    help="Frazione di CV usata per scegliere la soglia")
    args = ap.parse_args()

    percorso = Path(args.inp)
    if not percorso.exists():
        print(f"[ERRORE] File non trovato: {percorso}")
        sys.exit(1)

    dati = json.loads(percorso.read_text(encoding="utf-8"))
    gt = ground_truth()

    tutti = [c.get("score", 0)
             for e in dati
             for c in ((e.get("cv") or {}).get("certifications") or [])]

    print(f"\n{SEP}\n  PERCORSO CERTIFICAZIONI — valutazione\n{SEP}")
    print(f"  CV analizzati            {len(dati)}")
    print(f"  certificazioni vere, media   "
          f"{st.mean([len(gt.get(normalizza_id(e.get('cv_id')), set())) for e in dati]):.2f}")
    print(f"  certificazioni estratte, media {len(tutti)/max(len(dati),1):.2f}")
    if tutti:
        print(f"  punteggi: min {min(tutti):.3f}  mediana {st.median(tutti):.3f}"
              f"  max {max(tutti):.3f}")
        if min(tutti) > SOGLIA_ATTUALE - 0.05:
            print(f"\n  [ATTENZIONE] Il punteggio più basso è {min(tutti):.3f}: il "
                  f"parsing è avvenuto\n               con la soglia predefinita. "
                  f"Per esplorare valori più bassi\n               riparsare con "
                  f"--soglia-cert 0.55 --cert-max 40.")

    # ── Ricerca della soglia ─────────────────────────────────────────────────
    n_tara = int(len(dati) * args.quota_taratura)
    tara, riporto = dati[:n_tara], dati[n_tara:]

    valori = griglia(0.55, 0.98, args.passo)
    migliore, scelta = -1.0, SOGLIA_ATTUALE
    for v in valori:
        f1 = metriche(tara, gt, v)["f1"]
        if f1 > migliore + 1e-9:
            migliore, scelta = f1, v

    print(f"\n{SEP}\n  RICERCA DELLA SOGLIA\n{SEP}")
    print(f"  taratura su {len(tara)} CV, riporto su {len(riporto)}\n")
    print(f"  {'soglia':>8}{'Prec':>9}{'Rec':>9}{'F1':>9}"
          f"{'estratte/CV':>14}")
    print(f"  {'-'*49}")
    for v in [0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]:
        m = metriche(riporto, gt, v)
        stella = "  ←" if abs(v - scelta) < 1e-6 else ""
        etichetta = f"{v:.2f}" + (" *" if abs(v - SOGLIA_ATTUALE) < 1e-6 else "")
        print(f"  {etichetta:>8}{m['precision']:>9.3f}{m['recall']:>9.3f}"
              f"{m['f1']:>9.3f}{m['medie']:>14.2f}{stella}")
    print(f"\n  * = soglia attualmente in uso")

    m_att = metriche(riporto, gt, SOGLIA_ATTUALE)
    m_new = metriche(riporto, gt, scelta)

    print(f"\n{SEP}\n  ESITO (sul sottoinsieme di riporto)\n{SEP}")
    print(f"  {'configurazione':<24}{'Prec':>9}{'Rec':>9}{'F1':>9}"
          f"{'estratte/CV':>14}")
    print(f"  {'-'*65}")
    print(f"  {'soglia attuale 0.75':<24}{m_att['precision']:>9.3f}"
          f"{m_att['recall']:>9.3f}{m_att['f1']:>9.3f}{m_att['medie']:>14.2f}")
    print(f"  {'soglia calibrata ' + f'{scelta:.2f}':<24}{m_new['precision']:>9.3f}"
          f"{m_new['recall']:>9.3f}{m_new['f1']:>9.3f}{m_new['medie']:>14.2f}")

    delta = m_new["f1"] - m_att["f1"]
    print(f"\n  Guadagno di F1: {delta:+.3f}")
    if delta > 0.02:
        print(f"\n  La soglia va alzata da 0.75 a {scelta:.2f}. Comando per il")
        print(f"  parsing definitivo dei CV sintetici:")
        print(f"    python tests/batch_parse_cvs.py --soglia-cert {scelta:.2f}")
        print(f"  e per i curriculum reali:")
        print(f"    python tests/parse_cv_reali.py --cartella \"...\" --anonimo \\")
        print(f"           --soglia-cert {scelta:.2f}")
    elif delta > 0:
        print("  Il guadagno è modesto: la soglia non è il difetto principale.")
        print("  Verificare l'altro, cioè DOVE si cercano le certificazioni:")
        print("    python tests/batch_parse_cvs.py --max 150 --cert-solo-sezione \\")
        print("           --out outputs/cal_cert_sezione.json")
    else:
        print("  Nessun guadagno. Sul sintetico la soglia è già adeguata, e il")
        print("  problema osservato sui curriculum reali va cercato altrove —")
        print("  con ogni probabilità nel fatto che i candidati provengono anche")
        print("  dalle righe di competenze e istruzione.")

    print(SEP + "\n")


if __name__ == "__main__":
    main()
