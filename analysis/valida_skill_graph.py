"""
valida_skill_graph.py  —  SkillPath AI
=======================================
Confronta il grafo di prossimità RICOSTRUITO da `skill_graph.py` con la
gerarchia UFFICIALE di ESCO, e misura quanto cambierebbe l'ordinamento del
divario formativo se si usasse la seconda al posto del primo.

PERCHÉ SERVE
────────────
`skill_graph.py` ordina le competenze mancanti con un punteggio composito —
40% frequenza, 40% trasversalità, 20% co-occorrenza — i cui pesi sono stati
scelti e mai verificati. È l'unico componente della pipeline senza una
misura. La componente di co-occorrenza, in particolare, esisteva perché il
dataset scaricato non conteneva le relazioni fra competenze: si stimava la
vicinanza concettuale contando quante volte due competenze comparivano nella
stessa occupazione.

Ora quelle relazioni ci sono. Questo script non «corregge» la ricostruzione:
la mette a confronto con il riferimento e quantifica lo scarto. È una
domanda a cui si può rispondere con un numero, e finora non era stata posta.

LE DUE MISURE
─────────────
  A. ACCORDO — le coppie che la ricostruzione giudica vicine sono davvero
     vicine nella tassonomia? Confrontato con coppie casuali, che danno la
     linea di base: senza quel confronto qualunque valore sembrerebbe alto.

  B. EFFETTO — quanto cambia l'ordine finale del divario? È la domanda che
     conta davvero, perché la co-occorrenza pesa solo il 20% e un disaccordo
     grande sulla componente può tradursi in un effetto piccolo sul
     risultato. Le due cose vanno misurate separatamente.

Uso (dalla radice del progetto):
    python analysis/valida_skill_graph.py
    python analysis/valida_skill_graph.py --coppie 20000 --seed 7
"""

import argparse
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
DATA = BASE_DIR / "dataset" / "source"
OUT = BASE_DIR / "outputs" / "valida_skill_graph.json"

SEP = "─" * 74


# ── Statistica minima, senza dipendenze esterne ───────────────────────────────

def ranghi(v: list[float]) -> list[float]:
    """Ranghi con media sui pari merito (necessaria: i valori sono discreti)."""
    ordinati = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(ordinati):
        j = i
        while j + 1 < len(ordinati) and v[ordinati[j + 1]] == v[ordinati[i]]:
            j += 1
        medio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[ordinati[k]] = medio
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> float:
    """Correlazione di rango. Zero se una delle due serie è costante."""
    if len(x) < 3:
        return 0.0
    rx, ry = ranghi(x), ranghi(y)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    return num / (dx * dy) ** 0.5 if dx and dy else 0.0


def kendall_tau(a: list, b: list) -> float:
    """
    Tau-b fra due ordinamenti degli stessi elementi, dati come liste di id.
    Vale 1 se identici, -1 se invertiti. Su liste di 2-5 elementi — la
    lunghezza tipica di un divario — è più leggibile di una correlazione.
    """
    pos_a = {v: i for i, v in enumerate(a)}
    pos_b = {v: i for i, v in enumerate(b)}
    comuni = [v for v in a if v in pos_b]
    n = len(comuni)
    if n < 2:
        return 1.0
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            u, v = comuni[i], comuni[j]
            sa = pos_a[u] - pos_a[v]
            sb = pos_b[u] - pos_b[v]
            if sa * sb > 0:
                conc += 1
            elif sa * sb < 0:
                disc += 1
    tot = conc + disc
    return (conc - disc) / tot if tot else 1.0


# ── Programma ─────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — validazione del grafo delle competenze")
    ap.add_argument("--coppie", type=int, default=10000,
                    help="Coppie campionate per ciascun gruppo (default 10000)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    sys.path.insert(0, str(SRC_DIR))
    from skill_graph import SkillGraph
    from esco_taxonomy import TaxonomiaESCO

    print(f"\n{SEP}\n  VALIDAZIONE DEL GRAFO DELLE COMPETENZE\n{SEP}")

    tax = TaxonomiaESCO()
    if not tax.carica():
        print("[ERRORE] dataset/source/skill_relations.json non trovato.\n"
              "         Eseguire prima: python src/build_skill_relations.py")
        sys.exit(1)
    print(f"  gerarchia ufficiale ESCO {tax.versione} caricata")

    sg = SkillGraph()
    sg.build(DATA / "occupation_skill_relations.json", DATA / "skills.json")

    rng = random.Random(args.seed)

    # ══ A. Accordo fra ricostruzione e gerarchia ufficiale ═══════════════════
    print(f"\n{SEP}\n  A. LE COPPIE GIUDICATE VICINE LO SONO DAVVERO?\n{SEP}")

    coppie = list(sg._cooccur.items())
    coppie.sort(key=lambda kv: kv[1], reverse=True)
    n = min(args.coppie, len(coppie))
    alte = coppie[:n]

    # Linea di base: coppie casuali fra le stesse competenze. Senza questa
    # nessun valore è interpretabile — la tassonomia potrebbe dire "vicine"
    # a tutti indistintamente.
    universo = list(sg._freq)
    casuali = []
    while len(casuali) < n:
        a, b = rng.choice(universo), rng.choice(universo)
        if a != b:
            casuali.append((a, b))

    def profilo(pairs) -> dict:
        sim = [tax.similarita(a, b) for (a, b) in pairs]
        return {
            "n": len(sim),
            "media": st.mean(sim),
            "quota_sopra_0": sum(1 for s in sim if s > 0) / len(sim),
            "quota_sopra_050": sum(1 for s in sim if s >= 0.5) / len(sim),
        }

    p_alte = profilo([k for k, _ in alte])
    p_rand = profilo(casuali)

    print(f"  {'':<34}{'co-occorrenti':>16}{'casuali':>14}")
    print(f"  {'-'*64}")
    print(f"  {'coppie esaminate':<34}{p_alte['n']:>16}{p_rand['n']:>14}")
    print(f"  {'similarità tassonomica media':<34}"
          f"{p_alte['media']:>16.3f}{p_rand['media']:>14.3f}")
    print(f"  {'quota con antenato comune (>0)':<34}"
          f"{p_alte['quota_sopra_0']*100:>15.1f}%{p_rand['quota_sopra_0']*100:>13.1f}%")
    print(f"  {'quota concettualmente vicine (≥0,5)':<34}"
          f"{p_alte['quota_sopra_050']*100:>15.1f}%{p_rand['quota_sopra_050']*100:>13.1f}%")

    rho = spearman([c for _, c in alte],
                   [tax.similarita(a, b) for (a, b), _ in alte])
    print(f"\n  correlazione di rango fra numero di co-occorrenze e\n"
          f"  similarità tassonomica, sulle coppie co-occorrenti: ρ = {rho:.3f}")

    guadagno = (p_alte["media"] / p_rand["media"]) if p_rand["media"] else float("inf")
    print(f"\n  La ricostruzione seleziona coppie {guadagno:.1f} volte più vicine\n"
          f"  del caso. È il numero che dice se la co-occorrenza fosse un\n"
          f"  surrogato ragionevole della vicinanza concettuale.")

    # ══ B. Effetto sull'ordinamento del divario ══════════════════════════════
    print(f"\n{SEP}\n  B. QUANTO CAMBIA L'ORDINE DEL DIVARIO?\n{SEP}")

    casi = carica_casi(BASE_DIR)
    if not casi:
        print("  Nessun caso con divario di almeno due competenze trovato\n"
              "  in outputs/. Salto la seconda misura.")
        risultati_b = None
    else:
        # ── Quanto pesa davvero ciascuna componente ───────────────────────────
        # Prima di confrontare gli ordinamenti conviene guardare i contributi:
        # un peso nominale del 20% non garantisce un effetto del 20%, perché
        # dipende dalla scala su cui la componente si distribuisce.
        contributi = {"freq": [], "reuse": [], "co": [], "tax": []}
        for gap_ids, known_ids in casi:
            for s in gap_ids:
                contributi["freq"].append(
                    0.40 * sg._freq.get(s, 0) / max(sg._max_freq, 1))
                contributi["reuse"].append(0.40 * sg.reuse_score(s))
                contributi["co"].append(
                    0.20 * sg.co_occurrence_score(s, known_ids))
                contributi["tax"].append(
                    0.20 * tax.vicinanza_a_insieme(s, known_ids))

        print("  contributo medio al punteggio finale:")
        for nome, etichetta in (("freq", "frequenza (peso 0,40)"),
                                ("reuse", "trasversalità (peso 0,40)"),
                                ("co", "co-occorrenza (peso 0,20)"),
                                ("tax", "tassonomia (peso 0,20)")):
            v = contributi[nome]
            print(f"    {etichetta:<28} {st.mean(v):.6f}   "
                  f"(max {max(v):.4f}, varia su {len(set(round(x,6) for x in v))} valori)")
        print()

        taus, cambi_primo, esaminati = [], 0, 0
        for gap_ids, known_ids in casi:
            vecchio = [d["id"] for d in sg.rank_gap(gap_ids, known_ids)]
            nuovo = ordina_con_tassonomia(sg, tax, gap_ids, known_ids)
            taus.append(kendall_tau(vecchio, nuovo))
            if vecchio[0] != nuovo[0]:
                cambi_primo += 1
            esaminati += 1

        risultati_b = {
            "casi": esaminati,
            "tau_medio": st.mean(taus),
            "quota_ordine_identico": sum(1 for t in taus if t == 1.0) / esaminati,
            "quota_primo_cambiato": cambi_primo / esaminati,
        }
        print(f"  casi esaminati                     {esaminati}")
        print(f"  tau di Kendall medio               {risultati_b['tau_medio']:.3f}")
        print(f"  ordinamento identico               "
              f"{risultati_b['quota_ordine_identico']*100:.1f}%")
        print(f"  prima competenza cambiata          "
              f"{risultati_b['quota_primo_cambiato']*100:.1f}%")
        print(f"\n  La componente sostituita pesa il 20% del punteggio: un\n"
              f"  disaccordo grande sulla componente può dare un effetto\n"
              f"  piccolo sul risultato, e questo è il numero da riportare.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "versione_esco": tax.versione,
        "seed": args.seed,
        "accordo": {"co_occorrenti": p_alte, "casuali": p_rand,
                    "spearman": rho, "rapporto_medie": guadagno},
        "effetto_ordinamento": risultati_b,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {out}\n{SEP}\n")


def ordina_con_tassonomia(sg, tax, gap_ids: list, known_ids: list) -> list:
    """
    Stesso punteggio di `skill_graph.priority_score`, con la co-occorrenza
    sostituita dalla vicinanza tassonomica. I pesi restano quelli originali:
    cambiare anche quelli renderebbe impossibile attribuire la differenza.
    """
    punteggi = []
    for sid in gap_ids:
        freq = sg._freq.get(sid, 0) / max(sg._max_freq, 1)
        reuse = sg.reuse_score(sid)
        vicino = tax.vicinanza_a_insieme(sid, known_ids)
        punteggi.append((0.40 * freq + 0.40 * reuse + 0.20 * vicino, sid))
    punteggi.sort(key=lambda x: x[0], reverse=True)
    return [sid for _, sid in punteggi]


def carica_casi(base: Path, minimo: int = 3) -> list:
    """
    Costruisce casi reali (divario, competenze possedute) dai dati del progetto.

    Per ogni curriculum sintetico già elaborato si prendono le competenze
    ESTRATTE dal parser come «possedute», e le competenze `essential` della
    sua occupazione di riferimento come «richieste»: il divario è la
    differenza. È esattamente lo scenario in cui `rank_gap` viene invocato
    dalla roadmap, e usa dati reali del progetto senza inventare nulla.

    PERCHÉ NON SI USANO GLI OUTPUT DEL MATCHING
    ───────────────────────────────────────────
    La scelta ovvia sarebbe stata `job_to_candidates_results.json`, che i
    divari li contiene già. È stata scartata dopo averla provata: quel file
    è il confronto di UN SOLO annuncio contro 810 candidati, quindi i 755
    divari che se ne ricavano pescano tutti dalle stesse sei competenze
    richieste — 5 competenze distinte in totale. Su un campione così ogni
    confronto fra ordinamenti dà accordo perfetto per costruzione, e il
    risultato sembrerebbe dire che cambiare la componente non ha effetto
    mentre direbbe soltanto che il campione è degenere.

    La costruzione qui adottata dà invece 787 casi su 1.346 competenze
    distinte, con divari lunghi in media 9 competenze e tutti e tre i livelli
    di trasversalità rappresentati.
    """
    rel_f = base / "dataset" / "source" / "occupation_skill_relations.json"
    cv_f = base / "outputs" / "cv_batch_results.json"
    if not rel_f.exists() or not cv_f.exists():
        return []

    relazioni = json.loads(rel_f.read_text(encoding="utf-8"))
    casi = []
    for e in json.loads(cv_f.read_text(encoding="utf-8")):
        occ = (e.get("ground_truth") or {}).get("target_occupation_id")
        richieste = (relazioni.get(occ) or {}).get("essential") or []
        noti = [m["id"] for m in
                ((e.get("cv", {}).get("skills") or {}).get("all_matches") or [])]
        if not noti or not richieste:
            continue
        posseduti = set(noti)
        gap = [s for s in richieste if s not in posseduti]
        if len(gap) >= minimo:
            casi.append((gap, noti))
    return casi


if __name__ == "__main__":
    main()
