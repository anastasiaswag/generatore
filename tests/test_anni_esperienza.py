"""
test_anni_esperienza.py  —  SkillPath AI
=========================================
Collaudo del calcolo degli anni di esperienza su formati di data reali.

PERCHÉ SERVE UN TEST SCRITTO A MANO
───────────────────────────────────
Gli 810 CV sintetici non possono validare questa funzione. Il motivo è nel
generatore: `render_cvs.py` costruisce il periodo lavorativo con una sola
formattazione,

    period = f"{start_year} – 2024" if years else "2024"

quindi tutti e 810 i documenti usano lo stesso formato, prodotto dallo stesso
script che fornisce la ground truth. L'87,2% di stime esatte misurato su quel
dataset descrive la capacità di sottrarre due numeri in un formato noto, non la
capacità di leggere le date di un curriculum.

La prova su 15 curriculum reali lo ha confermato: 7 restituivano zero e uno
riportava 48 anni di esperienza.

Questo file elenca i formati che compaiono davvero nei curriculum italiani e
inglesi, con il risultato atteso. È l'unico modo di verificare la correzione
senza annotare a mano un campione di documenti veri — cosa che resta comunque
consigliabile, e che questo test non sostituisce.

Uso (dalla radice del progetto):
    python tests/test_anni_esperienza.py
"""

import sys
import types
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Il modulo importa sentence-transformers e PyMuPDF a livello globale, ma la
# funzione in prova non ne ha bisogno: si sostituiscono con segnaposto, così il
# test gira in un secondo invece che caricare un modello da 1 GB.
_sm = types.ModuleType("semantic_mapper")
_sm.SemanticMapper = type("SemanticMapper", (), {"__init__": lambda s, *a, **k: None})
sys.modules.setdefault("semantic_mapper", _sm)
_pe = types.ModuleType("pdf_extractor")
_pe.get_text = lambda *a, **k: []
_pe.filter_lines = lambda x: x
_pe.is_noise_line = lambda x: False
sys.modules.setdefault("pdf_extractor", _pe)

sys.path.insert(0, str(BASE_DIR / "src"))
from main_parser import _calculate_years_of_experience as anni  # noqa: E402

# Su Windows la console usa UTF-8, ma quando l'output viene rediretto o passato
# in pipe Python ricade sulla codifica di sistema (cp1252), che non contiene i
# caratteri di riquadro usati qui: lo script muore con UnicodeEncodeError prima
# ancora di fare il suo lavoro. Si forza UTF-8 sull'uscita.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


ANNO = datetime.now().year
SEP = "─" * 74

# (descrizione, righe del blocco experience, anni attesi)
CASI = [
    # ── Il formato del dataset sintetico, da non far regredire ──────────────
    ("sintetico: anno – anno con trattino medio",
     ["2019 – 2024"], 5.0),
    ("sintetico: anno singolo",
     ["2024"], 0.0),

    # ── Difetto 2: separatori mai riconosciuti ──────────────────────────────
    ("trattino lungo (em-dash), quello di Word",
     ["2019 — 2024"], 5.0),
    ("trattino breve senza spazi",
     ["2019-2024"], 5.0),
    ("forma discorsiva italiana",
     ["dal 2019 al 2024"], 5.0),
    ("forma discorsiva inglese",
     ["2019 to 2024"], 5.0),

    # ── Difetto 1: i mesi venivano scartati ─────────────────────────────────
    ("mesi italiani per esteso, dentro lo stesso anno",
     ["Gennaio 2020 – Novembre 2020"], 0.8),
    ("mesi italiani abbreviati",
     ["gen. 2020 – mar. 2023"], 3.2),
    ("mesi inglesi",
     ["June 2019 – December 2021"], 2.5),
    ("mese numerico e anno",
     ["01/2020 – 07/2023"], 3.5),
    ("anno a due cifre",
     ["01/20 – 07/23"], 3.5),

    # ── Difetto 3: formule di attualità ─────────────────────────────────────
    ("present", [f"2020 – present"], round((ANNO * 12 + datetime.now().month - 1
                                           - 2020 * 12) / 12, 1)),
    ("presente", [f"2020 – presente"], round((ANNO * 12 + datetime.now().month - 1
                                             - 2020 * 12) / 12, 1)),
    ("tuttora", [f"2020 – tuttora"], round((ANNO * 12 + datetime.now().month - 1
                                           - 2020 * 12) / 12, 1)),
    ("ad oggi", [f"2020 – ad oggi"], round((ANNO * 12 + datetime.now().month - 1
                                           - 2020 * 12) / 12, 1)),

    # ── Difetto 4: intervalli sovrapposti ───────────────────────────────────
    # Questi casi codificano una scelta, non solo una correzione. Il generatore
    # del dataset sintetico somma le durate dei ruoli anche quando li rende con
    # periodi sovrapposti: "2022 – 2024" più "2021 – 2024" vale 5 anni per la
    # ground truth e 3 per chiunque legga il documento. Qui si adotta la
    # seconda lettura. Vedi la docstring di _calculate_years_of_experience.
    ("due ruoli consecutivi: si sommano",
     ["2010 – 2015", "2015 – 2020"], 10.0),
    ("due ruoli sovrapposti: contano una volta",
     ["2010 – 2020", "2012 – 2018"], 10.0),
    ("il caso del dataset sintetico: due ruoli che finiscono lo stesso anno",
     ["2022 – 2024", "2021 – 2024"], 3.0),
    ("sovrapposizione parziale",
     ["2010 – 2016", "2014 – 2020"], 10.0),
    ("tre ruoli, due dei quali paralleli",
     ["2010 – 2014", "2012 – 2016", "2018 – 2020"], 8.0),

    # ── Curriculum a due colonne: date su righe separate ────────────────────
    # Formato osservato su un curriculum reale: la colonna laterale contiene
    # solo le date, che l'estrazione del PDF restituisce come righe isolate.
    ("date su righe consecutive, formato Mmm 'AA",
     ["Sep '22", "Sep '23", "Torino, IT"], 1.0),
    ("tre esperienze in colonna laterale",
     ["Sep '22", "Sep '23", "Torino, IT",
      "Mar '22", "Sep '22", "Torino, IT",
      "Mar '21", "Jun '21", "Cesena, IT"], 1.8),
    ("date in colonna con fine in corso",
     ["Mar '21", "present", "Milano, IT"],
     round((datetime.now().year * 12 + datetime.now().month - 1
            - (2021 * 12 + 2)) / 12, 1)),
    ("righe con date ma anche testo: non vanno accoppiate",
     ["Sviluppatore Sep '22", "Analista Sep '23"], 0.0),

    # ── Formato con apostrofo sulla stessa riga ─────────────────────────────
    ("Mmm 'AA – Mmm 'AA sulla stessa riga",
     ["Mar '19 – Set '22"], 3.5),

    # ── Casi che devono restare a zero ──────────────────────────────────────
    ("blocco vuoto", [], 0.0),
    ("nessuna data", ["Responsabile di produzione presso Acme S.p.A."], 0.0),

    # ── Casi realistici completi ────────────────────────────────────────────
    ("riga completa all'italiana",
     ["Ingegnere di processo — Acme S.p.A. — Gennaio 2018 – Dicembre 2022"], 5.0),
    ("riga completa all'inglese",
     ["Senior Developer, Acme Ltd — Mar 2015 to Sep 2019"], 4.5),
]


def main() -> None:
    print(f"\n{SEP}\n  CALCOLO DEGLI ANNI DI ESPERIENZA — collaudo\n{SEP}")
    passati = falliti = 0
    errori = []

    for descrizione, righe, atteso in CASI:
        ottenuto = anni(righe)
        # tolleranza di un mese: le formule "fino a oggi" dipendono dalla data
        # di esecuzione del test
        ok = abs(ottenuto - atteso) <= 0.1
        if ok:
            passati += 1
            esito = "  ok  "
        else:
            falliti += 1
            esito = " FALLITO"
            errori.append((descrizione, righe, atteso, ottenuto))
        print(f"  {esito}  {descrizione:<46}atteso {atteso:>5}  "
              f"ottenuto {ottenuto:>5}")

    print(f"\n{SEP}")
    print(f"  {passati} superati, {falliti} falliti su {len(CASI)}")
    if errori:
        print(f"\n  Dettaglio dei falliti:")
        for d, r, a, o in errori:
            print(f"    {d}")
            print(f"      righe:    {r}")
            print(f"      atteso {a}, ottenuto {o}")
    print(SEP + "\n")
    sys.exit(1 if falliti else 0)


if __name__ == "__main__":
    main()
