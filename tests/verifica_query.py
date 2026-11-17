"""
verifica_query.py  —  SkillPath AI
===================================
Verifica che l'aggiunta della chiave `query` in semantic_mapper.find_matches
non abbia alterato nulla.

La modifica è additiva — registra quale frase ha prodotto ogni match, dato
che prima veniva scartato — e non dovrebbe toccare né i punteggi né la
selezione. Questo script lo controlla invece di darlo per scontato:
confronta un parsing nuovo con quello di riferimento già in outputs/ e
segnala qualunque differenza negli identificativi estratti o nei punteggi.

Uso (dalla radice del progetto):
    python tests/batch_parse_cvs.py --max 20 --out outputs/prova_query.json
    python tests/verifica_query.py
"""

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BASE = Path(__file__).resolve().parent.parent
NUOVO = BASE / "outputs" / "prova_query.json"
RIFERIMENTO = BASE / "outputs" / "cv_batch_results.json"
SEP = "─" * 70


def indicizza(path: Path) -> dict:
    if not path.exists():
        print(f"[ERRORE] File non trovato: {path}")
        sys.exit(1)
    fuori = {}
    for e in json.loads(path.read_text(encoding="utf-8")):
        matches = ((e.get("cv", {}).get("skills") or {}).get("all_matches") or [])
        fuori[e.get("cv_id")] = {m["id"]: m.get("score") for m in matches}
    return fuori


def main() -> None:
    nuovo = indicizza(NUOVO)
    rif = indicizza(RIFERIMENTO)

    comuni = sorted(set(nuovo) & set(rif))
    print(f"\n{SEP}\n  VERIFICA DELLA MODIFICA ADDITIVA A semantic_mapper\n{SEP}")
    print(f"  documenti nel file nuovo     {len(nuovo)}")
    print(f"  documenti confrontabili      {len(comuni)}")

    if not comuni:
        print("\n  [ERRORE] Nessun cv_id in comune: i due file non sono\n"
              "           confrontabili. Verifica di aver usato lo stesso\n"
              "           insieme di curriculum.")
        sys.exit(1)

    diff_id, diff_score, con_query = 0, 0, 0
    for cid in comuni:
        a, b = nuovo[cid], rif[cid]
        mancanti = set(b) - set(a)
        aggiunte = set(a) - set(b)
        if mancanti or aggiunte:
            diff_id += 1
            print(f"\n  [DIFFERENZA] {cid}")
            for i in sorted(mancanti):
                print(f"      perso   {i}")
            for i in sorted(aggiunte):
                print(f"      nuovo   {i}")
        for i in set(a) & set(b):
            if a[i] != b[i]:
                diff_score += 1
                print(f"  [PUNTEGGIO] {cid} · {i}: {b[i]} → {a[i]}")

    # La chiave nuova deve esserci davvero: se mancasse, la modifica non è
    # stata caricata e il confronto sopra non proverebbe nulla.
    for e in json.loads(NUOVO.read_text(encoding="utf-8")):
        for m in ((e.get("cv", {}).get("skills") or {}).get("all_matches") or []):
            if m.get("query"):
                con_query += 1

    print(f"\n{SEP}")
    print(f"  documenti con competenze diverse   {diff_id}")
    print(f"  punteggi cambiati                  {diff_score}")
    print(f"  match con la frase di origine      {con_query}")

    if diff_id == 0 and diff_score == 0 and con_query > 0:
        print("\n  ESITO: la modifica è additiva come previsto.\n"
              "         Nessun risultato alterato, frase di origine presente.")
    elif con_query == 0:
        print("\n  [ATTENZIONE] Nessun match porta la frase di origine: la\n"
              "               modifica non è attiva. Il confronto qui sopra\n"
              "               non dimostra nulla.")
    else:
        print("\n  [ATTENZIONE] Qualcosa è cambiato. La modifica doveva essere\n"
              "               additiva: va capito perché prima di procedere.")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
