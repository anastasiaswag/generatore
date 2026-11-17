"""
verifica_ablazione.py  —  SkillPath AI
=======================================
Controlla se i file da cui nasce la tabella di ablazione del parser degli
annunci (Capitolo 6) sono stati prodotti con le soglie attualmente in uso.

PERCHÉ IL DUBBIO
────────────────
Aprendo il frontend su un annuncio sintetico, il parser ha estratto
`tradurre testi` — un falso positivo che con ogni probabilità nasce dalla
frase di servizio presente in coda a tutti gli annunci generati:
«Testo esportato in forma sintetica per screening candidature».

Quella etichetta però non compare in `batch_job_results.json`. Se non
comparisse nemmeno nel file usato per l'ablazione, significherebbe che la
tabella pubblicata e il codice consegnato girano con configurazioni diverse:
le soglie calibrate, più basse sulle singole parole, lasciano passare un
falso positivo sistematico che l'ablazione non registra.

Non è una prova definitiva — è un indizio forte, e dice dove guardare.

Uso (dalla radice del progetto):
    python tests/verifica_ablazione.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "outputs"
SEP = "─" * 72

# Etichette che, se presenti, indicano un parsing con le soglie basse
# attuali; se assenti ovunque, il file è probabilmente anteriore alla
# calibrazione.
SPIE = ["tradurre testi"]

# File coinvolti nella tabella di ablazione del Capitolo 6, più i due
# batch principali come riferimento temporale.
FILE = [
    "job_gt_batch_results.json",
    "batch_job_results.json",
    "ab_nodeny.json",
    "ab_full.json",
    "ab_multiword_deny.json",
    "ab_multiword_nodeny.json",
    "ab_bg.json",
    "eval_full.json",
    "eval_nodeny.json",
    "job_parser_eval.json",
]


def etichette(dati) -> list:
    """Estrae tutte le etichette di competenza, qualunque sia la forma."""
    fuori = []
    voci = dati if isinstance(dati, list) else [dati]
    for e in voci:
        if not isinstance(e, dict):
            continue
        sk = e.get("skills")
        if isinstance(sk, dict):
            for m in (sk.get("all_matches") or []):
                if isinstance(m, dict) and m.get("label"):
                    fuori.append(m["label"])
    return fuori


def main() -> None:
    print(f"\n{SEP}\n  COERENZA FRA I FILE DELL'ABLAZIONE E LE SOGLIE ATTUALI\n{SEP}")
    print(f"  {'file':<34}{'modificato':>18}{'etich.':>9}{'spia':>7}")
    print(f"  {'-'*68}")

    trovato_da_qualche_parte = False
    for nome in FILE:
        p = OUT / nome
        if not p.exists():
            print(f"  {nome:<34}{'assente':>18}{'—':>9}{'—':>7}")
            continue
        quando = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m %H:%M")
        try:
            dati = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  {nome:<34}{quando:>18}{'illeggibile':>9}{'—':>7}")
            continue
        lab = etichette(dati)
        n_spia = sum(1 for s in SPIE for x in lab if x == s)
        if n_spia:
            trovato_da_qualche_parte = True
        print(f"  {nome:<34}{quando:>18}{len(lab):>9}{n_spia:>7}")

    print(f"\n{SEP}")
    if trovato_da_qualche_parte:
        print("  L'etichetta spia compare: i file sono stati prodotti con le\n"
              "  soglie attuali. Nessuna incoerenza fra tesi e codice.")
    else:
        print("  L'etichetta spia NON compare in nessun file, ma il parser\n"
              "  attuale la produce. Due possibilità:\n")
        print("    a) i file dell'ablazione sono anteriori alla calibrazione\n"
              "       delle soglie → la Tabella 6.6 descrive una configurazione\n"
              "       diversa da quella che consegni;\n")
        print("    b) l'annuncio visto nel frontend non fa parte di questo\n"
              "       insieme, e la spia semplicemente non si applica.\n")
        print("  Per distinguerle: riparsa una decina di annunci con la\n"
              "  configurazione attuale e confronta le competenze estratte con\n"
              "  quelle memorizzate. Se coincidono è (b), se differiscono è (a).")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
