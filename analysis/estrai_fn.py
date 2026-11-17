"""
estrai_fn.py  —  SkillPath AI
==============================
Analizza i False Negative ricorrenti del parser sui CV sintetici renderizzati.

Per ogni CV confronta le skill trovate dal parser con il ground truth di
cvs.json, raccoglie le skill mancate (FN) e produce una classifica delle
skill più frequentemente non rilevate.

Queste sono le lacune strutturali di ESCO (skill reali non presenti
nell'ontologia) o skill presenti in ESCO ma sistematicamente sotto soglia.
Entrambe le categorie sono candidate per il dizionario supplementare.

Output:
    outputs/fn_analysis.json   — risultati dettagliati per CV + classifica FN
    stampa su console la top-N skill più mancate

Uso (dalla radice del progetto):
    python analysis/estrai_fn.py                  # tutti i CV nel manifest
    python analysis/estrai_fn.py --n 90           # primi 90 CV
    python analysis/estrai_fn.py --top 30         # mostra top 30 FN (default 20)
    python analysis/estrai_fn.py --load           # carica risultati salvati senza rieseguire
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent  # radice progetto (analysis/ è un livello sotto)
SRC_DIR   = BASE_DIR / "src"
DATA_SRC  = BASE_DIR / "dataset" / "source"
DATA_SYN  = BASE_DIR / "dataset" / "synthetic"
RENDERED  = DATA_SYN / "rendered"
OUT_PATH  = BASE_DIR / "outputs" / "fn_analysis.json"


def load_skill_labels() -> dict[str, str]:
    """Mappa id → label per tutte le skill ESCO (primarie + alt_labels)."""
    labels: dict[str, str] = {}
    skills_path = DATA_SRC / "skills.json"
    if not skills_path.exists():
        return labels
    with open(skills_path, encoding="utf-8") as f:
        data = json.load(f)
    for entry in data.values():
        sid   = entry.get("id", "")
        label = entry.get("label", "")
        if sid and label:
            labels[sid] = label
    return labels


def run_analysis(n_cv: int | None) -> dict:
    """
    Esegue il parser su tutti i CV del manifest e raccoglie i FN.
    Ritorna un dict con i risultati dettagliati e la classifica FN.
    """
    manifest_path = RENDERED / "manifest.json"
    if not manifest_path.exists():
        print("[estrai_fn] ERRORE: manifest.json non trovato. Esegui render_cvs.py prima.")
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Ground truth skill per CV
    cvs_path = DATA_SYN / "cvs.json"
    if not cvs_path.exists():
        print("[estrai_fn] ERRORE: cvs.json non trovato.")
        sys.exit(1)

    cv_skills_gt: dict[str, set] = {}
    with open(cvs_path, encoding="utf-8") as f:
        all_cvs = json.load(f)
    for entry in all_cvs:
        cid = entry.get("cv_id", "")
        skills = entry.get("cv", {}).get("skills", {})
        ids = set(skills.get("essential_ids", []) + skills.get("optional_ids", []))
        cv_skills_gt[cid] = ids

    # Label ESCO per tradurre ID → testo leggibile
    skill_labels = load_skill_labels()

    # Import parser
    try:
        sys.path.insert(0, str(SRC_DIR))
        from main_parser import MainParser
        parser = MainParser()
    except ImportError as e:
        print(f"[estrai_fn] ERRORE import MainParser: {e}")
        sys.exit(1)

    sample = manifest[:n_cv] if n_cv else manifest
    total  = len(sample)

    fn_counter: Counter = Counter()   # id → conteggio mancanze
    cv_results = []

    print(f"\n[estrai_fn] Analisi FN su {total} CV...\n")

    for i, entry in enumerate(sample, 1):
        cv_id    = entry.get("cv_id", f"cv_{i}")
        template = entry.get("template", "?")
        pdf_path = entry.get("path_pdf", "").replace("\\", "/")
        doc_path = entry.get("path_docx", "").replace("\\", "/")
        cv_path  = str(BASE_DIR / pdf_path) if pdf_path else str(BASE_DIR / doc_path)

        if not os.path.exists(cv_path):
            print(f"  [{i}/{total}] SKIP — file non trovato: {cv_path}")
            continue

        gt_ids = cv_skills_gt.get(cv_id, set())

        try:
            result    = parser.parse_cv(cv_path)
            found_ids = set(
                result["cv"]["skills"]["essential_ids"] +
                result["cv"]["skills"]["optional_ids"]
            )
        except Exception as ex:
            print(f"  [{i}/{total}] ERRORE su {cv_id}: {ex}")
            continue

        fn_ids = gt_ids - found_ids   # skill reali NON trovate
        tp_ids = gt_ids & found_ids
        fp_ids = found_ids - gt_ids

        for fid in fn_ids:
            fn_counter[fid] += 1

        cv_results.append({
            "cv_id":    cv_id,
            "template": template,
            "tp":       len(tp_ids),
            "fp":       len(fp_ids),
            "fn":       len(fn_ids),
            "fn_ids":   list(fn_ids),
        })

        if i % 50 == 0 or i == total:
            print(f"  [{i}/{total}] processati...")

    # Classifica FN con label
    fn_ranked = [
        {
            "rank":      rank,
            "id":        sid,
            "label":     skill_labels.get(sid, "[label non trovata]"),
            "missed_in": count,
            "missed_pct": round(count / total * 100, 1),
        }
        for rank, (sid, count) in enumerate(fn_counter.most_common(), 1)
    ]

    result_data = {
        "total_cv_analyzed": total,
        "fn_ranking":        fn_ranked,
        "cv_details":        cv_results,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)

    print(f"\n[estrai_fn] Risultati salvati in {OUT_PATH}")
    return result_data


def print_ranking(data: dict, top: int) -> None:
    """Stampa la classifica top-N dei FN più frequenti."""
    total   = data["total_cv_analyzed"]
    ranking = data["fn_ranking"]

    print(f"\n{'═'*65}")
    print(f"  TOP {top} SKILL PIÙ FREQUENTEMENTE MANCATE  (su {total} CV)")
    print(f"{'═'*65}\n")
    print(f"  {'#':>3}  {'Mancata':>7}  {'%':>5}  Label ESCO")
    print(f"  {'─'*60}")

    for entry in ranking[:top]:
        print(
            f"  {entry['rank']:>3}  "
            f"{entry['missed_in']:>7}  "
            f"{entry['missed_pct']:>4.1f}%  "
            f"{entry['label']}"
        )

    print(f"\n  Totale skill distinte mai trovate: "
          f"{len([e for e in ranking if e['missed_in'] == total])} "
          f"(mancate in TUTTI i CV che le richiedevano)")
    print(f"  Totale skill distinte mancate almeno una volta: {len(ranking)}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n",    type=int, default=None,
                    help="Numero di CV da analizzare (default: tutti)")
    ap.add_argument("--top",  type=int, default=20,
                    help="Quante skill mostrare nella classifica (default 20)")
    ap.add_argument("--load", action="store_true",
                    help="Carica risultati già salvati senza rieseguire il parser")
    args = ap.parse_args()

    if args.load:
        if not OUT_PATH.exists():
            print(f"[estrai_fn] Nessun file salvato trovato in {OUT_PATH}. "
                  f"Rimuovi --load per eseguire l'analisi.")
            sys.exit(1)
        with open(OUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[estrai_fn] Caricati risultati da {OUT_PATH}")
    else:
        data = run_analysis(args.n)

    print_ranking(data, args.top)


if __name__ == "__main__":
    main()
