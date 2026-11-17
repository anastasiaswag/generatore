"""
parse_cv_reali.py  —  SkillPath AI
====================================
Parsa una cartella di curriculum REALI con il parser dei CV.

PERCHÉ È DIVERSO DA batch_parse_cvs.py
──────────────────────────────────────
Il batch sui CV sintetici confronta l'estrazione con una ground truth completa e
produce precision, recall e F1. Qui la ground truth non esiste: nessuno ha
annotato quali competenze ESCO siano presenti in questi documenti.

Non è un limite da aggirare, è la natura della prova. Ciò che si vuole sapere
non è «quanto è accurato» — non sarebbe misurabile — ma se il parser **regge**
su documenti che non ha mai visto: se il testo viene estratto, se le sezioni
vengono riconosciute, se il numero di competenze estratte è nell'ordine di
grandezza giusto, se compaiono errori sistematici assenti sul sintetico.

Le metriche di questo script sono quindi indicatori di funzionamento, non di
qualità. La valutazione della qualità richiede di leggere i risultati a mano, e
lo script prepara il materiale per farlo.

DATI PERSONALI
──────────────
Questi documenti contengono dati personali reali. L'opzione --anonimo sostituisce
il nome del file con un identificativo progressivo nel file di output, così che
i risultati possano essere mostrati nella tesi senza esporre nomi. La
corrispondenza resta in un file separato che non va allegato.

Uso (dalla radice del progetto):
    python tests/parse_cv_reali.py --cartella "C:/Users/samue/Desktop/CV per test Da Riccardo"
    python tests/parse_cv_reali.py --cartella "..." --anonimo
"""

import argparse
import json
import sys
import time
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
OUT_FILE = BASE_DIR / "outputs" / "cv_reali_results.json"

ESTENSIONI = {".pdf", ".docx", ".doc", ".txt"}
SEP = "─" * 74


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — parsing di curriculum reali")
    ap.add_argument("--cartella", required=True,
                    help="Cartella contenente i curriculum")
    ap.add_argument("--out", default=str(OUT_FILE), help="File JSON di output")
    ap.add_argument("--anonimo", action="store_true",
                    help="Sostituisce i nomi dei file con identificativi "
                         "progressivi nell'output")
    ap.add_argument("--soglia-cert", type=float, default=None,
                    help="Soglia per le certificazioni (default 0.86)")
    ap.add_argument("--cert-max", type=int, default=None,
                    help="Numero massimo di certificazioni (default 10)")
    ap.add_argument("--cert-solo-sezione", action="store_true",
                    help="Cerca le certificazioni solo nella sezione dedicata")
    args = ap.parse_args()

    soglie = {}
    if args.soglia_cert is not None:
        soglie["cert"] = args.soglia_cert
    if args.cert_max is not None:
        soglie["cert_max"] = args.cert_max

    cartella = Path(args.cartella)
    if not cartella.is_dir():
        print(f"[ERRORE] Cartella non trovata: {cartella}")
        sys.exit(1)

    files = sorted(p for p in cartella.iterdir()
                   if p.is_file() and p.suffix.lower() in ESTENSIONI)
    if not files:
        print(f"[ERRORE] Nessun documento in {cartella}")
        sys.exit(1)

    print(f"\n{SEP}\n  PARSING DI CURRICULUM REALI\n{SEP}")
    print(f"  cartella: {cartella}")
    print(f"  documenti trovati: {len(files)}\n")

    sys.path.insert(0, str(SRC_DIR))
    from main_parser import MainParser
    parser = MainParser(soglie=soglie or None,
                        cert_solo_sezione=args.cert_solo_sezione)
    print(f"  soglia certificazioni: {parser.soglie['cert']}  "
          f"tetto: {int(parser.soglie['cert_max'])}  "
          f"solo sezione: {parser.cert_solo_sezione}\n")

    risultati = []
    errori = []
    mappa_nomi = {}
    t0 = time.time()

    for i, f in enumerate(files, 1):
        etichetta = f"cv_reale_{i:02d}" if args.anonimo else f.stem
        mappa_nomi[etichetta] = f.name

        print(f"  [{i}/{len(files)}] {f.name[:60]}")
        try:
            parsed = parser.parse_cv(str(f))
        except Exception as e:
            print(f"        ERRORE: {e}")
            errori.append({"file": etichetta, "motivo": str(e)})
            continue

        parsed["cv_id"] = etichetta
        parsed["file_originale"] = None if args.anonimo else f.name
        parsed["_reale"] = True
        risultati.append(parsed)

        cv = parsed.get("cv", {})
        n_skill = len((cv.get("skills") or {}).get("all_matches") or [])
        we = cv.get("work_experience") or []
        occ = we[0].get("label", "—") if we else "—"
        sez = (parsed.get("debug") or {}).get("section_sizes") or {}
        n_righe_skill = sez.get("skills", 0)
        print(f"        {n_skill} competenze · ruolo: {occ[:40]} · "
              f"righe sez. competenze: {n_righe_skill}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(risultati, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    print(f"\n{SEP}")
    print(f"  Completato in {(time.time()-t0)/60:.1f} min")
    print(f"  Parsati {len(risultati)}/{len(files)}  ·  errori {len(errori)}")
    print(f"  → {out}")

    if args.anonimo:
        mappa = out.parent / (out.stem + "_nomi.json")
        mappa.write_text(json.dumps(mappa_nomi, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        print(f"  → corrispondenza nomi in {mappa}")
        print(f"    (contiene dati personali: NON allegare alla tesi)")

    if errori:
        err = out.parent / (out.stem + "_errori.json")
        err.write_text(json.dumps(errori, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"  → errori in {err}")

    print(f"\n  Prossimo passo — analisi dei risultati:")
    print(f"    python analysis/analisi_cv_reali.py --in {out}")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
