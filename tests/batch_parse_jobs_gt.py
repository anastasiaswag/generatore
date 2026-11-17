"""
batch_parse_jobs_gt.py  —  SkillPath AI
=========================================
Parsa tutti gli annunci generati da generate_jobs.py (dataset/synthetic/jobs_gt/jobs.json)
con il JobParser reale e allega la ground truth, salvando job_gt_batch_results.json.

È l'equivalente, lato annunci, di batch_parse_cvs.py: da qui in poi
outputs/job_gt_batch_results.json può sostituire outputs/batch_job_results.json
in valida_matching_engine.py per una validazione dello Scenario 2 con
overlap completo sulle 135 occupation (invece che 3 aree).

Uso (dalla radice del progetto):
    python tests/batch_parse_jobs_gt.py               # tutti gli annunci
    python tests/batch_parse_jobs_gt.py --max 50      # test rapido su 50 annunci
    python tests/batch_parse_jobs_gt.py --resume      # riprende da dove era rimasto
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent  # radice progetto (tests/ è un livello sotto)
SRC_DIR    = BASE_DIR / "src"
JOBS_FILE  = BASE_DIR / "dataset" / "synthetic" / "jobs_gt" / "jobs.json"
OUT_FILE   = BASE_DIR / "outputs" / "job_gt_batch_results.json"


def main():
    ap = argparse.ArgumentParser(description="SkillPath AI — Batch parse annunci sintetici con ground truth")
    ap.add_argument("--max",    type=int, default=None, help="Limita a N annunci")
    ap.add_argument("--resume", action="store_true",    help="Riprende da dove era rimasto")
    ap.add_argument("--jobs",   default=str(JOBS_FILE),  help="File jobs.json generato da generate_jobs.py")
    ap.add_argument("--out",    default=str(OUT_FILE),   help="File output JSON")
    # ── Interruttori per i confronti A/B (vedi docstring di JobParser) ────────
    # Servono a misurare il contributo di ciascuna contromisura ai falsi
    # positivi invece di darlo per scontato.
    ap.add_argument("--no-hubness",  action="store_true",
                    help="Disattiva la correzione hubness")
    ap.add_argument("--no-mutual",   action="store_true",
                    help="Disattiva il vincolo di reciprocità")
    ap.add_argument("--no-denylist", action="store_true",
                    help="Disattiva la denylist delle etichette-calamita")
    ap.add_argument("--lexical",     action="store_true",
                    help="Attiva lo stadio di match lessicale")
    ap.add_argument("--spacy",       action="store_true",
                    help="Attiva il chunking dei sintagmi nominali (richiede spaCy)")
    ap.add_argument("--modello", default=None,
                    help="Encoder da usare (es. intfloat/multilingual-e5-small). "
                         "Omesso = predefinito del progetto")
    ap.add_argument("--classificatore", action="store_true",
                    help="Usa il filtro appreso al posto della denylist "
                         "(vedi analysis/addestra_filtro_skill.py)")
    # ── Soglie ────────────────────────────────────────────────────────────────
    # I valori predefiniti sono tarati sulla famiglia E5. Per confrontare
    # encoder di famiglie diverse vanno ricalibrati: vedi la docstring di
    # JobParser e analysis/calibra_soglie.py.
    ap.add_argument("--soglia-occ", type=float, default=None,
                    help="Soglia per l'occupazione (default 0.72)")
    ap.add_argument("--soglia-sw", type=float, default=None,
                    help="Soglia per i candidati di una parola (default 0.82)")
    ap.add_argument("--soglia-mw", type=float, default=None,
                    help="Soglia per i candidati di più parole (default 0.88)")
    ap.add_argument("--soglia-acr", type=float, default=None,
                    help="Soglia per gli acronimi (default 0.84)")
    ap.add_argument("--soglie-basse", action="store_true",
                    help="Porta tutte le soglie a 0.50. Da usare per il "
                         "parsing di calibrazione: conserva anche i match "
                         "deboli, così le soglie definitive possono essere "
                         "cercate fuori linea senza riparsare.")
    args = ap.parse_args()

    soglie = {}
    if args.soglie_basse:
        soglie = {"occ": 0.50, "sw": 0.50, "mw": 0.50, "acr": 0.50}
    for chiave, valore in (("occ", args.soglia_occ), ("sw", args.soglia_sw),
                           ("mw", args.soglia_mw), ("acr", args.soglia_acr)):
        if valore is not None:
            soglie[chiave] = valore

    jobs_path = Path(args.jobs)
    if not jobs_path.exists():
        print(f"[batch_job_gt] ERRORE: {jobs_path} non trovato.")
        print("  Esegui prima: python src/generate_jobs.py")
        sys.exit(1)

    with open(jobs_path, encoding="utf-8") as f:
        manifest = json.load(f)

    if args.max:
        manifest = manifest[:args.max]

    out_path = Path(args.out)
    already_done: dict[str, dict] = {}
    if args.resume and out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
        already_done = {r["job_id"]: r for r in existing}
        print(f"[batch_job_gt] Resume: {len(already_done)} annunci già parsati")

    sys.path.insert(0, str(SRC_DIR))
    from job_parser import JobParser
    parser = JobParser(
        hubness_correction=not args.no_hubness,
        mutual_only=not args.no_mutual,
        use_denylist=not args.no_denylist,
        use_lexical=args.lexical,
        use_spacy=args.spacy,
        use_classifier=args.classificatore,
        model_name=args.modello,
        soglie=soglie or None,
    )
    print(
        f"[config] hubness={not args.no_hubness}  mutual={not args.no_mutual}  "
        f"denylist={parser.use_denylist}  lexical={args.lexical}  "
        f"spacy={args.spacy}  classificatore={parser.filtro_appreso is not None}  "
        f"modello={parser.mapper.model_name}"
    )
    print(f"[soglie] " + "  ".join(f"{k}={v}" for k, v in parser.soglie.items()))

    results = list(already_done.values())
    errors  = []
    t0 = time.time()

    to_process = [e for e in manifest if e["job_id"] not in already_done]
    print(f"[batch_job_gt] {len(to_process)} annunci da parsare "
          f"({len(already_done)} già in cache)\n")

    for i, entry in enumerate(to_process, 1):
        job_id  = entry["job_id"]
        raw_txt = entry.get("job", {}).get("raw_text", "")
        gt      = entry.get("ground_truth", {})
        gen_meta = entry.get("job", {}).get("meta", {})
        gen_skills = entry.get("job", {}).get("skills", {})

        if not raw_txt.strip():
            errors.append({"job_id": job_id, "motivo": "testo_vuoto"})
            continue

        try:
            parsed = parser.parse_job_text(raw_txt, job_id=job_id)
        except Exception as e:
            errors.append({"job_id": job_id, "motivo": str(e)})
            continue

        # Aggiungi metadati utili per la validazione:
        # - meta generazione (ruolo, azienda, seniority... come scelti dal generatore)
        # - ground truth ESCO (occupation target)
        # - skill "attese" (quelle scelte dal generatore, non quelle rilevate dal parser)
        #   utili per validare il JobParser stesso (Precision/Recall skill).
        parsed["meta"]              = {**parsed.get("meta", {}), **gen_meta}
        parsed["ground_truth"]      = gt
        parsed["expected_skills"]   = gen_skills   # required_ids / preferred_ids "vere"

        results.append(parsed)

        if i % 50 == 0 or i == len(to_process):
            elapsed = time.time() - t0
            rate    = i / elapsed
            eta     = (len(to_process) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(to_process)}]  {elapsed:.0f}s  ETA {eta/60:.1f}min  "
                  f"({len(errors)} errori)")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False)

    # Configurazione a fianco dei risultati: senza di essa un file di output
    # non dice con quali soglie né con quale encoder è stato prodotto, e mesi
    # dopo diventa impossibile sapere cosa si sta confrontando.
    meta_path = out_path.with_suffix(".meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "modello": parser.mapper.model_name,
            "soglie": parser.soglie,
            "hubness": not args.no_hubness,
            "mutual": not args.no_mutual,
            "denylist": parser.use_denylist,
            "lexical": args.lexical,
            "spacy": args.spacy,
            "classificatore": parser.filtro_appreso is not None,
            "n_annunci": len(results),
        }, f, indent=2, ensure_ascii=False)

    elapsed_tot = time.time() - t0
    print(f"\n[batch_job_gt] ✓ Completato in {elapsed_tot/60:.1f} min")
    print(f"  → configurazione in {meta_path}")
    print(f"  Annunci parsati: {len(results)}  |  Errori: {len(errors)}")
    print(f"  → {out_path}")

    if errors:
        err_path = out_path.parent / "job_gt_batch_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        print(f"  → Errori in {err_path}")


if __name__ == "__main__":
    main()
