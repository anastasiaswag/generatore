"""
rivedi_corsi.py  —  SkillPath AI
=================================
Prepara un campione di raccomandazioni di corsi da giudicare a mano, e misura
alcune anomalie strutturali dell'indice.

PERCHÉ SERVE
────────────
Il raccomandatore è l'unico componente del sistema il cui output non è mai
stato guardato. La metrica esistente — 43,1% di copertura del gap — verifica
che per una competenza mancante ESISTA almeno un corso nell'indice. Non
verifica che quel corso sia pertinente. Sono due domande diverse, e finora è
stata misurata solo la prima.

La distinzione conta per come l'indice è costruito. Ogni corso porta dei tag;
la similarità viene calcolata fra il TAG e l'etichetta ESCO, e poi tutti i
corsi che portano quel tag vengono attribuiti alla competenza. La catena è
quindi:

    competenza ESCO  ←(similarità)→  tag  ←(appartenenza)→  corso

Solo il primo anello è misurato. Il secondo no: un tag pertinente può portarsi
dietro corsi che con la competenza non c'entrano nulla. Il punteggio
`esco_match_score` salvato in `course_index.json` misura il primo anello e non
dice niente sul secondo, pur avendo l'aspetto di un punteggio di pertinenza
della raccomandazione.

CHE COSA FA QUESTO SCRIPT
─────────────────────────
  1. ANOMALIE AUTOMATICHE
     Corsi attribuiti a molte competenze diverse, e tag che coprono centinaia
     di abbinamenti. Un corso che compare sotto venti competenze diverse è
     sospetto per lo stesso motivo per cui lo era l'etichetta `responsible` in
     792 annunci: la ricorrenza sistematica è un indizio di attribuzione
     spuria, non di rilevanza generale.

  2. CAMPIONE DA GIUDICARE
     Estrae N competenze con seme fisso e ne scrive le raccomandazioni in un
     file markdown, con accanto una casella da compilare. Il giudizio resta a
     chi legge: nessuna misura automatica può dire se un corso su Beethoven sia
     pertinente alla competenza «sviluppare un processo di produzione di opere
     teatrali».

Uso (dalla radice del progetto):
    python analysis/rivedi_corsi.py
    python analysis/rivedi_corsi.py --n 15 --corsi-per-skill 3 --seme 7
"""

import argparse
import json
import random
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
INDICE = BASE_DIR / "config" / "course_index.json"
SKILLS = BASE_DIR / "dataset" / "source" / "skills.json"
SKILLS_IT = BASE_DIR / "dataset" / "source_it" / "skills.json"
OUT = BASE_DIR / "docs" / "revisione_corsi.md"

SEP = "─" * 74


def etichette() -> dict:
    """id ESCO → (etichetta, descrizione). Preferisce l'italiano se presente."""
    fonte = SKILLS_IT if SKILLS_IT.exists() else SKILLS
    lab = {}
    for v in json.loads(fonte.read_text(encoding="utf-8")).values():
        if isinstance(v, dict) and v.get("id"):
            lab[v["id"]] = (v.get("label", ""), (v.get("description") or "")[:400])
    return lab


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — revisione a mano delle raccomandazioni")
    ap.add_argument("--n", type=int, default=10,
                    help="Competenze da campionare (default 10)")
    ap.add_argument("--corsi-per-skill", type=int, default=3,
                    help="Corsi da mostrare per competenza (default 3)")
    ap.add_argument("--seme", type=int, default=42,
                    help="Seme del campionamento, per riproducibilità")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if not INDICE.exists():
        print(f"[ERRORE] Indice non trovato: {INDICE}")
        sys.exit(1)

    ci = json.loads(INDICE.read_text(encoding="utf-8"))
    lab = etichette()

    # ══ 1. Anomalie strutturali ══════════════════════════════════════════════
    print(f"\n{SEP}\n  1. ANOMALIE STRUTTURALI DELL'INDICE\n{SEP}")

    per_corso = Counter()
    per_tag = Counter()
    punteggi = []
    for sid, corsi in ci.items():
        for c in corsi:
            per_corso[c.get("title", "?")] += 1
            per_tag[c.get("matched_via_tag", "?")] += 1
            punteggi.append(c.get("esco_match_score", 0))

    print(f"  competenze con almeno un corso   {len(ci)}")
    print(f"  corsi distinti                   {len(per_corso)}")
    print(f"  abbinamenti totali               {len(punteggi)}")
    print(f"  corsi per competenza, media      {len(punteggi)/len(ci):.1f}")
    print(f"  punteggio tag↔competenza         mediana {st.median(punteggi):.3f}"
          f"   min {min(punteggi):.3f}   max {max(punteggi):.3f}")

    print(f"\n  Corsi attribuiti a più competenze diverse:")
    for t, k in per_corso.most_common(8):
        print(f"     {k:>4} competenze   {t[:60]}")

    print(f"\n  Tag che generano più abbinamenti:")
    for t, k in per_tag.most_common(8):
        print(f"     {k:>5} abbinamenti  «{t}»")

    # La soglia va riferita alla distribuzione, non a un numero tondo. Con una
    # media di circa nove attribuzioni per corso, «almeno dieci» descriverebbe
    # metà dell'indice e non segnalerebbe nulla: sarebbe una statistica
    # dall'aria allarmante e priva di contenuto.
    conteggi = sorted(per_corso.values())
    mediana = st.median(conteggi)
    soglia = max(3 * mediana, mediana + 5)
    molti = [t for t, k in per_corso.items() if k >= soglia]
    print(f"\n  Attribuzioni per corso: mediana {mediana:.0f}, "
          f"massimo {conteggi[-1]}")
    print(f"  Corsi oltre il triplo della mediana (≥{soglia:.0f}): {len(molti)}"
          f"  ({len(molti)/len(per_corso):.1%} dell'indice)")
    if len(molti) / len(per_corso) < 0.02:
        print("  La coda è sottile: nessun corso domina l'indice, e le")
        print("  attribuzioni sono distribuite in modo abbastanza uniforme.")
    else:
        print("  Vanno guardati per primi: la ricorrenza sistematica è indizio")
        print("  di attribuzione spuria, non di rilevanza generale.")

    # Il segnale più informativo non è quanti corsi ricorrono, ma quanto
    # l'indice sia concentrato su pochi tag: un tag che genera centinaia di
    # abbinamenti attribuisce lo stesso insieme di corsi a competenze molto
    # diverse fra loro.
    tot_tag = sum(per_tag.values())
    primi10 = sum(k for _, k in per_tag.most_common(10))
    print(f"\n  Concentrazione sui tag: i 10 tag più usati generano "
          f"{primi10} abbinamenti\n  su {tot_tag}, cioè il "
          f"{primi10/tot_tag:.1%} dell'indice.")

    # ══ 2. Campione da giudicare ═════════════════════════════════════════════
    # Il campionamento resta `random.sample` su popolazione ordinata: è il
    # metodo con cui sono stati generati i campioni già giudicati, e cambiarlo
    # a raccolta iniziata li invaliderebbe. Una versione intermedia di questo
    # script usava una permutazione con prefisso — più garantita in teoria — ma
    # avrebbe prodotto un campione completamente disgiunto dal precedente,
    # buttando via i giudizi espressi. Non si cambia lo strumento di
    # campionamento dopo aver raccolto i dati.
    campione = random.Random(args.seme).sample(sorted(ci.keys()),
                                               min(args.n, len(ci)))

    # Recupero dei giudizi già espressi. Sovrascrivere il file cancellerebbe
    # ore di lettura: le marcature vengono rilette dal file esistente e
    # riapplicate per coppia (competenza, titolo del corso).
    giudizi: dict[tuple[str, str], str] = {}
    precedente = Path(args.out)
    if precedente.exists():
        testo = precedente.read_text(encoding="utf-8")
        titolo_corrente = None
        for riga in testo.splitlines():
            intest = re.match(r"^## \d+\. (.+)$", riga)
            if intest:
                titolo_corrente = intest.group(1).strip()
                continue
            voto = re.match(r"^- \[([SPN])\] \*\*(.+?)\*\*", riga)
            if voto and titolo_corrente:
                giudizi[(titolo_corrente, voto.group(2).strip())] = voto.group(1)
        if giudizi:
            print(f"\n  Recuperati {len(giudizi)} giudizi già espressi da "
                  f"{precedente.name}")
            # Verifica che il campione nuovo contenga davvero quello vecchio.
            # Se il campionamento fosse cambiato, i giudizi finirebbero
            # silenziosamente inutilizzati e il file tornerebbe tutto vuoto.
            etich_campione = {lab.get(sid, ("", ""))[0] for sid in campione}
            etich_giudicate = {k[0] for k in giudizi}
            perse = etich_giudicate - etich_campione
            if perse:
                print(f"  [ATTENZIONE] {len(perse)} competenze già giudicate NON "
                      f"sono nel nuovo campione:")
                for e in sorted(perse)[:5]:
                    print(f"               {e[:64]}")
                print("               Il campionamento è cambiato. Interrompo per "
                      "non sovrascrivere\n               il lavoro già fatto: "
                      "salvare una copia del file prima di procedere.")
                sys.exit(1)
            print(f"  Tutte le competenze già giudicate sono nel nuovo campione.")

    righe = [
        "# Revisione a mano delle raccomandazioni di corsi",
        "",
        f"Campione di {len(campione)} competenze estratte con seme {args.seme} "
        f"da `config/course_index.json`.",
        "",
        "## Come compilare",
        "",
        "Per ogni corso, sostituisci `[ ]` con uno di:",
        "",
        "- `[S]` **pertinente** — il corso insegna davvero quella competenza",
        "- `[P]` **parziale** — attinente all'area ma non alla competenza",
        "- `[N]` **non pertinente** — non c'entra",
        "",
        "Giudica il corso rispetto alla competenza, non rispetto al tag: il tag "
        "può essere corretto e il corso comunque sbagliato, ed è precisamente "
        "l'anello che le metriche esistenti non verificano.",
        "",
        "Alla fine conta: pertinenti su totale, e per ciascuna competenza se "
        "almeno un corso è pertinente. Il secondo numero è quello confrontabile "
        "con il 43,1% di copertura riportato in `docs/risultati_sessione.md`, "
        "che considera coperta una competenza se le è attribuito un corso "
        "qualsiasi.",
        "",
        "---",
        "",
    ]

    for i, sid in enumerate(campione, 1):
        etich, descr = lab.get(sid, ("(etichetta non trovata)", ""))
        righe.append(f"## {i}. {etich}")
        righe.append("")
        if descr:
            righe.append(f"> {descr.strip()}")
            righe.append("")
        for c in ci[sid][: args.corsi_per_skill]:
            titolo = c.get("title", "?")
            marca = giudizi.get((etich, titolo), " ")
            righe.append(
                f"- [{marca}] **{titolo}** — {c.get('provider', '?')}  ")
            righe.append(
                f"      tag «{c.get('matched_via_tag', '?')}» · "
                f"punteggio tag↔competenza {c.get('esco_match_score', 0):.3f} · "
                f"livello {c.get('level', '?')}")
        righe.append("")

    righe += [
        "---",
        "",
        "## Esito",
        "",
        "| indicatore | valore |",
        "|---|---|",
        "| corsi giudicati | |",
        "| pertinenti (S) | |",
        "| parziali (P) | |",
        "| non pertinenti (N) | |",
        "| competenze con almeno un corso pertinente | |",
        "",
        "**Precisione delle raccomandazioni** = pertinenti / corsi giudicati.",
        "",
        "**Copertura effettiva** = competenze con almeno un corso pertinente / "
        "competenze del campione. Da confrontare con il 43,1% di copertura "
        "nominale: la differenza fra i due è ciò che la metrica esistente non "
        "misurava.",
        "",
    ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(righe), encoding="utf-8")

    print(f"\n{SEP}\n  2. CAMPIONE DA GIUDICARE\n{SEP}")
    print(f"  {len(campione)} competenze, "
          f"{args.corsi_per_skill} corsi ciascuna, seme {args.seme}")
    print(f"  → {out}")
    print(f"\n  Aprilo, compila le caselle, e riporta i totali in fondo.")
    print(f"  Venti minuti di lettura, e il raccomandatore smette di essere")
    print(f"  l'unico componente non verificato del sistema.")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
