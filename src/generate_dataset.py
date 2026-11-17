"""
SkillPath AI — generate_dataset.py
Seleziona occupation rappresentative per macro-settore ISCO
e genera CV sintetici con skill già mappate su ID ESCO tramite LLM.

Uso:
    python src/generate_dataset.py --dataset ./dataset --output ./dataset/synthetic

    # Solo selezione occupation (senza generare CV):
    python src/generate_dataset.py --dataset ./dataset --select-only

    # Riprendi da dove ti sei fermato (skip CV già generati):
    python src/generate_dataset.py --dataset ./dataset --resume

    # Genera solo per un settore ISCO specifico:
    python src/generate_dataset.py --dataset ./dataset --sector 2

Output:
    dataset/synthetic/selected_occupations.json   ← 135 occupation selezionate
    dataset/synthetic/cvs.json                    ← tutti i CV generati
    dataset/synthetic/generation_log.json         ← log errori e stats
"""

import json
import argparse
import time
import random
import re
import os
from pathlib import Path
from collections import defaultdict
import requests
from dotenv import load_dotenv

load_dotenv()


# ─── Config ─────────────────────────────────────────────────────────────────

OCC_PER_SECTOR = 15
CVS_PER_OCC    = 6
SENIORITY_DIST = [
    ("junior", 2),
    ("mid",    2),
    ("senior", 2),
]
SENIORITY_YEARS = {
    "junior": (0, 2),
    "mid":    (3, 5),
    "senior": (6, 12),
}
# Vincoli skill coverage per seniority
COVERAGE_RANGE = {
    "junior": (0.35, 0.55),
    "mid":    (0.55, 0.75),
    "senior": (0.75, 0.92),
}
# Vincoli numero certificazioni per seniority
CERT_COUNT = {
    "junior": (0, 1),
    "mid":    (1, 2),
    "senior": (2, 3),
}
# Massimo livello CEFR per lingue straniere per seniority
MAX_FOREIGN_CEFR = {
    "junior": "B2",
    "mid":    "C1",
    "senior": "C2",
}

# ─── Config API Groq ─────────────────────────────────────────────────────────
MODEL   = "llama-3.3-70b-versatile"
API_KEY = os.getenv("GROQ_API_KEY")
API_URL = "https://api.groq.com/openai/v1/chat/completions"

ISCO_MAJOR_LABELS = {
    "1": "Managers",
    "2": "Professionals",
    "3": "Technicians and associate professionals",
    "4": "Clerical support workers",
    "5": "Service and sales workers",
    "6": "Skilled agricultural, forestry and fishery workers",
    "7": "Craft and related trades workers",
    "8": "Plant and machine operators and assemblers",
    "9": "Elementary occupations",
}

# Mapping nazionalità → codice lingua madre
NATIONALITY_MOTHER_TONGUE = {
    "Italian":    "it",
    "German":     "de",
    "French":     "fr",
    "Spanish":    "es",
    "Polish":     "pl",
    "Dutch":      "nl",
    "Portuguese": "pt",
    "Belgian":    "fr",
    "Romanian":   None,
    "Swedish":    None,
}

NATIONALITIES = list(NATIONALITY_MOTHER_TONGUE.keys())

FIRST_NAMES = [
    "Marco", "Laura", "Thomas", "Sophie", "Jan", "Maria", "Luca",
    "Emma", "Piotr", "Giulia", "Hans", "Isabelle", "Carlos", "Anna",
    "David", "Elena", "Mikael", "Fatima", "Roberto", "Claire",
]
LAST_NAMES = [
    "Rossi", "Müller", "Dupont", "García", "Kowalski", "De Vries",
    "Ionescu", "Lindgren", "Silva", "Martin", "Schmidt", "Fernández",
    "Nowak", "Conti", "Eriksson", "Bianchi", "Dubois", "Russo",
    "Weber", "Moreau",
]


# ─── Carica dizionari supplementari ─────────────────────────────────────────

def load_supplementary(dataset_dir: Path) -> dict:
    supp_dir = dataset_dir / "supplementary"
    with open(supp_dir / "language_levels.json", encoding="utf-8") as f:
        lang_data = json.load(f)
    with open(supp_dir / "degree_programs.json", encoding="utf-8") as f:
        deg_data = json.load(f)
    with open(supp_dir / "certifications.json", encoding="utf-8") as f:
        cert_data = json.load(f)
    with open(supp_dir / "companies.json", encoding="utf-8") as f:
        co_data = json.load(f)
    return {
        "languages": lang_data,
        "degrees":   deg_data,
        "certs":     cert_data,
        "companies": co_data,
    }


# ─── Helpers dizionari ───────────────────────────────────────────────────────

def get_degrees_for_isco(deg_data: dict, isco_major: str, seniority: str) -> list[dict]:
    """Filtra i corsi di laurea pertinenti per settore ISCO e seniority."""
    cycles_allowed = {
        "junior": ["secondario", "terziario_non_uni", "triennale", "magistrale"],
        "mid":    ["triennale", "magistrale", "ciclo_unico"],
        "senior": ["magistrale", "ciclo_unico", "dottorato"],
    }
    allowed = cycles_allowed[seniority]
    return [
        p for p in deg_data["programs"].values()
        if isco_major in (p.get("isco_relevant") or [])
        and p.get("cycle") in allowed
    ]


def get_certs_for_isco(cert_data: dict, isco_major: str, occ_label: str = "") -> list[dict]:
    """
    Filtra le certificazioni pertinenti per settore ISCO e tipo di occupation.
    Evita di proporre cert cloud/tech a ruoli come avvocato, diplomatico, ecc.
    """
    # Ruoli non-tech: escludi certificazioni tech anche se ISCO 2
    NON_TECH_KEYWORDS = [
        "lawyer", "legal", "judge", "notary", "diplomat", "relations officer",
        "social worker", "psychologist", "teacher", "professor", "nurse",
        "doctor", "physician", "pharmacist", "veterinarian", "archaeologist",
        "historian", "journalist", "librarian", "curator", "translator",
        "interpreter", "economist", "accountant", "auditor", "tax", "finance",
        "explosives", "geologist", "biologist", "chemist", "physicist",
        "agronomist", "forester", "zoologist", "ecologist", "anthropologist",
    ]
    occ_lower = occ_label.lower()
    is_non_tech = any(kw in occ_lower for kw in NON_TECH_KEYWORDS)

    results = []
    for c in cert_data["certifications"].values():
        if isco_major not in (c.get("isco_relevant") or []):
            continue
        # Per ruoli non-tech escludi le cert di area tech
        if is_non_tech and c.get("area") == "tech":
            continue
        results.append(c)

    return results


# ─── Selezione Occupation ────────────────────────────────────────────────────

def select_occupations(
    occupations: dict,
    relations:   dict,
    n_per_sector: int = OCC_PER_SECTOR,
    seed: int = 42,
) -> dict[str, list[dict]]:
    random.seed(seed)
    by_major: dict[str, list] = defaultdict(list)

    for oid, occ in occupations.items():
        isco_code = occ.get("isco_code") or ""
        major = isco_code[0] if isco_code and isco_code[0].isdigit() else None
        if not major or major == "0":
            continue
        essential = relations.get(oid, {}).get("essential", [])
        if len(essential) < 10:
            continue
        by_major[major].append({
            "id":               oid,
            "label":            occ["label"],
            "isco_major":       major,
            "isco_major_label": ISCO_MAJOR_LABELS.get(major, ""),
            "isco_code":        isco_code,
            "n_essential":      len(essential),
            "n_optional":       len(relations.get(oid, {}).get("optional", [])),
        })

    selected: dict[str, list[dict]] = {}
    total = 0
    for major in sorted(by_major.keys()):
        pool        = by_major[major]
        pool_sorted = sorted(pool, key=lambda x: x["n_essential"])
        step        = max(1, len(pool_sorted) // n_per_sector)
        picked      = [pool_sorted[i] for i in range(0, len(pool_sorted), step)][:n_per_sector]
        if len(picked) < n_per_sector:
            remaining = [o for o in pool if o not in picked]
            random.shuffle(remaining)
            picked += remaining[:n_per_sector - len(picked)]
        selected[major] = picked
        total += len(picked)
        print(f"  ISCO {major} — {ISCO_MAJOR_LABELS[major]:<45} → {len(picked)} occupation selezionate")

    print(f"\n  Totale selezionate: {total}")
    return selected


# ─── Negative Samples ────────────────────────────────────────────────────────

def pick_negative_samples(occ: dict, selected: dict, n: int = 2) -> list[dict]:
    """
    Seleziona N occupation distanti come negative samples.
    Sceglie da settori ISCO diversi per massimizzare la distanza semantica.
    """
    negatives = []
    other_majors = [m for m in selected.keys() if m != occ["isco_major"]]
    random.shuffle(other_majors)
    for major in other_majors[:n]:
        pool = selected[major]
        if pool:
            neg = random.choice(pool)
            negatives.append({
                "occupation_id":  neg["id"],
                "label":          neg["label"],
                "isco_major":     major,
                "expected_score": round(random.uniform(0.04, 0.18), 2),
            })
    return negatives


# Progressione seniority per work experience
SENIORITY_PROGRESSION = {
    "junior": ["junior"],
    "mid":    ["junior", "mid"],
    "senior": ["junior", "mid", "senior"],
}

# Job title suffixes per seniority
TITLE_PREFIX = {
    "junior":    ["Junior", "Associate", "Trainee"],
    "mid":       ["", "Senior", "Lead"],
    "senior":    ["Senior", "Lead", "Principal", "Head of"],
    "executive": ["Director of", "VP of", "Chief", "Head of"],
}


def build_work_experience(
    occ:         dict,
    seniority:   str,
    years_total: int,
    essential_skills: list[dict],
    co_data:     dict,
) -> list[dict]:
    """
    Genera la work experience coerente con seniority e anni totali.
    - junior:  1 esperienza
    - mid:     2 esperienze (junior → mid)
    - senior:  3 esperienze (junior → mid → senior)
    La somma degli anni combacia con years_total.
    """
    progression  = SENIORITY_PROGRESSION[seniority]
    n_exp        = len(progression)
    isco_major   = occ["isco_major"]

    # Pool aziende per questo settore
    sector_co_ids = co_data["by_sector"].get(isco_major, list(co_data["companies"].keys()))
    co_pool       = [co_data["companies"][cid] for cid in sector_co_ids if cid in co_data["companies"]]
    random.shuffle(co_pool)

    # Distribuisci gli anni tra le esperienze
    if n_exp == 1:
        years_per_exp = [max(1, years_total)]
    elif n_exp == 2:
        y1 = max(1, random.randint(1, max(1, years_total - 1)))
        years_per_exp = [y1, max(1, years_total - y1)]
    else:  # 3 esperienze
        y1 = max(1, random.randint(1, max(1, years_total - 2)))
        y2 = max(1, random.randint(1, max(1, years_total - y1 - 1)))
        years_per_exp = [y1, y2, max(1, years_total - y1 - y2)]

    # Subset skill per esperienza: più skill nelle esperienze recenti
    all_skill_ids = [s["id"] for s in essential_skills]
    n_skills      = len(all_skill_ids)

    experiences = []
    for i, (exp_seniority, years) in enumerate(zip(progression, years_per_exp)):
        company = co_pool[i % len(co_pool)]

        # Titolo job: prefisso + label occupation
        prefix    = random.choice(TITLE_PREFIX[exp_seniority])
        job_title = f"{prefix} {occ['label']}".strip()

        # Skill subset: cresce con il livello
        coverage_by_level = {"junior": 0.35, "mid": 0.60, "senior": 0.85}
        n_s  = max(1, int(n_skills * coverage_by_level[exp_seniority]))
        # Esperienze più recenti (indice più alto) prendono le skill più avanzate
        start = max(0, n_skills - n_s - i * 2)
        skill_subset = all_skill_ids[start: start + n_s]

        experiences.append({
            "company":   company["name"],
            "country":   company["country"],
            "real":      company["real"],
            "job_title": job_title,
            "years":     max(1, years),
            "seniority": exp_seniority,
            "skill_ids": skill_subset,
        })

    return experiences


# ─── Prompt Builder ──────────────────────────────────────────────────────────

def build_cv_prompt(
    occ:             dict,
    essential_skills: list[dict],
    optional_skills:  list[dict],
    seniority:        str,
    years_exp:        int,
    persona_name:     str,
    nationality:      str,
    degrees:          list[dict],
    certs:            list[dict],
    lang_data:        dict,
) -> str:
    ess_list  = "\n".join(f'  - [{s["id"]}] {s["label"]}' for s in essential_skills)
    opt_list  = "\n".join(f'  - [{s["id"]}] {s["label"]}' for s in optional_skills[:15])
    # Mostra 8 lauree con distribuzione bilanciata per area disciplinare
    deg_sample = []
    by_area: dict = {}
    for d in degrees:
        by_area.setdefault(d.get("area", "Generale"), []).append(d)
    for area_pool in by_area.values():
        random.shuffle(area_pool)
        deg_sample.append(area_pool[0])   # almeno 1 per area
    random.shuffle(deg_sample)
    deg_sample = deg_sample[:8]
    if not deg_sample:
        deg_sample = degrees[:8]

    deg_list  = "\n".join(
        f'  - [{d["id"]}] {d["label"]} ({d["class"] or d["cycle"]})'
        for d in deg_sample
    ) or "  - [deg_none] No university degree"
    cert_list = "\n".join(
        f'  - [{c["id"]}] {c["label"]}'
        for c in certs[:10]
    ) or "  - (none relevant for this sector)"

    # Lingue straniere disponibili: solo le 6 principali, esclusa madre lingua
    mt_code = NATIONALITY_MOTHER_TONGUE.get(nationality)
    foreign_entries = [
        e for e in lang_data["entries"].values()
        if e["language_code"] != mt_code
        and e["cefr_code"] != "native"
        and e["cefr_code"] in ["A2", "B1", "B2", "C1", "C2"]
        and e["language_code"] in ["en", "fr", "de", "es", "zh", "pt"]
    ]
    lang_sample = random.sample(foreign_entries, min(6, len(foreign_entries)))
    lang_list   = "\n".join(
        f'  - [{e["id"]}] {e["language_label"]} {e["cefr_code"]}'
        for e in lang_sample
    )

    # Entry lingua madre da iniettare direttamente nel JSON template
    mt_entry_id = f"lang_{mt_code}_native" if mt_code else None
    mt_entry    = lang_data["entries"].get(mt_entry_id) if mt_entry_id else None
    if mt_entry:
        mother_tongue_json = json.dumps({
            "lang_id":        mt_entry["id"],
            "language":       mt_entry["language_label"],
            "cefr":           "native",
            "certifications": []
        }, ensure_ascii=False)
    else:
        mother_tongue_json = json.dumps({
            "lang_id":        "lang_unknown_native",
            "language":       nationality,
            "cefr":           "native",
            "certifications": []
        }, ensure_ascii=False)

    cov_min, cov_max = COVERAGE_RANGE[seniority]
    cert_min, cert_max = CERT_COUNT[seniority]
    max_cefr = MAX_FOREIGN_CEFR[seniority]
    n_exp = len(SENIORITY_PROGRESSION[seniority])

    return f"""You are generating a synthetic European CV for the SkillPath AI training dataset.

OCCUPATION TARGET: {occ['label']} (ISCO {occ['isco_code']}, sector: {occ['isco_major_label']})
CANDIDATE: {persona_name}, {nationality}, {seniority} level, {years_exp} years of experience
WORK HISTORY: {n_exp} position(s), progressing from junior to {seniority} level

─── AVAILABLE ESSENTIAL SKILLS (ESCO IDs) ───
{ess_list}

─── AVAILABLE OPTIONAL SKILLS (ESCO IDs, sample) ───
{opt_list}

─── AVAILABLE DEGREE PROGRAMS ───
{deg_list}

─── AVAILABLE CERTIFICATIONS (sector-relevant) ───
{cert_list}

─── AVAILABLE FOREIGN LANGUAGES ───
{lang_list}

─── STRICT RULES ───

RULE 1 - SKILL COVERAGE:
  Pick essential_ids so that len(essential_ids) / {len(essential_skills)} is between {cov_min:.2f} and {cov_max:.2f}.
  That means pick EXACTLY between {max(1, int(len(essential_skills)*cov_min))} and {min(len(essential_skills)-1, int(len(essential_skills)*cov_max))} essential IDs.
  NEVER pick all {len(essential_skills)} essential IDs — always leave at least one out.
  For senior level this means a coverage of max {cov_max:.0%}, NOT 100%.

RULE 2 - EDUCATION:
  degree_id MUST be one of the IDs from the list above.
  "cycle" MUST be EXACTLY one of: triennale, magistrale, ciclo_unico, dottorato, secondario, terziario_non_uni
  The degree must be COHERENT with the occupation "{occ['label']}":
    - lawyer/legal → Giurisprudenza (deg_lmcu22)
    - software/ICT → Informatica or Ingegneria Informatica
    - economist/finance → Scienze Economiche or Finanza
    - engineer → Ingegneria (most relevant branch in the list)
    - teacher/educator → Scienze dell Educazione or Formazione Primaria
    - biologist/chemist → Biologia or Chimica
    - If uncertain, pick the closest available degree.

RULE 3 - CERTIFICATIONS:
  Pick {cert_min}-{cert_max} certifications ONLY from the list above.
  They MUST be coherent with "{occ['label']}".
  NEVER assign AWS, Azure, GCP, Cisco, or CCNA certifications to non-technical roles
  (lawyer, diplomat, social worker, teacher, relations officer, biologist, geologist, explosives engineer).
  If no relevant certification exists in the list, output: []

RULE 4 - LANGUAGES:
  languages[0] = mother tongue (fixed below, do not change).
  Add 1-2 foreign languages from the list. Max CEFR level: {max_cefr}.

RULE 5 - ALL IDs must come ONLY from the lists above. Never invent IDs.

RULE 6 - RAW TEXT: 2-4 prose paragraphs. Mention actual company names. Do not list IDs.

─── OUTPUT FORMAT ───
Respond ONLY with valid JSON. No markdown, no explanation, no extra keys.

{{
  "cv": {{
    "persona": {{
      "name": "{persona_name}",
      "nationality": "{nationality}",
      "years_experience": {years_exp},
      "seniority": "{seniority}"
    }},
    "education": {{
      "degree_id": "<id from degree list>",
      "label": "<exact label from degree list>",
      "class": "<class from degree list or null>",
      "cycle": "<EXACTLY one of: triennale, magistrale, ciclo_unico, dottorato, secondario, terziario_non_uni>",
      "area": "<area from degree list>"
    }},
    "languages": [
      {mother_tongue_json},
      {{"lang_id": "<id from language list>", "language": "<n>", "cefr": "<level, max {max_cefr}>", "certifications": []}}
    ],
    "certifications": [
      {{"cert_id": "<id from cert list>", "label": "<exact label from cert list>"}}
    ],
    "skills": {{
      "essential_ids": ["<id>", "..."],
      "optional_ids":  ["<id>", "..."]
    }},
    "raw_text": "<natural prose CV text here>"
  }},
  "ground_truth": {{
    "target_occupation_id":    "{occ['id']}",
    "target_occupation_label": "{occ['label']}",
    "isco_code":               "{occ['isco_code']}",
    "isco_major":              "{occ['isco_major']}",
    "skill_coverage":          0.0
  }}
}}"""


# ─── Validazione e Arricchimento ─────────────────────────────────────────────

def validate_and_enrich(
    raw:              dict,
    essential_ids:    set,
    optional_ids:     set,
    valid_deg_ids:    set,
    valid_cert_ids:   set,
    valid_lang_ids:   set,
    occ:              dict,
    negative_samples: list[dict],
) -> dict:
    """
    Valida tutti i campi del CV generato:
    - Rimuove ID non validi da skill, degree, cert, lang
    - Ricalcola skill_coverage sulla ground truth
    - Inietta i negative_samples nel ground_truth
    """
    cv = raw.get("cv", {})
    gt = raw.get("ground_truth", {})

    # ── Skills ──────────────────────────────────────────────────
    raw_ess   = set(cv.get("skills", {}).get("essential_ids", []))
    raw_opt   = set(cv.get("skills", {}).get("optional_ids",  []))
    valid_ess = list(raw_ess & essential_ids)
    valid_opt = list(raw_opt & optional_ids)
    cv.setdefault("skills", {})
    cv["skills"]["essential_ids"] = valid_ess
    cv["skills"]["optional_ids"]  = valid_opt

    # ── Education ───────────────────────────────────────────────
    edu = cv.get("education", {})
    if edu.get("degree_id") not in valid_deg_ids:
        edu = {"degree_id": "deg_none", "label": "Nessun titolo universitario",
               "class": None, "cycle": None, "area": None}
    else:
        # Normalizza il campo cycle se il modello ha usato valori liberi
        CYCLE_MAP = {
            "first": "triennale", "first cycle": "triennale", "1st cycle": "triennale",
            "second": "magistrale", "second cycle": "magistrale", "2nd cycle": "magistrale",
            "third": "dottorato", "third cycle": "dottorato", "3rd cycle": "dottorato",
            "bachelor": "triennale", "master": "magistrale", "phd": "dottorato",
            "undergraduate": "triennale", "graduate": "magistrale", "postgraduate": "dottorato",
        }
        VALID_CYCLES = {"triennale","magistrale","ciclo_unico","dottorato","secondario","terziario_non_uni"}
        raw_cycle = (edu.get("cycle") or "").lower().strip()
        if raw_cycle not in VALID_CYCLES:
            edu["cycle"] = CYCLE_MAP.get(raw_cycle, "magistrale")  # fallback magistrale
    cv["education"] = edu

    # ── Certifications ───────────────────────────────────────────
    raw_certs = cv.get("certifications", [])
    cv["certifications"] = [c for c in raw_certs if c.get("cert_id") in valid_cert_ids]

    # ── Languages ────────────────────────────────────────────────
    # Mantieni lingua madre (cefr=native) + lingue con ID valido
    #cv["languages"] = [
    #    l for l in cv.get("languages", [])
    #    if l.get("cefr") == "native" or l.get("lang_id") in valid_lang_ids
   # ]
   # ── Languages (con Patch Seniority) ──────────────────────────
    raw_langs = cv.get("languages", [])
    seniority = cv.get("persona", {}).get("seniority")
    
    clean_langs = []
    for l in raw_langs:
        l_id = l.get("lang_id")
        # Patch: Forza inglese almeno B1 per i Senior
        if seniority == "senior" and l_id in ["lang_en_a1", "lang_en_a2"]:
            l["lang_id"] = "lang_en_b1"
            l["cefr"] = "B1"
            l["language"] = "English"
            l_id = "lang_en_b1"
        
        # Mantieni solo se nativo o se ID presente nel dizionario
        if l.get("cefr") == "native" or l_id in valid_lang_ids:
            clean_langs.append(l)
            
    cv["languages"] = clean_langs

    # ── Ricalcola skill_coverage ─────────────────────────────────
    coverage = len(valid_ess) / len(essential_ids) if essential_ids else 0.0
    gt["skill_coverage"]          = round(coverage, 4)
    gt["target_occupation_id"]    = occ["id"]
    gt["target_occupation_label"] = occ["label"]
    gt["isco_code"]               = occ["isco_code"]
    gt["isco_major"]              = occ["isco_major"]
    gt["negative_samples"]        = negative_samples

    # ── Validation report ────────────────────────────────────────
    raw["_validation"] = {
        "essential_removed": len(raw_ess - essential_ids),
        "optional_removed":  len(raw_opt - optional_ids),
        "certs_removed":     len(raw_certs) - len(cv["certifications"]),
        "langs_kept":        len(cv["languages"]),
    }

    raw["cv"]           = cv
    raw["ground_truth"] = gt
    return raw


# ─── LLM Call ────────────────────────────────────────────────────────────────

def call_llm(prompt: str, max_retries: int = 3) -> dict | None:
    if not API_KEY:
        print("❌ GROQ_API_KEY non trovata nel file .env")
        return None

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model":           MODEL,
                    "messages":        [{"role": "user", "content": prompt}],
                    "temperature":     0.6,
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
            resp.raise_for_status()
            return json.loads(resp.json()["choices"][0]["message"]["content"])

        except requests.RequestException as e:
            try:
                err_body = e.response.json()
                err_msg  = err_body.get("error", {}).get("message", "")
                import re as _re
                match = _re.search(r"try again in ([\d.]+)s", err_msg)
                # Dev Tier: rispetta il retry-after di Groq + 1s di margine
                wait = float(match.group(1)) + 1.0 if match else 5.0
                print(f"      ⚠ Rate limit (tentativo {attempt+1}/{max_retries}), attendo {wait:.1f}s...")
            except Exception:
                wait = 60.0
                print(f"      ⚠ API error (tentativo {attempt+1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(wait)
    return None

# ─── Generazione CV per occupation ───────────────────────────────────────────

def generate_cvs_for_occupation(
    occ:             dict,
    profile:         dict,
    selected:        dict,
    supplementary:   dict,
    existing_cv_ids: set,
) -> list[dict]:
    cvs              = []
    essential_skills = profile.get("essential_skills", [])
    optional_skills  = profile.get("optional_skills",  [])
    essential_ids    = {s["id"] for s in essential_skills}
    optional_ids     = {s["id"] for s in optional_skills}

    lang_data = supplementary["languages"]
    deg_data  = supplementary["degrees"]
    cert_data = supplementary["certs"]
    co_data   = supplementary["companies"]

    valid_deg_ids  = set(deg_data["programs"].keys())
    valid_cert_ids = set(cert_data["certifications"].keys())
    valid_lang_ids = set(lang_data["entries"].keys())

    # Negative samples condivisi per tutti i CV di questa occupation
    negative_samples = pick_negative_samples(occ, selected)

    for seniority, count in SENIORITY_DIST:
        for i in range(count):
            cv_id = f"cv_{occ['id']}_{seniority}_{i}"
            if cv_id in existing_cv_ids:
                print(f"      ↷ Skip: {cv_id}")
                continue

            years_min, years_max = SENIORITY_YEARS[seniority]
            years_exp    = random.randint(years_min, years_max)
            persona_name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            nationality  = random.choice(NATIONALITIES)

            degrees = get_degrees_for_isco(deg_data, occ["isco_major"], seniority)
            certs   = get_certs_for_isco(cert_data, occ["isco_major"], occ["label"])

            # Genera work experience deterministicamente
            work_experience = build_work_experience(
                occ, seniority, years_exp, essential_skills, co_data
            )

            prompt = build_cv_prompt(
                occ, essential_skills, optional_skills,
                seniority, years_exp, persona_name, nationality,
                degrees, certs, lang_data,
            )

            print(f"      [{seniority}] {persona_name} ({nationality}, {years_exp}y)...", end=" ", flush=True)
            raw = call_llm(prompt)

            if raw is None:
                print("✗ FAIL")
                # Breve pausa dopo fail prima di riprovare
                time.sleep(5) 
                continue

            enriched = validate_and_enrich(
                raw, essential_ids, optional_ids,
                valid_deg_ids, valid_cert_ids, valid_lang_ids,
                occ, negative_samples,
            )

            enriched["cv"]["work_experience"] = work_experience
            enriched["cv_id"]        = cv_id
            enriched["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            v        = enriched["_validation"]
            coverage = enriched["ground_truth"]["skill_coverage"]
            n_exp    = len(work_experience)
            
            print(f"✓  cov={coverage:.0%}  exp={n_exp}  ess_removed={v['essential_removed']}  certs_removed={v['certs_removed']}  langs={v['langs_kept']}")

            cvs.append(enriched)
            
            # Dev Tier: 300k TPM, sleep minimo sufficiente
            time.sleep(2) 

    return cvs


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SkillPath AI — CV Generator")
    parser.add_argument("--dataset",     default="./dataset",           help="Cartella dataset JSON")
    parser.add_argument("--output",      default="./dataset/synthetic",  help="Cartella output")
    parser.add_argument("--select-only", action="store_true",            help="Solo selezione, no generazione")
    parser.add_argument("--resume",      action="store_true",            help="Riprendi da dove interrotto")
    parser.add_argument("--sector",      default=None,                   help="Solo settore ISCO (es. '2')")
    parser.add_argument("--seed",        type=int, default=42,           help="Random seed")
    args = parser.parse_args()

    out_dir     = Path(args.output)
    dataset_dir = Path(args.dataset)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "═" * 60)
    print("  SkillPath AI — CV Generator")
    print("═" * 60)

    # ── Carica dataset ────────────────────────────────────────────
    print("\n● Carico dataset...")
    with open(dataset_dir / "source/occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)
    with open(dataset_dir / "source/occupation_skill_relations.json", encoding="utf-8") as f:
        relations = json.load(f)
    with open(dataset_dir / "materialized/occupation_profiles.json", encoding="utf-8") as f:
        profiles = {p["id"]: p for p in json.load(f)}
    supplementary = load_supplementary(dataset_dir)
    print(f"  {len(occupations):,} occupation | {len(profiles):,} profili | dizionari supplementari caricati")

    # ── Selezione occupation ──────────────────────────────────────
    sel_path = out_dir / "selected_occupations.json"
    if sel_path.exists() and args.resume:
        print("\n● Carico selezione esistente...")
        with open(sel_path, encoding="utf-8") as f:
            selected = json.load(f)
    else:
        print("\n● Selezione occupation rappresentative...")
        selected = select_occupations(occupations, relations, OCC_PER_SECTOR, args.seed)
        with open(sel_path, "w", encoding="utf-8") as f:
            json.dump(selected, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Salvato: {sel_path}")

    if args.select_only:
        print("\n  --select-only attivo, stop.")
        return

    # ── Carica CV esistenti se --resume ──────────────────────────
    cvs_path = out_dir / "cvs.json"
    all_cvs: list[dict] = []
    existing_cv_ids: set = set()

    if cvs_path.exists() and args.resume:
        with open(cvs_path, encoding="utf-8") as f:
            all_cvs = json.load(f)
        existing_cv_ids = {cv["cv_id"] for cv in all_cvs}
        print(f"\n● Resume: {len(all_cvs)} CV già esistenti trovati")

    # ── Generazione ───────────────────────────────────────────────
    print(f"\n● Generazione CV ({CVS_PER_OCC} per occupation)...")
    log = {"errors": [], "stats": {}}
    t0  = time.time()

    sectors = [args.sector] if args.sector else sorted(selected.keys())

    for major in sectors:
        occs = selected.get(major, [])
        if not occs:
            continue
        print(f"\n  ── ISCO {major}: {ISCO_MAJOR_LABELS.get(major, major)} ({len(occs)} occ) ──")

        for occ in occs:
            profile = profiles.get(occ["id"])
            if not profile:
                print(f"    ⚠ Profilo non trovato per {occ['id']}, skip")
                log["errors"].append({"oid": occ["id"], "reason": "profile_not_found"})
                continue

            print(f"\n    [{occ['isco_code']}] {occ['label']}")
            new_cvs = generate_cvs_for_occupation(
                occ, profile, selected, supplementary, existing_cv_ids
            )
            all_cvs.extend(new_cvs)
            existing_cv_ids.update(cv["cv_id"] for cv in new_cvs)

            # Salva progressivamente dopo ogni occupation
            with open(cvs_path, "w", encoding="utf-8") as f:
                json.dump(all_cvs, f, ensure_ascii=False, indent=2)

    # ── Stats finali ──────────────────────────────────────────────
    elapsed    = time.time() - t0
    sen_counts = defaultdict(int)
    coverages  = []
    for cv in all_cvs:
        sen = cv.get("cv", {}).get("persona", {}).get("seniority", "unknown")
        sen_counts[sen] += 1
        cov = cv.get("ground_truth", {}).get("skill_coverage")
        if cov is not None:
            coverages.append(cov)

    avg_cov = sum(coverages) / len(coverages) if coverages else 0

    log["stats"] = {
        "total_cvs":           len(all_cvs),
        "by_seniority":        dict(sen_counts),
        "avg_skill_coverage":  round(avg_cov, 3),
        "generation_time_sec": round(elapsed, 1),
        "errors":              len(log["errors"]),
    }
    with open(out_dir / "generation_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print("\n" + "═" * 60)
    print(f"  ✅ Completato in {elapsed:.0f}s")
    print(f"  📄 CV totali:     {len(all_cvs)}")
    print(f"  📊 Avg coverage:  {avg_cov:.1%}")
    print(f"  ⚠  Errori:       {len(log['errors'])}")
    print(f"  📁 Output:        {out_dir.resolve()}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()