"""
build_course_index.py  —  SkillPath AI
=======================================
Costruisce course_index.json: un dizionario
    { esco_skill_id → [lista corsi che insegnano quella skill] }

partendo dal dataset Coursera (CSV Kaggle).

Il mapping skill-tag → ESCO ID avviene tramite SemanticMapper,
lo stesso motore semantico già usato dal CV parser e dal job parser.

Uso (dalla radice del progetto):
    python src/build_course_index.py --csv config/Coursera.csv
    python src/build_course_index.py --csv config/Coursera.csv --threshold 0.78 --max 500
    python src/build_course_index.py --csv config/Coursera.csv --out config/my_index.json
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)
DATA_IT  = BASE_DIR / "dataset" / "source_it"
DATA_EN  = BASE_DIR / "dataset" / "source_en"
DATA_SRC = BASE_DIR / "dataset" / "source"
if not DATA_EN.exists():
    DATA_EN = DATA_SRC


# ── Costanti ──────────────────────────────────────────────────────────────────

# Soglia semantica per il mapping skill-tag → ESCO
# Leggermente più bassa del CV parser (0.82) per catturare
# termini tecnici espressi in modo diverso rispetto ai label ESCO
DEFAULT_THRESHOLD = 0.78

# Tag-categoria Coursera da ignorare (appaiono in fondo alla lista Skills)
# pattern: tutto minuscolo con trattini, >1 trattino → slug di categoria
_SLUG_CATEGORY_RE = re.compile(
    r"^(information-technology|data-science|computer-science|"
    r"business|business-strategy|physical-science-and-engineering|"
    r"arts-and-humanities|social-sciences|health|language-learning|"
    r"math-and-logic|personal-development|social-sciences)$",
    re.IGNORECASE,
)

# Livelli → normalizzazione
_LEVEL_MAP = {
    "beginner":       "beginner",
    "intermediate":   "intermediate",
    "advanced":       "advanced",
    "conversant":     "beginner",    # alias Coursera per beginner
    "not calibrated": "mixed",
}


# ── Funzioni di supporto ──────────────────────────────────────────────────────

def parse_skills(raw: str) -> list[str]:
    """
    Parsa il campo Skills di Coursera.
    Separatore: doppio spazio "  "
    Filtra: tag corti, slug di categoria, tag puri numerici.
    """
    tags = []
    for tag in raw.split("  "):
        tag = tag.strip()
        if not tag or len(tag) < 3:
            continue
        if _SLUG_CATEGORY_RE.match(tag):
            continue
        if tag.isdigit():
            continue
        tags.append(tag)
    return tags


def load_csv(path: Path, max_rows: int | None = None) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if max_rows and len(rows) >= max_rows:
                break
            rows.append(row)
    return rows


def normalize_level(raw: str) -> str:
    return _LEVEL_MAP.get(raw.strip().lower(), "mixed")


# ── Pipeline principale ───────────────────────────────────────────────────────

def build_index(
    csv_path:  Path,
    out_path:  Path,
    threshold: float = DEFAULT_THRESHOLD,
    max_rows:  int | None = None,
    verbose:   bool = True,
) -> dict:
    """
    Costruisce e salva course_index.json.
    Ritorna le statistiche di build.
    """

    # ── Carica CSV ────────────────────────────────────────────────────────────
    rows = load_csv(csv_path, max_rows)
    if verbose:
        print(f"[build_index] {len(rows)} corsi caricati da {csv_path.name}")

    # ── Inizializza SemanticMapper con indice bilingue ────────────────────────
    sys.path.insert(0, str(BASE_DIR))
    from semantic_mapper import SemanticMapper
    mapper = SemanticMapper()

    if (DATA_IT / "skills.json").exists() and (DATA_EN / "skills.json").exists():
        if verbose:
            print("[build_index] Carico indice bilingue IT+EN...")
        mapper.load_databases_bilingual(
            str(DATA_IT / "skills.json"),
            str(DATA_EN / "skills.json"),
        )
    else:
        if verbose:
            print("[build_index] Carico indice EN (source/skills.json)...")
        mapper.load_database(str(DATA_SRC / "skills.json"))

    # ── Raccogli tutti i tag unici + mappa corso → tag ────────────────────────
    # Per efficienza: codifichiamo tutti i tag unici una sola volta,
    # poi ricostruiamo il mapping corso → ESCO ID
    tag_to_courses: dict[str, list[dict]] = defaultdict(list)

    total_tags = 0
    for row in rows:
        skills_raw = row.get("Skills", "").strip()
        if not skills_raw:
            continue
        tags = parse_skills(skills_raw)
        total_tags += len(tags)
        course_entry = {
            "title":    row["Course Name"].strip(),
            "platform": "Coursera",
            "url":      row.get("Course URL", "").strip(),
            "level":    normalize_level(row.get("Difficulty Level", "")),
            "rating":   _safe_float(row.get("Course Rating", "0")),
            "provider": row.get("University", "").strip(),
        }
        for tag in tags:
            tag_to_courses[tag].append(course_entry)

    unique_tags = list(tag_to_courses.keys())
    if verbose:
        print(f"[build_index] Tag unici da mappare: {len(unique_tags)}  "
              f"(totale tag: {total_tags})")

    # ── Mapping semantico tag → ESCO in batch ────────────────────────────────
    if verbose:
        print(f"[build_index] Mapping semantico  (threshold={threshold})...")

    t0 = time.time()
    # Batch: all unique tags in one call for efficiency
    # find_matches prende una lista e restituisce i top match per ogni elemento
    # NB: l'ordine di ritorno potrebbe non corrispondere all'input → usiamo ID
    matches = mapper.find_matches(
        unique_tags,
        threshold=threshold,
        top_k=1,
        max_results=len(unique_tags),
        return_scores=True,
    )
    elapsed = time.time() - t0
    if verbose:
        print(f"[build_index] Mapping completato in {elapsed:.1f}s  "
              f"→ {len(matches)} match ESCO trovati")

    # Costruiamo il dizionario id → label per il lookup inverso
    # matches è una lista di {id, label, score}
    # ma non sappiamo QUALE tag ha prodotto quale match (find_matches non
    # restituisce il query token di origine).
    # Soluzione: mappiamo label_ESCO → tag_originale via ricerca per label
    # oppure usiamo find_matches per ogni tag (più lento ma preciso).
    # Per il dataset Coursera usiamo l'approccio preciso.

    if verbose:
        print("[build_index] Mapping preciso tag → ESCO ID...")

    # Chunk processing per evitare memory issues
    CHUNK = 500
    tag_to_esco: dict[str, list[dict]] = {}   # tag → [{id, label, score}]

    for i in range(0, len(unique_tags), CHUNK):
        chunk = unique_tags[i : i + CHUNK]
        for tag in chunk:
            m = mapper.find_matches(
                [tag],
                threshold=threshold,
                top_k=1,
                max_results=1,
                return_scores=True,
            )
            if m:
                tag_to_esco[tag] = m[0]   # {id, label, score}

        if verbose and (i + CHUNK) % 2000 == 0:
            pct = min(i + CHUNK, len(unique_tags)) / len(unique_tags) * 100
            print(f"  {pct:.0f}%  ({min(i+CHUNK, len(unique_tags))}/{len(unique_tags)} tag)")

    matched_tags = len(tag_to_esco)
    if verbose:
        print(f"[build_index] Tag mappati su ESCO: {matched_tags} / {len(unique_tags)}")

    # ── Costruisce indice finale ──────────────────────────────────────────────
    # esco_id → lista corsi (deduplicati per URL, ordinati per rating desc)
    index: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)  # esco_id → set di URL già inseriti

    for tag, esco_match in tag_to_esco.items():
        esco_id = esco_match["id"]
        for course in tag_to_courses[tag]:
            url = course["url"]
            if url not in seen[esco_id]:
                seen[esco_id].add(url)
                # Arricchisci il corso con il match info
                entry = {**course, "matched_via_tag": tag,
                         "esco_match_score": round(esco_match["score"], 3)}
                index[esco_id].append(entry)

    # Ordina i corsi per rating decrescente in ogni bucket ESCO
    for esco_id in index:
        index[esco_id].sort(key=lambda c: c["rating"], reverse=True)

    # ── Salva JSON ────────────────────────────────────────────────────────────
    index_plain = dict(index)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index_plain, f, indent=2, ensure_ascii=False)

    # ── Statistiche ───────────────────────────────────────────────────────────
    n_skill_ids  = len(index)
    n_entries    = sum(len(v) for v in index.values())
    avg_per_skill = n_entries / n_skill_ids if n_skill_ids else 0
    top_skills = sorted(index.items(), key=lambda x: len(x[1]), reverse=True)[:5]

    stats = {
        "corsi_input":          len(rows),
        "tag_unici":            len(unique_tags),
        "tag_mappati_esco":     matched_tags,
        "skill_esco_coperte":   n_skill_ids,
        "corsi_nell_indice":    n_entries,
        "media_corsi_per_skill": round(avg_per_skill, 1),
        "top_skill_coperte": [
            {"id": sid, "n_corsi": len(cs), "esempio": cs[0]["title"][:50]}
            for sid, cs in top_skills
        ],
    }

    if verbose:
        print(f"\n{'═'*55}")
        print(f"  Course index costruito con successo")
        print(f"{'═'*55}")
        print(f"  Corsi input:            {stats['corsi_input']}")
        print(f"  Tag unici elaborati:    {stats['tag_unici']}")
        print(f"  Tag mappati su ESCO:    {stats['tag_mappati_esco']}")
        print(f"  Skill ESCO coperte:     {stats['skill_esco_coperte']}")
        print(f"  Corsi nell'indice:      {stats['corsi_nell_indice']}")
        print(f"  Media corsi/skill:      {stats['media_corsi_per_skill']}")
        print(f"  Top skill coperte:")
        for s in stats["top_skill_coperte"]:
            print(f"    {s['n_corsi']:>3} corsi  {s['esempio']}")
        print(f"\n  → {out_path}")
        print(f"{'═'*55}")

    return stats


def _safe_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Build course index da Coursera CSV")
    ap.add_argument("--csv",       default="config/Coursera.csv",
                    help="Path al CSV Coursera (default: config/Coursera.csv)")
    ap.add_argument("--out",       default="config/course_index.json",
                    help="File output JSON (default: config/course_index.json)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"Soglia semantica ESCO (default: {DEFAULT_THRESHOLD})")
    ap.add_argument("--max",       type=int, default=None,
                    help="Limita a N corsi (test rapido)")
    args = ap.parse_args()

    csv_path = Path(args.csv) if Path(args.csv).is_absolute() else BASE_DIR / args.csv
    out_path = Path(args.out) if Path(args.out).is_absolute() else BASE_DIR / args.out

    if not csv_path.exists():
        print(f"[build_index] ERRORE: file non trovato: {csv_path}")
        sys.exit(1)

    build_index(csv_path, out_path, args.threshold, args.max)


if __name__ == "__main__":
    main()
