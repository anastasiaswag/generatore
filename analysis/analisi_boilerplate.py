"""
analisi_boilerplate.py  —  SkillPath AI
========================================
Misura quanta parte del testo degli annunci NON è un requisito (presentazione
aziendale, benefit, formule di rito) e quanti candidati skill ne provengono.

PERCHÉ
──────
Il parser degli annunci estrae circa il doppio delle skill che dovrebbe
(26.9 estratte contro 13.5 attese, prima della denylist). Il problema di
precision è quindi di sovra-produzione, non di qualità del match.

L'ipotesi da verificare è che una quota rilevante dei candidati provenga da
frasi che non esprimono requisiti. È lì che vivono le etichette-calamita:
"sarà responsabile di…" è fraseologia, non una competenza, e da sola
produceva 792 falsi positivi su 810 annunci.

Se la quota di candidati da boilerplate è alta, conviene aggiungere al parser
uno stadio che riconosce le sezioni di requisiti e ignora il resto — l'
equivalente della struttura che i CV ottengono gratis dal rendering in PDF.
Se è bassa, l'ipotesi non regge e si evita di scrivere codice inutile.

NOTA: la classificazione è euristica (marcatori lessicali), quindi i numeri
vanno letti come ordine di grandezza, non come misura esatta.

USO
───
    python analysis/analisi_boilerplate.py
    python analysis/analisi_boilerplate.py --esempi 5
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
JOBS_FILE = BASE_DIR / "dataset" / "synthetic" / "jobs_gt" / "jobs.json"

# ── Marcatori di requisito ────────────────────────────────────────────────────
REQUISITO = re.compile(
    r"\b(require|required|must|should|need|experience|knowledge|skill|"
    r"proficien|familiar|ability|able to|expertise|degree|qualification|"
    r"background in|competen|richiest|necessari|gradit|preferibil|"
    r"conoscenz|esperienz|capacit)\w*",
    re.IGNORECASE,
)

# ── Marcatori di contorno (azienda, condizioni, candidatura) ──────────────────
BOILERPLATE = re.compile(
    r"\b(we are|we offer|our company|our team|join us|equal opportunit|"
    r"benefit|salary|compensation|apply now|application|contact us|"
    r"located in|founded|leading provider|mission|culture|siamo|offriamo|"
    r"azienda leader|sede|contratto|retribuz)\w*",
    re.IGNORECASE,
)


def carica_funzioni_parser() -> tuple:
    """
    Estrae _split_into_sentences e _extract_content_phrases da job_parser.py
    senza importarlo, per non dipendere da torch/sentence-transformers.
    """
    src = (SRC_DIR / "job_parser.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    ns: dict = {"re": re}
    volute = {"_split_into_sentences", "_extract_content_phrases"}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            nomi = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n.startswith("_") for n in nomi):
                try:
                    exec(ast.get_source_segment(src, node), ns)
                except Exception:
                    pass
        elif isinstance(node, ast.FunctionDef) and node.name in volute:
            exec(ast.get_source_segment(src, node), ns)

    mancanti = volute - ns.keys()
    if mancanti:
        print(f"[ERRORE] Funzioni non trovate in job_parser.py: {mancanti}")
        sys.exit(1)
    return ns["_split_into_sentences"], ns["_extract_content_phrases"]


def classifica(frase: str) -> str:
    ha_req = bool(REQUISITO.search(frase))
    ha_boi = bool(BOILERPLATE.search(frase))
    if ha_req and not ha_boi:
        return "requisito"
    if ha_boi and not ha_req:
        return "boilerplate"
    return "ambigua"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — quota di testo non-requisito negli annunci"
    )
    ap.add_argument("--jobs", default=str(JOBS_FILE))
    ap.add_argument("--esempi", type=int, default=3,
                    help="Quante frasi di esempio mostrare per classe")
    args = ap.parse_args()

    percorso = Path(args.jobs)
    if not percorso.exists():
        print(f"[ERRORE] Corpus non trovato: {percorso}")
        return

    split_frasi, estrai_frasi = carica_funzioni_parser()
    annunci = json.loads(percorso.read_text(encoding="utf-8"))

    n_frasi = {"requisito": 0, "boilerplate": 0, "ambigua": 0}
    n_cand = {"requisito": 0, "boilerplate": 0, "ambigua": 0}
    esempi: dict[str, list] = {k: [] for k in n_frasi}
    resp = {"requisito": 0, "boilerplate": 0, "ambigua": 0}

    for a in annunci:
        testo = a.get("job", {}).get("raw_text", "") or ""
        for frase in split_frasi(testo):
            cls = classifica(frase)
            n_frasi[cls] += 1
            n_cand[cls] += len(estrai_frasi(frase)) if len(frase) > 60 else 1
            if re.search(r"\bresponsib|\bresponsabil", frase, re.IGNORECASE):
                resp[cls] += 1
            if len(esempi[cls]) < args.esempi and 40 < len(frase) < 160:
                esempi[cls].append(frase.strip())

    tot_f = sum(n_frasi.values())
    tot_c = sum(n_cand.values())
    if not tot_f:
        print("[Nessuna frase analizzata]")
        return

    print(f"\n{'═'*68}")
    print(f"  COMPOSIZIONE DEL TESTO — {len(annunci)} annunci")
    print(f"{'═'*68}\n")
    print(f"  {'classe':<14} {'frasi':>8} {'%':>7} {'candidati':>11} {'%':>7}")
    print(f"  {'─'*54}")
    for cls in ("requisito", "boilerplate", "ambigua"):
        print(f"  {cls:<14} {n_frasi[cls]:>8} {n_frasi[cls]/tot_f:>7.1%} "
              f"{n_cand[cls]:>11} {n_cand[cls]/tot_c:>7.1%}")
    print(f"  {'─'*54}")
    print(f"  {'totale':<14} {tot_f:>8} {'':>7} {tot_c:>11}")

    print(f"\n  Frasi contenenti \"responsib/responsabil\":")
    for cls in ("requisito", "boilerplate", "ambigua"):
        print(f"    {cls:<14} {resp[cls]:>6}")

    for cls in ("requisito", "boilerplate", "ambigua"):
        if esempi[cls]:
            print(f"\n  Esempi — {cls}:")
            for e in esempi[cls]:
                print(f"    · {e[:150]}")

    quota = n_cand["boilerplate"] / tot_c
    print(f"\n{'─'*68}")
    print("  LETTURA")
    print(f"  Il {quota:.0%} dei candidati proviene da frasi di contorno.")
    if quota >= 0.25:
        print("  Quota alta: uno stadio che isola le sezioni di requisiti")
        print("  è promettente e vale la pena implementarlo.")
    elif quota >= 0.12:
        print("  Quota intermedia: il guadagno atteso è modesto; da valutare")
        print("  rispetto al costo di manutenzione dell'euristica.")
    else:
        print("  Quota bassa: il boilerplate NON è la fonte principale dei")
        print("  falsi positivi. Meglio non investire su questa strada.")
    print(f"{'─'*68}\n")


if __name__ == "__main__":
    main()
