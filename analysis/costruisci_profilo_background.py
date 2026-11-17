"""
costruisci_profilo_background.py  —  SkillPath AI
==================================================
Calibra il profilo di background usato dalla correzione hubness del
JobParser (vedi SemanticMapper.build_background_profile).

PERCHÉ SERVE QUESTO SCRIPT
──────────────────────────
La correzione hubness penalizza le etichette ESCO che somigliano a
qualunque cosa. Per stimare quanto una etichetta è "attrattiva" serve un
corpus di riferimento, e la scelta di quel corpus è decisiva.

Un primo tentativo campionava le descrizioni della stessa ontologia ESCO.
Non ha funzionato: misurato sugli 810 annunci di valutazione, l'etichetta
più dannosa ("comportarsi in modo responsabile", presente come falso
positivo in 792 annunci su 810) restava esattamente dov'era. Il motivo è
che rispetto al linguaggio dell'ontologia quella etichetta non è affatto
anomala; lo diventa rispetto alla fraseologia degli annunci di lavoro, dove
"sarà responsabile di…" compare praticamente ovunque.

La conclusione è che il corpus di background deve avere la stessa
distribuzione delle query che il parser genera davvero, cioè i candidati
estratti dai documenti. Questo script li produce usando lo stesso estrattore
del parser, così la calibrazione avviene sulla distribuzione giusta.

COSA USA E COSA NON USA
───────────────────────
Usa: il TESTO degli annunci (raw_text).
Non usa: le skill di ground truth, né alcuna informazione su quali
predizioni fossero corrette. La calibrazione resta quindi non supervisionata.

Per evitare anche solo effetti transduttivi (calibrare e valutare sugli
stessi documenti), l'opzione --split calibra su una metà del corpus: si
valuta poi sull'altra metà, che il profilo non ha mai visto.

USO
───
    # calibrazione su tutto il corpus
    python analysis/costruisci_profilo_background.py

    # calibrazione sulla prima metà (per validazione su holdout)
    python analysis/costruisci_profilo_background.py --split

Dopo l'esecuzione il JobParser carica automaticamente il profilo dalla
cache; per rimisurare l'effetto:

    python tests/batch_parse_jobs_gt.py --no-denylist --out outputs/ab_bg.json
    python analysis/analisi_job_parser.py --in outputs/ab_bg.json
"""

import argparse
import json
import random
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

JOBS_FILE = BASE_DIR / "dataset" / "synthetic" / "jobs_gt" / "jobs.json"
CACHE_FILE = BASE_DIR / "dataset" / "source_it" / "skills_bg_profile.pt"

DATA_IT = BASE_DIR / "dataset" / "source_it"
DATA_EN = BASE_DIR / "dataset" / "source"


def raccogli_candidati(jobs: list[dict], parser) -> list[str]:
    """
    Estrae i candidati skill dagli annunci con lo STESSO estrattore usato dal
    parser in produzione: è questo che garantisce che il background rispecchi
    la distribuzione reale delle query.
    """
    from pdf_extractor import filter_lines

    candidati: list[str] = []
    for j in jobs:
        testo = j.get("job", {}).get("raw_text", "") or ""
        if not testo.strip():
            continue
        righe = filter_lines([l for l in testo.splitlines() if l.strip()])
        cands, _ = parser._extract_skill_candidates(righe)
        candidati.extend(cands)
    return candidati


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — calibrazione del profilo di background (hubness)"
    )
    ap.add_argument("--jobs", default=str(JOBS_FILE),
                    help="Corpus di annunci da cui ricavare i candidati")
    ap.add_argument("--cache", default=None,
                    help="File su cui salvare il profilo. Se omesso, il nome "
                         "viene derivato dal modello in uso: il profilo NON è "
                         "trasferibile fra encoder diversi.")
    ap.add_argument("--modello", default=None,
                    help="Encoder per cui calibrare il profilo "
                         "(es. sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2). "
                         "Omesso = predefinito del progetto")
    ap.add_argument("--n", type=int, default=4000,
                    help="Numero di candidati campionati per la stima")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--split", action="store_true",
                    help="Calibra solo sulla prima metà del corpus "
                         "(per validare sull'altra metà, mai vista)")
    args = ap.parse_args()

    jobs_path = Path(args.jobs)
    if not jobs_path.exists():
        print(f"[ERRORE] Corpus non trovato: {jobs_path}")
        return

    with open(jobs_path, encoding="utf-8") as f:
        jobs = json.load(f)

    if args.split:
        meta = len(jobs) // 2
        jobs = jobs[:meta]
        print(f"[split] Calibrazione sui primi {len(jobs)} annunci; "
              f"gli altri restano non visti dal profilo.")

    print(f"[1/3] Estrazione candidati da {len(jobs)} annunci…")
    from job_parser import JobParser

    # hubness disattivo: qui il parser serve solo come estrattore di candidati
    parser = JobParser(hubness_correction=False, mutual_only=False,
                       use_denylist=False, model_name=args.modello)

    # Il profilo vive nello spazio vettoriale di un modello preciso e non è
    # trasferibile: il nome del file porta perciò il tag dell'encoder. Senza
    # questa accortezza un profilo calibrato su un altro modello verrebbe
    # caricato senza errori — le dimensioni coincidono — e ne falserebbe i
    # punteggi in modo silenzioso.
    tag = getattr(parser.mapper, "_tag", None) or "sconosciuto"
    cache_out = args.cache or str(DATA_IT / f"skills_bg_profile_{tag}.pt")
    print(f"[modello] {parser.mapper.model_name}")
    print(f"[profilo] destinazione: {cache_out}")

    candidati = raccogli_candidati(jobs, parser)
    print(f"      {len(candidati)} candidati raccolti")

    if len(candidati) < 200:
        print("[ERRORE] Troppo pochi candidati per una stima affidabile.")
        return

    rng = random.Random(args.seed)
    rng.shuffle(candidati)
    campione = candidati[: args.n]
    print(f"      campione di {len(campione)} usato per la stima")

    print("[2/3] Caricamento database skill ESCO…")
    it_skl, en_skl = DATA_IT / "skills.json", DATA_EN / "skills.json"
    if it_skl.exists() and en_skl.exists():
        parser.mapper.load_databases_bilingual(str(it_skl), str(en_skl))
    else:
        parser.mapper.load_database(str(BASE_DIR / "dataset" / "source" / "skills.json"))

    print("[3/3] Calcolo del profilo di background…")
    ok = parser.mapper.build_background_profile(
        campione, cache_path=cache_out, force=True
    )

    if ok:
        print(f"\n  Profilo salvato in {cache_out}")
        print("  Il JobParser lo userà automaticamente alla prossima esecuzione.")
        print("\n  Prossimo passo:")
        print("    python tests/batch_parse_jobs_gt.py --no-denylist --out outputs/ab_bg.json")
        print("    python analysis/analisi_job_parser.py --in outputs/ab_bg.json")
    else:
        print("\n  [ERRORE] Profilo non calcolato.")


if __name__ == "__main__":
    main()
