"""
analisi_parser.py  —  SkillPath AI
====================================
Script di analisi e visualizzazione delle prestazioni del parser.

Produce quattro sezioni di output:

    1. STATISTICHE DATASET    — dimensioni del dataset sintetico ESCO
    2. ANALISI THRESHOLD      — impatto della soglia cosine similarity
    3. ANALISI FILTRI         — quante label elimina ogni filtro
    4. VALUTAZIONE GROUND TRUTH — precision / recall su CV sintetici

Uso (dalla radice del progetto):
    python analysis/analisi_parser.py                  # analisi completa
    python analysis/analisi_parser.py --section threshold
    python analysis/analisi_parser.py --section filtri
    python analysis/analisi_parser.py --section gt --n 10

Output:
    stampa su console + salva outputs/analisi_risultati.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ─── path ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent  # radice progetto (analysis/ è un livello sotto)
SRC_DIR   = BASE_DIR / "src"
DATA_SRC  = BASE_DIR / "dataset" / "source"
DATA_SUPP = BASE_DIR / "dataset" / "supplementary"
DATA_SYN  = BASE_DIR / "dataset" / "synthetic"
RENDERED  = DATA_SYN / "rendered"

SEP = "─" * 65


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 1 — STATISTICHE DATASET
# ══════════════════════════════════════════════════════════════════════════════

def sezione_dataset():
    """
    Riepiloga le dimensioni dei database ESCO usati dal parser.

    Dati chiave per la presentazione:
    - Quante occupazioni / skill / corsi sono disponibili
    - Quanti CV sintetici sono stati generati
    - Distribuzione template nei CV renderizzati
    """
    print(f"\n{'═'*65}")
    print("  SEZIONE 1 — STATISTICHE DATASET")
    print(f"{'═'*65}\n")

    # ── Database ESCO ─────────────────────────────────────────────────────────
    db_files = {
        "Occupazioni ESCO":   DATA_SRC  / "occupations.json",
        "Skill ESCO":         DATA_SRC  / "skills.json",
        "Relazioni occ-skill": DATA_SRC / "occupation_skill_relations.json",
        "Corsi di laurea":    DATA_SUPP / "degree_programs.json",
        "Livelli lingua":     DATA_SUPP / "language_levels.json",
        "Certificazioni":     DATA_SUPP / "certifications.json",
    }

    print("  Database ESCO caricati dal parser:")
    print(f"  {'Nome':<28} {'Entries':>8}  {'Dimensione':>10}")
    print(f"  {SEP}")
    total_entries = 0
    for label, path in db_files.items():
        if path.exists():
            size_kb = path.stat().st_size / 1024
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                # Conta entries a seconda della struttura del file
                if isinstance(data, dict):
                    if "certifications" in data:
                        n = len(data["certifications"])
                    elif "entries" in data:
                        n = len(data["entries"])
                    elif "programs" in data:
                        n = len(data["programs"])
                    else:
                        n = len(data)
                elif isinstance(data, list):
                    n = len(data)
                else:
                    n = "?"
            except Exception:
                n = "errore"
                size_kb = 0
            total_entries += n if isinstance(n, int) else 0
            print(f"  {label:<28} {n:>8,}  {size_kb:>8.0f} KB")
        else:
            print(f"  {label:<28} {'[non trovato]':>8}")
    print(f"  {SEP}")
    print(f"  {'TOTALE entries':.<28} {total_entries:>8,}\n")

    # ── Dataset sintetico ─────────────────────────────────────────────────────
    cvs_path = DATA_SYN / "cvs.json"
    if cvs_path.exists():
        with open(cvs_path, encoding="utf-8") as f:
            cvs = json.load(f)
        print(f"  CV sintetici generati:  {len(cvs):,}")

        # Struttura: cv['cv']['persona']['seniority']
        sen_counts = {}
        for cv in cvs:
            sen = cv.get("cv", {}).get("persona", {}).get("seniority", "?")
            sen_counts[sen] = sen_counts.get(sen, 0) + 1
        print("  Distribuzione seniority nel dataset:")
        for k, v in sorted(sen_counts.items()):
            bar = "█" * (v * 20 // len(cvs))
            print(f"    {k:<10} {v:>5} ({v*100//len(cvs):2d}%)  {bar}")

        # Struttura: cv['cv']['skills']['essential_ids'] + ['optional_ids']
        skill_counts = [
            len(cv.get("cv", {}).get("skills", {}).get("essential_ids", []))
            + len(cv.get("cv", {}).get("skills", {}).get("optional_ids",  []))
            for cv in cvs
        ]
        avg_skills = sum(skill_counts) / len(skill_counts) if skill_counts else 0
        print(f"\n  Skill per CV (ground truth, set essential+optional):")
        print(f"    Media  : {avg_skills:.1f}")
        print(f"    Min    : {min(skill_counts)}")
        print(f"    Max    : {max(skill_counts)}")
    else:
        print("  [cvs.json non trovato — esegui prima generate_cvs.py]")

    # ── CV renderizzati ───────────────────────────────────────────────────────
    manifest = RENDERED / "manifest.json"
    if manifest.exists():
        with open(manifest, encoding="utf-8") as f:
            mfst = json.load(f)
        tmpl_counts = {}
        for e in mfst:
            t = e.get("template", "?")
            tmpl_counts[t] = tmpl_counts.get(t, 0) + 1
        print(f"\n  CV renderizzati (manifest): {len(mfst)}")
        print("  Per template:")
        for t, n in sorted(tmpl_counts.items()):
            print(f"    {t:<12} {n:>4} CV")
    else:
        print("\n  [manifest.json non trovato — esegui prima render_cvs.py]")


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 2 — ANALISI THRESHOLD
# ══════════════════════════════════════════════════════════════════════════════

def sezione_threshold():
    """
    Spiega cos'è la cosine similarity e mostra l'impatto della soglia
    analizzando i punteggi reali prodotti dal parser su un CV renderizzato.

    COS'È LA COSINE SIMILARITY
    ───────────────────────────
    Il modello sentence-transformers converte ogni testo in un vettore
    nello spazio R^768 (multilingual-e5-base). Due vettori u e v hanno cosine
    similarity:

        sim(u, v) = (u · v) / (‖u‖ · ‖v‖)   ∈ [−1, 1]

    Con embedding normalizzati (‖u‖ = ‖v‖ = 1), diventa il prodotto scalare.
    Valori tipici:
        > 0.90  →  testi quasi identici o sinonimi diretti
        0.80–0.90 →  stesso concetto, formulazione diversa
        0.70–0.80 →  stessa area semantica, concetti correlati
        < 0.70  →  concetti distanti

    Il threshold è la soglia minima per accettare un match. Sceglierlo
    troppo basso aumenta il recall ma abbassa la precision (più falsi
    positivi); troppo alto riduce i falsi positivi ma perde match legittimi.
    """
    print(f"\n{'═'*65}")
    print("  SEZIONE 2 — ANALISI THRESHOLD (cosine similarity)")
    print(f"{'═'*65}")

    # Modello e dimensione NON vanno scritti a mano: erano rimasti fermi a
    # paraphrase-multilingual-MiniLM-L12-v2 (384 dim) mentre il progetto era
    # già passato a multilingual-e5-base (768 dim), e questo blocco finisce
    # copiato nella relazione. Si leggono dalla firma di SemanticMapper.
    import inspect
    from semantic_mapper import SemanticMapper
    _modello = inspect.signature(SemanticMapper.__init__).parameters[
        "model_name"
    ].default
    _dim = {"intfloat/multilingual-e5-small": 384,
            "intfloat/multilingual-e5-base": 768,
            "intfloat/multilingual-e5-large": 1024,
            "paraphrase-multilingual-MiniLM-L12-v2": 384}.get(_modello, "?")

    print(f"""
  BACKGROUND MATEMATICO
  ─────────────────────
  Modello: {_modello}
  Dimensione spazio embedding: {_dim} dimensioni
  Normalizzazione: ‖v‖ = 1  →  sim(u,v) = u·v  (prodotto scalare)

  Interpretazione dei valori:
    ≥ 0.95  match quasi-esatto (stesso termine, lingua diversa)
    0.90–0.94  sinonimo forte (es. "progettazione" ↔ "design")
    0.85–0.89  stesso dominio concettuale
    0.80–0.84  correlazione semantica significativa
    0.75–0.79  area tematica condivisa (rumore possibile)
    < 0.75  bassa similarità → quasi certamente rumore

  Threshold usati nel parser dei CV (src/main_parser.py):
    Skill parola singola : 0.85  (token precisi, poco rumore semantico)
    Skill multi-parola   : 0.88  (frasi narrative, più rumore → soglia alta)
    Acronimi/CamelCase   : 0.85  (token già molto specifici)
    Occupazioni          : 0.80  (ammette varianti di titoli professionali)
    Certificazioni       : 0.75  (nomi molto specifici → soglia più bassa)
    Education            : 0.62  (nomi corsi italiani divergono molto dall'EN)
    Lingue               : 0.72  (fallback semantico — keyword è prioritaria)
""")

    # ── Dimostrazione live con SemanticMapper ─────────────────────────────────
    # Usa frasi rappresentative estratte da CV reali (IT) per mostrare come
    # il modello assegna punteggi diversi a query semanticamente vicine o lontane.
    demo_queries = [
        # Alta similarità attesa
        "Python",
        "SQL",
        "Microsoft Excel",
        "machine learning",
        "project management",
        # Media similarità
        "gestione progetti",
        "analisi dati",
        "programmazione",
        # Bassa similarità attesa (rumore)
        "laurea triennale",
        "Milano",
        "esperienze internazionali",
    ]

    try:
        sys.path.insert(0, str(SRC_DIR))
        from semantic_mapper import SemanticMapper
        skills_path = BASE_DIR / "dataset" / "source" / "skills.json"
        if skills_path.exists():
            mapper = SemanticMapper()
            mapper.load_database(str(skills_path))
            # Cerca con threshold molto basso per catturare tutti i punteggi
            raw_matches = mapper.find_matches(
                demo_queries, threshold=0.60, top_k=1,
                max_results=40, return_scores=True
            )
            if raw_matches:
                print("  IMPATTO THRESHOLD — demo su query rappresentative di CV IT")
                print(f"  {SEP}")
                thresholds = [0.70, 0.75, 0.80, 0.82, 0.85, 0.87, 0.90, 0.95]
                scores_all = sorted([m["score"] for m in raw_matches], reverse=True)
                print(f"  {'Threshold':>10}  {'Match accettati':>16}  {'Match esclusi':>14}")
                print(f"  {SEP}")
                for thr in thresholds:
                    accepted = sum(1 for s in scores_all if s >= thr)
                    rejected = len(scores_all) - accepted
                    marker = "  ← USATO per skill" if thr == 0.85 else ""
                    print(f"  {thr:>10.2f}  {accepted:>16}  {rejected:>14}{marker}")

                print(f"\n  Distribuzione punteggi (score → miglior label ESCO):")
                print(f"  {'Score':>8}  {'Label ESCO':<45}  OK?")
                print(f"  {SEP}")
                for m in sorted(raw_matches, key=lambda x: x["score"], reverse=True):
                    status = "✓" if m["score"] >= 0.85 else ("~" if m["score"] >= 0.75 else "✗")
                    print(f"  {m['score']:>8.4f}  {m['label']:<45}  {status}")
            else:
                print("  [Nessun match — verifica che skills.json sia disponibile]")
        else:
            print("  [skills.json non trovato — impossibile eseguire demo live]")
    except ImportError:
        print("  [SemanticMapper non disponibile — esegui su macchina con dipendenze installate]")
        # Fallback: leggi outputs/cv_parsed_result.json se disponibile
        cv_parsed = BASE_DIR / "outputs" / "cv_parsed_result.json"
        if cv_parsed.exists():
            try:
                with open(cv_parsed, encoding="utf-8") as f:
                    parsed = json.load(f)
                all_matches = parsed.get("cv", {}).get("skills", {}).get("all_matches", [])
                if all_matches:
                    print(f"\n  Skill nell'ultimo CV parsato (da cv_parsed_result.json):")
                    for m in sorted(all_matches, key=lambda x: x["score"], reverse=True):
                        status = "✓" if m["score"] >= 0.85 else "✗"
                        print(f"    {m['score']:.4f}  {m['label']}  {status}")
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 3 — ANALISI FILTRI
# ══════════════════════════════════════════════════════════════════════════════

def sezione_filtri():
    """
    Mostra quante label ESCO vengono eliminate da ogni filtro post-semantic,
    usando un campione casuale di label dal database skills.json.

    Questo permette di capire la "copertura" dei filtri:
    quante label ESCO avrebbero potuto risultare false positive
    e quante ne blocca ogni filtro.
    """
    print(f"\n{'═'*65}")
    print("  SEZIONE 3 — ANALISI FILTRI POST-SEMANTIC")
    print(f"{'═'*65}\n")

    skills_path = DATA_SRC / "skills.json"
    if not skills_path.exists():
        print("  [skills.json non trovato]")
        return

    with open(skills_path, encoding="utf-8") as f:
        skills_db = json.load(f)

    # Estrai TUTTE le label dal database (primarie + alt_labels)
    # come fa SemanticMapper._collect_labels() per costruire l'indice embedding.
    labels = []
    for k, v in skills_db.items():
        if not isinstance(v, dict):
            continue
        lbl = v.get("label", "")
        if lbl:
            labels.append(lbl)
        for alt in v.get("alt_labels", []) or []:
            if alt:
                labels.append(alt)

    total = len(labels)
    primary = sum(1 for k, v in skills_db.items() if isinstance(v,dict) and v.get("label"))
    print(f"  Label nel database skills.json:")
    print(f"    Label primarie   : {primary:>6,}")
    print(f"    Alt_labels       : {total-primary:>6,}")
    print(f"    Totale indicizzate: {total:>6,}\n")

    # Regex filtri (stessa logica di main_parser.py)
    _ESCO_TASK_LABEL_RE = re.compile(
        r"^(?:"
        r"using|utilise|use|apply\b|manage\b|operate|perform|conduct|"
        r"carry\b|provide|ensure|maintain|assess|analys[ei]|identif[yi]|"
        r"monitor|administer|co[-\s]?ordinate|coordinate|implement|"
        r"establish|build\b|support\b|assist|attend\b|verify\b|"
        r"inspect|check\b|prepare\b|handle\b|process\b|report\b|"
        r"respond|review\b|train\b|teach\b|advise|consult\b|"
        r"facilitate|resolve|evaluate|deliver\b|produce\b|complete\b|"
        r"develop\b|creat|be\b|"
        r"calculat|attend[a-z]*\s|verify[a-z]*\s|inspect[a-z]*\s"
        r")",
        re.IGNORECASE,
    )
    _EQUIPMENT_TERMS = {"apparatus", "equipment", "device", "machinery", "appliance"}

    # Conta label eliminate da ogni filtro (applicati in cascata)
    remaining = labels[:]
    results   = []

    # Filtro 1: label troppo corte
    f1_removed = [l for l in remaining if len(l) <= 4]
    remaining  = [l for l in remaining if len(l) > 4]
    results.append(("Label ≤ 4 caratteri",          len(f1_removed)))

    # Filtro 2: articolo iniziale
    f2_removed = [l for l in remaining if re.match(r"^(a|an|the)\s", l.lower())]
    remaining  = [l for l in remaining if not re.match(r"^(a|an|the)\s", l.lower())]
    results.append(("Iniziano con articolo (a/an/the)", len(f2_removed)))

    # Filtro 3: verbo/gerundio iniziale
    f3_removed = [l for l in remaining if _ESCO_TASK_LABEL_RE.match(l)]
    remaining  = [l for l in remaining if not _ESCO_TASK_LABEL_RE.match(l)]
    results.append(("Iniziano con verbo/gerundio",   len(f3_removed)))

    # Filtro 4: equipment terms (conta quante ne avrebbe bloccate senza il testo)
    f4_count = sum(
        1 for l in remaining
        if set(re.split(r"\W+", l.lower())) & _EQUIPMENT_TERMS
    )
    results.append(("Contengono termine 'equipment' (bloccate senza frase esatta)", f4_count))

    print(f"  {'Filtro':<52}  {'Eliminate':>9}  {'%':>5}")
    print(f"  {SEP}")
    cumulative_removed = 0
    for name, count in results:
        cumulative_removed += count
        pct = count * 100 / total if total > 0 else 0
        print(f"  {name:<52}  {count:>9,}  {pct:>4.1f}%")

    print(f"  {SEP}")
    print(f"  {'Label rimanenti (potenzialmente valide)':<52}  {len(remaining):>9,}  "
          f"{len(remaining)*100/total:.1f}%")

    # Mostra esempi di label eliminate per categoria
    print(f"\n  Esempi label eliminate dal filtro verbi:")
    for l in f3_removed[:8]:
        print(f"    → \"{l}\"")

    print(f"\n  Esempi label eliminate dal filtro articoli:")
    for l in f2_removed[:5]:
        print(f"    → \"{l}\"")

    print(f"\n  Esempi label con termine equipment:")
    eq_examples = [
        l for l in remaining
        if set(re.split(r"\W+", l.lower())) & _EQUIPMENT_TERMS
    ][:6]
    for l in eq_examples:
        print(f"    → \"{l}\"")


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 4 — VALUTAZIONE GROUND TRUTH
# ══════════════════════════════════════════════════════════════════════════════

def sezione_ground_truth(n_cv: int = 10):
    """
    Valuta il parser su n_cv CV sintetici renderizzati confrontando
    l'output con il ground truth del manifest.

    METRICHE
    ────────
    Per le skill (l'output più rilevante del parser):

        Precision = TP / (TP + FP)
            = "delle skill trovate, quante erano giuste?"

        Recall = TP / (TP + FN)
            = "delle skill reali, quante ne ha trovate?"

        F1 = 2 · Precision · Recall / (Precision + Recall)
            = media armonica tra precision e recall

    Dove:
        TP (True  Positive) = skill trovata dal parser E presente nel GT
        FP (False Positive) = skill trovata dal parser MA non nel GT (rumore)
        FN (False Negative) = skill nel GT MA non trovata dal parser (miss)

    LIMITAZIONE
    ──────────
    I CV sintetici sono stati generati con skill ESCO per ID. Il parser
    li cerca semanticamente (per similarità). Un match può essere
    "concettualmente corretto" anche se l'ID ESCO è leggermente diverso
    (es. due skill dello stesso dominio). La valutazione per ID esatto
    è quindi un lower bound della qualità reale.
    """
    print(f"\n{'═'*65}")
    print(f"  SEZIONE 4 — VALUTAZIONE GROUND TRUTH (n={n_cv} CV)")
    print(f"{'═'*65}\n")

    manifest_path = RENDERED / "manifest.json"
    if not manifest_path.exists():
        print("  [manifest.json non trovato — esegui prima render_cvs.py]")
        return

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    if not manifest:
        print("  [manifest.json vuoto]")
        return

    # Carica cvs.json per ottenere le skill di ground truth
    # (il manifest contiene solo l'occupazione target, non le skill IDs)
    cvs_path = DATA_SYN / "cvs.json"
    cv_skills_gt: dict[str, set] = {}
    if cvs_path.exists():
        with open(cvs_path, encoding="utf-8") as f:
            all_cvs = json.load(f)
        for entry_cv in all_cvs:
            cid = entry_cv.get("cv_id", "")
            skills_block = entry_cv.get("cv", {}).get("skills", {})
            ids = set(
                skills_block.get("essential_ids", []) +
                skills_block.get("optional_ids",  [])
            )
            cv_skills_gt[cid] = ids
    else:
        print("  [cvs.json non trovato — ground truth skill non disponibile]")

    # Importa il parser solo se richiesto (evita errori di import se non disponibile)
    try:
        sys.path.insert(0, str(SRC_DIR))
        from main_parser import MainParser
        parser = MainParser()
    except ImportError as e:
        print(f"  [Impossibile importare MainParser: {e}]")
        return

    sample = manifest[:n_cv]

    # Metriche aggregate
    all_precision, all_recall, all_f1 = [], [], []
    results_by_template = {}

    print(f"  {'CV':>6}  {'Template':<12}  {'Prec':>6}  {'Rec':>6}  {'F1':>6}  "
          f"{'TP':>3}  {'FP':>3}  {'FN':>3}")
    print(f"  {SEP}")

    for i, entry in enumerate(sample):
        cv_id    = entry.get("cv_id", f"cv_{i}")
        template = entry.get("template", "?")

        # Recupera le skill IDs dal cvs.json tramite cv_id
        gt_skills = cv_skills_gt.get(cv_id, set())

        # Scegli il path PDF o DOCX (i path nel manifest usano separatore Windows)
        pdf_path  = entry.get("path_pdf", "").replace("\\", "/")
        docx_path = entry.get("path_docx", "").replace("\\", "/")
        cv_path   = str(BASE_DIR / pdf_path) if pdf_path else str(BASE_DIR / docx_path)

        if not os.path.exists(cv_path):
            print(f"  {i+1:>6}  {template:<12}  [file non trovato: {cv_path}]")
            continue

        try:
            result     = parser.parse_cv(cv_path)
            found_ids  = set(
                result["cv"]["skills"]["essential_ids"] +
                result["cv"]["skills"]["optional_ids"]
            )
        except Exception as ex:
            print(f"  {i+1:>6}  {template:<12}  [errore: {ex}]")
            continue

        tp = len(found_ids & gt_skills)
        fp = len(found_ids - gt_skills)
        fn = len(gt_skills - found_ids)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)

        all_precision.append(precision)
        all_recall.append(recall)
        all_f1.append(f1)

        if template not in results_by_template:
            results_by_template[template] = {"prec": [], "rec": [], "f1": []}
        results_by_template[template]["prec"].append(precision)
        results_by_template[template]["rec"].append(recall)
        results_by_template[template]["f1"].append(f1)

        print(f"  {i+1:>6}  {template:<12}  {precision:>6.2f}  {recall:>6.2f}  "
              f"{f1:>6.2f}  {tp:>3}  {fp:>3}  {fn:>3}")

    if not all_precision:
        print("  [Nessun CV processato con successo]")
        return

    # Medie aggregate
    avg_p  = sum(all_precision) / len(all_precision)
    avg_r  = sum(all_recall)    / len(all_recall)
    avg_f1 = sum(all_f1)        / len(all_f1)

    print(f"  {SEP}")
    print(f"  {'MEDIA':>6}  {'':12}  {avg_p:>6.2f}  {avg_r:>6.2f}  {avg_f1:>6.2f}")

    print(f"\n  Per template:")
    for tmpl, vals in sorted(results_by_template.items()):
        n = len(vals["f1"])
        mp = sum(vals["prec"]) / n
        mr = sum(vals["rec"])  / n
        mf = sum(vals["f1"])   / n
        print(f"    {tmpl:<12}  (n={n})  Prec={mp:.2f}  Rec={mr:.2f}  F1={mf:.2f}")

    print(f"""
  INTERPRETAZIONE
  ───────────────
  Precision {avg_p:.2f} → delle skill trovate, il {avg_p*100:.0f}% era corretto
  Recall    {avg_r:.2f} → delle skill reali,    il {avg_r*100:.0f}% è stato trovato
  F1        {avg_f1:.2f} → media armonica tra i due

  Una Precision bassa indica troppi falsi positivi (rumore semantico).
  Un Recall basso indica skill nel CV non rilevate (miss del parser).
  L'obiettivo del progetto è massimizzare F1 bilanciando i due.

  NOTA: la valutazione per ID esatto è un lower bound.
  Match semanticamente corretti ma con ID ESCO diverso vengono
  contati come FP/FN anche se concettualmente giusti.
""")

    return {
        "avg_precision": round(avg_p,  3),
        "avg_recall":    round(avg_r,  3),
        "avg_f1":        round(avg_f1, 3),
        "per_template":  {
            t: {k: round(sum(v)/len(v), 3) for k, v in vals.items()}
            for t, vals in results_by_template.items()
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def sezione_ground_truth_da_batch(batch_path: Path) -> dict:
    """
    Valuta il parser su TUTTI i CV già parsati da tests/batch_parse_cvs.py,
    invece di riparsare a campione i PDF.

    Perché esiste: sezione_ground_truth() riparsa i PDF uno per uno, quindi per
    ragioni di tempo gira su un campione (default 10 CV). Dieci CV non bastano
    a stimare precision e recall in modo stabile, e soprattutto rendono il
    risultato non confrontabile con la valutazione degli annunci, che gira su
    tutti gli 810. Questa funzione riusa il batch già calcolato e produce le
    metriche sull'intero dataset in pochi secondi, con la stessa definizione di
    TP/FP/FN usata da analysis/analisi_job_parser.py.
    """
    cvs_path = DATA_SYN / "cvs.json"
    if not batch_path.exists() or not cvs_path.exists():
        return {}

    with open(cvs_path, encoding="utf-8") as f:
        gt_map = {}
        for c in json.load(f):
            s = c.get("cv", {}).get("skills", {})
            gt_map[c.get("cv_id", "")] = set(
                s.get("essential_ids", []) + s.get("optional_ids", [])
            )
    with open(batch_path, encoding="utf-8") as f:
        risultati = json.load(f)

    # Il template non è ricavabile dal cv_id (contiene solo la seniority):
    # va letto dal manifest prodotto da render_cvs.py.
    template_di: dict[str, str] = {}
    manifest_path = RENDERED / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            for voce in json.load(f):
                if voce.get("cv_id"):
                    template_di[voce["cv_id"]] = voce.get("template", "?")

    print(f"\n{'═'*65}")
    print(f"  SEZIONE 4b — VALUTAZIONE GROUND TRUTH SU TUTTO IL DATASET")
    print(f"{'═'*65}\n")

    all_p, all_r, all_f1 = [], [], []
    tp_t = fp_t = fn_t = 0
    per_template: dict[str, list] = {}
    per_seniority: dict[str, list] = {}

    for r in risultati:
        cid = r.get("cv_id", "")
        if cid.startswith("parsed_"):
            cid = cid[len("parsed_"):]
        if cid.endswith(".pdf"):
            cid = cid[:-4]
        gt = gt_map.get(cid)
        if gt is None:
            continue
        s = r.get("cv", {}).get("skills", {})
        trovate = set(s.get("essential_ids", []) + s.get("optional_ids", []))
        if not gt and not trovate:
            continue

        tp, fp, fn = len(trovate & gt), len(trovate - gt), len(gt - trovate)
        tp_t += tp; fp_t += fp; fn_t += fn
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * p * rec / (p + rec)) if (p + rec) else 0.0
        all_p.append(p); all_r.append(rec); all_f1.append(f1)

        tpl = template_di.get(cid, "?")
        per_template.setdefault(tpl, []).append((p, rec, f1))
        sen = next((s for s in ("junior", "mid", "senior") if s in cid), "?")
        per_seniority.setdefault(sen, []).append((p, rec, f1))

    if not all_p:
        print("  [Nessun CV valutabile]")
        return {}

    ap_, ar_, af_ = (sum(x)/len(x) for x in (all_p, all_r, all_f1))
    print(f"  CV valutati: {len(all_p)}\n")
    print(f"  {'Metrica':<14}{'Valore':>8}")
    print(f"  {'-'*22}")
    print(f"  {'Precision':<14}{ap_:>8.3f}")
    print(f"  {'Recall':<14}{ar_:>8.3f}")
    print(f"  {'F1':<14}{af_:>8.3f}")
    print(f"\n  TP={tp_t}  FP={fp_t}  FN={fn_t}")

    print(f"\n  Per template:")
    out_tpl = {}
    for tpl, vals in sorted(per_template.items()):
        n_t = len(vals)
        mp, mr, mf = (sum(v[i] for v in vals)/n_t for i in range(3))
        out_tpl[tpl] = {"n": n_t, "precision": round(mp, 3),
                        "recall": round(mr, 3), "f1": round(mf, 3)}
        print(f"    {tpl:<10} (n={n_t:>3})  Prec={mp:.3f}  Rec={mr:.3f}  F1={mf:.3f}")

    print(f"\n  Per seniority:")
    out_sen = {}
    for sen, vals in sorted(per_seniority.items()):
        n_s = len(vals)
        mp, mr, mf = (sum(v[i] for v in vals)/n_s for i in range(3))
        out_sen[sen] = {"n": n_s, "precision": round(mp, 3),
                        "recall": round(mr, 3), "f1": round(mf, 3)}
        print(f"    {sen:<10} (n={n_s:>3})  Prec={mp:.3f}  Rec={mr:.3f}  F1={mf:.3f}")

    print("\n  NOTA: valutazione per ID ESCO esatto — lower bound.\n")
    return {
        "n_cv": len(all_p),
        "avg_precision": round(ap_, 3),
        "avg_recall": round(ar_, 3),
        "avg_f1": round(af_, 3),
        "tp": tp_t, "fp": fp_t, "fn": fn_t,
        "per_template": out_tpl,
        "per_seniority": out_sen,
    }


def main():
    ap = argparse.ArgumentParser(description="Analisi parser SkillPath AI")
    ap.add_argument("--section", choices=["dataset", "threshold", "filtri", "gt", "all"],
                    default="all", help="Sezione da eseguire")
    ap.add_argument("--n", type=int, default=10,
                    help="Numero CV per la valutazione ground truth riparsando i PDF "
                         "(default 10; ignorato con --from-batch)")
    ap.add_argument("--from-batch", dest="from_batch", action="store_true",
                    help="Valuta su TUTTI i CV di outputs/cv_batch_results.json "
                         "invece di riparsare un campione di PDF (consigliato: "
                         "è la modalità confrontabile con l'analisi degli annunci)")
    ap.add_argument("--batch-file", default=None,
                    help="Percorso del file di batch (default outputs/cv_batch_results.json)")
    args = ap.parse_args()

    os.chdir(BASE_DIR)

    gt_results = None

    if args.section in ("all", "dataset"):
        sezione_dataset()

    if args.section in ("all", "threshold"):
        sezione_threshold()

    if args.section in ("all", "filtri"):
        sezione_filtri()

    if args.section in ("all", "gt"):
        if args.from_batch:
            batch = Path(args.batch_file) if args.batch_file else (
                BASE_DIR / "outputs" / "cv_batch_results.json"
            )
            gt_results = sezione_ground_truth_da_batch(batch)
            if not gt_results:
                print(f"  [{batch} non trovato — eseguo prima "
                      f"python tests/batch_parse_cvs.py]")
        else:
            gt_results = sezione_ground_truth(n_cv=args.n)

    # Salva risultati in JSON
    out = {
        "ground_truth_eval": gt_results,
    }
    out_path = BASE_DIR / "outputs" / "analisi_risultati.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n  [Risultati salvati in {out_path}]")


if __name__ == "__main__":
    main()
