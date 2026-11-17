"""
SkillPath AI — generate_jobs.py
Genera annunci di lavoro sintetici con ground truth ESCO, sulla stessa linea
metodologica di generate_dataset.py (CV): stesse 135 occupation selezionate
(dataset/synthetic/selected_occupations.json), stesso LLM (Groq), stessa logica
di validazione/enrichment degli ID contro l'ontologia ESCO — ma output solo
testuale (nessun rendering PDF, nessun dato anagrafico).

Riusa deliberatamente lo stesso set di occupation dei CV: è la condizione
necessaria per rendere CV e annunci comparabili nella validazione del
matching engine (Scenario 2), cosa che il dataset job_descriptions/ attuale
(estratto da Excel, solo 3 aree) non permette.

LLM: OpenRouter, modello meta-llama/llama-3.3-70b-instruct — stesso identico
modello usato per generare i CV (via Groq), quindi piena coerenza tra i due
dataset sintetici. Passati da Groq perché lì il modello 70B ha un tetto di
100.000 token/giorno sul tier free (troppo poco: ~40 annunci/giorno, 17-20
giorni per finire tutto). La variante gratuita ":free" su OpenRouter è stata
nel frattempo ritirata dal provider, quindi si usa la versione a pagamento
(0,10$/M token input, 0,32$/M output — costo stimato <1$ per l'intero
dataset, a valere sui 10$ già caricati sull'account).
Serve un file .env nella radice del progetto con:
    OPENROUTER_API_KEY=sk-or-v1-...

Uso (dalla radice del progetto):
    python src/generate_jobs.py                        # genera tutto (135 occ x 6)
    python src/generate_jobs.py --resume                # riprende da dove interrotto
    python src/generate_jobs.py --sector 2               # solo settore ISCO 2
    python src/generate_jobs.py --max 5                  # test rapido, 5 annunci totali

Output:
    dataset/synthetic/jobs_gt/jobs.json             ← tutti gli annunci generati
    dataset/synthetic/jobs_gt/generation_log.json   ← log errori e stats
"""

import json
import argparse
import time
import random
import os
import sys
from pathlib import Path
from collections import defaultdict
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dataset import pick_negative_samples  # riuso la stessa logica dei CV


# ─── Config ─────────────────────────────────────────────────────────────────

JOBS_PER_OCC   = 6
SENIORITY_DIST = [
    ("junior", 2),
    ("mid",    2),
    ("senior", 2),
]
# Quota di skill essenziali richieste nell'annuncio (in % delle essential_skills
# dell'occupation) — un annuncio, come un CV, raramente le richiede tutte.
REQUIRED_COVERAGE_RANGE = {
    "junior": (0.30, 0.50),
    "mid":    (0.45, 0.65),
    "senior": (0.55, 0.80),
}
PREFERRED_COUNT_RANGE = (2, 6)   # skill "preferibili/nice-to-have" da optional_skills

CONTRACT_TYPES = ["Permanent", "Fixed-term", "Apprenticeship", "Full-time", "Part-time"]
TITLE_PREFIX = {
    "junior": ["Junior", "Associate", "Trainee", ""],
    "mid":    ["", "Senior"],
    "senior": ["Senior", "Lead", "Principal", "Head of"],
}
EU_CITIES = [
    "Milan", "Rome", "Turin", "Berlin", "Munich", "Paris", "Lyon",
    "Madrid", "Barcelona", "Amsterdam", "Warsaw", "Lisbon", "Vienna",
    "Brussels", "Dublin", "Stockholm", "Remote (EU)",
]

MODEL   = "meta-llama/llama-3.3-70b-instruct"   # versione a pagamento (":free" ritirata
                                                 # da OpenRouter) — stesso modello dei CV,
                                                 # costo stimato <1$ per l'intero dataset
API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

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


# ─── Prompt Builder ──────────────────────────────────────────────────────────

def build_job_prompt(
    occ:              dict,
    essential_skills: list[dict],
    optional_skills:  list[dict],
    seniority:        str,
    company_name:     str,
    company_country:  str,
    city:             str,
    contract:         str,
) -> str:
    ess_list = "\n".join(f'  - [{s["id"]}] {s["label"]}' for s in essential_skills)
    opt_list = "\n".join(f'  - [{s["id"]}] {s["label"]}' for s in optional_skills[:15])

    cov_min, cov_max = REQUIRED_COVERAGE_RANGE[seniority]
    pref_min, pref_max = PREFERRED_COUNT_RANGE
    prefix = random.choice(TITLE_PREFIX[seniority])
    job_title = f"{prefix} {occ['label']}".strip()

    return f"""You are generating a synthetic English job posting for the SkillPath AI evaluation dataset.

ROLE TARGET: {occ['label']} (ISCO {occ['isco_code']}, sector: {occ['isco_major_label']})
SENIORITY: {seniority}
COMPANY: {company_name} ({company_country})
LOCATION: {city}
CONTRACT: {contract}

─── AVAILABLE ESSENTIAL SKILLS (ESCO IDs) ───
{ess_list}

─── AVAILABLE OPTIONAL SKILLS (ESCO IDs, sample) ───
{opt_list}

─── STRICT RULES ───

RULE 1 - REQUIRED SKILLS:
  Pick required_ids ONLY from the essential list above.
  len(required_ids) / {len(essential_skills)} must be between {cov_min:.2f} and {cov_max:.2f}.
  That means pick EXACTLY between {max(1, int(len(essential_skills)*cov_min))} and {min(len(essential_skills)-1, int(len(essential_skills)*cov_max))} IDs.
  NEVER pick all {len(essential_skills)} essential IDs.

RULE 2 - PREFERRED SKILLS:
  Pick {pref_min}-{pref_max} "nice to have" IDs ONLY from the optional list above.

RULE 3 - ALL IDs must come ONLY from the lists above. Never invent IDs.

RULE 4 - TEXT: write a realistic English job posting, 2-3 short paragraphs
  (company blurb + responsibilities + a short "Requirements" / "Nice to have"
  section in prose). Mention the skills in natural language, NOT as a bullet
  list of raw ESCO labels, and NEVER print the IDs in the text.
  Mention the job title, company name, location, contract type, seniority.

─── OUTPUT FORMAT ───
Respond ONLY with valid JSON. No markdown, no explanation, no extra keys.

{{
  "job": {{
    "meta": {{
      "ruolo":     "{job_title}",
      "azienda":   "{company_name}",
      "localita":  "{city}",
      "seniority": "{seniority}",
      "contratto": "{contract}"
    }},
    "skills": {{
      "required_ids":  ["<id>", "..."],
      "preferred_ids": ["<id>", "..."]
    }},
    "raw_text": "<natural job posting text here>"
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

def validate_and_enrich_job(
    raw:              dict,
    essential_ids:    set,
    optional_ids:     set,
    occ:              dict,
    negative_samples: list[dict],
) -> dict:
    job = raw.get("job", {})
    gt  = raw.get("ground_truth", {})

    raw_req = set(job.get("skills", {}).get("required_ids",  []))
    raw_pref = set(job.get("skills", {}).get("preferred_ids", []))
    valid_req  = list(raw_req & essential_ids)
    valid_pref = list(raw_pref & optional_ids)
    job.setdefault("skills", {})
    job["skills"]["required_ids"]  = valid_req
    job["skills"]["preferred_ids"] = valid_pref

    coverage = len(valid_req) / len(essential_ids) if essential_ids else 0.0
    gt["skill_coverage"]          = round(coverage, 4)
    gt["target_occupation_id"]    = occ["id"]
    gt["target_occupation_label"] = occ["label"]
    gt["isco_code"]               = occ["isco_code"]
    gt["isco_major"]              = occ["isco_major"]
    gt["negative_samples"]        = negative_samples

    raw["_validation"] = {
        "required_removed":  len(raw_req - essential_ids),
        "preferred_removed": len(raw_pref - optional_ids),
    }
    raw["job"]          = job
    raw["ground_truth"] = gt
    return raw


# ─── LLM Call ────────────────────────────────────────────────────────────────

# Il tetto fisso di 20 RPM di OpenRouter vale solo per le varianti ":free";
# sul modello a pagamento il limite è quello di capacità globale del
# provider, molto più permissivo — spacing ridotto, il retry su 429 in
# call_llm resta comunque il paracadute in caso di picchi.
BASE_SLEEP_S = 2.0


def pace_next_call() -> None:
    time.sleep(BASE_SLEEP_S)


def call_llm(prompt: str, max_retries: int = 4) -> dict | None:
    if not API_KEY:
        print("❌ OPENROUTER_API_KEY non trovata nel file .env")
        return None

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://skillpath-ai.local",  # richiesto da OpenRouter per l'attribuzione
                    "X-Title":       "SkillPath AI - generate_jobs",
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
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)   # può fallire se l'LLM tronca/rompe il JSON

        except requests.RequestException as e:
            wait = 60.0
            try:
                err_body = e.response.json()
                err_msg  = err_body.get("message") or err_body.get("error", {}).get("message", "")
                import re as _re
                match = _re.search(r"try again in ([\d.]+)s", err_msg, _re.IGNORECASE)
                if match:
                    wait = float(match.group(1)) + 1.0
                elif e.response is not None and e.response.status_code == 429:
                    wait = 30.0   # rate limit senza retry-after esplicito
                else:
                    wait = 10.0
                print(f"      ⚠ API error {e.response.status_code if e.response is not None else '?'} "
                      f"(tentativo {attempt+1}/{max_retries}), attendo {wait:.1f}s... [{err_msg[:80]}]")
            except Exception:
                print(f"      ⚠ Errore rete (tentativo {attempt+1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                time.sleep(wait)

        except (ValueError, KeyError, IndexError, TypeError) as e:
            # risposta 200 ma corpo malformato/troncato (es. JSON tagliato a metà,
            # "choices" mancante...) — non è un errore di rete, ma non deve
            # comunque far crashare un run di ore: si logga e si riprova.
            print(f"      ⚠ Risposta malformata (tentativo {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
    return None


# ─── Generazione annunci per occupation ──────────────────────────────────────

def generate_jobs_for_occupation(
    occ:              dict,
    profile:          dict,
    selected:         dict,
    co_data:          dict,
    existing_job_ids: set,
    max_new:          int | None = None,   # limite annunci da generare in questa chiamata
) -> list[dict]:
    jobs             = []
    essential_skills = profile.get("essential_skills", [])
    optional_skills  = profile.get("optional_skills",  [])
    essential_ids    = {s["id"] for s in essential_skills}
    optional_ids     = {s["id"] for s in optional_skills}

    sector_co_ids = co_data["by_sector"].get(occ["isco_major"], list(co_data["companies"].keys()))
    co_pool       = [co_data["companies"][cid] for cid in sector_co_ids if cid in co_data["companies"]]
    if not co_pool:
        co_pool = list(co_data["companies"].values())

    # Negative samples condivisi per tutti gli annunci di questa occupation
    negative_samples = pick_negative_samples(occ, selected)

    for seniority, count in SENIORITY_DIST:
        if max_new is not None and len(jobs) >= max_new:
            break
        for i in range(count):
            if max_new is not None and len(jobs) >= max_new:
                break
            job_id = f"jobgt_{occ['id']}_{seniority}_{i}"
            if job_id in existing_job_ids:
                print(f"      ↷ Skip: {job_id}")
                continue

            company  = random.choice(co_pool)
            city     = random.choice(EU_CITIES)
            contract = random.choice(CONTRACT_TYPES)

            prompt = build_job_prompt(
                occ, essential_skills, optional_skills,
                seniority, company["name"], company["country"], city, contract,
            )

            print(f"      [{seniority}] {company['name']} ({city})...", end=" ", flush=True)

            # Un JSON sintatticamente valido non basta: l'LLM a volte lascia
            # raw_text vuoto, o copia il segnaposto del prompt, o propone solo
            # ID inesistenti (required/preferred finiscono entrambi a 0 dopo
            # il filtro). Sono "successi" strutturali ma dati inutilizzabili
            # come ground truth — qui si ritenta invece di accettarli.
            QUALITY_RETRIES = 3
            enriched = None
            for qattempt in range(QUALITY_RETRIES):
                raw = call_llm(prompt)
                if raw is None:
                    break   # call_llm ha già esaurito i suoi retry (rete/JSON), non ha senso insistere

                try:
                    candidate = validate_and_enrich_job(
                        raw, essential_ids, optional_ids, occ, negative_samples,
                    )
                    txt      = candidate["job"].get("raw_text", "") or ""
                    n_req_c  = len(candidate["job"]["skills"]["required_ids"])
                    n_pref_c = len(candidate["job"]["skills"]["preferred_ids"])
                    is_placeholder = "natural job posting text here" in txt.lower()
                    if len(txt.strip()) < 150 or is_placeholder or (n_req_c == 0 and n_pref_c == 0):
                        reason = ("testo vuoto/segnaposto" if (len(txt.strip()) < 150 or is_placeholder)
                                  else "nessuna skill valida")
                        print(f"↻(qualità: {reason}, tentativo {qattempt+1}/{QUALITY_RETRIES}) ", end="", flush=True)
                        time.sleep(3)
                        continue
                    enriched = candidate
                    break
                except Exception as e:
                    print(f"↻(struttura inattesa: {e}, tentativo {qattempt+1}/{QUALITY_RETRIES}) ", end="", flush=True)
                    time.sleep(3)
                    continue

            if enriched is None:
                print("✗ FAIL (qualità insufficiente dopo i retry)")
                time.sleep(5)
                continue

            enriched["job_id"]       = job_id
            enriched["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            v        = enriched["_validation"]
            coverage = enriched["ground_truth"]["skill_coverage"]
            n_req    = len(enriched["job"]["skills"]["required_ids"])
            n_pref   = len(enriched["job"]["skills"]["preferred_ids"])

            print(f"✓  req={n_req} pref={n_pref} cov={coverage:.0%}  "
                  f"req_removed={v['required_removed']}  pref_removed={v['preferred_removed']}")

            jobs.append(enriched)
            pace_next_call()   # spacing costante sotto le 20 RPM fisse di OpenRouter

    return jobs


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SkillPath AI — Job Posting Generator (con ground truth ESCO)")
    parser.add_argument("--dataset", default="./dataset",                  help="Cartella dataset JSON")
    parser.add_argument("--output",  default="./dataset/synthetic/jobs_gt", help="Cartella output")
    parser.add_argument("--resume",  action="store_true",                  help="Riprendi da dove interrotto")
    parser.add_argument("--sector",  default=None,                         help="Solo settore ISCO (es. '2')")
    parser.add_argument("--max",     type=int, default=None,               help="Limita il numero totale di annunci (test rapido)")
    parser.add_argument("--seed",    type=int, default=42,                 help="Random seed")
    args = parser.parse_args()

    random.seed(args.seed)

    out_dir     = Path(args.output)
    dataset_dir = Path(args.dataset)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "═" * 60)
    print("  SkillPath AI — Job Posting Generator")
    print("═" * 60)

    # ── Carica selezione occupation (STESSA usata per i CV) ────────
    sel_path = dataset_dir / "synthetic" / "selected_occupations.json"
    if not sel_path.exists():
        print(f"[jobs] ERRORE: {sel_path} non trovato.")
        print("  Genera prima i CV (python src/generate_dataset.py --select-only)")
        sys.exit(1)

    print("\n● Carico selezione occupation (condivisa con i CV)...")
    with open(sel_path, encoding="utf-8") as f:
        selected = json.load(f)
    n_occ = sum(len(v) for v in selected.values())
    print(f"  {n_occ} occupation caricate da {sel_path.name}")

    with open(dataset_dir / "materialized" / "occupation_profiles.json", encoding="utf-8") as f:
        profiles = {p["id"]: p for p in json.load(f)}
    with open(dataset_dir / "supplementary" / "companies.json", encoding="utf-8") as f:
        co_data = json.load(f)

    # ── Carica annunci esistenti se --resume ─────────────────────
    jobs_path = out_dir / "jobs.json"
    all_jobs: list[dict] = []
    existing_job_ids: set = set()

    if jobs_path.exists() and args.resume:
        with open(jobs_path, encoding="utf-8") as f:
            all_jobs = json.load(f)
        existing_job_ids = {j["job_id"] for j in all_jobs}
        print(f"\n● Resume: {len(all_jobs)} annunci già esistenti trovati")

    # ── Generazione ───────────────────────────────────────────────
    print(f"\n● Generazione annunci ({JOBS_PER_OCC} per occupation)...")
    log = {"errors": [], "stats": {}}
    t0  = time.time()

    sectors = [args.sector] if args.sector else sorted(selected.keys())

    for major in sectors:
        occs = selected.get(major, [])
        if not occs:
            continue
        print(f"\n  ── ISCO {major}: {ISCO_MAJOR_LABELS.get(major, major)} ({len(occs)} occ) ──")

        for occ in occs:
            if args.max and len(all_jobs) >= args.max:
                break
            profile = profiles.get(occ["id"])
            if not profile:
                print(f"    ⚠ Profilo non trovato per {occ['id']}, skip")
                log["errors"].append({"oid": occ["id"], "reason": "profile_not_found"})
                continue

            print(f"\n    [{occ['isco_code']}] {occ['label']}")
            remaining = (args.max - len(all_jobs)) if args.max else None
            try:
                new_jobs = generate_jobs_for_occupation(
                    occ, profile, selected, co_data, existing_job_ids, max_new=remaining
                )
            except Exception as e:
                # Non deve mai far cadere l'intero run: si salva il progresso
                # fatto finora, si logga l'errore e si passa all'occupation dopo.
                print(f"    ✗ ERRORE imprevisto su {occ['label']}: {e}")
                log["errors"].append({"oid": occ["id"], "reason": f"unexpected: {e}"})
                new_jobs = []
            all_jobs.extend(new_jobs)
            existing_job_ids.update(j["job_id"] for j in new_jobs)

            with open(jobs_path, "w", encoding="utf-8") as f:
                json.dump(all_jobs, f, ensure_ascii=False, indent=2)

        if args.max and len(all_jobs) >= args.max:
            break

    # ── Stats finali ──────────────────────────────────────────────
    elapsed    = time.time() - t0
    sen_counts = defaultdict(int)
    coverages  = []
    for j in all_jobs:
        sen = j.get("job", {}).get("meta", {}).get("seniority", "unknown")
        sen_counts[sen] += 1
        cov = j.get("ground_truth", {}).get("skill_coverage")
        if cov is not None:
            coverages.append(cov)

    avg_cov = sum(coverages) / len(coverages) if coverages else 0

    log["stats"] = {
        "total_jobs":          len(all_jobs),
        "by_seniority":        dict(sen_counts),
        "avg_skill_coverage":  round(avg_cov, 3),
        "generation_time_sec": round(elapsed, 1),
        "errors":              len(log["errors"]),
    }
    with open(out_dir / "generation_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print("\n" + "═" * 60)
    print(f"  ✅ Completato in {elapsed:.0f}s")
    print(f"  📄 Annunci totali: {len(all_jobs)}")
    print(f"  📊 Avg coverage:   {avg_cov:.1%}")
    print(f"  ⚠  Errori:        {len(log['errors'])}")
    print(f"  📁 Output:         {out_dir.resolve()}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
