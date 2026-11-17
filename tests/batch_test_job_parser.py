"""
batch_test_job_parser.py  —  SkillPath AI
==========================================
Elabora in batch tutte le offerte di lavoro dalla cartella job_descriptions/
(file .txt estratti dall'Excel) e produce:

  1. batch_job_results.json  — risultati completi del parser per ogni offerta
  2. batch_job_summary.csv   — riassunto tabulare (ID, Ruolo, Area, occ_label,
                               n_required, n_preferred, skill_labels)
  3. batch_job_stats.json    — statistiche aggregate

Uso (dalla radice del progetto):
    python tests/batch_test_job_parser.py
    python tests/batch_test_job_parser.py --max 50          # solo prime 50
    python tests/batch_test_job_parser.py --area Meccanica  # filtra per area
    python tests/batch_test_job_parser.py --out mia_cartella/
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent  # radice progetto (tests/ è un livello sotto)
SRC_DIR    = BASE_DIR / "src"
JOBS_DIR   = BASE_DIR / "job_descriptions"

sys.path.insert(0, str(SRC_DIR))


def load_rows(
    jobs_dir: Path,
    area_filter: str | None = None,
    max_rows: int | None = None,
) -> list[dict]:
    """
    Carica le offerte dalla cartella job_descriptions/.
    Ogni file ha il formato:
        ID: <n>
        Area: <area>
        Ruolo: <ruolo>
        Azienda: <azienda>
        Località: <localita>

        <testo annuncio>
    """
    txt_files = sorted(jobs_dir.glob("job_*.txt"))
    if not txt_files:
        print(f"[batch] ERRORE: nessun file .txt in {jobs_dir}")
        sys.exit(1)

    rows = []
    for path in txt_files:
        content = path.read_text(encoding="utf-8")
        lines   = content.splitlines()

        # Estrai metadati dall'intestazione (prime righe con "Chiave: valore")
        meta: dict[str, str] = {}
        body_start = 0
        for i, line in enumerate(lines):
            m = re.match(r"^(ID|Area|Ruolo|Azienda|Località|Seniority):\s*(.*)", line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
                body_start = i + 1
            elif line.strip() == "" and meta:
                body_start = i + 1
                break

        testo = "\n".join(lines[body_start:]).strip()

        if area_filter and meta.get("Area", "") != area_filter:
            continue

        rows.append({
            "id":        meta.get("ID", path.stem),
            "area":      meta.get("Area", ""),
            "ruolo":     meta.get("Ruolo", ""),
            "azienda":   meta.get("Azienda", ""),
            "localita":  meta.get("Località", ""),
            "seniority": meta.get("Seniority", ""),
            "testo":     testo,
        })

        if max_rows and len(rows) >= max_rows:
            break

    return rows


def _safe_write(path: Path, data: list) -> None:
    """
    Scrive il JSON su un file temporaneo e poi rinomina atomicamente.
    Se la scrittura viene interrotta, il file originale rimane intatto.
    """
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)   # rename atomico — fallisce solo se disco pieno


def run_batch(
    rows:     list[dict],
    out_dir:  Path,
    verbose:  bool = True,
    save_every: int = 10,   # salva ogni 10 nuovi job
) -> dict:
    """
    Esegue il job parser su ogni riga e aggrega i risultati.
    Salva progressivamente ogni `save_every` job per evitare perdite
    in caso di interruzione. Ritorna un dizionario con statistiche.
    """
    # Import lazy per non bloccare se il modello non è ancora caricato
    from job_parser import JobParser

    jp = JobParser()
    json_path = out_dir / "batch_job_results.json"
    print(f"[batch] JobParser inizializzato — {len(rows)} offerte da elaborare\n")

    # Resume: carica risultati già salvati
    already_done: set[str] = set()
    results: list[dict] = []
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                existing = json.load(f)
            results = existing
            already_done = {r["job_id"] for r in existing}
            if already_done:
                print(f"[batch] Resume: {len(already_done)} job già elaborati, riprendo...")
        except Exception:
            results = []

    failures = []
    t0 = time.time()
    new_count = 0

    for i, row in enumerate(rows, start=1):
        job_id = f"job_{int(row['id']):04d}"

        # Salta job già elaborati (resume)
        if job_id in already_done:
            continue

        testo = row.get("testo") or ""
        if not testo.strip():
            failures.append({"id": job_id, "motivo": "testo_vuoto"})
            continue

        try:
            parsed = jp.parse_job_text(testo, job_id=job_id)
        except Exception as e:
            failures.append({"id": job_id, "motivo": str(e)})
            continue

        parsed["meta"] = {
            "id":        row["id"],
            "area":      row["area"],
            "ruolo":     row["ruolo"],
            "azienda":   row["azienda"],
            "seniority": row["seniority"],
        }
        results.append(parsed)
        new_count += 1

        # Salvataggio progressivo ogni save_every job (via file temporaneo)
        if new_count % save_every == 0:
            _safe_write(json_path, results)
            if verbose:
                elapsed = time.time() - t0
                remaining = len(rows) - len(already_done) - new_count
                eta = (elapsed / new_count * remaining) if new_count > 0 else 0
                print(f"  [{i}/{len(rows)}]  {elapsed:.0f}s  ETA {eta/60:.1f}min  "
                      f"— {parsed['raw_title'][:45]}  "
                      f"({len(parsed['skills']['required_ids'])} req)")

    elapsed_total = time.time() - t0
    print(f"\n[batch] Completato in {elapsed_total:.1f}s  "
          f"({len(results)} totale, {new_count} nuovi, {len(failures)} errori)")

    # ── Salva JSON finale completo (via file temporaneo → rename atomico) ────
    _safe_write(json_path, results)
    print(f"[batch] → {json_path}")

    # ── Salva CSV riassuntivo ────────────────────────────────────────────────
    csv_path = out_dir / "batch_job_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "job_id", "area", "ruolo", "seniority",
            "occ_label", "occ_score",
            "n_required", "n_preferred",
            "skill_required_labels",
        ])
        for r in results:
            m = r.get("meta", {})
            sk = r.get("skills", {})
            occ = r.get("occupation", {})
            req_labels = "; ".join(
                x["label"] for x in sk.get("all_matches", [])
                if x["id"] in sk.get("required_ids", [])
            )
            writer.writerow([
                r.get("job_id", ""),
                m.get("area", ""),
                m.get("ruolo", ""),
                m.get("seniority", ""),
                occ.get("label", ""),
                round(occ.get("score", 0.0), 3),
                len(sk.get("required_ids",  [])),
                len(sk.get("preferred_ids", [])),
                req_labels,
            ])
    print(f"[batch] → {csv_path}")

    # ── Statistiche aggregate ────────────────────────────────────────────────
    n_req_vals  = [len(r["skills"]["required_ids"])  for r in results]
    n_pref_vals = [len(r["skills"]["preferred_ids"]) for r in results]
    occ_scores  = [r["occupation"]["score"] for r in results if r["occupation"]["score"] > 0]

    stats = {
        "totale_elaborati":   len(results),
        "totale_errori":      len(failures),
        "avg_skill_required": round(sum(n_req_vals)  / max(len(n_req_vals),  1), 2),
        "avg_skill_preferred":round(sum(n_pref_vals) / max(len(n_pref_vals), 1), 2),
        "avg_occ_score":      round(sum(occ_scores)  / max(len(occ_scores),  1), 3),
        "offerte_senza_skill":[r["job_id"] for r in results
                               if not r["skills"]["required_ids"]],
    }

    stats_path = out_dir / "batch_job_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*50}")
    print(f"  Totale elaborati:     {stats['totale_elaborati']}")
    print(f"  Errori:               {stats['totale_errori']}")
    print(f"  Avg skill required:   {stats['avg_skill_required']}")
    print(f"  Avg skill preferred:  {stats['avg_skill_preferred']}")
    print(f"  Avg occupation score: {stats['avg_occ_score']}")
    print(f"  Offerte senza skill:  {len(stats['offerte_senza_skill'])}")
    print(f"{'═'*50}")

    return stats


def main():
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Batch test job parser su cartella job_descriptions/")
    ap.add_argument("--jobs", default=str(JOBS_DIR),
                    help=f"Cartella con i file .txt (default: {JOBS_DIR})")
    ap.add_argument("--area",  default=None,
                    help="Filtra per area (Informatica | Meccanica | Elettronica)")
    ap.add_argument("--max",   type=int, default=None,
                    help="Limita a N offerte (test rapido)")
    ap.add_argument("--out",   default=str(BASE_DIR / "outputs"),
                    help="Cartella output (default: outputs/)")
    args = ap.parse_args()

    jobs_dir = Path(args.jobs)
    if not jobs_dir.exists():
        print(f"[batch] ERRORE: cartella non trovata: {jobs_dir}")
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[batch] Lettura da {jobs_dir}/")
    rows = load_rows(jobs_dir, area_filter=args.area, max_rows=args.max)
    print(f"[batch] {len(rows)} offerte caricate"
          + (f" (area={args.area})" if args.area else ""))

    run_batch(rows, out_dir)


if __name__ == "__main__":
    main()
