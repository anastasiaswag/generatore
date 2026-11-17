"""
genera_pool_annotazione.py  —  SkillPath AI
============================================
Costruisce l'insieme di candidati da annotare a mano sui curriculum reali.

PERCHÉ ESISTE QUESTO PASSO
──────────────────────────
Sui 15 curriculum reali non esiste una ground truth: nessuno ha mai stabilito
quali competenze ESCO siano davvero presenti. Senza quella lista si può dire
che il parser «regge», non quanto sia accurato.

Per costruirla servirebbe, in teoria, esaminare tutte le 13.939 competenze
ESCO per ogni documento. È impraticabile. Si usa quindi il **pooling**, il
metodo con cui si valutano i sistemi di retrieval da decenni: si fa girare il
sistema in più configurazioni, si raccoglie l'unione di tutto ciò che una
qualsiasi di esse ha proposto, e si annota soltanto quell'insieme.

Il richiamo che se ne ricava è **relativo al pool**, non assoluto, e va
dichiarato come tale. In cambio il lavoro passa da impossibile a una serata.

PERCHÉ PIÙ CONFIGURAZIONI E NON SOLO QUELLA DI PRODUZIONE
─────────────────────────────────────────────────────────
Se il pool contenesse solo ciò che la configurazione di produzione propone,
il richiamo misurato sarebbe 1,0 per costruzione: non si potrebbe mai
scoprire una competenza che il parser ha mancato. Le configurazioni a soglia
più bassa servono esattamente a far emergere quei casi.

Resta comunque possibile, in fase di annotazione, aggiungere a mano una
competenza che nessuna configurazione ha proposto: l'interfaccia ha una
ricerca libera su tutte le etichette ESCO. Quelle aggiunte sono i falsi
negativi che nemmeno il pool allargato aveva intercettato, e vanno contate.

DATI PERSONALI
──────────────
I curriculum contengono dati reali. Con --anonimo il file prodotto usa
identificativi progressivi e la corrispondenza con i nomi finisce in un file
separato, che non va allegato alla tesi. Il testo del documento viene però
salvato nel pool, perché serve per annotare: quel file resta materiale di
lavoro e non va distribuito.

Uso (dalla radice del progetto):
    python analysis/genera_pool_annotazione.py --cartella "C:/.../CV per test" --anonimo
    python analysis/genera_pool_annotazione.py --cartella "..." --solo-produzione
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
OUT_FILE = BASE_DIR / "outputs" / "pool_annotazione.json"

ESTENSIONI = {".pdf", ".docx", ".doc", ".txt"}
SEP = "─" * 74

# Le configurazioni del pool. La prima è quella di produzione: i suoi
# candidati sono quelli su cui si misurerà la precisione. Le altre due
# allargano progressivamente le soglie sulle competenze per far emergere
# ciò che la produzione scarta — sono la sola fonte possibile di falsi
# negativi osservabili, insieme alle aggiunte manuali.
CONFIGURAZIONI = {
    "produzione": {},
    "larga": {"sw": 0.80, "mw": 0.83, "acr": 0.80, "skill_max": 40},
    "larghissima": {"sw": 0.75, "mw": 0.78, "acr": 0.75, "skill_max": 60},
}

# Oltre questa dimensione l'annotazione non si finisce in una sera: lo script
# avverte invece di lasciartelo scoprire a metà lavoro.
SOGLIA_AVVISO = 600


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — pool di candidati per l'annotazione manuale")
    ap.add_argument("--cartella", required=True,
                    help="Cartella contenente i curriculum reali")
    ap.add_argument("--out", default=str(OUT_FILE))
    ap.add_argument("--anonimo", action="store_true",
                    help="Identificativi progressivi al posto dei nomi file")
    ap.add_argument("--solo-produzione", action="store_true",
                    help="Usa solo la configurazione di produzione. ATTENZIONE: "
                         "così il richiamo non è misurabile, serve solo per "
                         "una prova rapida dell'interfaccia.")
    args = ap.parse_args()

    cartella = Path(args.cartella)
    if not cartella.is_dir():
        print(f"[ERRORE] Cartella non trovata: {cartella}")
        sys.exit(1)

    files = sorted(p for p in cartella.iterdir()
                   if p.is_file() and p.suffix.lower() in ESTENSIONI)
    if not files:
        print(f"[ERRORE] Nessun documento in {cartella}")
        sys.exit(1)

    configurazioni = ({"produzione": {}} if args.solo_produzione
                      else CONFIGURAZIONI)

    print(f"\n{SEP}\n  POOL DI ANNOTAZIONE — CURRICULUM REALI\n{SEP}")
    print(f"  documenti      : {len(files)}")
    print(f"  configurazioni : {', '.join(configurazioni)}")
    if args.solo_produzione:
        print("  [ATTENZIONE] Una sola configurazione: il richiamo misurato\n"
              "               risulterebbe 1,0 per costruzione.")
    print()

    sys.path.insert(0, str(SRC_DIR))
    from main_parser import MainParser
    from pdf_extractor import get_text

    # Un parser per configurazione, istanziato una volta sola: il costruttore
    # carica l'indice degli embedding, che è la parte lenta.
    parser_per_config = {}
    for nome, soglie in configurazioni.items():
        print(f"  [init] {nome} …")
        parser_per_config[nome] = MainParser(soglie=soglie or None)

    risultati = []
    mappa_nomi = {}
    t0 = time.time()

    for i, f in enumerate(files, 1):
        cv_id = f"cv_reale_{i:02d}" if args.anonimo else f.stem
        mappa_nomi[cv_id] = f.name
        print(f"\n  [{i}/{len(files)}] {f.name[:58]}")

        try:
            righe = get_text(str(f)) or []
        except Exception as e:
            print(f"        [ERRORE] estrazione testo: {e}")
            righe = []

        # candidato_id → voce del pool
        candidati: dict[str, dict] = {}
        for nome, parser in parser_per_config.items():
            try:
                parsed = parser.parse_cv(str(f))
            except Exception as e:
                print(f"        [ERRORE] configurazione {nome}: {e}")
                continue
            matches = ((parsed.get("cv", {}).get("skills") or {})
                       .get("all_matches") or [])
            for m in matches:
                sid = m.get("id")
                if not sid:
                    continue
                voce = candidati.setdefault(sid, {
                    "id": sid,
                    "label": m.get("label", sid),
                    "score_max": 0.0,
                    "configurazioni": [],
                    "frasi_origine": [],
                })
                voce["score_max"] = max(voce["score_max"], m.get("score", 0.0))
                if nome not in voce["configurazioni"]:
                    voce["configurazioni"].append(nome)
                # Frase del CV che ha generato il match. Configurazioni
                # diverse possono partire da frasi diverse: si conservano
                # tutte, perché durante l'annotazione una può chiarire ciò
                # che un'altra lascia ambiguo.
                q = (m.get("query") or "").strip()
                if q and q not in voce["frasi_origine"]:
                    voce["frasi_origine"].append(q)
            print(f"        {nome:<12} {len(matches):>3} competenze")

        ordinati = sorted(candidati.values(),
                          key=lambda c: -c["score_max"])
        n_prod = sum(1 for c in ordinati if "produzione" in c["configurazioni"])
        print(f"        → pool {len(ordinati)} candidati "
              f"({n_prod} dalla produzione, "
              f"{len(ordinati) - n_prod} solo dalle configurazioni larghe)")

        risultati.append({
            "cv_id": cv_id,
            "file_originale": None if args.anonimo else f.name,
            "testo": righe,
            "candidati": ordinati,
        })

    totale = sum(len(r["candidati"]) for r in risultati)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "configurazioni": {k: v for k, v in configurazioni.items()},
        "n_documenti": len(risultati),
        "n_candidati": totale,
        "documenti": risultati,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{SEP}")
    print(f"  Completato in {(time.time()-t0)/60:.1f} min")
    print(f"  Candidati da annotare: {totale}  "
          f"(media {totale/len(risultati):.1f} per documento)")
    print(f"  → {out}")

    if args.anonimo:
        mappa = out.parent / (out.stem + "_nomi.json")
        mappa.write_text(json.dumps(mappa_nomi, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        print(f"  → corrispondenza nomi in {mappa}")
        print(f"    (dati personali: NON allegare alla tesi)")

    if totale > SOGLIA_AVVISO:
        print(f"\n  [AVVISO] {totale} candidati sono più di quanti se ne\n"
              f"           annotino in una sera. Puoi ridurre il pool\n"
              f"           togliendo la configurazione 'larghissima' dalla\n"
              f"           costante CONFIGURAZIONI in testa a questo file —\n"
              f"           ma ogni configurazione tolta abbassa il numero di\n"
              f"           falsi negativi osservabili, e va dichiarato.")

    print(f"\n  Prossimo passo — annotazione:")
    print(f"    python -m streamlit run app/annota_cv.py")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
