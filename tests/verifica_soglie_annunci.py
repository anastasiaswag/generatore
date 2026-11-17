"""
verifica_soglie_annunci.py  —  SkillPath AI
============================================
Stabilisce se `job_gt_batch_results.json` — il file da cui nascono la
Tabella 6.6 dell'ablazione e le metriche del parser degli annunci — sia stato
prodotto con le soglie oggi predefinite nel codice.

COME
────
Si riparsano pochi annunci con la configurazione attuale e si confrontano le
competenze estratte con quelle memorizzate per gli stessi annunci. Se
coincidono, il file è coerente col codice. Se differiscono, la tabella
pubblicata descrive una configurazione diversa da quella consegnata, e va
deciso cosa fare: rigenerare le misure, oppure dichiarare in tesi con quali
soglie sono state ottenute.

Nessuna delle due è grave di per sé. Grave sarebbe non saperlo.

Uso (dalla radice del progetto):
    python tests/batch_parse_jobs_gt.py --max 10 --out outputs/prova_soglie.json
    python tests/verifica_soglie_annunci.py
"""

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BASE = Path(__file__).resolve().parent.parent
NUOVO = BASE / "outputs" / "prova_soglie.json"
RIFERIMENTO = BASE / "outputs" / "job_gt_batch_results.json"
SEP = "─" * 72


def indicizza(path: Path) -> dict:
    if not path.exists():
        print(f"[ERRORE] File non trovato: {path}\n"
              f"         Generalo con: python tests/batch_parse_jobs_gt.py "
              f"--max 10 --out outputs/prova_soglie.json")
        sys.exit(1)
    fuori = {}
    for e in json.loads(path.read_text(encoding="utf-8")):
        if not isinstance(e, dict):
            continue
        sk = e.get("skills") or {}
        fuori[e.get("job_id")] = {
            "skills": {m["id"]: m.get("score") for m in (sk.get("all_matches") or [])},
            "etichette": {m["id"]: m.get("label", "") for m in (sk.get("all_matches") or [])},
            "occ": (e.get("occupation") or {}).get("id"),
        }
    return fuori


def main() -> None:
    nuovo = indicizza(NUOVO)
    rif = indicizza(RIFERIMENTO)
    comuni = sorted(set(nuovo) & set(rif))

    print(f"\n{SEP}\n  LE SOGLIE DEL FILE DI RIFERIMENTO SONO QUELLE ATTUALI?\n{SEP}")
    print(f"  annunci riparsati            {len(nuovo)}")
    print(f"  annunci confrontabili        {len(comuni)}")

    if not comuni:
        print("\n  [ERRORE] Nessun job_id in comune fra i due file.")
        sys.exit(1)

    diversi, occ_diverse = 0, 0
    tot_nuove, tot_perse = 0, 0
    for jid in comuni:
        a, b = nuovo[jid], rif[jid]
        aggiunte = set(a["skills"]) - set(b["skills"])
        mancanti = set(b["skills"]) - set(a["skills"])
        if aggiunte or mancanti:
            diversi += 1
            tot_nuove += len(aggiunte)
            tot_perse += len(mancanti)
            print(f"\n  [DIFFERENZA] {jid}")
            for i in sorted(aggiunte):
                print(f"      in più   {a['etichette'].get(i, i)}")
            for i in sorted(mancanti):
                print(f"      in meno  {b['etichette'].get(i, i)}")
        if a["occ"] != b["occ"]:
            occ_diverse += 1

    print(f"\n{SEP}")
    print(f"  annunci con competenze diverse    {diversi}/{len(comuni)}")
    print(f"  competenze in più con il codice attuale   {tot_nuove}")
    print(f"  competenze in meno                        {tot_perse}")
    print(f"  occupazioni riconosciute diversamente     {occ_diverse}")

    if diversi == 0 and occ_diverse == 0:
        print("\n  ESITO: il file di riferimento è coerente con il codice\n"
              "         attuale. La Tabella 6.6 descrive ciò che consegni.")
    else:
        print("\n  ESITO: il file di riferimento è stato prodotto con una\n"
              "         configurazione diversa da quella attuale.\n")
        print("  Due strade, entrambe legittime:\n")
        print("    1) Rigenerare le misure con le soglie attuali. Corretto,\n"
              "       ma comporta rifare l'ablazione e ogni tabella a valle.\n")
        print("    2) Lasciare i numeri e dichiarare in tesi con quali soglie\n"
              "       sono stati ottenuti, indicandole esplicitamente. Costa\n"
              "       due righe e non invalida nulla: le misure restano vere\n"
              "       per la configurazione con cui sono state prese.\n")
        print("  A tesi scritta, la seconda è quasi sempre la scelta giusta.")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
