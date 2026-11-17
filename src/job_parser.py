"""
job_parser.py  —  SkillPath AI
================================
Parser per job description / offerte di lavoro.

A differenza del CV parser, non si basa su sezioni rigide (education,
experience, ecc.) ma lavora sull'intero testo in modo generico, adattandosi
a qualsiasi formato di annuncio: PDF, DOCX, testo grezzo incollato.

PIPELINE
--------
  Testo grezzo  →  righe pulite  →  candidati skill  →  match ESCO
                                  ↓
                          marcatori linguistici
                          (required / preferred)

OUTPUT JSON
-----------
{
  "job_id": "...",
  "occupation": { "id": "...", "label": "...", "score": 0.0 },
  "skills": {
    "required_ids":  [...],   # skill esplicitamente richieste
    "preferred_ids": [...],   # skill preferibili / nice-to-have
    "all_matches":   [...]    # tutti i match con score
  },
  "raw_title": "..."          # titolo grezzo estratto dall'annuncio
}

USO
---
  # Da file
  from job_parser import JobParser
  jp = JobParser()
  result = jp.parse_job("offerta.pdf")
  result = jp.parse_job("offerta.docx")

  # Da testo grezzo (es. incollato dall'utente)
  result = jp.parse_job_text("Cerchiamo sviluppatore Python con Django...")

  # CLI (dalla radice del progetto)
  python src/job_parser.py samples/offerta1.txt
  python src/job_parser.py --text "Cerchiamo sviluppatore Python..."
"""

import json
import os
import re
import sys
from pathlib import Path

from pdf_extractor import get_text, filter_lines, is_noise_line
from semantic_mapper import SemanticMapper


BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)
DATA_SRC = BASE_DIR / "dataset" / "source"
DATA_IT  = BASE_DIR / "dataset" / "source_it"
DATA_EN  = BASE_DIR / "dataset" / "source_en"
# Se source_en non esiste, usa source/ come EN di riserva
if not DATA_EN.exists():
    DATA_EN = DATA_SRC


# ══════════════════════════════════════════════════════════════════════════════
# MARCATORI LINGUISTICI  required / preferred
# ══════════════════════════════════════════════════════════════════════════════

_REQUIRED_MARKERS = re.compile(
    r"\b("
    # Aggettivi richiesto/a/i/e (singolare e plurale)
    r"richiest[oaie]|necessari[oa]|indispensabil[ei]|obbligatori[oa]|"
    r"essenzial[ei]|must\s*have|required|mandatory|essential|"
    # Frasi verbali italiane
    r"si\s*richied[ei]|si\s*richiedono|"
    # Header di sezione comuni
    r"requisiti\s*necessari|requisiti\s*minimi|requisiti\s*tecnici|"
    r"competenze\s*richieste|competenze\s*tecniche|"
    r"cosa\s*cerchiamo|profilo\s*richiesto|il\s*profilo\s*ideale|"
    r"il\/la\s*candidato|il\s*candidato\s*ideale|"
    # "Requisiti" da solo come parola (tipico header di sezione)
    r"requisiti|requirements|responsibilities|responsabilit[àa]"
    r")\b",
    re.IGNORECASE,
)

_PREFERRED_MARKERS = re.compile(
    r"\b("
    # Marcatori classici
    r"preferibil[ei]|gradit[ao]|opzional[ei]|nice\s*to\s*have|"
    r"costituisc[ei]\s*titolo|titolo\s*preferenzial[ei]|"
    r"preferred|desirable|advantageous|"
    # Frasi verbali italiane tipiche degli annunci
    r"sarà\s+(considerato|valutato|un)\s+(un\s+)?plus|"
    r"rappresenta\s*(un\s+)?(plus|vantaggio|atout)|"
    r"rappresenter[àa]\s*(un\s+)?(plus|vantaggio)|"
    r"completano\s*il\s*profilo|completer[àa]\s*il\s*profilo|"
    r"costituir[àa]\s*titolo\s*(di\s+)?preferenz[ai]|"
    r"viene\s+considerata?\s+(un\s+)?plus|"
    r"verr[àa]\s+considerata?\s+(un\s+)?(plus|vantaggio)|"
    r"considerata?\s+un\s+(plus|vantaggio)|"
    # Avverbi e aggettivi aggiuntivi
    r"idealmente|preferibilmente|auspicabile|auspicato|"
    r"gradita\s+la\s+conoscenza|gradita\s+(un[a']?\s+)?esperienza|"
    # Header di sezione tipici
    r"requisiti\s*preferenziali|competenze\s*preferibili|"
    r"skill\s*preferenziali|plus\s*del\s*profilo|"
    r"requisiti\s*desiderati|what\s+we[''']d\s+love"
    r")\b",
    re.IGNORECASE,
)

# Split a livello di frase: separa su '.', '!', '?' seguiti da spazio e
# lettera maiuscola (euristica anti-abbreviazioni). Usato per spezzare
# paragrafi di prosa continua in unità più piccole prima dell'estrazione
# candidati — senza, un intero paragrafo viene trattato come "una riga sola"
# e finisce nel fallback grezzo per righe lunghe (solo prime 5 parole).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])")

_SEP_RE   = re.compile(r"[,/;|•·]|\s-\s")
_PAREN_RE = re.compile(r"\(([^)]{2,30})\)")
_QUALI_RE = re.compile(r"(?:quali|come|tra\s+cui|including|such\s+as)[:\s]+(.+)",
                        re.IGNORECASE)
_CONJ_RE  = re.compile(r"\s+(?:e|ed|and|or|o)\s+")

# Stopword usate SOLO come confini per l'estrazione di frasi candidate
# (stile RAKE — Rapid Automatic Keyword Extraction): non filtrano nulla dal
# testo, servono a decidere dove "spezzare" per isolare le sequenze di
# parole di contenuto (potenziali skill) tra due funzioni grammaticali.
_STOPWORDS_EXTRACTION = {
    # inglese — articoli, preposizioni, congiunzioni, ausiliari, filler comuni
    "a","an","the","and","or","but","if","then","of","to","in","on","at","for","with","by",
    "from","as","is","are","was","were","be","been","being","have","has","had","will","would",
    "should","must","can","could","may","might","this","that","these","those","it","its","we",
    "you","your","our","their","they","he","she","who","which","what","when","where","how",
    "not","no","also","very","more","most","some","any","all","such","than","so","because",
    "while","about","into","through","during","before","after","above","below","up","down",
    "out","off","over","under","again","once","here","there","both","each","other","own",
    "same","too","just","only","looking","join","team","role","position","candidate",
    "ideal","strong","good","excellent","great","proven","solid","ability","experience",
    "knowledge","skills","years","plus","preferred","required","mandatory","essential",
    # italiano — equivalenti
    "il","la","lo","gli","le","i","un","una","uno","del","della","dei","degli","delle","di",
    "da","dal","dalla","dai","dagli","dalle","al","alla","ai","agli","alle","nel","nella",
    "nei","negli","nelle","su","sul","sulla","sui","sugli","sulle","con","per","tra","fra",
    "e","ed","o","ma","se","che","chi","cui","non","anche","molto","più","meno","tutto",
    "tutti","tutte","questo","questa","questi","queste","quello","quella","siamo","sono",
    "essere","avere","abbiamo","cerchiamo","candidato","candidata","ideale","ottima",
    "ottimo","buona","buon","esperienza","conoscenza","competenze","anni","richiesto",
    "richiesta","preferibile","gradito","gradita","come",
}


def _extract_content_phrases(text: str, max_words: int = 6) -> list[str]:
    """
    Estrae frasi candidate spezzando il testo sui confini di stopword e
    punteggiatura (stile RAKE): le sequenze di parole "di contenuto" tra due
    stopword diventano candidati. Sostituisce il taglio grezzo "prime N
    parole" — non perde le skill menzionate a metà o fine frase, che è
    proprio il tipo di miss più comune su prosa continua.
    """
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+\-\.]*|[^\w\s]", text)
    phrases: list[str] = []
    current: list[str] = []

    def _flush() -> None:
        if current:
            phrase = " ".join(current[:max_words]).strip()
            if len(phrase) >= 3:
                phrases.append(phrase)
            current.clear()

    for tok in tokens:
        if not re.match(r"\w", tok):
            _flush()          # punteggiatura → confine
            continue
        if tok.lower() in _STOPWORDS_EXTRACTION:
            _flush()          # stopword → confine
            continue
        current.append(tok)
    _flush()

    return phrases


# ══════════════════════════════════════════════════════════════════════════════
# CHUNKING SINTAGMI NOMINALI (opzionale, richiede spaCy)
# ══════════════════════════════════════════════════════════════════════════════
# Alternativa a _extract_content_phrases(): invece di segmentare la frase sui
# confini di stopword, usa l'analisi sintattica per estrarre i sintagmi
# nominali ("un solido background nella gestione dei bioreattori" → "solido
# background", "gestione dei bioreattori").
#
# STATO: NON VALIDATO SPERIMENTALMENTE. È disponibile ma disattivo di default
# (JobParser(use_spacy=True) per attivarlo). Va confrontato A/B con
# l'estrazione a stopword prima di considerarlo un miglioramento: nel corso di
# questo lavoro si è visto che un'aggiunta plausibile ma non misurata (lo
# stadio lessicale) può peggiorare la precisione complessiva.
#
# Installazione:
#     pip install spacy
#     python -m spacy download it_core_news_sm
#     python -m spacy download en_core_web_sm
_SPACY_CACHE: dict = {}


def _spacy_noun_chunks(text: str, max_words: int = 6) -> list[str]:
    """
    Estrae i sintagmi nominali della frase tramite spaCy.

    Ritorna una lista vuota se spaCy o i modelli non sono installati: il
    chiamante deve prevedere il fallback su _extract_content_phrases().
    """
    if _SPACY_CACHE.get("unavailable"):
        return []

    nlp = _SPACY_CACHE.get("nlp")
    if nlp is None:
        try:
            import spacy
        except ImportError:
            print("[job_parser] spaCy non installato: uso l'estrazione standard.")
            _SPACY_CACHE["unavailable"] = True
            return []
        for model in ("it_core_news_sm", "en_core_web_sm"):
            try:
                nlp = spacy.load(model, disable=["ner", "lemmatizer"])
                _SPACY_CACHE["nlp"] = nlp
                print(f"[job_parser] Chunking spaCy attivo (modello {model})")
                break
            except OSError:
                continue
        if nlp is None:
            print(
                "[job_parser] Nessun modello spaCy trovato "
                "(python -m spacy download it_core_news_sm): "
                "uso l'estrazione standard."
            )
            _SPACY_CACHE["unavailable"] = True
            return []

    try:
        doc = nlp(text)
    except Exception as e:
        print(f"[job_parser] Errore spaCy ({e}): uso l'estrazione standard.")
        _SPACY_CACHE["unavailable"] = True
        return []

    phrases: list[str] = []
    seen: set[str] = set()
    for chunk in doc.noun_chunks:
        # Rimuove determinanti e preposizioni iniziali, che non portano
        # informazione e abbassano la qualità del match semantico.
        tokens = [
            t.text for t in chunk
            if t.pos_ not in ("DET", "ADP", "PRON", "PUNCT")
        ]
        if not tokens or len(tokens) > max_words:
            continue
        phrase = " ".join(tokens).strip()
        key = phrase.lower()
        if len(phrase) < 3 or key in seen:
            continue
        seen.add(key)
        phrases.append(phrase)
    return phrases


# ══════════════════════════════════════════════════════════════════════════════
# LIVELLO DI ESPERIENZA RICHIESTO
# ══════════════════════════════════════════════════════════════════════════════
# Il matching engine deve poter confrontare l'esperienza del candidato con
# quella richiesta dall'annuncio, altrimenti tende a proporre posizioni
# sotto-livello: il suo punteggio è una copertura delle skill richieste, e gli
# annunci junior ne elencano meno (10,8 in media contro 16,2 dei senior),
# risultando così più facili da coprire per chiunque.
#
# Il livello si ricava da due segnali, in ordine di priorità:
#   1. termini espliciti nel titolo o nel testo ("junior", "senior", "lead")
#   2. anni di esperienza richiesti ("almeno 5 anni", "3+ years")
# Se nessuno dei due compare, si restituisce None: meglio nessuna informazione
# che una stima inventata, perché il motore sa gestire l'assenza.

_SENIORITY_EXPLICIT = [
    ("senior", re.compile(
        r"\b(senior|sr\.?|lead|principal|head\s+of|capo|responsabile\s+di|"
        r"esperto|expert|manager\s+di|direttore|chief|staff\s+engineer)\b",
        re.IGNORECASE)),
    ("junior", re.compile(
        r"\b(junior|jr\.?|entry[\s-]?level|graduate|neo[\s-]?laureat[oi]|"
        r"trainee|stagista|internship|tirocin|apprendist|"
        r"prima\s+esperienza|no\s+experience\s+required)\b",
        re.IGNORECASE)),
    ("mid", re.compile(
        r"\b(mid[\s-]?level|middle|intermedio|intermediate|"
        r"esperienza\s+intermedia)\b",
        re.IGNORECASE)),
]

# "almeno 5 anni", "5+ years", "3-5 anni di esperienza", "minimo 2 anni"
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*"
    r"(?:anni|anno|years?|yrs?)\b[^.]{0,30}?"
    r"(?:esperienz|experience|nel\s+ruolo|in\s+a\s+similar)",
    re.IGNORECASE,
)


def _detect_seniority(title: str, text: str) -> dict:
    """
    Stima il livello di esperienza richiesto da un annuncio.

    Ritorna {"level": "junior"|"mid"|"senior"|None, "years": int|None,
             "evidence": str} — `evidence` conserva il frammento che ha
    determinato la decisione, utile per il debug e per giustificare il
    risultato all'utente finale.

    Il titolo ha precedenza sul corpo: "Junior Developer" resta junior anche
    se il testo cita "affiancherà figure senior".
    """
    for sorgente in (title or "", text or ""):
        for livello, pattern in _SENIORITY_EXPLICIT:
            m = pattern.search(sorgente)
            if m:
                return {"level": livello, "years": None,
                        "evidence": m.group(0)}

    m = _YEARS_RE.search(text or "")
    if m:
        try:
            anni = int(m.group(1))
        except (TypeError, ValueError):
            anni = None
        if anni is not None:
            # Soglie allineate a quelle usate per generare i CV sintetici
            livello = "junior" if anni < 2 else ("mid" if anni <= 5 else "senior")
            return {"level": livello, "years": anni,
                    "evidence": m.group(0)[:60]}

    return {"level": None, "years": None, "evidence": ""}


# ══════════════════════════════════════════════════════════════════════════════
# ETICHETTE TROPPO GENERICHE (filtro residuo)
# ══════════════════════════════════════════════════════════════════════════════
# Alcune etichette ESCO sono formulate in modo così generico da essere
# abbinate a quasi qualsiasi annuncio pur non essendo la competenza richiesta
# ("lavorare indipendentemente", "prestare attenzione ai dettagli",
# "fornire il primo soccorso"). Vengono escluse dall'output.
#
# RUOLO NELLA PIPELINE — secondario, non principale.
# La causa maggiore dei falsi positivi era a monte: la segmentazione della
# prosa produceva frammenti grammaticali privi di contenuto ("responsible",
# "seeking"), corretta con il vincolo multi-parola in
# _extract_skill_candidates. Questa lista rimuove ciò che resta dopo.
#   nessun rimedio                 P 0.297  R 0.615  F1 0.391
#   solo questa lista              P 0.529  R 0.607  F1 0.551
#   solo vincolo multi-parola      P 0.540  R 0.581  F1 0.546
#   entrambi                       P 0.600  R 0.575  F1 0.572
#
# COSTRUZIONE — analysis/ricostruisci_denylist.py
# Criterio: almeno 10 occorrenze e almeno l'85% di esse errate.
# Validazione su holdout (lista costruita su 405 annunci, effetto misurato
# sui 405 mai visti): P 0.543 → 0.585, F1 0.551 → 0.570, recall invariata.
# Una taratura più permissiva (5 occorrenze, 75% di errore) rendeva di più
# sull'holdout, ma sceglierla sulla base di quel confronto avrebbe reso la
# stima ottimistica: si sono mantenuti i parametri fissati a priori.
#
# LIMITE da dichiarare: a differenza della correzione nel segmentatore,
# questa lista è ricavata GUARDANDO quali predizioni erano sbagliate. È
# quindi supervisionata e specifica del dominio su cui è stata costruita, e
# su annunci reali va rimisurata. Disattivabile con JobParser(use_denylist=False).
_GENERIC_ATTRACTOR_IDS = {
    "42ab725f-e57f-4320-a9fd-ac3d6717963d", "6d56955d-2b6c-471f-890d-8c17ab16053b", "76526bf6-bada-4ca1-8e79-6b9d4228b607",
    "15a33d76-4640-438d-ae64-fdc0c1d3eebc", "d2d9051a-10e1-41c5-9cfb-bbdc58016176", "bda0d115-f315-453e-99dc-f8b0e5862db3",
    "6badc79b-4353-4f95-b248-57a9ed07c7ac", "1d21f6ad-340f-45da-a0a3-4e83867f47a6", "c29aa9d2-4da8-4bdd-831c-8d4a2fb51730",
    "83e6510b-ffeb-4aec-959c-4265fd0ff7b7", "045f71e6-0699-4169-8a54-9c6b96f3174d", "5d9e766b-8f17-4e17-bfab-3bb0e0719791",
    "632a96bc-498c-48ea-a83f-fdc42d811a51", "0450eaee-1a00-4622-8f4e-5356fce816d2", "a34f4fd4-1aff-4941-82d5-542ac94f81c3",
    "c1e0de6d-ec3b-4323-92d4-d1c62df2064a", "f7e7ccb6-fadc-4c35-935d-e1040be40dfe", "3e75d405-c3d1-4a66-9963-05a9397d68fb",
    "791fa659-3382-49f8-a8dd-505226d0da48", "0f351347-3117-417a-b372-7e58d28dce07", "63095511-1841-4483-8224-f31a30bcdb85",
    "03aa85d2-9a67-455f-b901-595e685afdd2", "d1072655-88ce-4445-8803-e6273da273e7", "26f17354-aa39-464a-8c02-266a50f9d789",
    "c42a92b2-a802-4cf6-a645-3904004bbdbe", "fa46ff13-5ad7-4a11-85d6-4b0614e411de", "afd49651-9119-4327-91fc-844a6dda1254",
    "a1a032e1-4b7a-4603-8516-43d83707ffac", "4e756773-ae14-4981-838b-9fe27e81c0af", "39aa5c41-960d-420a-a0bb-1ad9686d6369",
    "03b9b491-fc9b-4868-914a-bf7cd47b5041", "f39a5dcd-1b8b-4eff-a021-a96196fd71eb", "08fe5910-8c4c-4679-a988-eb2ded3c4909",
    "f5584cdb-fded-4dfe-b246-ef06f442d3a7", "0cb013af-6dd9-4fb2-b34e-63dda1a5cf82", "f005306e-5de6-4b23-bd5f-65d8b542b83a",
    "8ce4a4af-969b-4d1c-8bfe-891cff82f913", "aa238394-8126-4ada-be2f-9dfe065cf314", "377861af-f966-4c87-a2db-7e99904312b9",
    "41235c52-558f-4f94-9f14-dc69154e5081", "afdcb380-ef9f-4785-b877-cc551f035034", "cdd2b6cc-b4a9-42a0-824b-766f52176fd3",
    "ab6265f2-a9bf-49e8-a9a5-67cbab4de38b", "c65ac31c-fdaf-4e87-beca-8ed952c3aa35", "7f7756fc-d89d-41d5-93ef-85991603f4ad",
    "f509c7cb-ec40-49b8-a2eb-c3bc35934bbc", "db77825e-0f3e-47d0-abdb-356794484272", "5c606d18-6404-4047-b235-350f18e11827",
    "0e21e183-e787-4f23-a240-93b416c088c2", "86d8a19f-1694-4314-9048-8f36c227a42c", "666e7d29-247b-4032-a3ce-8ee27554a044",
    "2399e65b-cf2b-4f5b-9002-607e790fcf2a", "7f95caff-98c0-46a7-ac76-1a1e992ba7c5", "70ed0119-0a2d-46bc-b1e8-da11a5ccdfbe",
    "0bca9840-478a-40fd-a6c3-c8cc923add98", "9013b46e-5a9b-4929-8918-fcadfdfd37ce", "509ae385-e593-4535-8bac-28c96b200a70",
    "b2ad4e50-cb82-4a34-ab3e-5b5f6c4f9b65", "21a40266-69b6-48be-b882-38b2f55fd703", "28d715e3-3e5b-4fb6-8dd2-4be4919c8587",
    "17fa2e6a-ca80-4d60-afb0-03f170e9d5f3", "c5efe5ad-c5e3-4bd1-9c8b-4a514940f4d6", "8168333b-8257-48f6-82c5-6b5128c21ecc",
    "d6d3fee7-47e2-47f4-a0ec-6c75f28c6abd",
}


_ACRONYM_STOP = {
    "DAL","DEL","NEL","CON","PER","CHE","UNA","UNO","ALL","ALLA",
    "SUI","SUL","COI","COL","AGLI","ALLE","ALLO","DEGLI","DELLE",
    "SIA","NON","HO","HA","AL","IL","LA","LE","LO","DI","DA",
    "IN","A","E","O","LT","RM","MI","TO","FI","BO","NA","VE",
    "SPA","SRL","UE","EU","NB","OK","HR","VS","ID","NR","NO","SI",
    "THE","AND","FOR","WITH","FROM","THAT","THIS","ARE","WAS",
    "HAS","HAVE","WILL","YOUR","OUR","YOU","CAN","NOT","BUT",
}

_ACRONYM_RE = re.compile(r"\b([A-Z]{2,6})\b")
_CAMEL_RE   = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]*)+)\b")

_NOISE_RE = re.compile(
    r"^(?:https?://|www\.|mailto:|"
    r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|"
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}|"
    r"\+?\d[\d\s\-\.]{7,}\d"
    r")",
    re.IGNORECASE,
)

# Pulizia candidati skill
_LEAD_ARTICLE_RE = re.compile(
    r"^(?:il|la|le|lo|gli|i|un|una|del|della|dei|degli|delle|"
    r"di|da|a|al|alla|alle|agli|ai|per|con|in|su)\s+", re.IGNORECASE)
_BULLET_STRIP_RE = re.compile(r"^[\-–—•·\*]\s*")


def _split_into_sentences(line: str) -> list[str]:
    """
    Spezza una riga lunga (probabile paragrafo di prosa) in frasi.
    Righe già brevi (<=60 char, verosimilmente già un item di lista breve)
    vengono lasciate intatte per non alterare il comportamento su testo
    già itemizzato (liste puntate, vecchio formato annunci).
    """
    if len(line) <= 60:
        return [line]
    parts = _SENTENCE_SPLIT_RE.split(line)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else [line]


# ══════════════════════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

class JobParser:
    """
    Parser generico per job description.

    Funziona su qualsiasi formato testuale di offerta di lavoro senza
    dipendere da header di sezione specifici. Estrae:
      - Occupazione target (match semantico su ESCO occupations)
      - Skill richieste e preferibili (match semantico su ESCO skills)
    """

    def __init__(
        self,
        hubness_correction: bool = False,
        mutual_only: bool = False,
        use_lexical: bool = False,
        use_spacy: bool = False,
        use_denylist: bool = True,
        use_classifier: bool = True,
        model_name: str | None = None,
        soglie: dict | None = None,
    ):
        """
        Parametri (tutti disattivabili per confronti A/B in fase di tesi):

        soglie
            Soglie di similarità, una per tipo di candidato:
                occ  occupazione dal titolo          (default 0.72)
                sw   candidato di una sola parola    (default 0.82)
                mw   candidato di più parole         (default 0.88)
                acr  acronimo                        (default 0.84)

            NON SONO TRASFERIBILI FRA ENCODER. I valori predefiniti sono stati
            tarati sulla famiglia E5, che per come è addestrata produce coseni
            assoluti alti. Un encoder di altra famiglia lavora su una scala
            diversa, e le stesse soglie vi assumono un significato diverso: con
            paraphrase-multilingual-MiniLM-L12-v2 la soglia 0.72 sull'occupazione
            viene superata in appena 45 annunci su 810, benché in quei 45 casi
            il modello indovini l'84.4% delle volte — più di e5-base, che si
            ferma al 75.9%. Sul lato competenze l'effetto è opposto: i punteggi
            di MiniLM sono più alti, le soglie risultano permissive e la
            precisione scende.

            Confrontare encoder diversi a soglie fisse misura quindi quanto
            ciascuno somigli a E5 nella scala dei punteggi, non quanto sia
            capace. Per un confronto equo ogni encoder va ricalibrato: si parsa
            una volta con soglie basse e si cercano poi i valori migliori fuori
            linea sui punteggi già salvati (analysis/calibra_soglie.py).

        hubness_correction
            Penalizza le etichette ESCO che somigliano indiscriminatamente a
            qualsiasi testo, sottraendo a ciascuna la propria similarità media
            contro un corpus di background non etichettato
            (analysis/costruisci_profilo_background.py).

            ESITO SPERIMENTALE: NEGATIVO. Disattivo di default.
            Sugli 810 annunci di valutazione, con profilo calibrato sui
            candidati reali e attivo su tutti i documenti:
                senza correzione   P 0.297  R 0.615  F1 0.391
                con  correzione    P 0.298  R 0.615  F1 0.392
            Nessun effetto. La diagnosi è che il problema non risiede nelle
            etichette ma nelle query: il falso positivo dominante nasce dal
            candidato "responsible", un frammento grammaticale per il quale
            "comportarsi in modo responsabile" è in realtà il match corretto.
            Correggere il lato ontologia non può rimediare a un candidato
            privo di contenuto — la soluzione efficace agisce a monte, nella
            segmentazione (vedi il vincolo multi-parola in
            _extract_skill_candidates).
            Il codice resta per riproducibilità del confronto.

        mutual_only
            Vincolo di reciprocità: ogni etichetta ESCO può essere assegnata a
            una sola frase del documento, quella che le somiglia di più.

            ESITO SPERIMENTALE: INEFFICACE. Disattivo di default.
            Riduce le skill estratte solo dell'1,3% (21756 → 21481) perché
            presuppone un problema che qui non esiste: si è verificato che le
            etichette problematiche compaiono ESATTAMENTE UNA VOLTA per
            documento (792 occorrenze in 792 annunci distinti). Il fenomeno è
            fra documenti, non dentro il documento, e la reciprocità agisce
            solo su quest'ultimo.

        use_lexical
            Stadio di riconoscimento letterale delle etichette ESCO
            (lexical_matcher). DISATTIVO di default: misurato sugli 810
            annunci di valutazione, il suo contributo incrementale rispetto
            allo stadio semantico ha precision 0.27, sotto quella dello stadio
            semantico (0.53), quindi in unione peggiora la precisione. Resta
            disponibile perché da solo ha precision superiore (0.56) e perché
            su annunci reali, con annotazioni complete, il bilancio potrebbe
            cambiare — va rimisurato prima di attivarlo.

        use_spacy
            Estrazione candidati tramite chunking dei sintagmi nominali.
            DISATTIVO di default e NON validato sperimentalmente: richiede
            spaCy e i modelli it_core_news_sm / en_core_web_sm. Da attivare
            solo dopo un confronto A/B esplicito.

        use_denylist
            Applica _GENERIC_ATTRACTOR_IDS, la lista di etichette-calamita
            ricavata osservando i falsi positivi su questo stesso dataset.
            È un correttivo efficace ma specifico dei dati su cui è stato
            costruito. La correzione hubness affronta lo stesso problema in
            modo non supervisionato: se, disattivando la denylist, le metriche
            restano equivalenti, la denylist può essere rimossa e il parser
            diventa metodologicamente più solido. Questo confronto va
            eseguito e riportato.

        use_classifier
            Sostituisce la denylist con il classificatore appreso
            (src/filtro_skill.py, addestrato da
            analysis/addestra_filtro_skill.py). Attivandolo si disattiva
            automaticamente la denylist: i due filtri agiscono sullo stesso
            fenomeno e applicarli insieme scarterebbe troppo.

            ATTIVO di default. Due misure lo giustificano.

            Sul test per occupazioni mai viste, con entrambi i filtri costruiti
            sulle stesse occupazioni di training, il classificatore supera la
            regola scritta a mano: F1 0.734 contro 0.721. È la stima onesta,
            perché la denylist attualmente nel codice è stata derivata da tutti
            gli 810 annunci e sulle occupazioni di test aveva già visto le
            risposte (in quel confronto sleale segnava 0.747).

            Sull'intera pipeline, 810 annunci:
                denylist 64      P 0.614  R 0.577  F1 0.580   3703 FP
                classificatore   P 0.807  R 0.539  F1 0.629   1280 FP

            La precisione passa da tre skill corrette su cinque a quattro su
            cinque, e i falsi positivi si riducono di due terzi. Il costo è il
            6% dei veri positivi: per ogni skill corretta sacrificata ne
            vengono eliminate più di sei sbagliate.

            Effetto collaterale da conoscere: il parser diventa conservativo,
            estraendo 8,5 skill per annuncio contro le 13,5 attese. Prima ne
            estraeva 11,9. Se in una applicazione la recall contasse più della
            precisione — per esempio nel suggerire corsi, dove una competenza
            mancata è un'occasione persa — conviene tornare alla denylist con
            use_classifier=False.
        """
        # model_name=None -> predefinito di SemanticMapper. Specificarlo serve
        # al confronto fra encoder: le cache degli embedding sono separate per
        # modello, quindi cambiarlo non contamina i risultati precedenti.
        self.mapper = SemanticMapper(model_name) if model_name else SemanticMapper()
        self.hubness_correction = hubness_correction
        self.mutual_only = mutual_only
        self.use_spacy = use_spacy

        # Soglie di similarità. Vedi la docstring: i valori predefiniti valgono
        # per la famiglia E5 e non sono trasferibili ad altri encoder.
        self.soglie = {"occ": 0.72, "sw": 0.82, "mw": 0.88, "acr": 0.84}
        if soglie:
            ignote = set(soglie) - set(self.soglie)
            if ignote:
                raise ValueError(
                    f"Soglie sconosciute: {sorted(ignote)}. "
                    f"Attese: {sorted(self.soglie)}")
            self.soglie.update(soglie)
        self.use_denylist = use_denylist and not use_classifier

        self.filtro_appreso = None
        if use_classifier:
            try:
                from filtro_skill import FiltroSkillAppreso
                f = FiltroSkillAppreso()
                if f.disponibile:
                    self.filtro_appreso = f
                else:
                    print("[job_parser] Classificatore non disponibile: "
                          "riattivo la denylist.")
                    self.use_denylist = use_denylist
            except Exception as e:
                print(f"[job_parser] Classificatore non caricabile ({e}): "
                      "riattivo la denylist.")
                self.use_denylist = use_denylist

        self.lexical = None
        if use_lexical:
            try:
                from lexical_matcher import LexicalSkillMatcher
                self.lexical = LexicalSkillMatcher(
                    [str(DATA_IT / "skills.json"), str(DATA_EN / "skills.json")]
                )
            except Exception as e:
                print(f"[job_parser] Stadio lessicale non disponibile: {e}")

        # Profilo di background per la correzione hubness, tenuto in memoria
        # dopo il primo caricamento da disco.
        self._bg_tensor = None
        self._bg_warned = False

    # ──────────────────────────────────────────────────────────────────────────
    def _ensure_background_profile(self) -> None:
        """
        Garantisce che il profilo di background sia attivo sul DB skill
        corrente.

        ATTENZIONE — va richiamato per OGNI documento, non una sola volta.
        SemanticMapper.load_database*() azzera `bg_deviation` a ogni cambio di
        indice, e il parser alterna occupazioni e skill su ciascun annuncio:
        il profilo viene quindi invalidato di continuo.

        Una versione precedente memorizzava il nome del database già
        processato e usciva subito se coincideva. Il risultato era che dal
        secondo documento in poi la guardia scattava mentre `bg_deviation` era
        stato appena azzerato: la correzione agiva solo sul primo documento e
        le valutazioni risultavano indistinguibili da quelle senza correzione.
        Per questo la condizione di uscita controlla ora lo stato effettivo
        del profilo, non un identificativo.
        """
        if not self.hubness_correction:
            return
        if self.mapper.bg_deviation is not None:
            return                      # profilo già attivo sull'indice corrente

        # Ripristino da memoria (nessun accesso a disco)
        if self._bg_tensor is not None:
            self.mapper.bg_deviation = self._bg_tensor
            return

        # Il profilo di background è una deviazione per etichetta calcolata
        # NELLO SPAZIO VETTORIALE DI UN MODELLO SPECIFICO: non è trasferibile a
        # un encoder diverso. La sua lunghezza però dipende solo dal numero di
        # etichette, identico fra modelli, quindi un file calibrato su un altro
        # encoder si caricherebbe senza errori e ne falserebbe silenziosamente i
        # punteggi. Il nome del file porta perciò il tag del modello, come già
        # avviene per le cache degli embedding (SemanticMapper._tag_modello).
        tag = getattr(self.mapper, "_tag", None) or "sconosciuto"
        cache = DATA_IT / f"skills_bg_profile_{tag}.pt"

        if cache.exists():
            # Profilo calibrato da analysis/costruisci_profilo_background.py
            if self.mapper.build_background_profile([], cache_path=str(cache)):
                self._bg_tensor = self.mapper.bg_deviation
        elif not self._bg_warned:
            self._bg_warned = True
            print(
                f"[job_parser] ATTENZIONE: profilo di background assente per "
                f"il modello {tag}.\n"
                "             La correzione hubness resta inattiva. Per "
                "calibrarla:\n"
                "             python analysis/costruisci_profilo_background.py"
            )

    # ──────────────────────────────────────────────────────────────────────────
    def parse_job(self, file_path: str) -> dict:
        """Parsa una job description da file PDF, DOCX o TXT."""
        if not os.path.isabs(file_path):
            file_path = str(BASE_DIR / file_path)

        job_id = Path(file_path).stem

        if not os.path.exists(file_path):
            print(f"[job_parser] ERRORE: file non trovato: {file_path}")
            return self._empty_result(job_id)

        # Supporto file .txt (job description estratte dall'Excel)
        if file_path.endswith(".txt"):
            text = Path(file_path).read_text(encoding="utf-8")
            # Salta le righe di metadati (ID:, Area:, Ruolo:, ecc.)
            lines = []
            skip_meta = True
            for line in text.splitlines():
                if skip_meta and re.match(r"^(ID|Area|Ruolo|Azienda|Località|Seniority):", line):
                    continue
                skip_meta = False
                lines.append(line)
            return self._parse_lines([l for l in lines if l.strip()], job_id)

        lines = get_text(file_path)
        if not lines:
            print(f"[job_parser] ERRORE: nessun testo estratto da {file_path}")
            return self._empty_result(job_id)

        return self._parse_lines(lines, job_id)

    # ──────────────────────────────────────────────────────────────────────────
    def parse_job_text(self, text: str, job_id: str = "job_inline") -> dict:
        """Parsa una job description da testo grezzo."""
        lines = [l for l in text.splitlines() if l.strip()]
        return self._parse_lines(lines, job_id)

    # ──────────────────────────────────────────────────────────────────────────
    def _parse_lines(self, lines: list[str], job_id: str) -> dict:
        """Pipeline interna comune a parse_job() e parse_job_text()."""

        clean_lines = filter_lines(lines)

        raw_title = self._extract_title(lines)

        # ── Occupazione target ────────────────────────────────────────────────
        if (DATA_IT / "occupations.json").exists() and (DATA_EN / "occupations.json").exists():
            self.mapper.load_databases_bilingual(
                str(DATA_IT / "occupations.json"),
                str(DATA_EN / "occupations.json"),
            )
        else:
            self.mapper.load_database(str(DATA_SRC / "occupations.json"))

        title_candidates = [raw_title] if raw_title else clean_lines[:5]
        occ_matches = self.mapper.find_matches(
            title_candidates,
            threshold=self.soglie["occ"],
            top_k=1,
            max_results=3,
            return_scores=True,
        )
        occupation = occ_matches[0] if occ_matches else {}

        # ── Skill extraction ──────────────────────────────────────────────────
        if (DATA_IT / "skills.json").exists() and (DATA_EN / "skills.json").exists():
            self.mapper.load_databases_bilingual(
                str(DATA_IT / "skills.json"),
                str(DATA_EN / "skills.json"),
            )
        else:
            self.mapper.load_database(str(DATA_SRC / "skills.json"))

        # Il profilo hubness dipende dal DB caricato: va garantito qui, dopo
        # il caricamento del database skill e prima del matching.
        self._ensure_background_profile()

        skill_candidates, candidate_contexts = self._extract_skill_candidates(clean_lines)
        acronym_candidates = self._extract_acronyms(clean_lines)

        # Separa candidati per contesto
        req_cands  = [c for c, ctx in zip(skill_candidates, candidate_contexts)
                      if ctx == "required"]
        pref_cands = [c for c, ctx in zip(skill_candidates, candidate_contexts)
                      if ctx == "preferred"]
        # Candidati senza contesto esplicito → required per default
        neutral_cands = [c for c, ctx in zip(skill_candidates, candidate_contexts)
                         if ctx == "neutral"]
        req_cands = req_cands + neutral_cands

        # Match semantico separato per required e preferred
        def _search(cands, acr=None):
            sw = [c for c in cands if len(c.split()) == 1]
            mw = [c for c in cands if len(c.split()) > 1]
            # La correzione hubness e la reciprocità si applicano ai candidati
            # testuali. Gli acronimi ne sono esclusi: sono token già molto
            # discriminanti, e il vincolo di reciprocità li penalizzerebbe
            # ingiustamente quando lo stesso acronimo ricorre più volte.
            opts = {
                "hubness_correction": self.hubness_correction,
                "mutual_only": self.mutual_only,
            }
            m_sw = self.mapper.find_matches(sw, threshold=self.soglie["sw"],
                                            top_k=1,
                                            max_results=30, return_scores=True,
                                            **opts) if sw else []
            m_mw = self.mapper.find_matches(mw, threshold=self.soglie["mw"],
                                            top_k=1,
                                            max_results=30, return_scores=True,
                                            **opts) if mw else []
            m_ac = self.mapper.find_matches(acr or [],
                                            threshold=self.soglie["acr"], top_k=1,
                                            max_results=20, return_scores=True,
                                            hubness_correction=self.hubness_correction,
                                            ) if acr else []
            # Ogni match porta il tipo di candidato da cui proviene. Serve alla
            # calibrazione delle soglie fuori linea (analysis/calibra_soglie.py):
            # senza questo campo si potrebbe applicare a posteriori una sola
            # soglia globale, mentre le tre soglie hanno valori distinti proprio
            # perché i tre tipi di candidato hanno affidabilità diverse.
            for m in m_sw:
                m["tipo"] = "sw"
            for m in m_mw:
                m["tipo"] = "mw"
            for m in m_ac:
                m["tipo"] = "acr"

            # Deduplica per ID mantenendo score migliore
            best: dict[str, dict] = {}
            for m in m_sw + m_mw + m_ac:
                if m["id"] not in best or m["score"] > best[m["id"]]["score"]:
                    best[m["id"]] = m
            return list(best.values())

        matches_req  = _search(req_cands,  acronym_candidates)
        matches_pref = _search(pref_cands)

        # ── Stadio lessicale (opzionale) ──────────────────────────────────────
        # Le skill nominate nel testo con la stessa formulazione di ESCO non
        # richiedono inferenza semantica. Vengono unite ai match required.
        if self.lexical is not None:
            lex_hits = self.lexical.match_lines(clean_lines)
            known = {m["id"] for m in matches_req} | {m["id"] for m in matches_pref}
            matches_req.extend(h for h in lex_hits if h["id"] not in known)

        # Applica filtri e deduplica tra required e preferred
        matches_req  = self._apply_esco_filters(matches_req)
        matches_pref = self._apply_esco_filters(matches_pref)

        # ── Filtro appreso (alternativo alla denylist) ────────────────────────
        # Riceve i match dell'intero annuncio perché alcuni attributi — la
        # posizione in classifica e il numero di skill del documento —
        # dipendono dal contesto e non sono calcolabili su un match isolato.
        if self.filtro_appreso is not None:
            testo_annuncio = " ".join(clean_lines)
            ids_req = {m["id"] for m in matches_req}
            tutti = matches_req + matches_pref
            tenuti = {m["id"] for m in self.filtro_appreso.filtra(
                tutti, testo_annuncio, ids_req)}
            matches_req  = [m for m in matches_req  if m["id"] in tenuti]
            matches_pref = [m for m in matches_pref if m["id"] in tenuti]

        req_ids_set  = {m["id"] for m in matches_req}
        pref_ids_set = {m["id"] for m in matches_pref} - req_ids_set

        all_matches = matches_req + [m for m in matches_pref if m["id"] in pref_ids_set]

        return {
            "job_id":     job_id,
            "raw_title":  raw_title,
            "occupation": occupation,
            "seniority":  _detect_seniority(raw_title, " ".join(clean_lines)),
            "skills": {
                "required_ids":  list(req_ids_set),
                "preferred_ids": list(pref_ids_set),
                "all_matches":   all_matches,
            },
        }

    # ──────────────────────────────────────────────────────────────────────────
    def _extract_title(self, lines: list[str]) -> str:
        """Estrae il titolo del ruolo dalla prima riga significativa."""
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            if _NOISE_RE.match(line):
                continue
            if len(line) <= 80 and not line[0].isdigit():
                return line
        return ""

    # ──────────────────────────────────────────────────────────────────────────
    def _extract_skill_candidates(
        self, lines: list[str]
    ) -> tuple[list[str], list[str]]:
        """
        Estrae candidati skill dalle righe della job description.

        Returns:
            (candidates, contexts) — liste parallele.
            context ∈ {"required", "preferred", "neutral"}
        """
        candidates: list[str] = []
        contexts:   list[str] = []
        current_section_ctx = "neutral"   # contesto di sezione (sticky)

        def _clean(text: str) -> str:
            text = _BULLET_STRIP_RE.sub("", text).strip()
            text = _LEAD_ARTICLE_RE.sub("", text).strip()
            return text.rstrip(".,;:)(").strip()

        def _add(tok: str, ctx: str) -> None:
            tok = _clean(tok)
            if tok and len(tok) >= 3:
                candidates.append(tok)
                contexts.append(ctx)

        def _is_section_header(line: str) -> bool:
            """Riga breve che funge da header (es. 'Requisiti preferibili:')."""
            s = line.strip()
            return len(s) < 80 and s.endswith(":")

        for raw_line in lines:
            if not raw_line.strip() or is_noise_line(raw_line):
                continue

            # Spezza paragrafi di prosa in frasi: il resto della logica sotto
            # (marcatori, split righe lunghe...) opera così su unità più
            # piccole e mirate invece che su un intero paragrafo come "riga".
            for line in _split_into_sentences(raw_line):
                has_req  = bool(_REQUIRED_MARKERS.search(line))
                has_pref = bool(_PREFERRED_MARKERS.search(line))

                # ── Aggiorna contesto di sezione (sticky) ──────────────────────
                # Lo sticky cambia solo su header di sezione o su righe che
                # contengono SOLO un marcatore (nessun testo mixed).
                if has_req and not has_pref:
                    current_section_ctx = "required"
                elif has_pref and not has_req:
                    current_section_ctx = "preferred"

                # ── Contesto effettivo per QUESTA riga ─────────────────────────
                # Marcatori inline hanno precedenza sul contesto di sezione.
                # Questo cattura frasi come "Gradita esperienza con Docker"
                # anche quando la sezione corrente è "required".
                if has_pref and not has_req:
                    line_ctx = "preferred"
                elif has_req and not has_pref:
                    line_ctx = "required"
                else:
                    line_ctx = current_section_ctx

                # Se è un puro header di sezione senza contenuto, skippa l'estrazione
                if _is_section_header(line):
                    continue

                # ── Estrazione candidati ────────────────────────────────────────

                # Token dentro parentesi
                for m in _PAREN_RE.finditer(line):
                    _add(m.group(1), line_ctx)

                # Pattern "quali: X e Y" / "such as X and Y"
                m_q = _QUALI_RE.search(line)
                if m_q:
                    rest = m_q.group(1).strip()
                    for chunk in _SEP_RE.split(rest):
                        for sub in _CONJ_RE.split(chunk.strip()):
                            _add(sub.strip().rstrip(".,;"), line_ctx)

                # Righe lunghe residue (frasi ancora corpose dopo lo split a
                # livello di frase): estrazione a confini di stopword invece
                # del vecchio taglio grezzo "prime 5 parole".
                if len(line) > 60:
                    phrases = (
                        _spacy_noun_chunks(line) if self.use_spacy else []
                    ) or _extract_content_phrases(line)
                    for phrase in phrases:
                        # Solo candidati multi-parola dalla prosa.
                        #
                        # Il taglio sui confini di stopword lascia orfane le
                        # parole di impalcatura della frase. Da "The successful
                        # candidate will be responsible for coordinating
                        # technological activities, using our ICT ticketing
                        # system" escono tre candidati buoni ("coordinating
                        # technological activities", "ICT ticketing system",
                        # "legal regulations") e quattro detriti grammaticali
                        # ("successful", "responsible", "using", "complying").
                        #
                        # Quei detriti sono il 45% dei candidati da prosa e
                        # sono la vera origine dei falsi positivi sistematici:
                        # sugli 810 annunci di valutazione il candidato
                        # "responsible" compare in 792 documenti e l'etichetta
                        # "comportarsi in modo responsabile" risulta falso
                        # positivo in esattamente 792; "seeking" compare in 773
                        # e "motori di ricerca" in 772. La corrispondenza è
                        # uno-a-uno.
                        #
                        # Il vincolo vale SOLO per la prosa: negli elenchi
                        # ("Python, SQL, Docker") e fra parentesi le parole
                        # singole sono competenze legittime e continuano a
                        # passare. Le sigle tecniche hanno comunque un percorso
                        # dedicato (_extract_acronyms) con soglia propria.
                        if len(phrase.split()) < 2:
                            continue
                        _add(phrase, line_ctx)
                    continue

                # Split su separatori standard
                parts = [p.strip() for p in _SEP_RE.split(line) if p.strip()]
                if len(parts) > 1:
                    for p in parts:
                        _add(p, line_ctx)
                else:
                    _add(line.strip(), line_ctx)

        return candidates, contexts

    # ──────────────────────────────────────────────────────────────────────────
    def _extract_acronyms(self, lines: list[str]) -> list[str]:
        """Estrae acronimi e CamelCase dall'intero testo."""
        seen: set[str] = set()
        result: list[str] = []
        for line in lines:
            for m in _ACRONYM_RE.finditer(line):
                tok = m.group(1)
                if tok not in _ACRONYM_STOP and tok.lower() not in seen:
                    seen.add(tok.lower())
                    result.append(tok)
            for m in _CAMEL_RE.finditer(line):
                tok = m.group(1)
                if tok.lower() not in seen:
                    seen.add(tok.lower())
                    result.append(tok)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    def _apply_esco_filters(self, matches: list[dict]) -> list[dict]:
        """Rimuove match con label che iniziano con articolo (rumore) e le
        etichette "calamita" identificate come falsi positivi sistematici
        (vedi _GENERIC_ATTRACTOR_IDS)."""
        _ARTICLE_RE = re.compile(
            r"^(a|an|the|to|in|of|for|with|by|on|at|from)\b", re.IGNORECASE
        )
        deny = _GENERIC_ATTRACTOR_IDS if self.use_denylist else frozenset()
        return [
            m for m in matches
            if not _ARTICLE_RE.match(m.get("label", ""))
            and m.get("id") not in deny
        ]

    # ──────────────────────────────────────────────────────────────────────────
    def _empty_result(self, job_id: str) -> dict:
        return {
            "job_id":     job_id,
            "raw_title":  "",
            "occupation": {},
            "seniority":  {"level": None, "years": None, "evidence": ""},
            "skills": {
                "required_ids":  [],
                "preferred_ids": [],
                "all_matches":   [],
            },
        }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="SkillPath AI — Job Parser")
    ap.add_argument("file", nargs="?", default=None,
                    help="File PDF/DOCX/TXT da parsare")
    ap.add_argument("--text", default=None,
                    help="Testo grezzo da parsare (alternativa al file)")
    ap.add_argument("--out",  default="outputs/job_parsed_result.json",
                    help="File output JSON")
    args = ap.parse_args()

    jp = JobParser()

    if args.text:
        result = jp.parse_job_text(args.text)
    elif args.file:
        result = jp.parse_job(args.file)
    else:
        # Default: parsa samples/offerta1.txt se esiste
        default = BASE_DIR / "samples" / "offerta1.txt"
        if default.exists():
            result = jp.parse_job(str(default))
        else:
            ap.print_help()
            sys.exit(1)

    out_path = BASE_DIR / args.out
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[job_parser] → {out_path}")
    print(f"  Titolo:            {result['raw_title']}")
    occ = result.get("occupation", {})
    print(f"  Occupazione:       {occ.get('label','')}  (score {occ.get('score',0):.2f})")
    sk = result["skills"]
    print(f"  Skill richieste:   {len(sk['required_ids'])}")
    print(f"  Skill preferibili: {len(sk['preferred_ids'])}")
    if sk["all_matches"]:
        print("  Top skill:")
        for m in sorted(sk["all_matches"], key=lambda x: x["score"], reverse=True)[:5]:
            tag = "[REQ]" if m["id"] in sk["required_ids"] else "[PREF]"
            print(f"    {tag} {m['score']:.3f}  {m['label']}")


if __name__ == "__main__":
    main()
