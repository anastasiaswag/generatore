"""
diagnostica_date.py  —  SkillPath AI
======================================
Mostra che cosa il parser vede quando cerca le date in un curriculum.

PERCHÉ SERVE
────────────
Il calcolo degli anni di esperienza produce un numero solo, e quando quel
numero è sbagliato non dice perché. Le cause possibili sono tre e richiedono
rimedi diversi:

  - la sezione "experience" non è stata riconosciuta, quindi il blocco arriva
    vuoto e nessuna espressione regolare può farci nulla;
  - il blocco c'è ma le date sono scritte in un formato che la regex non copre;
  - la regex aggancia qualcosa che data non è — una data di nascita, un numero
    civico, una frazione — e il risultato è un intervallo spurio.

Il terzo caso è il più insidioso perché produce un numero plausibile. È anche
il più difficile da diagnosticare senza vedere il testo: questo script stampa
le righe della sezione esperienza e, per ciascuna, gli intervalli riconosciuti
con il contributo in mesi.

Uso (dalla radice del progetto):
    python analysis/diagnostica_date.py --cartella "C:/.../CV per test Da Riccardo"
    python analysis/diagnostica_date.py --cartella "..." --solo cv_reale_04
    python analysis/diagnostica_date.py --file "C:/.../un_cv.pdf"
"""

import argparse
import sys
from datetime import datetime
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
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

SEP = "─" * 74
ESTENSIONI = {".pdf", ".docx", ".doc", ".txt"}


def analizza(percorso: Path, etichetta: str, mostra_tutto: bool) -> None:
    from pdf_extractor import get_text
    # Si riusano le funzioni del parser invece di riprodurne la logica: così
    # la diagnostica non può divergere da ciò che il parser fa davvero. La
    # prima versione di questo script duplicava l'estrazione dei gruppi ed è
    # andata in errore appena i nomi dei gruppi sono cambiati.
    from main_parser import (MainParser, _INTERVALLO_RE, _SOLO_DATA_RE,
                             _calculate_years_of_experience,
                             _estremo_da_gruppi, _mese_assoluto)

    # ATTENZIONE ALL'ORDINE, ed è un errore già commesso qui.
    # `filter_lines` scarta come rumore le righe composte SOLO da una data:
    # è corretto, perché quelle righe non devono finire nel matcher semantico.
    # Ma sono anche le uniche che contano per il calcolo degli anni. Il parser
    # lo sa e passa a `_calculate_years_of_experience` il blocco NON filtrato
    # (`blocks["experience"]`); una prima versione di questa diagnostica
    # filtrava prima di segmentare e perdeva proprio quelle righe, riportando
    # zero intervalli dove il parser ne trovava diversi.
    righe = get_text(str(percorso))
    blocchi = MainParser.segment_cv(None, righe)
    esperienza = blocchi.get("experience", [])

    print(f"\n{SEP}\n  {etichetta}\n{SEP}")
    print(f"  righe totali nel documento      {len(righe)}")
    print(f"  righe nella sezione esperienza  {len(esperienza)}")

    if not esperienza:
        print("\n  [CAUSA] La sezione esperienza non è stata riconosciuta.")
        print("          Il blocco arriva vuoto: nessuna correzione alle date")
        print("          può aiutare. Il problema è nella segmentazione.")
        print("\n  Intestazioni presenti nel documento (prime 40 righe brevi):")
        for r in righe[:60]:
            if 3 < len(r.strip()) <= 40:
                print(f"     {r.strip()}")
        return

    trovati = 0
    print(f"\n  Righe della sezione esperienza e intervalli riconosciuti:\n")
    for r in esperienza:
        match = list(_INTERVALLO_RE.finditer(r))
        if not match and not mostra_tutto:
            continue
        testo = r.strip()
        print(f"    │ {testo[:88]}")
        for m in match:
            trovati += 1
            g = m.groupdict()
            ini = _estremo_da_gruppi(g, "_i")
            if g.get("ora"):
                o = datetime.now()
                fin = (o.year, o.month)
            else:
                fin = _estremo_da_gruppi(g, "_f")
            if not ini or not fin:
                print(f"    │     → \"{m.group(0)}\"  (estremi non ricostruibili)")
                continue
            mesi = _mese_assoluto(fin[0], fin[1]) - _mese_assoluto(ini[0], ini[1])
            print(f"    │     → \"{m.group(0)}\"  =  {ini[0]}/{ini[1] or '?'} … "
                  f"{fin[0]}/{fin[1] or '?'}  =  {mesi} mesi")

    # ── Seconda passata: date su righe consecutive (curriculum a due colonne) ─
    coppie = 0
    solo_date = []
    for idx, r in enumerate(esperienza):
        m = _SOLO_DATA_RE.match(r)
        if not m:
            continue
        if m.groupdict().get("ora_s"):
            solo_date.append((idx, "ora", r.strip()))
        else:
            e = _estremo_da_gruppi(m.groupdict(), "_s")
            if e:
                solo_date.append((idx, e, r.strip()))
    usate = set()
    for k in range(len(solo_date) - 1):
        ia, va, ta = solo_date[k]
        ib, vb, tb = solo_date[k + 1]
        if ia in usate or ib != ia + 1 or va == "ora":
            continue
        coppie += 1
        usate.update({ia, ib})
        if coppie == 1:
            print(f"\n  Righe contenenti solo una data, accoppiate a due a due:")
        print(f"    │ \"{ta}\"  +  \"{tb}\"")

    anni = _calculate_years_of_experience(esperienza)
    print(f"\n  intervalli riconosciuti: {trovati}")
    print(f"  stima finale: {anni} anni")

    print(f"  coppie su righe consecutive: {coppie}")

    if trovati == 0 and coppie == 0 and anni > 0:
        print("\n  [ATTENZIONE] Nessun intervallo riconosciuto, eppure la stima")
        print("               non è zero: il numero viene dal RIPIEGO, che prende")
        print("               l'anno più piccolo e il più grande presenti nel")
        print("               blocco e li sottrae. Non corrisponde ad alcun")
        print("               periodo dichiarato ed è quindi inaffidabile,")
        print("               benché abbia l'aspetto di un dato.")
    elif trovati == 0 and coppie == 0:
        print("\n  [CAUSA] Nessun intervallo riconosciuto: le date sono in un")
        print("          formato non coperto, oppure non ci sono date.")
    elif anni < 1 and trovati:
        print("\n  [SOSPETTO] Intervalli riconosciuti ma stima quasi nulla.")
        print("             Controllare sopra se qualcuno di essi è spurio: un")
        print("             intervallo falso impedisce al ripiego sugli anni")
        print("             isolati di intervenire, che è il caso peggiore.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — diagnostica del riconoscimento delle date")
    ap.add_argument("--cartella", help="Cartella di curriculum")
    ap.add_argument("--file", help="Un singolo curriculum")
    ap.add_argument("--solo", help="Analizza solo questo identificativo "
                                   "(es. cv_reale_04)")
    ap.add_argument("--tutte-le-righe", action="store_true",
                    help="Mostra anche le righe senza intervalli")
    args = ap.parse_args()

    if args.file:
        analizza(Path(args.file), Path(args.file).name, args.tutte_le_righe)
        return

    if not args.cartella:
        print("[ERRORE] Indicare --cartella oppure --file")
        sys.exit(1)

    cartella = Path(args.cartella)
    if not cartella.is_dir():
        print(f"[ERRORE] Cartella non trovata: {cartella}")
        sys.exit(1)

    files = sorted(p for p in cartella.iterdir()
                   if p.is_file() and p.suffix.lower() in ESTENSIONI)
    for i, f in enumerate(files, 1):
        etichetta = f"cv_reale_{i:02d}"
        if args.solo and args.solo != etichetta:
            continue
        analizza(f, f"{etichetta}  ({f.name[:50]})", args.tutte_le_righe)

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    main()
