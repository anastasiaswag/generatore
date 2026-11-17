"""
streamlit_app.py  —  SkillPath AI
====================================
Frontend minimale per la pipeline CV ↔ Job Description.

Non contiene logica di business: richiama solo i moduli già presenti
in src/ (main_parser, job_parser, matching_engine, course_recommender).

Modalità supportate:
    1. 1 CV ↔ 1 annuncio                       (confronto singolo)
    2. 1 annuncio ↔ più CV  (ranking candidati) — scenario recruiter
    3. 1 CV ↔ più annunci   (ranking annunci)   — scenario candidato

Per i confronti multipli si può usare il dataset sintetico già elaborato
in batch (outputs/cv_batch_results.json, outputs/batch_job_results.json —
istantaneo, nessun re-parsing) oppure caricare più file reali dal vivo
(più lento: ogni file passa dal parser semantico).

Uso (dalla radice del progetto):
    streamlit run app/streamlit_app.py
    # oppure, se 'streamlit' non è nel PATH:
    python -m streamlit run app/streamlit_app.py

NOTA: al primo utilizzo, il caricamento del modello semantico
(sentence-transformers / scipy / sklearn) può richiedere alcuni minuti
su Windows — è normale, non è un blocco.
"""

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

BASE_DIR    = Path(__file__).resolve().parent.parent  # radice progetto (app/ è un livello sotto)
SRC_DIR     = BASE_DIR / "src"
CONFIG_DIR  = BASE_DIR / "config"
JOBS_DIR    = BASE_DIR / "job_descriptions"
OUTPUTS_DIR = BASE_DIR / "outputs"

sys.path.insert(0, str(SRC_DIR))

st.set_page_config(page_title="SkillPath AI", page_icon="🎯", layout="wide")


# ══════════════════════════════════════════════════════════════════════════════
# STILE — piccolo strato di CSS sopra il tema di config.toml
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
.chip-row { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; margin-bottom:4px; }
.chip {
    display:inline-block; padding:4px 12px; border-radius:999px;
    font-size:0.82rem; font-weight:500; line-height:1.2;
}
.grade-badge {
    display:inline-block; padding:10px 20px; border-radius:10px;
    font-weight:700; font-size:1.15rem; text-align:center;
}
div[data-testid="stMetricValue"] { font-size:1.6rem; }
.block-container { padding-top: 2rem; }
hr { margin: 1.2rem 0; }
</style>
""", unsafe_allow_html=True)

GRADE_STYLE = {
    "ottimo":        {"color": "#1B8A5A", "label": "Ottimo"},
    "buono":         {"color": "#2E5EAA", "label": "Buono"},
    "discreto":      {"color": "#D98E04", "label": "Discreto"},
    "insufficiente": {"color": "#C0392B", "label": "Insufficiente"},
}

MODE_SINGLE     = "1 CV ↔ 1 annuncio"
MODE_CANDIDATES = "1 annuncio ↔ più CV  (ranking candidati)"
MODE_JOBS       = "1 CV ↔ più annunci  (ranking annunci)"


def chip(text: str, color: str, filled: bool = False) -> str:
    bg = color if filled else f"{color}1f"
    fg = "#ffffff" if filled else color
    return (f'<span class="chip" style="background:{bg};color:{fg};'
            f'border:1px solid {color}66;">{text}</span>')


# ══════════════════════════════════════════════════════════════════════════════
# CARICAMENTO RISORSE (pesanti — cache per sessione, lazy)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def _get_cv_parser():
    from main_parser import MainParser
    return MainParser()


@st.cache_resource(show_spinner=False)
def _get_job_parser():
    from job_parser import JobParser
    return JobParser()


@st.cache_resource(show_spinner=False)
def _get_matching_engine():
    from matching_engine import JobMatchingEngine
    return JobMatchingEngine()


@st.cache_resource(show_spinner=False)
def _get_course_recommender():
    from course_recommender import CourseRecommender
    return CourseRecommender(str(CONFIG_DIR / "course_index.json"))


@st.cache_data(show_spinner=False)
def _list_sample_jobs():
    """Elenca gli annunci sintetici con un'etichetta leggibile (Ruolo · Area)."""
    if not JOBS_DIR.exists():
        return []
    items = []
    for p in sorted(JOBS_DIR.glob("job_*.txt")):
        meta = {}
        try:
            for line in p.read_text(encoding="utf-8").splitlines()[:5]:
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
        except Exception:
            pass
        label = f"{meta.get('Ruolo', p.stem)}  ·  {meta.get('Area', '?')}"
        items.append((str(p), label))
    return items


@st.cache_data(show_spinner=False)
def _load_batch_jobs():
    """Carica outputs/batch_job_results.json (1000 annunci già parsati)."""
    path = OUTPUTS_DIR / "batch_job_results.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.warning(
            "outputs/batch_job_results.json è presente ma corrotto o vuoto. "
            "Rigeneralo con: `python tests/batch_test_job_parser.py`"
        )
        return []


@st.cache_data(show_spinner=False)
def _load_batch_cvs():
    """Carica outputs/cv_batch_results.json (CV sintetici già parsati)."""
    path = OUTPUTS_DIR / "cv_batch_results.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.warning(
            "outputs/cv_batch_results.json è presente ma corrotto o vuoto. "
            "Rigeneralo con: `python tests/batch_parse_cvs.py`"
        )
        return []


def _save_upload(uploaded_file) -> str:
    """Salva un file caricato da Streamlit in un file temporaneo e ne ritorna il path."""
    suffix = Path(uploaded_file.name).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return tmp.name


def _parse_uploaded_cvs(files) -> list[tuple[str, dict]]:
    parser = _get_cv_parser()
    out = []
    prog = st.progress(0.0, text="Parsing CV...")
    n = len(files)
    for i, f in enumerate(files, 1):
        try:
            path = _save_upload(f)
            profile = parser.parse_cv(path)
            out.append((f.name, profile))
        except Exception as e:
            st.warning(f"Errore nel parsing di {f.name}: {e}")
        prog.progress(i / n, text=f"Parsing CV... ({i}/{n})")
    prog.empty()
    return out


def _parse_uploaded_jobs(files) -> list[tuple[str, dict]]:
    parser = _get_job_parser()
    out = []
    prog = st.progress(0.0, text="Parsing annunci...")
    n = len(files)
    for i, f in enumerate(files, 1):
        try:
            path = _save_upload(f)
            profile = parser.parse_job(path)
            label = profile.get("raw_title") or f.name
            out.append((label, profile))
        except Exception as e:
            st.warning(f"Errore nel parsing di {f.name}: {e}")
        prog.progress(i / n, text=f"Parsing annunci... ({i}/{n})")
    prog.empty()
    return out


def _run_batch_match(base_profile: dict, others: list[tuple[str, dict]], base_is_cv: bool,
                      progress_label: str) -> list[dict]:
    """Confronta base_profile con ciascun elemento di 'others' e ordina per punteggio."""
    engine = _get_matching_engine()
    results = []
    n = len(others)
    prog = st.progress(0.0, text=progress_label)
    for i, (label, prof) in enumerate(others, 1):
        try:
            m = engine.match(base_profile, prof) if base_is_cv else engine.match(prof, base_profile)
            results.append({"label": label, "match": m})
        except Exception as e:
            st.warning(f"Errore nel confronto con {label}: {e}")
        prog.progress(i / n, text=f"{progress_label} ({i}/{n})")
    prog.empty()
    results.sort(key=lambda r: r["match"]["match_score"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# BLOCCHI DI RENDERING
# ══════════════════════════════════════════════════════════════════════════════

def render_cv_summary(profile: dict, label: str) -> None:
    cv           = profile.get("cv", {})
    persona      = cv.get("persona", {})
    work_exp     = cv.get("work_experience", [])
    skills       = cv.get("skills", {})
    all_matches  = skills.get("all_matches", [])
    essential_ids = set(skills.get("essential_ids", []))
    languages    = cv.get("languages", [])

    st.markdown(f"**{label}**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Seniority", str(persona.get("seniority", "?")).capitalize())
    c2.metric("Anni esperienza", f"{persona.get('years_of_experience', 0):.1f}")
    c3.metric("Skill trovate", len(all_matches))

    if work_exp:
        st.caption(f"Ruolo rilevato: **{work_exp[0].get('label', '')}**")

    if all_matches:
        with st.expander(f"Skill individuate ({len(all_matches)})"):
            st.caption("In blu le skill classificate come essenziali, in grigio le opzionali.")
            html = "".join(
                chip(m["label"], "#2E5EAA", filled=m["id"] in essential_ids)
                for m in sorted(all_matches, key=lambda x: x["score"], reverse=True)
            )
            st.markdown(f'<div class="chip-row">{html}</div>', unsafe_allow_html=True)

    if languages:
        with st.expander(f"Lingue rilevate ({len(languages)})"):
            for l in languages:
                st.write(f"- {l.get('label','?')}  (score {l.get('score',0):.2f})")


def render_job_summary(profile: dict) -> None:
    occ          = profile.get("occupation") or {}
    skills       = profile.get("skills", {})
    all_matches  = skills.get("all_matches", [])
    req_ids      = set(skills.get("required_ids", []))
    pref_ids     = set(skills.get("preferred_ids", []))

    st.markdown(f"**{profile.get('raw_title') or 'Annuncio senza titolo'}**")
    if occ.get("label"):
        st.caption(f"Occupazione rilevata: **{occ['label']}**  (score {occ.get('score', 0):.2f})")

    c1, c2 = st.columns(2)
    c1.metric("Skill richieste", len(req_ids))
    c2.metric("Skill preferibili", len(pref_ids))

    if all_matches:
        with st.expander(f"Skill nell'annuncio ({len(all_matches)})"):
            st.caption("In blu le skill richieste, in grigio le preferibili.")
            html = "".join(
                chip(m["label"], "#2E5EAA", filled=m["id"] in req_ids)
                for m in sorted(all_matches, key=lambda x: x["score"], reverse=True)
            )
            st.markdown(f'<div class="chip-row">{html}</div>', unsafe_allow_html=True)


def render_match_result(result: dict) -> None:
    grade = result.get("grade", "insufficiente")
    style = GRADE_STYLE.get(grade, GRADE_STYLE["insufficiente"])
    score = result.get("match_score", 0.0)

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.metric("Compatibilità", f"{score:.0%}")
    with c2:
        st.markdown(
            f'<div class="grade-badge" style="background:{style["color"]}1f;'
            f'color:{style["color"]};border:1px solid {style["color"]}">{style["label"]}</div>',
            unsafe_allow_html=True,
        )
    with c3:
        occ = result.get("occupation_match", {})
        if occ.get("candidate_label") and occ.get("job_label"):
            st.caption(f"Ruolo candidato: {occ['candidate_label']}")
            st.caption(f"Ruolo richiesto: {occ['job_label']}  ·  similarità {occ.get('similarity', 0):.2f}")

    st.progress(min(max(score, 0.0), 1.0))

    matched = result.get("matched_skills", [])
    gap     = result.get("skill_gap", [])

    mc, gc = st.columns(2)
    with mc:
        st.markdown(f"**✅ Skill coperte ({len(matched)})**")
        for m in sorted(matched, key=lambda x: x["score"], reverse=True):
            detail = "match esatto" if m["match_type"] == "exact" else f"match semantico (via \"{m.get('matched_by','')}\")"
            st.markdown(f"- **{m['label']}** — {detail}, score {m['score']:.2f}")
        if not matched:
            st.caption("Nessuna skill coperta.")
    with gc:
        st.markdown(f"**⚠️ Skill mancanti ({len(gap)})**")
        for g in gap:
            reuse = g.get("reuse_level", "")
            freq  = g.get("occupation_freq", 0)
            st.markdown(f"- **[{g.get('priority', '?')}] {g['label']}**  —  {reuse}, richiesta da {freq} occupazioni ESCO")
        if not gap:
            st.caption("Nessun gap: copertura completa!")


def render_roadmap(roadmap: list[dict]) -> None:
    if not roadmap:
        st.caption("Nessuna raccomandazione disponibile.")
        return
    for item in roadmap:
        title = f"[{item['priority']}] {item['skill_label']}  ·  {item['n_available']} corsi disponibili"
        with st.expander(title):
            if not item["courses"]:
                st.write("Nessun corso trovato per questa skill.")
                continue
            for c in item["courses"]:
                stars = "★" * round(c.get("rating", 0) or 0)
                st.markdown(
                    f"**[{c.get('title','(senza titolo)')}]({c.get('url','')})**  \n"
                    f"{c.get('provider','')}  ·  {stars} {c.get('rating','')}  ·  {c.get('level','')}"
                )


def render_course_button_and_roadmap(match_result: dict, state_key: str) -> None:
    """Bottone 'Genera roadmap corsi' + visualizzazione, riusabile in ogni modalità."""
    gap = match_result.get("skill_gap", [])
    if not gap:
        st.success("Nessuna skill mancante: nessun corso da suggerire.")
        return
    if st.button("Genera roadmap corsi", key=f"course_btn_{state_key}"):
        with st.spinner("Cerco i corsi più pertinenti..."):
            rec = _get_course_recommender()
            st.session_state[state_key] = rec.recommend(gap)
    if st.session_state.get(state_key):
        render_roadmap(st.session_state[state_key])


def render_cv_input_block(key_prefix: str, profile_key: str, label_key: str,
                           reset_keys: tuple[str, ...] = ()) -> None:
    """
    Blocco UI per scegliere UN CV: upload di un file reale oppure selezione
    diretta di un CV già pronto nel dataset sintetico (cv_batch_results.json —
    nessun parsing necessario, istantaneo).
    """
    source = st.radio(
        "Sorgente CV", ["Carica file", "Scegli dal dataset"],
        horizontal=True, label_visibility="collapsed", key=f"{key_prefix}_cv_source",
    )

    if source == "Carica file":
        cv_file = st.file_uploader("Carica CV (PDF o DOCX)", type=["pdf", "docx"], key=f"{key_prefix}_cv_uploader")
        if st.button("Analizza CV", disabled=cv_file is None, key=f"{key_prefix}_cv_analyze"):
            with st.spinner("Carico il modello semantico e analizzo il CV (la prima volta può richiedere qualche minuto)..."):
                path = _save_upload(cv_file)
                parser = _get_cv_parser()
                st.session_state[profile_key] = parser.parse_cv(path)
                st.session_state[label_key]   = cv_file.name
                for rk in reset_keys:
                    st.session_state[rk] = None
    else:
        batch_cvs = _load_batch_cvs()
        if not batch_cvs:
            st.warning("outputs/cv_batch_results.json non trovato o corrotto. Esegui prima `python tests/batch_parse_cvs.py`.")
        else:
            options = []
            for c in batch_cvs:
                sen  = c.get("cv", {}).get("persona", {}).get("seniority", "?")
                we   = c.get("cv", {}).get("work_experience", [])
                role = we[0]["label"] if we else ""
                label = f"{c.get('cv_id', '?')}  ·  {sen}" + (f"  ·  {role}" if role else "")
                options.append((label, c))
            choice = st.selectbox("Scegli un CV dal dataset", options,
                                   format_func=lambda x: x[0], key=f"{key_prefix}_cv_select")
            if choice and st.button("Usa questo CV", key=f"{key_prefix}_cv_use"):
                st.session_state[profile_key] = choice[1]
                st.session_state[label_key]   = choice[0]
                for rk in reset_keys:
                    st.session_state[rk] = None


def render_ranking_table(results: list[dict], label_header: str, key: str) -> dict | None:
    """Mostra la tabella di ranking e un selettore per il dettaglio di una riga."""
    if not results:
        st.info("Nessun risultato da mostrare.")
        return None
    rows = [{
        label_header:      r["label"],
        "Compatibilità":   f"{r['match']['match_score']:.0%}",
        "Grade":           GRADE_STYLE.get(r["match"]["grade"], {}).get("label", r["match"]["grade"]),
        "Skill coperte":   len(r["match"].get("matched_skills", [])),
        "Skill mancanti":  len(r["match"].get("skill_gap", [])),
    } for r in results]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    options = [r["label"] for r in results]
    chosen = st.selectbox("Vedi dettaglio di:", options, key=f"detail_select_{key}")
    return next((r for r in results if r["label"] == chosen), None)


# ══════════════════════════════════════════════════════════════════════════════
# STATO SESSIONE
# ══════════════════════════════════════════════════════════════════════════════

for key in ("cv_profile", "cv_label", "job_profile", "match_result", "roadmap",
            "candidates_uploaded", "jobs_uploaded",
            "ranking_candidates", "ranking_jobs",
            "roadmap_candidates", "roadmap_jobs"):
    st.session_state.setdefault(key, None)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("SkillPath AI")
    st.caption("Matching CV ↔ Job Description su ontologia ESCO")
    st.divider()
    st.caption(
        "Il primo utilizzo di ogni sezione carica un modello semantico "
        "(sentence-transformers): può richiedere qualche minuto, poi resta "
        "in cache per tutta la sessione."
    )
    n_batch_cvs  = len(_load_batch_cvs())
    n_batch_jobs = len(_load_batch_jobs())
    st.caption(f"Dataset sintetico disponibile: {n_batch_cvs} CV, {n_batch_jobs} annunci già elaborati.")
    st.divider()
    if st.button("↺ Ricomincia da capo", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# HEADER + SELETTORE MODALITÀ
# ══════════════════════════════════════════════════════════════════════════════

st.title("🎯 SkillPath AI")
st.caption("Carica un CV e un annuncio di lavoro per calcolare la compatibilità e generare una roadmap di corsi.")

mode = st.radio(
    "Modalità", [MODE_SINGLE, MODE_CANDIDATES, MODE_JOBS],
    horizontal=True,
)
st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# MODALITÀ 1 — 1 CV ↔ 1 annuncio
# ══════════════════════════════════════════════════════════════════════════════

if mode == MODE_SINGLE:

    col_cv, col_job = st.columns(2, gap="large")

    with col_cv:
        st.subheader("1 · Curriculum")
        render_cv_input_block("single", "cv_profile", "cv_label", reset_keys=("match_result", "roadmap"))

        if st.session_state.cv_profile:
            render_cv_summary(st.session_state.cv_profile, st.session_state.cv_label)
        else:
            st.info("Carica un CV o scegline uno dal dataset sintetico.")

    with col_job:
        st.subheader("2 · Annuncio di lavoro")
        job_mode = st.radio(
            "Sorgente annuncio", ["Incolla testo", "Carica file", "Esempio dal dataset"],
            horizontal=True, label_visibility="collapsed", key="job_mode_single",
        )

        job_text, job_path = None, None
        if job_mode == "Incolla testo":
            job_text = st.text_area(
                "Testo dell'annuncio", height=170,
                placeholder="Incolla qui il testo dell'offerta di lavoro...",
                label_visibility="collapsed",
            )
        elif job_mode == "Carica file":
            job_file = st.file_uploader("Carica annuncio (PDF, DOCX o TXT)", type=["pdf", "docx", "txt"], key="job_uploader")
            if job_file:
                job_path = _save_upload(job_file)
        else:
            job_items = _list_sample_jobs()
            if job_items:
                choice = st.selectbox(
                    "Scegli un annuncio di esempio", job_items,
                    format_func=lambda x: x[1], label_visibility="collapsed",
                )
                if choice:
                    job_path = choice[0]
            else:
                st.warning("Cartella job_descriptions/ non trovata o vuota.")

        if st.button("Analizza annuncio", disabled=not (job_text or job_path), use_container_width=True):
            with st.spinner("Carico il modello semantico e analizzo l'annuncio (la prima volta può richiedere qualche minuto)..."):
                jparser = _get_job_parser()
                result = jparser.parse_job_text(job_text) if job_text else jparser.parse_job(job_path)
                st.session_state.job_profile = result
                st.session_state.match_result = None
                st.session_state.roadmap = None

        if st.session_state.job_profile:
            render_job_summary(st.session_state.job_profile)
        else:
            st.info("Incolla un testo, carica un file o scegli un esempio, poi premi \"Analizza annuncio\".")

    st.divider()
    st.subheader("3 · Compatibilità")

    can_match = bool(st.session_state.cv_profile and st.session_state.job_profile)
    if st.button("Confronta CV e annuncio", disabled=not can_match, type="primary"):
        with st.spinner("Calcolo il punteggio di compatibilità..."):
            engine = _get_matching_engine()
            st.session_state.match_result = engine.match(
                st.session_state.cv_profile, st.session_state.job_profile
            )
            st.session_state.roadmap = None

    if st.session_state.match_result:
        render_match_result(st.session_state.match_result)
        st.divider()
        st.subheader("4 · Corsi consigliati")
        render_course_button_and_roadmap(st.session_state.match_result, "roadmap")
    elif not can_match:
        st.info("Analizza sia il CV sia l'annuncio per calcolare la compatibilità.")


# ══════════════════════════════════════════════════════════════════════════════
# MODALITÀ 2 — 1 annuncio ↔ più CV  (ranking candidati)
# ══════════════════════════════════════════════════════════════════════════════

elif mode == MODE_CANDIDATES:

    st.subheader("1 · Annuncio di riferimento")
    job_mode = st.radio(
        "Sorgente annuncio", ["Incolla testo", "Carica file", "Esempio dal dataset"],
        horizontal=True, label_visibility="collapsed", key="job_mode_rc",
    )
    job_text, job_path = None, None
    if job_mode == "Incolla testo":
        job_text = st.text_area("Testo dell'annuncio", height=150, label_visibility="collapsed",
                                 placeholder="Incolla qui il testo dell'offerta di lavoro...", key="rc_job_text")
    elif job_mode == "Carica file":
        job_file = st.file_uploader("Carica annuncio (PDF, DOCX o TXT)", type=["pdf", "docx", "txt"], key="rc_job_uploader")
        if job_file:
            job_path = _save_upload(job_file)
    else:
        job_items = _list_sample_jobs()
        if job_items:
            choice = st.selectbox("Scegli un annuncio di esempio", job_items,
                                   format_func=lambda x: x[1], label_visibility="collapsed", key="rc_job_select")
            if choice:
                job_path = choice[0]
        else:
            st.warning("Cartella job_descriptions/ non trovata o vuota.")

    if st.button("Analizza annuncio", disabled=not (job_text or job_path), key="rc_analyze_job"):
        with st.spinner("Analizzo l'annuncio..."):
            jparser = _get_job_parser()
            result = jparser.parse_job_text(job_text) if job_text else jparser.parse_job(job_path)
            st.session_state.job_profile = result
            st.session_state.ranking_candidates = None

    if st.session_state.job_profile:
        render_job_summary(st.session_state.job_profile)

    st.divider()
    st.subheader("2 · Candidati da confrontare")
    source = st.radio("Sorgente CV", ["Dataset sintetico già elaborato", "Carica più CV"], horizontal=True)

    candidates: list[tuple[str, dict]] = []

    if source == "Dataset sintetico già elaborato":
        batch_cvs = _load_batch_cvs()
        if not batch_cvs:
            st.warning("outputs/cv_batch_results.json non trovato. Esegui prima `python tests/batch_parse_cvs.py`.")
        else:
            seniority = st.selectbox("Filtra per seniority", ["Tutti", "junior", "mid", "senior"])
            filtered = batch_cvs if seniority == "Tutti" else [
                c for c in batch_cvs if c.get("cv", {}).get("persona", {}).get("seniority") == seniority
            ]
            max_n = st.number_input("Numero massimo di candidati da confrontare", 1, max(len(filtered), 1),
                                     min(100, max(len(filtered), 1)))
            for c in filtered[:max_n]:
                sen = c.get("cv", {}).get("persona", {}).get("seniority", "?")
                label = f"{c.get('cv_id', '?')}  ·  {sen}"
                candidates.append((label, c))
            st.caption(f"{len(candidates)} candidati selezionati su {len(filtered)} disponibili.")
    else:
        cv_files = st.file_uploader("Carica più CV (PDF o DOCX)", type=["pdf", "docx"],
                                     accept_multiple_files=True, key="rc_cv_uploader")
        if cv_files and st.button("Analizza candidati caricati"):
            st.session_state.candidates_uploaded = _parse_uploaded_cvs(cv_files)
        if st.session_state.candidates_uploaded:
            candidates = st.session_state.candidates_uploaded
            st.caption(f"{len(candidates)} CV analizzati.")

    if st.button("Confronta candidati con l'annuncio", type="primary",
                  disabled=not (st.session_state.job_profile and candidates)):
        st.session_state.ranking_candidates = _run_batch_match(
            st.session_state.job_profile, candidates, base_is_cv=False,
            progress_label="Confronto candidati...",
        )
        st.session_state.roadmap_candidates = None

    if st.session_state.ranking_candidates:
        st.divider()
        st.subheader("3 · Ranking candidati")
        selected = render_ranking_table(st.session_state.ranking_candidates, "Candidato", "candidates")
        if selected:
            render_match_result(selected["match"])
            st.subheader("Corsi consigliati per questo candidato")
            render_course_button_and_roadmap(selected["match"], "roadmap_candidates")


# ══════════════════════════════════════════════════════════════════════════════
# MODALITÀ 3 — 1 CV ↔ più annunci  (ranking annunci)
# ══════════════════════════════════════════════════════════════════════════════

elif mode == MODE_JOBS:

    st.subheader("1 · Curriculum di riferimento")
    render_cv_input_block("rj", "cv_profile", "cv_label", reset_keys=("ranking_jobs", "roadmap_jobs"))

    if st.session_state.cv_profile:
        render_cv_summary(st.session_state.cv_profile, st.session_state.cv_label)

    st.divider()
    st.subheader("2 · Annunci da confrontare")
    source = st.radio("Sorgente annunci", ["Dataset sintetico già elaborato", "Carica più annunci"], horizontal=True)

    jobs: list[tuple[str, dict]] = []

    if source == "Dataset sintetico già elaborato":
        batch_jobs = _load_batch_jobs()
        if not batch_jobs:
            st.warning("outputs/batch_job_results.json non trovato. Esegui prima `python tests/batch_test_job_parser.py`.")
        else:
            areas = sorted({j.get("meta", {}).get("area", "") for j in batch_jobs if j.get("meta", {}).get("area")})
            area = st.selectbox("Filtra per area", ["Tutte"] + areas)
            filtered = batch_jobs if area == "Tutte" else [
                j for j in batch_jobs if j.get("meta", {}).get("area") == area
            ]
            max_n = st.number_input("Numero massimo di annunci da confrontare", 1, max(len(filtered), 1),
                                     min(100, max(len(filtered), 1)))
            for j in filtered[:max_n]:
                meta = j.get("meta", {})
                label = f"{meta.get('ruolo') or j.get('raw_title') or j.get('job_id', '?')}  ·  {meta.get('area','?')}"
                jobs.append((label, j))
            st.caption(f"{len(jobs)} annunci selezionati su {len(filtered)} disponibili.")
    else:
        job_files = st.file_uploader("Carica più annunci (PDF, DOCX o TXT)", type=["pdf", "docx", "txt"],
                                      accept_multiple_files=True, key="rj_job_uploader")
        if job_files and st.button("Analizza annunci caricati"):
            st.session_state.jobs_uploaded = _parse_uploaded_jobs(job_files)
        if st.session_state.jobs_uploaded:
            jobs = st.session_state.jobs_uploaded
            st.caption(f"{len(jobs)} annunci analizzati.")

    if st.button("Confronta CV con gli annunci", type="primary",
                  disabled=not (st.session_state.cv_profile and jobs)):
        st.session_state.ranking_jobs = _run_batch_match(
            st.session_state.cv_profile, jobs, base_is_cv=True,
            progress_label="Confronto annunci...",
        )
        st.session_state.roadmap_jobs = None

    if st.session_state.ranking_jobs:
        st.divider()
        st.subheader("3 · Ranking annunci")
        selected = render_ranking_table(st.session_state.ranking_jobs, "Annuncio", "jobs")
        if selected:
            render_match_result(selected["match"])
            st.subheader("Corsi consigliati per questo annuncio")
            render_course_button_and_roadmap(selected["match"], "roadmap_jobs")
