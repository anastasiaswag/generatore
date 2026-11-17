"""
annota_cv.py  —  SkillPath AI
==============================
Interfaccia di annotazione manuale dei curriculum reali.

Legge il pool prodotto da `analysis/genera_pool_annotazione.py`, mostra una
competenza candidata per volta accanto al testo del documento, e registra il
giudizio umano. Il risultato è la ground truth con cui `analysis/
valuta_annotazione.py` calcola precisione e richiamo su dati reali.

TRE SCELTE DI PROGETTO, E IL MOTIVO
───────────────────────────────────
1. NESSUN MODELLO VIENE CARICATO QUI.
   La ricerca per aggiungere una competenza mancata è testuale, non
   semantica: filtra le etichette ESCO per sottostringa. Se fosse semantica
   l'app impiegherebbe minuti ad avviarsi e — soprattutto — i candidati
   suggeriti verrebbero dallo stesso modello che si sta valutando.

2. SI PUÒ AGGIUNGERE CIÒ CHE IL PARSER NON HA PROPOSTO.
   È il punto che rende la misura non circolare. Un'annotazione limitata ad
   accettare o rifiutare le proposte del sistema darebbe richiamo 1,0 per
   costruzione: non misurerebbe il richiamo, lo assumerebbe.

3. I GIUDIZI SONO SALVATI PER COPPIA (documento, competenza).
   Non per posizione nella lista. Se il pool viene rigenerato con soglie
   diverse, i giudizi già dati restano attaccati alla loro coppia e si
   annotano solo le voci nuove. La stessa precauzione adottata nella
   revisione dei corsi, dove un cambio di campionamento rischiava di
   invalidare i giudizi già raccolti.

CHE COSA SIGNIFICANO LE TRE RISPOSTE
────────────────────────────────────
  SÌ       la competenza è realmente dimostrata dal documento
  NO       non lo è: il match è un falso positivo
  INCERTO  il testo non permette di decidere

Gli incerti non vengono conteggiati né fra i corretti né fra gli errori, e la
loro quota va riportata: se fosse alta, la ground truth stessa sarebbe fragile.

Uso (dalla radice del progetto):
    python -m streamlit run app/annota_cv.py
"""

import json
import unicodedata
from datetime import datetime
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_FILE = BASE_DIR / "outputs" / "pool_annotazione.json"
ANNOT_FILE = BASE_DIR / "outputs" / "annotazione_cv_reali.json"
SKILLS_FILE = BASE_DIR / "dataset" / "source" / "skills.json"

st.set_page_config(page_title="SkillPath — Annotazione", layout="wide")


# ── Caricamento ───────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def carica_pool(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def carica_etichette(path: str) -> list:
    """
    Prepara l'indice testuale per la ricerca libera.

    Ogni voce è (chiave_normalizzata, id, etichetta). Le denominazioni
    alternative sono incluse perché una competenza può comparire nel CV con un
    nome diverso da quello primario — è la stessa ragione per cui l'indice
    degli embedding le include.
    """
    p = Path(path)
    if not p.exists():
        return []
    dati = json.loads(p.read_text(encoding="utf-8"))
    voci = []
    for sid, s in dati.items():
        primaria = s.get("label", "")
        nomi = [primaria] + list(s.get("alt_labels") or [])
        for n in nomi:
            if n:
                voci.append((normalizza(n), sid, primaria))
    return voci


def normalizza(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def carica_annotazioni() -> dict:
    if ANNOT_FILE.exists():
        try:
            return json.loads(ANNOT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            st.error("annotazione_cv_reali.json illeggibile: non lo sovrascrivo. "
                     "Spostalo o riparalo prima di continuare.")
            st.stop()
    return {"giudizi": {}, "aggiornato": None}


def salva(annot: dict) -> None:
    """Salva a ogni decisione: una sessione interrotta non perde nulla."""
    annot["aggiornato"] = datetime.now().isoformat(timespec="seconds")
    ANNOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANNOT_FILE.write_text(json.dumps(annot, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def chiave(cv_id: str, skill_id: str) -> str:
    return f"{cv_id}|{skill_id}"


# ── Stato ─────────────────────────────────────────────────────────────────────

pool = carica_pool(str(POOL_FILE))
if not pool:
    st.error(f"Pool non trovato in {POOL_FILE}.\n\n"
             "Generalo prima con:\n\n"
             "`python analysis/genera_pool_annotazione.py --cartella \"...\" --anonimo`")
    st.stop()

documenti = pool.get("documenti", [])
if "annot" not in st.session_state:
    st.session_state.annot = carica_annotazioni()
if "i_doc" not in st.session_state:
    st.session_state.i_doc = 0

annot = st.session_state.annot
giudizi = annot["giudizi"]


# ── Barra laterale: avanzamento e navigazione ─────────────────────────────────

with st.sidebar:
    st.subheader("Avanzamento")

    tot = sum(len(d["candidati"]) for d in documenti)
    fatti = sum(1 for d in documenti for c in d["candidati"]
                if chiave(d["cv_id"], c["id"]) in giudizi)
    st.progress(fatti / tot if tot else 0.0)
    st.caption(f"{fatti} / {tot} candidati giudicati")

    etichette_doc = []
    for d in documenti:
        n = sum(1 for c in d["candidati"]
                if chiave(d["cv_id"], c["id"]) in giudizi)
        segno = "✓" if n == len(d["candidati"]) else f"{n}/{len(d['candidati'])}"
        etichette_doc.append(f"{d['cv_id']}  ·  {segno}")

    scelta = st.radio("Documento", range(len(documenti)),
                      format_func=lambda i: etichette_doc[i],
                      index=st.session_state.i_doc)
    st.session_state.i_doc = scelta

    st.divider()
    # Questi due numeri sono la verifica di non aver firmato in bianco: se la
    # quota di rifiuti fosse prossima a zero, l'annotazione non starebbe
    # aggiungendo informazione rispetto all'output del parser.
    si = sum(1 for g in giudizi.values() if g["giudizio"] == "si")
    no = sum(1 for g in giudizi.values() if g["giudizio"] == "no")
    inc = sum(1 for g in giudizi.values() if g["giudizio"] == "incerto")
    agg = sum(1 for g in giudizi.values() if g.get("aggiunta"))
    st.caption("**Bilancio dei giudizi**")
    st.caption(f"sì {si} · no {no} · incerti {inc}")
    st.caption(f"aggiunte manuali: {agg}")
    if si + no >= 30 and no / max(si + no, 1) < 0.05:
        st.warning("Rifiuti sotto il 5%: verifica di non stare accettando "
                   "per inerzia.")


doc = documenti[st.session_state.i_doc]
cv_id = doc["cv_id"]

st.title(f"Annotazione — {cv_id}")

col_testo, col_lavoro = st.columns([1.1, 1])

# ── Colonna sinistra: il documento ────────────────────────────────────────────

with col_testo:
    st.subheader("Testo del curriculum")
    filtro = st.text_input("Cerca nel testo", key=f"filtro_{cv_id}",
                           placeholder="es. Python, saldatura, 2019…")
    righe = doc.get("testo") or []
    if filtro:
        f = normalizza(filtro)
        righe_mostrate = [r for r in righe if f in normalizza(r)]
        st.caption(f"{len(righe_mostrate)} righe su {len(righe)}")
    else:
        righe_mostrate = righe
    st.text_area("Documento", "\n".join(righe_mostrate), height=560,
                 label_visibility="collapsed")

# ── Colonna destra: il candidato corrente ─────────────────────────────────────

with col_lavoro:
    da_fare = [c for c in doc["candidati"]
               if chiave(cv_id, c["id"]) not in giudizi]

    st.subheader("Candidato")
    if not da_fare:
        st.success("Documento completato.")
    else:
        c = da_fare[0]
        st.caption(f"{len(da_fare)} rimasti in questo documento")
        st.markdown(f"### {c['label']}")

        conf = c.get("configurazioni") or []
        in_produzione = "produzione" in conf
        st.caption(
            f"punteggio massimo {c['score_max']:.3f} · "
            f"proposto da: {', '.join(conf) if conf else '—'}"
        )
        if not in_produzione:
            # Distinzione importante: questi candidati non entrano nel calcolo
            # della precisione della configurazione di produzione, ma se
            # giudicati corretti sono suoi falsi negativi.
            st.info("Non proposto dalla configurazione di produzione: se è "
                    "corretto, è un falso negativo.")

        # ── La frase che ha generato il match, nascosta di proposito ──────────
        # Mostrarla subito cambierebbe la domanda: da «questa competenza è
        # dimostrata dal documento?» a «questo abbinamento è plausibile?».
        # La seconda si approva con più facilità, perché si giudica il sistema
        # usando la giustificazione che il sistema stesso fornisce. Resta
        # disponibile per i casi in cui la prova non si trova, e l'uso viene
        # registrato: la differenza fra la quota di accettazione con e senza
        # aiuto misura quanto l'indizio abbia influenzato il giudizio.
        k_riv = f"riv_{cv_id}_{c['id']}"
        frasi = c.get("frasi_origine") or []
        if st.session_state.get(k_riv):
            if frasi:
                for fr in frasi:
                    st.info(f"Frase di origine: «{fr}»")
            else:
                st.caption("Nessuna frase registrata per questo candidato "
                           "(pool generato prima di questa funzione).")
        else:
            if st.button("Mostra da dove viene", key=f"btn_{k_riv}"):
                st.session_state[k_riv] = True
                st.rerun()

        b1, b2, b3 = st.columns(3)

        def registra(valore: str) -> None:
            giudizi[chiave(cv_id, c["id"])] = {
                "cv_id": cv_id,
                "skill_id": c["id"],
                "label": c["label"],
                "giudizio": valore,
                "in_produzione": in_produzione,
                "score_max": c["score_max"],
                "aggiunta": False,
                "rivelato": bool(st.session_state.get(k_riv)),
                "quando": datetime.now().isoformat(timespec="seconds"),
            }
            salva(annot)

        if b1.button("Sì", use_container_width=True, type="primary"):
            registra("si")
            st.rerun()
        if b2.button("No", use_container_width=True):
            registra("no")
            st.rerun()
        if b3.button("Incerto", use_container_width=True):
            registra("incerto")
            st.rerun()

    st.divider()

    # ── Aggiunta manuale ──────────────────────────────────────────────────────
    st.subheader("Aggiungi una competenza mancata")
    st.caption("Cerca fra tutte le etichette ESCO, comprese le denominazioni "
               "alternative. Serve a registrare ciò che nessuna "
               "configurazione ha proposto.")

    etichette = carica_etichette(str(SKILLS_FILE))
    if not etichette:
        st.warning("skills.json non trovato: ricerca non disponibile.")
    else:
        q = st.text_input("Cerca in ESCO", key=f"esco_{cv_id}",
                          placeholder="almeno tre caratteri")
        if q and len(q) >= 3:
            qn = normalizza(q)
            visti, trovati = set(), []
            for chiave_norm, sid, primaria in etichette:
                if qn in chiave_norm and sid not in visti:
                    visti.add(sid)
                    trovati.append((sid, primaria))
                if len(trovati) >= 25:
                    break
            if not trovati:
                st.caption("Nessun risultato.")
            for sid, primaria in trovati:
                k = chiave(cv_id, sid)
                gia = giudizi.get(k)
                etichetta = f"{primaria}" + (
                    f"  — già: {gia['giudizio']}" if gia else "")
                if st.button(etichetta, key=f"add_{cv_id}_{sid}",
                             use_container_width=True, disabled=bool(gia)):
                    giudizi[k] = {
                        "cv_id": cv_id,
                        "skill_id": sid,
                        "label": primaria,
                        "giudizio": "si",
                        "in_produzione": False,
                        "score_max": None,
                        "aggiunta": True,
                        "rivelato": False,
                        "quando": datetime.now().isoformat(timespec="seconds"),
                    }
                    salva(annot)
                    st.rerun()

st.caption(f"Giudizi salvati in {ANNOT_FILE.name} a ogni decisione. "
           f"Puoi chiudere e riprendere quando vuoi.")
