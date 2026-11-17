"""
analisi_job_parser.py  —  SkillPath AI
=========================================
Valutazione quantitativa del JobParser sugli annunci sintetici con ground
truth ESCO (dataset/synthetic/jobs_gt/), l'equivalente della SEZIONE 4 di
analisi_parser.py ma per gli annunci invece che per i CV.

Confronta, per ogni annuncio:
  - le skill "vere" scelte dal generatore (expected_skills, required+preferred)
    contro le skill effettivamente rilevate dal JobParser sul testo
  - l'occupation ESCO rilevata dal parser contro quella target del generatore

METRICHE
--------
Skill:
    Precision = TP / (TP + FP)  → delle skill trovate, quante erano giuste
    Recall    = TP / (TP + FN)  → delle skill vere,     quante sono state trovate
    F1        = media armonica

Occupation:
    Accuracy esatta   = quota di annunci in cui l'ID ESCO rilevato coincide
                         esattamente con quello target
    Accuracy settore  = quota in cui coincide almeno il macro-settore ISCO
                         (metrica più permissiva, utile perché due occupation
                         affini possono avere embedding molto vicini)

LIMITAZIONE (stessa nota della valutazione CV)
-----------------------------------------------
La valutazione per ID ESCO esatto è un lower bound: un match semanticamente
corretto ma con ID leggermente diverso viene contato come FP/FN anche se
concettualmente valido.

Uso (dalla radice del progetto):
    python analysis/analisi_job_parser.py                # tutto il dataset
    python analysis/analisi_job_parser.py --n 100         # campione di 100
    python analysis/analisi_job_parser.py --seed 7

Richiede che sia già stato eseguito:
    python tests/batch_parse_jobs_gt.py --resume

Output:
    stampa su console + salva outputs/job_parser_eval.json
"""

import argparse
import json
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (analysis/ è un livello sotto)
IN_FILE  = BASE_DIR / "outputs" / "job_gt_batch_results.json"
OUT_FILE = BASE_DIR / "outputs" / "job_parser_eval.json"

SEP = "─" * 65


def evaluate(n: int | None, seed: int, in_file: Path | None = None) -> dict:
    in_file = in_file or IN_FILE
    if not in_file.exists():
        print(f"  [ERRORE] {in_file} non trovato.")
        print("  Esegui prima: python tests/batch_parse_jobs_gt.py")
        return {}

    print(f"  [input: {in_file.name}]")
    with open(in_file, encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("  [job_gt_batch_results.json vuoto]")
        return {}

    # Il JobParser restituisce solo {id, label, score} per l'occupation trovata,
    # NON l'ISCO major — va recuperato dal database ESCO per poter fare il
    # confronto "stesso macro-settore" con la ground truth.
    occ_isco_major: dict[str, str] = {}
    occupations_path = BASE_DIR / "dataset" / "source" / "occupations.json"
    if occupations_path.exists():
        with open(occupations_path, encoding="utf-8") as f:
            occ_db = json.load(f)
        for oid, o in occ_db.items():
            isco_code = (o.get("isco_code") or "") if isinstance(o, dict) else ""
            if isco_code and isco_code[0].isdigit():
                occ_isco_major[oid] = isco_code[0]
    else:
        print(f"  [ATTENZIONE] {occupations_path} non trovato — accuracy settore non disponibile")

    random.seed(seed)
    sample = data if n is None else random.sample(data, min(n, len(data)))

    print(f"\n{'═'*65}")
    print(f"  VALUTAZIONE JOB PARSER  —  n={len(sample)} annunci")
    print(f"{'═'*65}\n")

    all_p, all_r, all_f1 = [], [], []
    occ_exact_hits, occ_sector_hits, occ_total = 0, 0, 0
    by_seniority: dict[str, dict] = {}
    skipped = 0

    for entry in sample:
        expected = entry.get("expected_skills", {})
        gt_skills = set(expected.get("required_ids", []) + expected.get("preferred_ids", []))

        skills_block = entry.get("skills", {})
        found_skills = set(skills_block.get("required_ids", []) + skills_block.get("preferred_ids", []))

        if not gt_skills and not found_skills:
            skipped += 1
            continue

        tp = len(found_skills & gt_skills)
        fp = len(found_skills - gt_skills)
        fn = len(gt_skills - found_skills)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)

        all_p.append(precision)
        all_r.append(recall)
        all_f1.append(f1)

        seniority = entry.get("meta", {}).get("seniority", "?")
        by_seniority.setdefault(seniority, {"prec": [], "rec": [], "f1": []})
        by_seniority[seniority]["prec"].append(precision)
        by_seniority[seniority]["rec"].append(recall)
        by_seniority[seniority]["f1"].append(f1)

        # ── Occupation ──────────────────────────────────────────────
        gt_occ_id      = entry.get("ground_truth", {}).get("target_occupation_id", "")
        gt_isco_maj    = entry.get("ground_truth", {}).get("isco_major", "")
        found_occ_id   = entry.get("occupation", {}).get("id", "")
        found_isco_maj = occ_isco_major.get(found_occ_id, "")

        if gt_occ_id:
            occ_total += 1
            if found_occ_id == gt_occ_id:
                occ_exact_hits += 1
            if found_isco_maj and found_isco_maj == str(gt_isco_maj):
                occ_sector_hits += 1

    if not all_p:
        print("  [Nessun annuncio valutabile]")
        return {}

    avg_p, avg_r = sum(all_p) / len(all_p), sum(all_r) / len(all_r)
    avg_f1 = sum(all_f1) / len(all_f1)
    occ_exact_acc  = occ_exact_hits  / occ_total if occ_total else 0.0
    occ_sector_acc = occ_sector_hits / occ_total if occ_total else 0.0

    print(f"  {'Metrica skill':<30} {'Valore':>8}")
    print(f"  {SEP}")
    print(f"  {'Precision':<30} {avg_p:>8.3f}")
    print(f"  {'Recall':<30} {avg_r:>8.3f}")
    print(f"  {'F1':<30} {avg_f1:>8.3f}")
    print(f"\n  {'Metrica occupation':<30} {'Valore':>8}")
    print(f"  {SEP}")
    print(f"  {'Accuracy esatta (ID ESCO)':<30} {occ_exact_acc:>8.3f}")
    print(f"  {'Accuracy settore (ISCO 1-digit)':<30} {occ_sector_acc:>8.3f}")

    print(f"\n  Per seniority:")
    per_sen_out = {}
    for sen, vals in sorted(by_seniority.items()):
        n_s = len(vals["f1"])
        mp = sum(vals["prec"]) / n_s
        mr = sum(vals["rec"])  / n_s
        mf = sum(vals["f1"])   / n_s
        per_sen_out[sen] = {"n": n_s, "precision": round(mp, 3), "recall": round(mr, 3), "f1": round(mf, 3)}
        print(f"    {sen:<10} (n={n_s:>3})  Prec={mp:.3f}  Rec={mr:.3f}  F1={mf:.3f}")

    if skipped:
        print(f"\n  [{skipped} annunci saltati: né ground truth né skill rilevate]")

    print(f"""
  INTERPRETAZIONE
  ───────────────
  Precision {avg_p:.2f} → delle skill rilevate dal parser, il {avg_p*100:.0f}% era corretto
  Recall    {avg_r:.2f} → delle skill realmente presenti,  il {avg_r*100:.0f}% è stato trovato
  Accuracy occupation esatta  {occ_exact_acc*100:.0f}%
  Accuracy occupation settore {occ_sector_acc*100:.0f}%  (più permissiva, stesso macro-settore ISCO)

  NOTA: valutazione per ID ESCO esatto — lower bound, vedi docstring.
""")

    result = {
        "n_annunci_valutati": len(all_p),
        "skill_precision":    round(avg_p, 3),
        "skill_recall":       round(avg_r, 3),
        "skill_f1":           round(avg_f1, 3),
        "occupation_accuracy_esatta":  round(occ_exact_acc, 3),
        "occupation_accuracy_settore": round(occ_sector_acc, 3),
        "per_seniority": per_sen_out,
        "skipped": skipped,
    }
    return result


def main():
    ap = argparse.ArgumentParser(description="SkillPath AI — Valutazione JobParser su ground truth ESCO")
    ap.add_argument("--n",    type=int, default=None, help="Campione di N annunci (default: tutti)")
    ap.add_argument("--seed", type=int, default=42,   help="Random seed per il campionamento")
    # Permette di valutare configurazioni diverse senza sovrascriverne i
    # risultati: ogni run di batch_parse_jobs_gt.py --out <file> va analizzata
    # con il corrispondente --in <file>.
    ap.add_argument("--in",  dest="in_file",  default=str(IN_FILE),
                    help="File di input prodotto da batch_parse_jobs_gt.py")
    ap.add_argument("--out", dest="out_file", default=str(OUT_FILE),
                    help="File JSON su cui salvare le metriche")
    args = ap.parse_args()

    result = evaluate(args.n, args.seed, Path(args.in_file))

    if result:
        with open(args.out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  [Risultati salvati in {args.out_file}]")


if __name__ == "__main__":
    main()
