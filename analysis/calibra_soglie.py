"""
calibra_soglie.py  —  SkillPath AI
===================================
Cerca le soglie di similarità migliori per un encoder, senza riparsare.

IL PROBLEMA
───────────
Le quattro soglie del job parser — 0.72 per l'occupazione, 0.82 per i candidati
di una parola, 0.88 per quelli di più parole, 0.84 per gli acronimi — sono state
scelte osservando i punteggi prodotti da intfloat/multilingual-e5-base. Un
coseno però non ha un significato assoluto: dipende da come il modello è stato
addestrato. I modelli E5, ottimizzati con obiettivo contrastivo, producono
similarità concentrate in alto; altri encoder lavorano su scale diverse.

Applicare le stesse soglie a un encoder di un'altra famiglia non ne misura la
capacità, ma quanto la sua scala somigli a quella di E5. Il caso limite
osservato: con paraphrase-multilingual-MiniLM-L12-v2 la soglia 0.72
sull'occupazione viene superata in 45 annunci su 810, ma in quei 45 casi il
modello indovina l'84.4% delle volte, contro il 75.9% di e5-base. Il modello
ordina meglio e sembra dieci volte peggio.

L'IDEA
──────
Le soglie sono un filtro applicato dopo il calcolo dei punteggi. Se il parsing
avviene una volta sola con soglie molto basse, tutti i match deboli restano nel
file di output, e qualunque soglia più alta può essere applicata a posteriori
filtrando quei punteggi. Cercare le soglie migliori non richiede quindi di
riparsare: è una scansione su dati già salvati, che dura secondi invece di ore.

DIVISIONE DEI DATI
──────────────────
Scegliere le soglie e misurarne l'effetto sugli stessi annunci significherebbe
riportare il valore massimo di una ricerca, non una prestazione. Gli annunci
vengono perciò divisi in due parti disgiunte: le soglie si scelgono sulla prima,
le metriche si riportano sulla seconda. Lo scarto fra i due valori dice quanto
la scelta si sia adattata al rumore dei dati di taratura.

IL PARSING DI CALIBRAZIONE VA FATTO SENZA FILTRI
────────────────────────────────────────────────
`all_matches` viene scritto DOPO il classificatore e la denylist: se questi
sono attivi, i match che scartano non compaiono nel file e la ricerca non può
più vederli. Il parsing di calibrazione va quindi eseguito senza
--classificatore e con --no-denylist, in modo che il file contenga l'insieme
grezzo dei match.

Ne segue che le soglie vengono scelte sul comportamento della pipeline senza
filtro appreso, mentre il parsing definitivo lo applica. È un'approssimazione
accettabile — il classificatore rimuove falsi positivi a prescindere dalla
soglia — ma va dichiarata: le soglie sono ottime per la pipeline nuda, non
necessariamente per quella completa.

USO
───
  1) Parsing di calibrazione, una volta per encoder:
       python tests/batch_parse_jobs_gt.py --modello <ENCODER> --soglie-basse \
              --no-hubness --no-denylist --out outputs/calibrazione/<TAG>.json

  2) Ricerca delle soglie:
       python analysis/calibra_soglie.py --in outputs/calibrazione/<TAG>.json

  3) Le soglie trovate si passano al parser definitivo:
       python tests/batch_parse_jobs_gt.py --modello <ENCODER> --classificatore \
              --no-hubness --soglia-occ .. --soglia-sw .. --soglia-mw .. --soglia-acr ..
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

SEP = "─" * 74

# Griglia di ricerca. Passo 0.02: più fine sarebbe rumore, dato che la
# differenza fra due soglie contigue sposta pochi match.
def griglia(lo: float, hi: float, passo: float = 0.02) -> list[float]:
    n = int(round((hi - lo) / passo)) + 1
    return [round(lo + i * passo, 4) for i in range(n)]


# ══════════════════════════════════════════════════════════════════════════════
# Metriche
# ══════════════════════════════════════════════════════════════════════════════

def metriche_skill(entries: list[dict], soglie: dict) -> tuple[float, float, float]:
    """Precision, recall e F1 macro applicando le soglie ai match già salvati."""
    P = R = F = 0.0
    n = 0
    for e in entries:
        gt = set(e["expected_skills"]["required_ids"]
                 + e["expected_skills"]["preferred_ids"])
        trovate = {
            m["id"] for m in (e.get("skills", {}) or {}).get("all_matches", [])
            if m.get("score", 0) >= soglie.get(m.get("tipo", "mw"), 1.1)
        }
        if not gt and not trovate:
            continue
        n += 1
        a = len(trovate & gt)
        b = len(trovate - gt)
        c = len(gt - trovate)
        p = a / (a + b) if a + b else 0.0
        r = a / (a + c) if a + c else 0.0
        P += p
        R += r
        F += (2 * p * r / (p + r)) if p + r else 0.0
    if not n:
        return 0.0, 0.0, 0.0
    return P / n, R / n, F / n


def accuratezza_occupazione(entries: list[dict], soglia: float) -> tuple[float, float]:
    """Accuratezza e quota di documenti in cui un'occupazione viene proposta."""
    ok = proposte = tot = 0
    for e in entries:
        gt = (e.get("ground_truth") or {}).get("target_occupation_id", "")
        if not gt:
            continue
        tot += 1
        o = e.get("occupation") or {}
        if o.get("id") and (o.get("score", 0) >= soglia):
            proposte += 1
            if o["id"] == gt:
                ok += 1
    if not tot:
        return 0.0, 0.0
    return ok / tot, proposte / tot


# ══════════════════════════════════════════════════════════════════════════════
# Ricerca
# ══════════════════════════════════════════════════════════════════════════════

def cerca_soglie_skill(tara: list[dict], passo: float) -> dict:
    """
    Ricerca a coordinate: si ottimizza una soglia per volta, ripetendo finché
    nessuna si muove. Una ricerca esaustiva sulle tre soglie insieme costerebbe
    migliaia di valutazioni senza dare un risultato migliore, perché i tre tipi
    di candidato agiscono su insiemi di match quasi disgiunti.
    """
    soglie = {"sw": 0.82, "mw": 0.88, "acr": 0.84}
    valori = griglia(0.60, 0.98, passo)

    # Quanti match esistono per ciascun tipo. Una soglia stimata su una
    # manciata di esempi non è calibrata: è rumore travestito da numero. Il
    # caso concreto è `sw`, quasi scomparso da quando dalla prosa si accettano
    # solo candidati di almeno due parole: su 60 annunci ne restano 2. Sotto la
    # soglia minima di campioni il valore predefinito resta intoccato.
    conteggi: dict[str, int] = {}
    for e in tara:
        for m in (e.get("skills", {}) or {}).get("all_matches", []) or []:
            t = m.get("tipo", "mw")
            conteggi[t] = conteggi.get(t, 0) + 1
    MIN_CAMPIONI = 100

    migliore = metriche_skill(tara, soglie)[2]
    for _ in range(4):                      # 4 passate bastano a stabilizzare
        mosso = False
        for tipo in ("mw", "sw", "acr"):
            if conteggi.get(tipo, 0) < MIN_CAMPIONI:
                continue                    # troppo pochi esempi: non si tocca
            corrente = soglie[tipo]
            for v in valori:
                prova = dict(soglie, **{tipo: v})
                f1 = metriche_skill(tara, prova)[2]
                if f1 > migliore + 1e-6:
                    migliore, corrente, mosso = f1, v, True
            soglie[tipo] = corrente
        if not mosso:
            break
    return soglie, conteggi, MIN_CAMPIONI


def cerca_soglia_occupazione(tara: list[dict], passo: float) -> float:
    """
    Per l'occupazione il criterio è l'accuratezza sul totale dei documenti, non
    su quelli in cui il sistema si pronuncia: altrimenti la soglia migliore
    sarebbe la più alta possibile, che risponde una volta sola e indovina.

    A parità di accuratezza si sceglie la soglia PIÙ ALTA, non la più bassa.
    Quando un encoder produce punteggi tutti al di sopra di un certo valore,
    ogni soglia inferiore dà lo stesso risultato: prendere la più bassa
    restituirebbe un numero arbitrario — 0.30 nella prima versione — che
    sembra calibrato e non lo è. La più alta fra quelle equivalenti indica
    invece il punto oltre il quale l'accuratezza comincerebbe a scendere, che
    è un'informazione vera sul modello.
    """
    migliore, scelta = -1.0, 0.72
    for v in griglia(0.30, 0.95, passo):
        acc, _ = accuratezza_occupazione(tara, v)
        if acc >= migliore - 1e-9:          # >= : a parità vince la più alta
            migliore, scelta = acc, v
    return scelta


# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — calibrazione delle soglie per encoder")
    ap.add_argument("--in", dest="inp", required=True,
                    help="File prodotto dal parsing con --soglie-basse")
    ap.add_argument("--quota-taratura", type=float, default=0.25,
                    help="Frazione di annunci usata per scegliere le soglie "
                         "(default 0.25). Il resto serve a riportare le "
                         "metriche.")
    ap.add_argument("--passo", type=float, default=0.02,
                    help="Passo della griglia di ricerca (default 0.02)")
    ap.add_argument("--out", default=None,
                    help="File JSON su cui salvare le soglie trovate")
    args = ap.parse_args()

    percorso = Path(args.inp)
    if not percorso.exists():
        print(f"[ERRORE] File non trovato: {percorso}")
        sys.exit(1)

    entries = json.loads(percorso.read_text(encoding="utf-8"))

    # Controllo di sanità: senza il campo `tipo` il file proviene da una
    # versione precedente del parser e le tre soglie non sono separabili.
    campione = [m for e in entries[:50]
                for m in (e.get("skills", {}) or {}).get("all_matches", [])]
    if campione and not any("tipo" in m for m in campione):
        print("[ERRORE] I match non riportano il campo `tipo`.\n"
              "         Il file è stato prodotto da una versione precedente "
              "del parser.\n"
              "         Riparsare con --soglie-basse dopo aver aggiornato "
              "job_parser.py.")
        sys.exit(1)

    meta_path = percorso.with_suffix(".meta.json")
    modello = "sconosciuto"
    soglie_parsing = None
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        modello = meta.get("modello", modello)
        soglie_parsing = meta.get("soglie") or None
        if soglie_parsing and max(soglie_parsing.values()) > 0.70:
            print(f"[ATTENZIONE] Il file è stato parsato con soglie alte "
                  f"({soglie_parsing}).\n              I match sotto quelle "
                  f"soglie sono assenti: la ricerca\n              non potrà "
                  f"esplorare valori più bassi.\n")

    # ── Divisione ────────────────────────────────────────────────────────────
    # Divisione per posizione, non casuale: gli annunci sono già generati in
    # ordine sparso rispetto all'occupazione, e una divisione deterministica
    # rende il risultato riproducibile senza dover fissare un seme.
    n_tara = int(len(entries) * args.quota_taratura)
    tara, riporto = entries[:n_tara], entries[n_tara:]

    print(f"\n{SEP}\n  CALIBRAZIONE DELLE SOGLIE — {modello}\n{SEP}")
    print(f"  annunci totali {len(entries)}   taratura {len(tara)}   "
          f"riporto {len(riporto)}")

    scala = [m.get("score", 0)
             for e in entries
             for m in (e.get("skills", {}) or {}).get("all_matches", [])]
    if scala:
        print(f"  scala dei punteggi: mediana {st.median(scala):.3f}  "
              f"min {min(scala):.3f}  max {max(scala):.3f}")
        # Se il punteggio più basso è comunque alto ci sono due spiegazioni
        # opposte, e vanno distinte perché una è un errore e l'altra no.
        #   - Il parsing è avvenuto con soglie alte: i match deboli mancano dal
        #     file e la ricerca è cieca sotto quel valore. Va riparsato.
        #   - Il parsing è avvenuto con soglie basse e il modello semplicemente
        #     non produce punteggi più bassi. Ogni candidato contribuisce il
        #     suo match migliore, e gli encoder addestrati per contrasto —
        #     tutta la famiglia E5 — concentrano le similarità in alto. Non
        #     c'è nulla da correggere: la ricerca ha visto tutto ciò che esiste.
        # Il file di configurazione permette di sapere in quale dei due casi ci
        # si trova, invece di allarmare a vuoto.
        if min(scala) > 0.65:
            if soglie_parsing and max(soglie_parsing.values()) <= 0.70:
                print(f"\n  Nota: nessun match sotto {min(scala):.3f} pur "
                      f"avendo parsato a soglie basse.\n"
                      f"  È una proprietà del modello, non un problema: la "
                      f"ricerca ha esplorato\n"
                      f"  tutto l'intervallo effettivamente popolato.")
            else:
                print(f"\n  [ATTENZIONE] Il punteggio più basso nel file è "
                      f"{min(scala):.3f}, e non risulta\n"
                      "               un parsing a soglie basse. I match più "
                      "deboli potrebbero\n"
                      "               essere assenti dal file: in tal caso la "
                      "ricerca non può\n"
                      "               esplorarli. Riparsare con --soglie-basse.")

    # ── Ricerca ──────────────────────────────────────────────────────────────
    print(f"\n  Ricerca in corso…")
    soglie, conteggi, min_campioni = cerca_soglie_skill(tara, args.passo)
    soglie["occ"] = cerca_soglia_occupazione(tara, args.passo)

    # La soglia sull'occupazione è "inattiva" se nessun documento le sta sotto:
    # in quel caso non filtra nulla e non va letta come una calibrazione.
    occ_scores = [(e.get("occupation") or {}).get("score", 0) for e in entries]
    occ_scores = [s for s in occ_scores if s]
    occ_inattiva = bool(occ_scores) and min(occ_scores) >= soglie["occ"]

    # ── Confronto ────────────────────────────────────────────────────────────
    default = {"sw": 0.82, "mw": 0.88, "acr": 0.84, "occ": 0.72}

    print(f"\n{SEP}\n  SOGLIE\n{SEP}")
    print(f"  {'tipo':<10}{'predefinita':>14}{'calibrata':>12}{'scarto':>10}")
    print(f"  {'-'*46}")
    for k, etichetta in (("occ", "occupazione"), ("sw", "una parola"),
                         ("mw", "più parole"), ("acr", "acronimi")):
        d, c = default[k], soglie[k]
        nota = ""
        if k != "occ" and conteggi.get(k, 0) < min_campioni:
            nota = f"   (solo {conteggi.get(k, 0)} match: lasciata invariata)"
        if k == "occ" and occ_inattiva:
            nota = "   (tutti i documenti la superano: soglia inattiva)"
        print(f"  {etichetta:<10}{d:>14.2f}{c:>12.2f}{c-d:>+10.2f}{nota}")

    print(f"\n{SEP}\n  EFFETTO SUL SOTTOINSIEME DI RIPORTO (mai usato per "
          f"scegliere)\n{SEP}")
    print(f"  {'configurazione':<22}{'Prec':>9}{'Rec':>9}{'F1':>9}"
          f"{'occ.':>9}{'propone':>10}")
    print(f"  {'-'*68}")
    for nome, s in (("soglie predefinite", default), ("soglie calibrate", soglie)):
        p, r, f = metriche_skill(riporto, s)
        acc, prop = accuratezza_occupazione(riporto, s["occ"])
        print(f"  {nome:<22}{p:>9.3f}{r:>9.3f}{f:>9.3f}{acc:>9.3f}{prop:>10.1%}")

    p_t, r_t, f_t = metriche_skill(tara, soglie)
    _, _, f_r = metriche_skill(riporto, soglie)
    print(f"\n  F1 in taratura {f_t:.3f}   in riporto {f_r:.3f}   "
          f"scarto {f_t-f_r:+.3f}")
    if f_t - f_r > 0.03:
        print("  Lo scarto è ampio: la scelta si è adattata al rumore del "
              "sottoinsieme\n  di taratura. Conviene allargarlo o irrobustire "
              "la griglia.")
    else:
        print("  Lo scarto è contenuto: le soglie generalizzano.")

    # ── Comando pronto ───────────────────────────────────────────────────────
    print(f"\n{SEP}\n  PARSING DEFINITIVO CON QUESTE SOGLIE\n{SEP}")
    print(f"  python tests/batch_parse_jobs_gt.py --modello {modello} \\\n"
          f"         --classificatore --no-hubness \\\n"
          f"         --soglia-occ {soglie['occ']} --soglia-sw {soglie['sw']} "
          f"--soglia-mw {soglie['mw']} --soglia-acr {soglie['acr']} \\\n"
          f"         --out outputs/confronto_modelli/"
          f"{modello.split('/')[-1]}.json")
    print(SEP)

    out = Path(args.out) if args.out else percorso.with_name(
        percorso.stem + "_soglie.json")
    out.write_text(json.dumps(
        {"modello": modello, "soglie": soglie,
         "n_taratura": len(tara), "n_riporto": len(riporto)},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Soglie salvate in {out}\n")


if __name__ == "__main__":
    main()
