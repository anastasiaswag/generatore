"""
build_skill_relations.py  —  SkillPath AI
==========================================
Converte i due file CSV ufficiali delle relazioni fra competenze ESCO nel
formato JSON usato dal progetto.

PERCHÉ QUESTO FILE ESISTE
─────────────────────────
Il dataset scaricato all'inizio del progetto conteneva tre soli file:
occupazioni, competenze e relazione occupazione→competenze. Mancavano le
relazioni *fra* competenze, e `skill_graph.py` le ha quindi ricostruite per
co-occorrenza. Questo script chiude quella lacuna usando i dati ufficiali.

CHE COSA CONTENGONO DAVVERO I DUE FILE
──────────────────────────────────────
Vale la pena dirlo perché il nome inganna, ed è il contrario di quanto ci si
aspetta leggendo i titoli:

  skillSkillRelations.csv      5.818 coppie su 5.650 competenze (41% del
                               totale). Non sono somiglianze ma DIPENDENZE:
                               `essential` (189) e `optional` (5.629), cioè
                               "per questa competenza serve quella conoscenza".
                               Troppo rado per ordinare un divario qualsiasi.

  broaderRelationsSkillPillar  20.183 righe di gerarchia, che coprono TUTTE
                               le 13.939 competenze. Ogni competenza punta ai
                               suoi concetti più generali.

Il file utile è quindi il secondo, non quello dal nome più promettente. Dalla
gerarchia si ricava una distanza tassonomica definita per ogni coppia di
competenze, ed è quella che sostituisce la co-occorrenza ricostruita.

LA GERARCHIA È UN GRAFO ACICLICO, NON UN ALBERO
───────────────────────────────────────────────
Una competenza può avere più concetti più generali: la media è 1,45 e il
massimo osservato è 9. Nessun algoritmo che presupponga un padre unico è
corretto qui, e questa è la ragione per cui la profondità viene calcolata con
una visita in ampiezza dalle radici invece che risalendo i genitori.

Convivono inoltre due spazi di nomi: le competenze e i gruppi di competenze
usano URI `/esco/skill/<uuid>`, mentre i settori di conoscenza usano
`/esco/isced-f/<codice>`. Le chiavi ISCED-F vengono prefissate per evitare
collisioni con gli UUID.

USO (dalla radice del progetto):
    python src/build_skill_relations.py
    python src/build_skill_relations.py --verifica-versione
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict, deque
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
SRC_DATA = BASE_DIR / "dataset" / "source"

CSV_GERARCHIA = SRC_DATA / "broaderRelationsSkillPillar_en.csv"
CSV_DIPENDENZE = SRC_DATA / "skillSkillRelations_en.csv"
SKILLS_JSON = SRC_DATA / "skills.json"
OUT_JSON = SRC_DATA / "skill_relations.json"

SEP = "─" * 74

_UUID_RE = re.compile(
    r"/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*$"
)
_ISCED_RE = re.compile(r"/esco/isced-f/([^/\s]+)\s*$")


def chiave(uri: str) -> str | None:
    """
    Riduce un URI ESCO a una chiave stabile.

    Le competenze e i gruppi restituiscono il proprio UUID; i settori di
    conoscenza ISCED-F restituiscono `isced-f/<codice>`. Il prefisso serve a
    non confondere i due spazi di nomi in un unico dizionario.
    """
    uri = (uri or "").strip()
    if not uri:
        return None
    m = _UUID_RE.search(uri)
    if m:
        return m.group(1).lower()
    m = _ISCED_RE.search(uri)
    if m:
        return f"isced-f/{m.group(1)}"
    return None


def carica_gerarchia(path: Path) -> tuple[dict, dict, dict]:
    """
    Legge broaderRelationsSkillPillar e restituisce (genitori, etichette, tipi).

    `genitori` mappa ogni concetto sulla lista dei suoi concetti più generali.
    Le righe con URI non riconoscibile vengono contate e segnalate invece di
    essere ignorate in silenzio: se il formato del file cambiasse, un conteggio
    a zero è l'unica prova che la conversione è ancora corretta.
    """
    genitori: dict[str, list[str]] = defaultdict(list)
    etichette: dict[str, str] = {}
    tipi: dict[str, str] = {}
    scartate = 0

    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = chiave(r.get("conceptUri", ""))
            p = chiave(r.get("broaderUri", ""))
            if not k or not p:
                scartate += 1
                continue
            if p not in genitori[k]:
                genitori[k].append(p)
            etichette.setdefault(k, (r.get("conceptLabel") or "").strip())
            etichette.setdefault(p, (r.get("broaderLabel") or "").strip())
            tipi.setdefault(k, (r.get("conceptType") or "").strip())
            tipi.setdefault(p, (r.get("broaderType") or "").strip())
            # I genitori compaiono anche come concetti in altre righe: il
            # setdefault evita che un tipo dedotto sovrascriva quello esplicito.

    if scartate:
        print(f"  [ATTENZIONE] {scartate} righe con URI non riconoscibile.")
    return dict(genitori), etichette, tipi


def carica_dipendenze(path: Path) -> dict:
    """
    Legge skillSkillRelations e restituisce le dipendenze per competenza.

    La relazione è orientata: `essential`/`optional` dicono di quali altre
    competenze quella di partenza ha bisogno. Non è simmetrica e non va
    confusa con una somiglianza.
    """
    dip: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"essential": [], "optional": []})
    scartate = 0

    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = chiave(r.get("originalSkillUri", ""))
            b = chiave(r.get("relatedSkillUri", ""))
            tipo = (r.get("relationType") or "").strip()
            if not a or not b or tipo not in ("essential", "optional"):
                scartate += 1
                continue
            if b not in dip[a][tipo]:
                dip[a][tipo].append(b)

    if scartate:
        print(f"  [ATTENZIONE] {scartate} righe di dipendenza scartate.")
    return {k: v for k, v in dip.items()}


def calcola_profondita(genitori: dict) -> dict:
    """
    Profondità di ogni concetto come cammino PIÙ LUNGO da una radice.

    La scelta del cammino più lungo invece di quello più corto non è un
    dettaglio: è necessaria alla correttezza della misura di similarità.

    In ESCO un concetto può essere più generale di un altro senza stargli
    sopra di un livello. «Programmazione informatica» e «Python» pendono
    entrambi dal gruppo «sviluppo e analisi di software e applicazioni», e al
    tempo stesso la prima è dichiarata più generale del secondo. Contando i
    passi minimi risulterebbero alla stessa profondità, e una formula che
    divide per la somma delle profondità restituirebbe 1,0 — cioè identità —
    per due competenze che identiche non sono.

    Il cammino più lungo garantisce invece che un concetto sia sempre più
    profondo di ciascuno dei suoi antenati, che è la proprietà su cui la
    similarità di Wu-Palmer si regge.

    Il calcolo procede in ordine topologico (algoritmo di Kahn): un concetto
    riceve la propria profondità solo quando tutti i suoi genitori l'hanno
    ricevuta.
    """
    figli: dict[str, list[str]] = defaultdict(list)
    tutti = set(genitori)
    for k, ps in genitori.items():
        for p in ps:
            figli[p].append(k)
            tutti.add(p)

    da_fare = {n: len(genitori.get(n, ())) for n in tutti}
    prof = {n: 0 for n in tutti if da_fare[n] == 0}
    coda = deque(prof)
    visitati = 0
    while coda:
        n = coda.popleft()
        visitati += 1
        for c in figli.get(n, []):
            prof[c] = max(prof.get(c, 0), prof[n] + 1)
            da_fare[c] -= 1
            if da_fare[c] == 0:
                coda.append(c)

    if visitati != len(tutti):
        # Accade solo se il grafo contiene un ciclo, che ESCO non dovrebbe
        # avere: va segnalato invece che aggirato in silenzio.
        mancanti = tutti - set(prof)
        print(f"  [ATTENZIONE] {len(tutti) - visitati} concetti non ordinabili "
              f"topologicamente (ciclo nei dati).")
        for n in mancanti:
            prof[n] = 1
    return prof


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — conversione delle relazioni ESCO ufficiali")
    ap.add_argument("--gerarchia", default=str(CSV_GERARCHIA))
    ap.add_argument("--dipendenze", default=str(CSV_DIPENDENZE))
    ap.add_argument("--out", default=str(OUT_JSON))
    ap.add_argument("--versione", default="v1.2.1",
                    help="Versione ESCO da annotare nel file prodotto")
    args = ap.parse_args()

    print(f"\n{SEP}\n  CONVERSIONE DELLE RELAZIONI ESCO UFFICIALI\n{SEP}")

    for p in (Path(args.gerarchia), Path(args.dipendenze), SKILLS_JSON):
        if not p.exists():
            print(f"[ERRORE] File non trovato: {p}")
            sys.exit(1)

    skills = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
    noti = set(skills)
    print(f"  competenze nel dataset locale : {len(noti)}")

    genitori, etichette, tipi = carica_gerarchia(Path(args.gerarchia))
    dipendenze = carica_dipendenze(Path(args.dipendenze))
    profondita = calcola_profondita(genitori)

    # ── Verifica di coerenza fra i CSV ufficiali e il dataset locale ──────────
    # Se le due versioni di ESCO non coincidessero, qui comparirebbero
    # identificativi orfani: è il controllo che rende la conversione sicura.
    concetti_ksc = {k for k, t in tipi.items()
                    if t == "KnowledgeSkillCompetence"}
    coperte = noti & concetti_ksc
    mancanti = noti - concetti_ksc
    estranei = {k for k in dipendenze} - noti

    print(f"  competenze con gerarchia      : {len(coperte)} "
          f"({len(coperte)/len(noti)*100:.1f}%)")
    print(f"  competenze senza gerarchia    : {len(mancanti)}")
    print(f"  id nelle dipendenze ma non nel dataset : {len(estranei)}")

    if mancanti or estranei:
        print("\n  [ATTENZIONE] Le due fonti non coincidono del tutto: i CSV\n"
              "               potrebbero essere di una versione ESCO diversa\n"
              "               da quella del dataset locale. Verificare prima\n"
              "               di usare il file prodotto.")
    else:
        print(f"\n  Corrispondenza completa: il dataset locale e i CSV sono\n"
              f"  della stessa versione ESCO ({args.versione}).")

    out = {
        "versione_esco": args.versione,
        "generato_da": [Path(args.gerarchia).name, Path(args.dipendenze).name],
        "n_concetti": len(profondita),
        "n_competenze_coperte": len(coperte),
        "genitori": genitori,
        "profondita": profondita,
        "tipi": tipi,
        "etichette": etichette,
        "dipendenze": dipendenze,
    }
    p_out = Path(args.out)
    p_out.parent.mkdir(parents=True, exist_ok=True)
    p_out.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    print(f"\n{SEP}")
    print(f"  concetti totali (competenze + gruppi + ISCED-F): {len(profondita)}")
    print(f"  profondità massima: {max(profondita.values())}")
    print(f"  → {p_out}  ({p_out.stat().st_size/1e6:.1f} MB)")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
