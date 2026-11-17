"""
batch_parse_cvs.py  —  SkillPath AI
=====================================
Parsa tutti gli 810 CV sintetici e salva i risultati in
cv_batch_results.json (da eseguire una sola volta).

Uso (dalla radice del progetto):
    python tests/batch_parse_cvs.py               # tutti gli 810 CV
    python tests/batch_parse_cvs.py --max 50      # test rapido su 50 CV
    python tests/batch_parse_cvs.py --resume      # riprende da dove era rimasto
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent  # radice progetto (tests/ è un livello sotto)
SRC_DIR   = BASE_DIR / "src"
MANIFEST  = BASE_DIR / "dataset" / "synthetic" / "rendered" / "manifest.json"
OUT_FILE  = BASE_DIR / "outputs" / "cv_batch_results.json"


def main():
    ap = argparse.ArgumentParser(description="SkillPath AI — Batch parse CV sintetici")
    ap.add_argument("--max",    type=int, default=None, help="Limita a N CV")
    ap.add_argument("--resume", action="store_true",    help="Riprende da dove era rimasto")
    ap.add_argument("--out",    default=str(OUT_FILE),  help="File output JSON")
    # Soglie parametriche: vedi la docstring di MainParser. Servono a misurare
    # il contributo di ciascuna invece di darlo per scontato.
    ap.add_argument("--soglia-cert", type=float, default=None,
                    help="Soglia per le certificazioni (default 0.86)")
    ap.add_argument("--cert-max", type=int, default=None,
                    help="Numero massimo di certificazioni estratte (default 10)")
    ap.add_argument("--cert-solo-sezione", action="store_true",
                    help="Cerca le certificazioni solo nella sezione dedicata")
    args = ap.parse_args()

    soglie = {}
    if args.soglia_cert is not None:
        soglie["cert"] = args.soglia_cert
    if args.cert_max is not None:
        soglie["cert_max"] = args.cert_max

    if not MANIFEST.exists():
        print(f"[batch_cv] ERRORE: manifest non trovato: {MANIFEST}")
        sys.exit(1)

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)

    if args.max:
        manifest = manifest[:args.max]

    # Resume: carica risultati già salvati
    out_path = Path(args.out)
    already_done: dict[str, dict] = {}
    if args.resume and out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
        already_done = {r["cv_id"]: r for r in existing}
        print(f"[batch_cv] Resume: {len(already_done)} CV già parsati")

    sys.path.insert(0, str(SRC_DIR))
    from main_parser import MainParser
    parser = MainParser(soglie=soglie or None,
                        cert_solo_sezione=args.cert_solo_sezione)
    print(f"[soglie] " + "  ".join(f"{k}={v}" for k, v in parser.soglie.items()))
    print(f"[cert] solo sezione dedicata: {parser.cert_solo_sezione}")

    results = list(already_done.values())
    errors  = []
    t0 = time.time()

    to_process = [e for e in manifest if e["cv_id"] not in already_done]
    print(f"[batch_cv] {len(to_process)} CV da parsare "
          f"({len(already_done)} già in cache)\n")

    for i, entry in enumerate(to_process, 1):
        cv_id    = entry["cv_id"]
        template = entry["template"]
        gt       = entry.get("ground_truth", {})

        # Normalizza il path (Windows → Linux e viceversa)
        pdf_rel  = entry["path_pdf"].replace("\\", "/")
        pdf_path = BASE_DIR / pdf_rel

        if not pdf_path.exists():
            errors.append({"cv_id": cv_id, "motivo": "file_non_trovato"})
            continue

        try:
            parsed = parser.parse_cv(str(pdf_path))
        except Exception as e:
            errors.append({"cv_id": cv_id, "motivo": str(e)})
            continue

        # Aggiungi metadati utili per il ranking
        parsed["template"]     = template
        parsed["ground_truth"] = gt

        results.append(parsed)

        # Progress e salvataggio periodico
        if i % 50 == 0 or i == len(to_process):
            elapsed = time.time() - t0
            rate    = i / elapsed
            eta     = (len(to_process) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(to_process)}]  {elapsed:.0f}s  ETA {eta/60:.1f}min  "
                  f"({len(errors)} errori)")
            # Salva progressivamente
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False)

    elapsed_tot = time.time() - t0
    print(f"\n[batch_cv] ✓ Completato in {elapsed_tot/60:.1f} min")
    print(f"  CV parsati: {len(results)}  |  Errori: {len(errors)}")
    print(f"  → {out_path}")

    if errors:
        err_path = out_path.parent / "cv_batch_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        print(f"  → Errori in {err_path}")


if __name__ == "__main__":
    main()
