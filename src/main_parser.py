"""
main_parser.py  —  SkillPath AI
================================
Parser CV end-to-end: da file PDF/DOCX a struttura JSON pronta per il
matching_engine.

PIPELINE GENERALE
-----------------
                    ┌──────────────────────────────────────────┐
  PDF / DOCX  ──►   │  pdf_extractor  →  lista di righe pulite │
                    └──────────────┬───────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────┐
                    │  segment_cv  →  blocchi per sezione       │
                    │  (experience / education / skills / ...)  │
                    └──────────────┬───────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────┐
                    │  SemanticMapper  →  match su ESCO         │
                    │  (occupazioni, skill, istruzione, lingue) │
                    └──────────────┬───────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────┐
                    │  JSON output  →  matching_engine          │
                    └──────────────────────────────────────────┘

DIPENDENZE ESTERNE
------------------
- pdf_extractor.py  : estrazione testo da PDF (PyMuPDF) e DOCX (python-docx)
- semantic_mapper.py: embedding con sentence-transformers + cosine similarity su ESCO
- Dataset ESCO:
    dataset/source/occupations.json          (~3 000 occupazioni)
    dataset/source/skills.json               (~13 000 skill)
    dataset/source/occupation_skill_relations.json
    dataset/supplementary/degree_programs.json
    dataset/supplementary/language_levels.json
    dataset/supplementary/certifications.json
"""

import json
import os
import re
import unicodedata
from datetime import datetime

from pdf_extractor import get_text, filter_lines, is_noise_line
from semantic_mapper import SemanticMapper


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAZIONE SEZIONI CV
# ══════════════════════════════════════════════════════════════════════════════
#
# I CV italiani ed europei usano titoli di sezione molto variabili:
#   "Esperienza professionale" (classic IT), "Work experience" (Europass EN),
#   "▸ EXPERIENCE" (template modern).
# Mappa sezione-logica → lista di keyword attese nel CV.
#
SECTION_KEYWORDS = {
    "experience": [
        "esperienza professionale", "esperienze professionali", "esperienza lavorativa",
        "esperienze lavorative", "esperienze", "esperienza", "work experience",
        "professional experience", "employment history", "career history", "lavoro",
        "experience",
    ],
    "education": [
        "istruzione e formazione", "istruzione", "formazione", "education",
        "educazione", "studi", "percorso di studi", "academic background",
        "qualifiche", "titoli di studio",
    ],
    "skills": [
        "competenze tecniche", "competenze professionali", "competenze personali",
        "competenze", "skills", "technical skills", "soft skills", "hard skills",
        "capacità e competenze", "capacità", "conoscenze",
    ],
    "languages": [
        "lingue straniere", "lingue conosciute", "lingue", "languages",
        "language skills", "foreign languages",
    ],
    "certifications": [
        "certificazioni", "certificazione", "certifications", "certificates",
        "abilitazioni",
    ],
}

# ══════════════════════════════════════════════════════════════════════════════
# NOMI DI LINGUA
# ══════════════════════════════════════════════════════════════════════════════
# ESCO cataloga le lingue come competenze ("francese", "neerlandese", …).
# Nel CV però le lingue sono già gestite dal rilevatore keyword dedicato, che
# le restituisce con il livello CEFR nel blocco "languages". Lasciarle passare
# anche fra le skill duplica l'informazione e, rispetto alla ground truth dei
# CV sintetici (dove le lingue non sono skill), produce solo falsi positivi.
_LANGUAGE_NAMES = {
    # italiano
    "italiano", "inglese", "francese", "spagnolo", "tedesco", "portoghese",
    "neerlandese", "olandese", "fiammingo", "svedese", "danese", "norvegese",
    "finlandese", "islandese", "irlandese", "gaelico", "gallese", "greco",
    "polacco", "ceco", "slovacco", "sloveno", "croato", "serbo", "bosniaco",
    "macedone", "albanese", "bulgaro", "rumeno", "ungherese", "estone",
    "lettone", "lituano", "maltese", "russo", "ucraino", "bielorusso",
    "turco", "arabo", "ebraico", "persiano", "hindi", "urdu", "bengalese",
    "cinese", "mandarino", "cantonese", "giapponese", "coreano", "vietnamita",
    "thailandese", "indonesiano", "malese", "filippino", "swahili",
    "catalano", "basco", "galiziano", "lussemburghese", "latino",
    # inglese
    "italian", "english", "french", "spanish", "german", "portuguese",
    "dutch", "flemish", "swedish", "danish", "norwegian", "finnish",
    "icelandic", "irish", "gaelic", "welsh", "greek", "polish", "czech",
    "slovak", "slovenian", "croatian", "serbian", "bosnian", "macedonian",
    "albanian", "bulgarian", "romanian", "hungarian", "estonian", "latvian",
    "lithuanian", "maltese", "russian", "ukrainian", "belarusian", "turkish",
    "arabic", "hebrew", "persian", "bengali", "chinese", "mandarin",
    "cantonese", "japanese", "korean", "vietnamese", "thai", "indonesian",
    "malay", "filipino", "catalan", "basque", "galician", "luxembourgish",
    "latin",
}

# Qualificatori che possono accompagnare un nome di lingua senza cambiarne la
# natura: "inglese fluente", "francese B2", "spagnolo livello base"…
_LANG_QUALIFIERS = {
    "madrelingua", "madre", "lingua", "native", "fluente", "fluent",
    "ottimo", "ottima", "buono", "buona", "base", "scolastico", "livello",
    "level", "intermedio", "intermediate", "avanzato", "advanced",
    "elementare", "elementary", "corrente", "scritto", "parlato",
    "written", "spoken", "a1", "a2", "b1", "b2", "c1", "c2",
}


def _normalize_lang(text: str) -> str:
    """Forma canonica di confronto per i nomi di lingua (minuscole, no accenti)."""
    if not text:
        return ""
    txt = unicodedata.normalize("NFKD", text.strip().lower())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", txt).strip()


def _is_language_only(text: str) -> bool:
    """
    True se il testo è soltanto un nome di lingua, eventualmente accompagnato
    da un qualificatore di livello ("francese", "inglese B2", "spagnolo base").

    Serve a impedire che le righe della sezione Lingue, quando finiscono nel
    blocco competenze (accade con i template che annidano "Lingue" dentro
    "Competenze"), vengano trattate come candidati skill.
    """
    norm = _normalize_lang(text)
    if not norm:
        return False
    tokens = norm.split()
    if not tokens or len(tokens) > 4:
        return False
    if not any(t in _LANGUAGE_NAMES for t in tokens):
        return False
    return all(
        t in _LANGUAGE_NAMES or t in _LANG_QUALIFIERS for t in tokens
    )


# Dizionario keyword.upper() → nome-sezione.
# Usato per il matching rapido degli header MAIUSCOLI del template "modern".
_UPPERCASE_SECTION_MAP = {
    kw.upper(): sec
    for sec, kws in SECTION_KEYWORDS.items()
    for kw in kws
}

# Lunghezza massima in caratteri di una riga affinché venga considerata header.
# Oltre 60 caratteri è quasi certamente contenuto (frase, descrizione), non titolo.
_HEADER_MAX_LEN = 60


# ══════════════════════════════════════════════════════════════════════════════
# FILTRO LABEL ESCO "TASK-ORIENTED"
# ══════════════════════════════════════════════════════════════════════════════
#
# L'ontologia ESCO contiene circa 13 700 skill. Una parte di esse però non
# descrive una competenza nominale ("Python", "machine learning") ma una
# *attività* o *processo* espresso come frase verbale:
#   "using consulting techniques"    → attività, non skill
#   "utilise machinery control programmes"
#   "attend to quality"
#   "verify feasibility"
#
# Queste label iniziano con un verbo all'infinito o al gerundio e non hanno
# senso come voce in un CV ("competenze: using consulting techniques" ← assurdo).
# Il filtro le rimuove sistematicamente prima del post-processing.
#
# Pattern: corrisponde a qualsiasi label che INIZIA con uno dei verbi listati.
# Usa \b (word boundary) dove il verbo potrebbe essere prefisso di un nome
# legittimo (es. "design" ≠ "designer", "build" ≠ "building automation").
#
_ESCO_TASK_LABEL_RE = re.compile(
    r"^(?:"
    # Verbi all'infinito / forme base
    r"using|utilise|use|apply\b|manage\b|operate|perform|conduct|"
    r"carry\b|provide|ensure|maintain|assess|analys[ei]|identif[yi]|"
    r"monitor|administer|co[-\s]?ordinate|coordinate|implement|"
    r"establish|build\b|support\b|assist|attend\b|verify\b|"
    r"inspect|check\b|prepare\b|handle\b|process\b|report\b|"
    r"respond|review\b|train\b|teach\b|advise|consult\b|"
    r"facilitate|resolve|evaluate|deliver\b|produce\b|complete\b|"
    r"develop\b|creat|be\b|delegate\b|assign\b|"
    # Gerundi che aprono frasi multi-parola (pattern "calcolating X")
    # NON filtriamo gerundi a parola singola: "programming", "accounting" sono legittimi
    r"calculat|attend[a-z]*\s|verify[a-z]*\s|inspect[a-z]*\s"
    r")",
    re.IGNORECASE,
)


# ══════════════════════════════════════════════════════════════════════════════
# RILEVAMENTO HEADER DI SEZIONE
# ══════════════════════════════════════════════════════════════════════════════

def _line_is_header(line: str) -> tuple[bool, str | None]:
    """
    Determina se una riga del CV è un'intestazione di sezione.

    Gestisce tre stili di template:
    ┌─────────────┬───────────────────────────────┬────────────────────────┐
    │  Template   │  Stile header nel PDF/DOCX     │  Esempio               │
    ├─────────────┼───────────────────────────────┼────────────────────────┤
    │  classic    │  Titolo capitalizzato (IT)     │  "Esperienza profess." │
    │  europass   │  Titolo capitalizzato (EN)     │  "Work experience"     │
    │  modern     │  MAIUSCOLO con prefisso ▸      │  "▸ EXPERIENCE"        │
    └─────────────┴───────────────────────────────┴────────────────────────┘

    Problema del template modern:
        Il carattere ▸ (U+25B8) non è presente nel font Helvetica usato da
        reportlab. PyMuPDF lo estrae come "I" (lettera maiuscola I).
        Quindi "▸ EXPERIENCE" diventa "I EXPERIENCE" nel testo estratto.
        Soluzione: rimuoviamo il prefisso non-alfabetico e poi una singola
        lettera maiuscola iniziale prima di cercare la keyword.

    Returns:
        (True, nome_sezione)  se la riga è un header riconosciuto
        (False, None)         altrimenti
    """
    stripped = line.strip()
    if not stripped or len(stripped) > _HEADER_MAX_LEN:
        return False, None

    # ── Percorso 1: header in MAIUSCOLO (template modern) ────────────────────
    upper_clean = re.sub(r"^[^A-Za-z]+", "", stripped)   # rimuovi "▸ " o "• "
    upper_clean = re.sub(r"^[A-Z]\s+", "", upper_clean)  # rimuovi "I " (▸ mal-encodato)
    upper_clean = upper_clean.rstrip(":.- ")
    if (upper_clean
            and upper_clean == upper_clean.upper()
            and upper_clean.replace(" ", "").isalpha()):
        if upper_clean in _UPPERCASE_SECTION_MAP:
            return True, _UPPERCASE_SECTION_MAP[upper_clean]

    # ── Percorso 2: header in minuscolo / misto (template classic / europass) ─
    clean = stripped.lower().rstrip(":.- ")
    clean = re.sub(r"^[\W_]+", "", clean)   # rimuovi punteggiatura iniziale
    if not clean:
        return False, None
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            # Match esatto, o keyword seguita da spazio/due-punti (evita falsi
            # positivi tipo "ho sviluppato competenze avanzate" per "competenze")
            if clean == kw or clean.startswith(kw + " ") or clean.startswith(kw + ":"):
                return True, section
            if re.fullmatch(rf"{re.escape(kw)}[\s:–\-]*", clean):
                return True, section
    return False, None


# ══════════════════════════════════════════════════════════════════════════════
# CALCOLO ANNI DI ESPERIENZA
# ══════════════════════════════════════════════════════════════════════════════

_MESI = {
    "gennaio": 1, "gen": 1, "january": 1, "jan": 1,
    "febbraio": 2, "feb": 2, "february": 2,
    "marzo": 3, "mar": 3, "march": 3,
    "aprile": 4, "apr": 4, "april": 4,
    "maggio": 5, "mag": 5, "may": 5,
    "giugno": 6, "giu": 6, "june": 6, "jun": 6,
    "luglio": 7, "lug": 7, "july": 7, "jul": 7,
    "agosto": 8, "ago": 8, "august": 8, "aug": 8,
    "settembre": 9, "set": 9, "sett": 9, "september": 9, "sep": 9, "sept": 9,
    "ottobre": 10, "ott": 10, "october": 10, "oct": 10,
    "novembre": 11, "nov": 11, "november": 11,
    "dicembre": 12, "dic": 12, "december": 12, "dec": 12,
}

# Un estremo di intervallo. La funzione genera lo stesso schema con nomi di
# gruppo distinti, così da poterlo usare due volte nella stessa espressione:
# costruirlo per sostituzione di stringhe era fragile e si rompeva a ogni
# formato aggiunto.
_NOMI_MESE = "|".join(sorted(_MESI, key=len, reverse=True))


def _schema_estremo(s: str) -> str:
    """Schema di un estremo di data, con i gruppi suffissati da `s`."""
    return (
        # "Sep '22", "mar '19" — mese e anno a due cifre con apostrofo.
        # L'apostrofo è obbligatorio: senza, "Sep 22" sarebbe ambiguo con un
        # giorno del mese.
        rf"(?:(?P<mesea{s}>{_NOMI_MESE})\.?\s*['’´`]\s*(?P<aaa{s}>\d{{2}})(?!\d)"
        # "Gennaio 2020", "gen. 2020"
        rf"|(?P<mese{s}>{_NOMI_MESE})\.?\s+(?P<annom{s}>\d{{4}})"
        # "01/2020", "01-2020"
        rf"|(?P<mm{s}>\d{{1,2}})\s*[/\-.]\s*(?P<annon{s}>\d{{4}})"
        # "01/20"
        rf"|(?P<mm2{s}>\d{{1,2}})\s*/\s*(?P<aa{s}>\d{{2}})(?!\d)"
        # "2020"
        rf"|(?P<anno{s}>\d{{4}}))"
    )


# Formule che indicano "fino a oggi". La versione precedente ne riconosceva
# quattro; sui curriculum reali ne compaiono molte di più.
_ATTUALE = (r"(?:present(?:e|ly)?|attual(?:e|mente)|tuttora|oggi|ad\s+oggi"
            r"|in\s*corso|current(?:ly)?|now|today|to\s+date|in\s+carica)")

# Separatori di intervallo. La versione precedente usava [-–to/]: mancavano il
# trattino lungo — che è quello inserito automaticamente dai word processor —
# e le forme discorsive italiane "dal … al …".
_SEPARATORE = r"(?:\s*[-–—‒―~]+\s*|\s+(?:a|al|to|fino\s+a(?:l)?)\s+)"

_INTERVALLO_RE = re.compile(
    _schema_estremo("_i") + _SEPARATORE +
    rf"(?:(?P<ora>{_ATTUALE})|" + _schema_estremo("_f") + ")",
    re.IGNORECASE,
)

# Una riga che contiene SOLO una data, nient'altro. Serve per i curriculum a
# due colonne: l'estrazione del PDF restituisce la colonna laterale come righe
# isolate, e un intervallo si trova spezzato su due righe consecutive.
_SOLO_DATA_RE = re.compile(
    rf"^\s*{_schema_estremo('_s')}\s*$|^\s*(?P<ora_s>{_ATTUALE})\s*$",
    re.IGNORECASE,
)


def _estremo_da_gruppi(g: dict, s: str) -> tuple[int, int | None] | None:
    """Ricava (anno, mese) dai gruppi con suffisso `s`. None se assenti."""
    if g.get(f"aaa{s}"):
        return _normalizza_anno(g[f"aaa{s}"]), _MESI[g[f"mesea{s}"].lower()]
    if g.get(f"annom{s}"):
        return int(g[f"annom{s}"]), _MESI[g[f"mese{s}"].lower()]
    if g.get(f"annon{s}"):
        return int(g[f"annon{s}"]), int(g[f"mm{s}"])
    if g.get(f"aa{s}"):
        return _normalizza_anno(g[f"aa{s}"]), int(g[f"mm2{s}"])
    if g.get(f"anno{s}"):
        return int(g[f"anno{s}"]), None
    return None


def _mese_assoluto(anno: int, mese: int | None) -> int:
    """Indice progressivo in mesi. Mese ignoto → gennaio, per non inventare
    durata dove il documento non la dichiara."""
    return anno * 12 + ((mese or 1) - 1)


def _normalizza_anno(a2: str) -> int:
    """Anno a due cifre → quattro. 90-99 = XX secolo, il resto = XXI."""
    n = int(a2)
    return 1900 + n if n >= 50 else 2000 + n


def _calculate_years_of_experience(experience_lines: list[str],
                                   con_provenienza: bool = False):
    """
    Stima gli anni di esperienza lavorativa dagli intervalli di date presenti
    nel blocco "experience" del curriculum.

    FORMATI RICONOSCIUTI
    ────────────────────
      2020 – 2023            2020 — 2023          2020-2023
      dal 2020 al 2023       2020 a 2023          2020 to 2023
      Gennaio 2020 – Marzo 2023        gen. 2020 – mar. 2023
      01/2020 – 06/2023      01/20 – 06/23
      June 2019 – present    2022 – oggi / attuale / tuttora / in corso

    PERCHÉ È STATA RISCRITTA
    ────────────────────────
    La versione precedente otteneva l'87,2% di stime esatte sugli 810 CV
    sintetici e falliva su 7 curriculum reali su 15, restituendo zero. Il
    divario non era casuale: `render_cvs.py` genera il periodo lavorativo con
    una sola formattazione — `f"{start_year} – 2024"` — quindi l'estrattore era
    stato validato su un unico formato, prodotto dallo stesso script che
    fornisce la ground truth. Su documenti veri, dove ognuno scrive le date come
    preferisce, quella validazione non diceva nulla.

    I quattro difetti corretti:

      1. I MESI VENIVANO SCARTATI. Erano catturati da un gruppo non catturante e
         il calcolo era (anno_fine − anno_inizio) × 12: "Gennaio 2020 – Novembre
         2020" valeva ZERO mesi. Ogni esperienza interna a un anno solare
         spariva. Sui CV sintetici non si notava perché i periodi erano sempre
         su anni interi.

      2. IL TRATTINO LUNGO NON ERA UN SEPARATORE. La classe era [-–to/]:
         conteneva trattino breve e medio, non l'em-dash —, che è quello
         inserito automaticamente da Word.

      3. LE FORMULE DI ATTUALITÀ ERANO QUATTRO. Mancavano "presente", "ad oggi",
         "tuttora", "currently", "now", "today".

      4. GLI INTERVALLI SI SOMMAVANO SENZA UNIRLI. Due ruoli paralleli venivano
         contati due volte. Un curriculum reale risultava avere 48 anni di
         esperienza. Ora gli intervalli vengono uniti prima di sommarli, quindi
         i periodi sovrapposti contano una volta sola.

    CONVENZIONE SUI MESI IGNOTI
    ───────────────────────────
    Quando il documento indica solo l'anno, si assume gennaio a entrambi gli
    estremi. "2020 – 2023" vale quindi 36 mesi, come nella versione precedente.

    L'UNIONE DEGLI INTERVALLI CAMBIA IL CONFRONTO CON LA GROUND TRUTH
    ────────────────────────────────────────────────────────────────
    Va dichiarato, perché ne discende un numero diverso da quello riportato in
    precedenza. Il generatore rende due ruoli come "2022 – 2024" e
    "2021 – 2024" — periodi che nel documento si sovrappongono — ma la ground
    truth li somma: 2 + 3 = 5 anni. Un lettore umano, guardando quel
    curriculum, direbbe 3, che è l'arco temporale effettivamente coperto. La
    discrepanza riguarda 540 CV su 810.

    Ne segue che l'87,2% di stime esatte attribuito alla versione precedente
    non misurava la capacità di leggere le date: misurava il fatto che la
    funzione sommava senza unire, replicando così l'aritmetica del generatore.
    Con l'unione — che è la lettura corretta del documento e ciò che elimina il
    caso reale dei 48 anni di esperienza — l'accordo con quella ground truth
    scende al 22,1%.

    I due numeri vanno riportati insieme: il divario misura un'incoerenza fra
    ciò che il generatore scrive e ciò che dichiara, non un peggioramento del
    parser.
    """
    ora = datetime.now()
    intervalli: list[tuple[int, int]] = []

    def registra(anno_i, mese_i, anno_f, mese_f) -> None:
        if not (1950 <= anno_i <= ora.year + 1 and 1950 <= anno_f <= ora.year + 1):
            return
        if (mese_i and not 1 <= mese_i <= 12) or (mese_f and not 1 <= mese_f <= 12):
            return
        a, b = _mese_assoluto(anno_i, mese_i), _mese_assoluto(anno_f, mese_f)
        if b >= a:
            intervalli.append((a, b))

    # ── Passata 1: intervalli contenuti in una sola riga ────────────────────
    for riga in experience_lines:
        for m in _INTERVALLO_RE.finditer(riga):
            g = m.groupdict()
            estremo_i = _estremo_da_gruppi(g, "_i")
            if estremo_i is None:
                continue
            if g.get("ora"):
                estremo_f = (ora.year, ora.month)
            else:
                estremo_f = _estremo_da_gruppi(g, "_f")
            if estremo_f is None:
                continue
            registra(estremo_i[0], estremo_i[1], estremo_f[0], estremo_f[1])

    # ── Passata 2: intervalli spezzati su due righe consecutive ─────────────
    # I curriculum a due colonne mettono le date in una colonna laterale, e
    # l'estrazione del PDF le restituisce come righe isolate:
    #     Sep '22
    #     Sep '23
    #     Torino, IT
    # La passata 1 non le vede, perché lavora una riga per volta. Qui si
    # accoppiano le righe che contengono SOLTANTO una data: la condizione è
    # restrittiva di proposito, perché accoppiare righe che contengono anche
    # altro produrrebbe intervalli inventati fra esperienze diverse.
    solo_date: list[tuple[int, tuple[int, int | None] | str]] = []
    for idx, riga in enumerate(experience_lines):
        m = _SOLO_DATA_RE.match(riga)
        if not m:
            continue
        if m.groupdict().get("ora_s"):
            solo_date.append((idx, "ora"))
        else:
            e = _estremo_da_gruppi(m.groupdict(), "_s")
            if e:
                solo_date.append((idx, e))

    usate: set[int] = set()
    for k in range(len(solo_date) - 1):
        idx_a, val_a = solo_date[k]
        idx_b, val_b = solo_date[k + 1]
        if idx_a in usate or idx_b != idx_a + 1:
            continue
        if val_a == "ora":          # "oggi" non può essere l'inizio
            continue
        fine_estremo = (ora.year, ora.month) if val_b == "ora" else val_b
        registra(val_a[0], val_a[1], fine_estremo[0], fine_estremo[1])
        usate.update({idx_a, idx_b})

    # ── Unione degli intervalli sovrapposti ─────────────────────────────────
    # Due ruoli contemporanei non raddoppiano l'esperienza della persona.
    totale = 0
    if intervalli:
        intervalli.sort()
        inizio, fine = intervalli[0]
        for a, b in intervalli[1:]:
            if a <= fine:
                fine = max(fine, b)
            else:
                totale += fine - inizio
                inizio, fine = a, b
        totale += fine - inizio

    provenienza = "intervalli" if totale else "assente"

    # ── Ripiego: anni isolati ───────────────────────────────────────────────
    # Prende l'anno più piccolo e il più grande presenti nel blocco e li
    # sottrae. Non corrisponde ad alcun periodo dichiarato: è una congettura,
    # e su due dei quindici curriculum reali ha prodotto 16 e 20 anni senza che
    # fosse stato riconosciuto un solo intervallo. Il valore resta perché
    # spesso è approssimativamente giusto, ma viene marcato come tale: chi lo
    # consuma deve poter distinguere una misura da una stima.
    if totale == 0:
        anno_re = re.compile(r"\b((?:19|20)\d{2})\b")
        trovati = set()
        for riga in experience_lines:
            for m in anno_re.finditer(riga):
                y = int(m.group(1))
                if 1990 <= y <= ora.year:
                    trovati.add(y)
        if len(trovati) >= 2:
            totale = (max(trovati) - min(trovati)) * 12
            provenienza = "ripiego"

    anni = round(totale / 12, 1)
    return (anni, provenienza) if con_provenienza else anni


def _seniority_from_years(years: float) -> str:
    """
    Classifica il candidato in base agli anni di esperienza.

    Soglie:
        < 2 anni  → junior
        2–4 anni  → mid
        ≥ 5 anni  → senior
    """
    if years >= 5:
        return "senior"
    if years >= 2:
        return "mid"
    return "junior"


# ══════════════════════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

class MainParser:
    """
    Parser CV end-to-end per SkillPath AI.

    Carica i database ESCO una volta sola per categoria (con cache degli
    embedding su disco), poi li riutilizza per tutti i CV processati.
    """

    def __init__(self, soglie: dict | None = None,
                 cert_solo_sezione: bool = False):
        """
        soglie
            Soglie di similarità per i vari percorsi di estrazione:
                sw   candidato di una parola       0.85
                mw   candidato di più parole       0.88
                acr  acronimo o CamelCase          0.85
                occ  occupazione                   0.80
                edu  titolo di studio              0.62
                lang lingua (ripiego semantico)    0.72
                cert certificazione                0.86
            e due limiti di produzione:
                cert_max   quante certificazioni al massimo   10
                skill_max  quante competenze al massimo       25

            NOTA SULLA SOGLIA DELLE CERTIFICAZIONI. Il valore 0.75 è molto più
            basso di quelli usati per le competenze, e sui curriculum reali
            produce quasi solo rumore: su 15 documenti veri, «Abilitazione
            PES/PAV» è stata assegnata a 14 persone e «Abilitazione Muletto» a
            10, e 9 documenti su 15 hanno saturato il tetto di 10
            certificazioni. Sul dataset sintetico il difetto era invisibile,
            perché il generatore pescava le certificazioni dalla stessa lista
            usata per il riconoscimento: i match risultavano corretti per
            costruzione. La ground truth dice però che i CV sintetici hanno in
            media 1.34 certificazioni, contro le 4.6 estratte: la
            sovraproduzione c'era anche lì, semplicemente non era mai stata
            misurata.

        cert_solo_sezione
            Se True, le certificazioni vengono cercate SOLO nella sezione
            dedicata. Il comportamento predefinito le cerca anche fra le righe
            di competenze e istruzione, il che recupera qualcosa quando la
            sezione non viene riconosciuta, ma espone ogni riga di competenze
            al rischio di essere scambiata per una certificazione. Sui 15
            curriculum reali la sezione dedicata è stata riconosciuta in un solo
            documento: quasi tutti i candidati arrivavano quindi da righe che
            certificazioni non erano.
        """
        # La soglia delle certificazioni è 0.86 e non più 0.75. Il valore
        # precedente produceva, sul dataset sintetico, precisione 0,250 e 4,77
        # certificazioni per curriculum contro le 1,34 vere; su 15 curriculum
        # reali assegnava «Abilitazione Muletto» a 10 persone su 15 e saturava
        # il tetto di 10 in 9 documenti. Il catalogo conta 45 voci in tutto:
        # con una soglia bassa e un tetto di 10, ogni curriculum ne pescava
        # oltre un quinto. Misurato su 567 CV di riporto mai usati per la
        # scelta: precisione 0,250 → 0,837, richiamo invariato (0,779 → 0,781),
        # F1 0,364 → 0,799. Vedi analysis/valuta_certificazioni.py.
        self.soglie = {"sw": 0.85, "mw": 0.88, "acr": 0.85, "occ": 0.80,
                       "edu": 0.62, "lang": 0.72, "cert": 0.86,
                       "cert_max": 10, "skill_max": 25}
        if soglie:
            ignote = set(soglie) - set(self.soglie)
            if ignote:
                raise ValueError(
                    f"Soglie sconosciute: {sorted(ignote)}. "
                    f"Attese: {sorted(self.soglie)}")
            self.soglie.update(soglie)
        self.cert_solo_sezione = cert_solo_sezione

        # radice progetto: src/ è un livello sotto la root
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.src_dir  = os.path.join(self.base_dir, "dataset", "source")
        self.supp_dir = os.path.join(self.base_dir, "dataset", "supplementary")
        # Dataset bilingue: IT come primary, EN come fallback
        self.src_it = os.path.join(self.base_dir, "dataset", "source_it")
        self.src_en = os.path.join(self.base_dir, "dataset", "source_en")
        # Se source_en non esiste ancora, usa source/ come EN di riserva
        if not os.path.exists(self.src_en):
            self.src_en = self.src_dir
        # SemanticMapper gestisce il modello sentence-transformers e la cache embedding
        self.mapper = SemanticMapper()

    # ──────────────────────────────────────────────────────────────────────────
    def segment_cv(self, lines: list[str]) -> dict[str, list[str]]:
        """
        Divide il testo del CV in blocchi tematici scansionando le righe
        in ordine e cambiando "sezione corrente" ogni volta che viene
        riconosciuto un header.

        Algoritmo (O(n · k) con n = righe, k = keyword totali):
            current_section ← "summary"
            per ogni riga:
                se è un header → aggiorna current_section
                altrimenti     → appendi riga al blocco current_section

        Le righe che precedono il primo header finiscono in "summary"
        (tipicamente: nome, contatti, profilo introduttivo).

        Returns:
            dict con chiavi: "summary", "experience", "education",
                             "skills", "languages", "certifications"
            ciascuna mappata alla lista di righe che appartengono a quel blocco.
        """
        current = "summary"
        blocks: dict[str, list[str]] = {k: [] for k in SECTION_KEYWORDS}
        blocks["summary"] = []

        for raw in lines:
            is_h, section = _line_is_header(raw)
            if is_h and section:
                current = section
                continue
            blocks[current].append(raw)
        return blocks

    # ──────────────────────────────────────────────────────────────────────────
    def parse_cv(self, cv_path: str) -> dict:
        """
        Esegue la pipeline completa su un singolo CV (PDF o DOCX).

        Fasi:
            1. Estrazione testo → lista righe pulite
            2. Segmentazione → blocchi per sezione
            3. Filtro rumore  → elimina date isolate, righe troppo corte, ecc.
            4. Match semantico per categoria (education, occupations, skills,
               languages, certifications)
            5. Classificazione skill in essential / optional tramite ESCO relations
            6. Costruzione JSON output

        Args:
            cv_path: percorso assoluto o relativo al file PDF/DOCX.

        Returns:
            Dizionario JSON compatibile con il formato atteso dal matching_engine.
        """
        # Risolvi percorso relativo rispetto alla cartella dello script
        if not os.path.isabs(cv_path):
            cv_path = os.path.join(self.base_dir, cv_path)

        # ── FASE 1: Estrazione testo ──────────────────────────────────────────
        # get_text() delega a PyMuPDF (PDF) o python-docx (DOCX).
        # Ritorna una lista di stringhe, una per riga del documento.
        raw_lines = get_text(cv_path)
        if not raw_lines:
            print(f"[main_parser] Nessun testo estratto da {cv_path}")
            return self._empty_result(cv_path)
        pdf_path = cv_path  # alias per retro-compatibilità interna

        # ── FASE 2: Segmentazione ─────────────────────────────────────────────
        blocks = self.segment_cv(raw_lines)

        # ── FASE 3: Filtro rumore ─────────────────────────────────────────────
        # filter_lines() rimuove: righe < 3 char, righe solo-data (es. "2022"),
        # righe senza lettere. Le righe rumorose non vengono passate all'embedding
        # per evitare match semantici senza senso.
        exp_lines     = filter_lines(blocks["experience"])
        edu_lines     = filter_lines(blocks["education"])
        skl_lines     = filter_lines(blocks["skills"])
        lng_lines     = filter_lines(blocks["languages"])
        cert_lines    = filter_lines(blocks["certifications"])
        summary_lines = filter_lines(blocks["summary"])

        # ── Seniority (basata su date reali, non su keyword) ──────────────────
        years_exp, years_src = _calculate_years_of_experience(
            blocks["experience"], con_provenienza=True)
        seniority = _seniority_from_years(years_exp)

        # ══════════════════════════════════════════════════════════════════════
        # FASE 4A — ISTRUZIONE
        # ══════════════════════════════════════════════════════════════════════
        # Database: degree_programs.json (~400 corsi di laurea italiani MIUR)
        # Candidati: righe della sezione education; se vuota, usa il summary
        #            (alcuni CV mettono il titolo di studio nell'intro).
        # Threshold: 0.62 — più basso degli altri perché i nomi dei corsi
        #            italiani divergono molto dalle etichette del database.
        self.mapper.load_database(os.path.join(self.supp_dir, "degree_programs.json"))
        edu_candidates = edu_lines or summary_lines
        edu_matches = self.mapper.find_matches(
            edu_candidates, threshold=self.soglie["edu"], top_k=2, max_results=3,
            return_scores=True
        )

        # ══════════════════════════════════════════════════════════════════════
        # FASE 4B — OCCUPAZIONE (titolo professionale)
        # ══════════════════════════════════════════════════════════════════════
        # Database: occupations.json (~3 000 occupazioni ESCO)
        # Candidati: estratti con _extract_role_candidates() che filtra
        #            righe-titolo plausibili dall'experience block.
        #            Se troppo pochi (<3), aggiunge exp_lines + summary_lines
        #            come fallback (es. CV senza sezione experience esplicita).
        # Threshold: 0.80 — soglia alta per evitare titoli generici.
        # max_results: 3 — massimo 3 occupazioni per candidato.
        # Caricamento bilingue occupazioni (IT + EN) se source_it disponibile
        _it_occ = os.path.join(self.src_it, "occupations.json")
        _en_occ = os.path.join(self.src_en, "occupations.json")
        if os.path.exists(_it_occ) and os.path.exists(_en_occ):
            self.mapper.load_databases_bilingual(_it_occ, _en_occ)
        else:
            self.mapper.load_database(os.path.join(self.src_dir, "occupations.json"))
        occ_candidates = self._extract_role_candidates(exp_lines)
        if len(occ_candidates) < 3:
            occ_candidates = list(dict.fromkeys(
                occ_candidates + exp_lines + summary_lines
            ))
        occ_matches = self.mapper.find_matches(
            occ_candidates, threshold=self.soglie["occ"], top_k=1, max_results=3,
            return_scores=True
        )

        # ══════════════════════════════════════════════════════════════════════
        # FASE 4C — SKILL
        # ══════════════════════════════════════════════════════════════════════
        #
        # PREPARAZIONE CANDIDATI
        # ──────────────────────
        # I CV elencano le skill in modi molto diversi:
        #   (a) una per riga:         "Python\nSQL\nDocker"
        #   (b) comma-separated:      "Python, SQL, Docker, Git"
        #   (c) frasi con "quali:":   "Sistemi ERP quali: TeamSystem e SAP"
        #   (d) dentro parentesi:     "modellazione 3D (Solidworks)"
        #   (e) frasi narrative:      "Ho applicato la tecnica dello SMED..."
        #
        # _split_skill_candidates() gestisce a/b/c/d estraendo token individuali.
        # Il caso (e) viene catturato alzando il limite da 60 a 80 char: frasi
        # tra 61–80 char contengono spesso UN nome tecnologia dominante e il
        # modello multilingue riesce comunque ad estrarne il segnale semantico.
        # Oltre 80 char il rapporto segnale/rumore scende troppo.
        #
        # Caricamento bilingue skill (IT + EN) se source_it disponibile
        _it_skl = os.path.join(self.src_it, "skills.json")
        _en_skl = os.path.join(self.src_en, "skills.json")
        if os.path.exists(_it_skl) and os.path.exists(_en_skl):
            self.mapper.load_databases_bilingual(_it_skl, _en_skl)
        else:
            self.mapper.load_database(os.path.join(self.src_dir, "skills.json"))

        # Candidati da sezione skills + experience (split + parentesi + quali:)
        raw_skill_candidates = self._split_skill_candidates(skl_lines + exp_lines)

        # Acronimi e nomi CamelCase estratti DIRETTAMENTE dal testo grezzo.
        # Molte skill tecniche appaiono come acronimi dentro frasi narrative
        # troppo lunghe per passare il filtro 60 char: "VBA" in una frase da
        # 78 char, "SMED" in una frase da 69 char, ecc.
        # La regex estrae:
        #   - MAIUSCOLO 2-6 char: VBA, ERP, SAP, SMED, MRP, CAD, SPA...
        #   - CamelCase senza spazi: SolidWorks, TeamSystem, BaaN...
        # Filtro stop-word: esclude articoli/preposizioni italiani maiuscoli
        # (DAL, DEL, NEL, CON, PER...) che sono rumore garantito.
        # Aggiunto: codici provincia IT (LT, RM, MI, TO...), sigle geografiche,
        # suffissi aziendali (SPA, SRL), termini personali (UE, CV, NR, ID).
        _IT_STOP = {
            "DAL","DEL","NEL","CON","PER","CHE","UNA","UNO","ALL","ALLA",
            "SUI","SUL","COI","COL","AGLI","ALLE","ALLO","DEGLI","DELLE",
            "DELLE","SIA","NON","HO","HA","AL","IL","LA","LE","LO","DI",
            "DA","IN","A","E","O",
            # Sigle geografiche italiane (province)
            "LT","RM","MI","TO","FI","BO","NA","VE","GE","PA","BA","CT",
            "CA","TS","AN","PE","RC","TA","CB","PG","AO","BZ","TN","UD",
            "GO","TR","VT","RI","FR","LT","AQ","CH","TE","IS","CE","SA",
            "AV","BN","KR","CZ","CS","VV","ME","AG","CL","EN","RG","SR","TP",
            "Roma","ROMA",
            # Suffissi aziendali
            "SPA","SRL","NV","SA","AS",
            # Sigle generiche non-skill
            "UE","EU","NB","OK","HR","VS","ID","NR","NO","SI",
            # Termini personali / legali
            "DATI","GDPR","UE",
        }
        _acronym_re = re.compile(r"\b([A-Z]{2,6})\b")
        _camel_re   = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]*)+)\b")
        acronym_candidates: list[str] = []
        _seen_acr: set[str] = set()
        for line in skl_lines + exp_lines:
            for m in _acronym_re.finditer(line):
                tok = m.group(1)
                if tok not in _IT_STOP and tok.lower() not in _seen_acr:
                    _seen_acr.add(tok.lower())
                    acronym_candidates.append(tok)
            for m in _camel_re.finditer(line):
                tok = m.group(1)
                if tok.lower() not in _seen_acr:
                    _seen_acr.add(tok.lower())
                    acronym_candidates.append(tok)

        # Filtro lunghezza 60 char sui candidati normali
        skill_candidates = [c for c in raw_skill_candidates if len(c) <= 60]

        # ── Filtro qualità candidati ───────────────────────────────────────────
        # Rimuove token che non possono essere skill:
        #   1. Parole singole interamente minuscole (articoli, preposizioni,
        #      aggettivi comuni che entrano se il PDF estrae una parola per riga)
        #   2. Pattern dati personali (Nato a, Residente, coniugato, date "Dal X")
        #   3. Numeri isolati e frammenti senza lettere sufficienti
        _PERSONAL_RE = re.compile(
            r"^(?:nato\s+a|residente|coniugato|celibe|nubile|dal\s+\d|"
            r"il\s+\d|dati\s+personali|gdpr|679\s*\(|autorizza)",
            re.IGNORECASE
        )
        _DATE_FRAG_RE = re.compile(r"^\d{1,2}[/\-\.]\d{1,2}([/\-\.]\d{2,4})?$")

        def _is_valid_skill_candidate(c: str) -> bool:
            stripped = c.strip().rstrip(".,;")
            # Scarta candidati con dati personali
            if _PERSONAL_RE.match(stripped):
                return False
            # Scarta righe che sono solo una lingua (+ eventuale livello):
            # sono già gestite dal rilevatore lingue dedicato
            if _is_language_only(stripped):
                return False
            # Scarta frammenti data puri
            if _DATE_FRAG_RE.match(stripped):
                return False
            # Parola singola: tieni solo se inizia con maiuscola (nome proprio/tecnico)
            # oppure è un noto termine tecnico minuscolo
            words = stripped.split()
            if len(words) == 1:
                w = words[0].rstrip(".,;")
                # Minuscola → quasi certamente preposizione/aggettivo comune, scarta
                if w and w[0].islower():
                    return False
            return True

        skill_candidates = [c for c in skill_candidates if _is_valid_skill_candidate(c)]
        # ─────────────────────────────────────────────────────────────────────

        # MATCH SEMANTICO
        # ───────────────
        # Soglie calibrate per multilingual-e5-base:
        # - 0.88 per frasi (candidati narrativi, più rumore semantico)
        # - 0.85 per acronimi/CamelCase (token già precisi, rischio FP basso)
        # Gli acronimi/CamelCase vengono cercati separatamente perché sono
        # token molto specifici: score alto → alta confidenza, score basso →
        # il termine non esiste in ESCO con quel nome.
# Candidati parola-singola (es. "Excel", "Office", "Solidworks"):
        # soglia più bassa perché sono token precisi con poco rumore semantico.
        # Candidati multi-parola (frasi narrative): soglia più alta per filtrare FP.
        single_word_cands = [c for c in skill_candidates if len(c.split()) == 1]
        multi_word_cands  = [c for c in skill_candidates if len(c.split()) > 1]

        skill_matches_sw = self.mapper.find_matches(
            single_word_cands, threshold=self.soglie["sw"], top_k=1,
            max_results=int(self.soglie["skill_max"]),
            return_scores=True
        )
        skill_matches_mw = self.mapper.find_matches(
            multi_word_cands, threshold=self.soglie["mw"], top_k=1,
            max_results=int(self.soglie["skill_max"]),
            return_scores=True
        )
        skill_matches = skill_matches_sw + skill_matches_mw
        # Merge acronimi: stessa soglia 0.85, poi deduplicazione per ID
        acr_matches = self.mapper.find_matches(
            acronym_candidates, threshold=self.soglie["acr"], top_k=1,
            max_results=int(self.soglie["skill_max"]),
            return_scores=True
        ) if acronym_candidates else []

        _seen_ids: dict[str, dict] = {}
        for m in skill_matches + acr_matches:
            if m["id"] not in _seen_ids or m["score"] > _seen_ids[m["id"]]["score"]:
                _seen_ids[m["id"]] = m
        skill_matches = sorted(_seen_ids.values(), key=lambda x: x["score"], reverse=True)[:25]

        # PIPELINE DI FILTRI POST-SEMANTIC (6 stadi)
        # ──────────────────────────────────────────
        # I filtri vengono applicati in cascata sull'output del semantic match.
        # L'ordine è rilevante: i filtri più economici (regex) precedono
        # quelli che richiedono più logica.

        # Filtro 1 — Label troppo corte
        # Acronimi di 1-4 caratteri ("VB", "R", "SAP") sono ambigui:
        # "R" può essere il linguaggio statistico o la lettera dell'alfabeto.
        # Si eliminano per ridurre il rumore.
        skill_matches = [m for m in skill_matches if len(m["label"]) > 4]

        # Filtro 2 — Label con articolo iniziale
        # In ESCO esistono label come "a production process", "an understanding of...".
        # Sono frammenti di frase (non skill nominali) che entrano nel database
        # ESCO come descrizioni di competenza. Non appartengono a un CV.
        skill_matches = [
            m for m in skill_matches
            if not re.match(r"^(a|an|the)\s", m["label"].lower())
        ]

        # Filtro 3 — Label task-oriented (verbi/gerundi)
        # Analizzato in dettaglio sopra (_ESCO_TASK_LABEL_RE).
        # Rimuove: "using consulting techniques", "verify feasibility", ecc.
        skill_matches = [
            m for m in skill_matches
            if not _ESCO_TASK_LABEL_RE.match(m["label"])
        ]

        # Filtro 3-bis — Nomi di lingua
        # ESCO contiene le lingue come skill ("francese", "neerlandese",
        # "svedese"…). Le lingue dichiarate nel CV vengono però già estratte
        # dal rilevatore dedicato (_detect_languages_by_keyword) e finiscono
        # nel blocco "languages" dell'output, non fra le skill.
        # Senza questo filtro la stessa informazione entra due volte, e la
        # seconda come falso positivo: sui CV sintetici di valutazione i soli
        # nomi di lingua producevano circa un terzo di TUTTI i falsi positivi
        # del parser (es. "francese" 183 FP e 0 TP, "neerlandese" 111 FP e 0).
        skill_matches = [
            m for m in skill_matches
            if _normalize_lang(m["label"]) not in _LANGUAGE_NAMES
        ]

        # Filtro 4 — Equipment terms
        # Applicato da _verify_skill_mentions():
        # label contenenti "apparatus", "machinery", "device", "equipment",
        # "appliance" vengono accettate SOLO se la frase esatta compare nel testo.
        # Motivo: "office apparatus" matcha semanticamente perché "office" appare
        # nel CV (es. Microsoft Office), ma l'ontologia intende attrezzatura fisica.
        skill_matches = self._verify_skill_mentions(
            skill_matches, " ".join(raw_lines)
        )

        # ── Lookup dizionario supplementare (bypass filtro verbo) ────────────
        # Le skill ESCO con label verb-start (manage, use, train, identify…)
        # vengono sistematicamente rimosse dal Filtro 3 anche quando il testo
        # le contiene. Questo lookup le recupera tramite pattern italiani
        # direttamente sul testo grezzo, iniettando gli ID nel risultato finale
        # DOPO i filtri semantici. Gli alias sono in skill_aliases.json.
        raw_full_text = " ".join(raw_lines)
        alias_matches = self._lookup_skill_aliases(
            raw_full_text,
            already_found={m["id"] for m in skill_matches},
        )
        skill_matches = skill_matches + alias_matches

        # ══════════════════════════════════════════════════════════════════════
        # FASE 4D — LINGUE
        # ══════════════════════════════════════════════════════════════════════
        #
        # Strategia a due livelli (keyword first, semantic fallback):
        #
        # Livello 1 — Rilevamento keyword (prioritario):
        #   Più affidabile del semantic per le lingue perché i nomi delle lingue
        #   e i codici CEFR (B2, C1...) sono token molto specifici.
        #   Lavora riga per riga per evitare cross-contaminazione:
        #   "Italiano madrelingua / Inglese B2" → due righe separate,
        #   altrimenti "madrelingua" potrebbe essere assegnato all'inglese.
        #   Regola speciale: italiano senza livello esplicito → "native"
        #   (su un CV italiano, la propria lingua è sempre madrelingua).
        #
        # Livello 2 — Match semantico (fallback):
        #   Usato solo se il rilevamento keyword non trova nulla.
        #   Threshold 0.72 (più basso) per catturare formulazioni meno esplicite.
        #
        lang_matches = self._detect_languages_by_keyword(raw_lines)
        if not lang_matches:
            self.mapper.load_database(
                os.path.join(self.supp_dir, "language_levels.json")
            )
            lang_candidates = lng_lines + skl_lines + summary_lines
            lang_matches = self.mapper.find_matches(
                lang_candidates, threshold=self.soglie["lang"], top_k=2, max_results=6,
                return_scores=True,
            )

        # ══════════════════════════════════════════════════════════════════════
        # FASE 4E — CERTIFICAZIONI
        # ══════════════════════════════════════════════════════════════════════
        # Database opzionale (non tutti i progetti lo includono).
        # Cerca nei blocchi certifications, skills e education.
        cert_matches = []
        cert_db = os.path.join(self.supp_dir, "certifications.json")
        if os.path.exists(cert_db):
            self.mapper.load_database(cert_db)
            cert_candidates = (cert_lines if self.cert_solo_sezione
                               else cert_lines + skl_lines + edu_lines)
            cert_matches = self.mapper.find_matches(
                cert_candidates, threshold=self.soglie["cert"], top_k=1,
                max_results=int(self.soglie["cert_max"]),
                return_scores=True,
            )

        # ══════════════════════════════════════════════════════════════════════
        # FASE 5 — ESSENTIAL vs OPTIONAL
        # ══════════════════════════════════════════════════════════════════════
        #
        # ESCO definisce per ogni occupazione due insiemi di skill:
        #   - essential: skill fondamentali per svolgere il ruolo
        #   - optional:  skill utili ma non indispensabili
        #
        # Algoritmo:
        #   Per ogni occupazione trovata in fase 4B, legge le relazioni da
        #   occupation_skill_relations.json e separa le skill trovate in 4C
        #   nelle due categorie. Le skill non classificate → optional "extra".
        #
        essential_ids, optional_ids = self._split_skills_by_relation(
            occ_matches, skill_matches
        )

        # ══════════════════════════════════════════════════════════════════════
        # FASE 6 — OUTPUT JSON
        # ══════════════════════════════════════════════════════════════════════
        return {
            "cv_id": f"parsed_{os.path.basename(pdf_path)}",
            "cv": {
                "persona": {
                    "seniority": seniority,
                    "years_of_experience": years_exp,
                    # Da dove viene il numero sopra:
                    #   "intervalli" — letto da periodi dichiarati nel testo
                    #   "ripiego"    — congettura da anno minimo e massimo
                    #   "assente"    — nessuna data riconosciuta, valore 0
                    "years_source": years_src,
                },
                "education": {
                    # Se nessun match trovato, usa "deg_none" come placeholder
                    "degree_id":  edu_matches[0]["id"] if edu_matches else "deg_none",
                    "candidates": edu_matches,
                },
                "languages": [
                    {"lang_id": m["id"], "label": m["label"], "score": m["score"]}
                    for m in lang_matches
                ],
                "skills": {
                    "essential_ids": essential_ids,
                    "optional_ids":  optional_ids,
                    "all_matches":   skill_matches,
                },
                "work_experience": [
                    {"job_title_id": m["id"], "label": m["label"], "score": m["score"]}
                    for m in occ_matches
                ],
                "certifications": cert_matches,
            },
            "debug": {
                # section_sizes: utile per diagnosticare CV mal-segmentati
                "section_sizes": {k: len(v) for k, v in blocks.items()},
            },
        }

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — DIZIONARIO SUPPLEMENTARE (bypass filtro verbo)
    # ══════════════════════════════════════════════════════════════════════════

    def _lookup_skill_aliases(
        self, raw_text: str, already_found: set[str]
    ) -> list[dict]:
        """
        Cerca nel testo grezzo del CV le espressioni italiane del dizionario
        supplementare e restituisce i match ESCO corrispondenti.

        Questo bypass è necessario perché le skill ESCO con label verb-start
        (manage, use, train, identify...) vengono filtrate dal Filtro 3
        (_ESCO_TASK_LABEL_RE) anche quando il semantic search le avrebbe trovate.

        Il lookup usa pattern regex case-insensitive; ogni match trovato viene
        aggiunto con score 0.95 e match_type "alias" (distinguibile in debug).

        Args:
            raw_text:      testo grezzo del CV concatenato in una stringa
            already_found: set di ESCO ID già trovati dalla pipeline semantica

        Returns:
            Lista di dict {id, label, score, match_type} da appendere a skill_matches
        """
        alias_path = os.path.join(self.supp_dir, "skill_aliases.json")
        if not os.path.exists(alias_path):
            return []

        try:
            with open(alias_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        entries = data.get("entries", [])
        text_lower = raw_text.lower()
        results: list[dict] = []

        for entry in entries:
            esco_id = entry.get("esco_id", "")
            label   = entry.get("label", "")
            if not esco_id or esco_id in already_found:
                continue

            patterns = entry.get("patterns", [])
            found = False
            for pat in patterns:
                try:
                    if re.search(pat, raw_text, re.IGNORECASE):
                        found = True
                        break
                except re.error:
                    # Pattern regex malformato: skip silenzioso
                    continue

            if found:
                results.append({
                    "id":         esco_id,
                    "label":      label,
                    "score":      0.95,
                    "match_type": "alias",
                })
                already_found.add(esco_id)

        return results

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — ESTRAZIONE CANDIDATI TITOLO PROFESSIONALE
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_role_candidates(exp_lines: list[str]) -> list[str]:
        """
        Estrae le righe "titolo di ruolo" dall'experience block.

        Due layout distinti dei CV:
        ┌─────────────────────────────────────────────────────┐
        │  Single-column (classic/modern)                     │
        │    riga corta, <= 55 char, inizia maiuscola,        │
        │    <= 7 parole, <= 2 cifre                          │
        │    Es: "Software Engineer"                          │
        ├─────────────────────────────────────────────────────┤
        │  Tabella Europass (2 colonne)                       │
        │    riga lunga separata da "—" o "–"                 │
        │    "Senior Engineer — Siemens AG — 2020–2024"       │
        │    → estrae solo il PRIMO segmento                   │
        │    → controlla cifre solo sul primo segmento        │
        │    (la riga intera ha le cifre degli anni)          │
        └─────────────────────────────────────────────────────┘

        Returns:
            Lista di candidati (max 20) ordinati per posizione nel CV.
        """
        out  = []
        seen = set()
        sep_re = re.compile(r"\s*[—\-–|]\s*")

        for line in exp_lines:
            if is_noise_line(line):
                continue
            if "@" in line or "www." in line or "http" in line:
                continue
            digits = sum(ch.isdigit() for ch in line)

            # Layout single-column: riga corta già pronta come candidato
            if len(line) <= 55 and digits <= 2 and line[0].isupper():
                if len(line.split()) <= 7:
                    if line.lower() not in seen:
                        seen.add(line.lower())
                        out.append(line)
                    continue

            # Layout Europass: estrai il titolo dal primo segmento
            if len(line) > 55:
                parts = sep_re.split(line)
                if parts:
                    first        = parts[0].strip()
                    first_digits = sum(ch.isdigit() for ch in first)
                    if (first
                            and 3 < len(first) <= 55
                            and first[0].isupper()
                            and len(first.split()) <= 7
                            and first_digits <= 2):
                        if first.lower() not in seen:
                            seen.add(first.lower())
                            out.append(first)

        return out[:20]

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — RILEVAMENTO LINGUE BY KEYWORD
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _detect_languages_by_keyword(lines: list[str]) -> list[dict]:
        """
        Rileva lingue e livello CEFR tramite ricerca keyword diretta.

        Preferito al match semantico per le lingue perché:
        1. I nomi delle lingue sono token molto specifici → meno ambiguità
        2. I codici CEFR (B2, C1...) non hanno equivalenti semantici
        3. Evita confusione: "inglese" e "italian" → stesso concetto,
           il modello potrebbe confonderli

        Processo per ogni riga del CV (contesto autonomo):
            a. Cerca il nome di una lingua nota (IT o EN)
            b. Cerca un indicatore di livello nella STESSA riga
            c. Se nessun livello trovato: italiano → native, altri → B1 (default)

        L'elaborazione per-riga evita che "madrelingua" di una lingua
        contamini la lingua menzionata nella riga successiva.

        Returns:
            Lista di dict {id, label, score} compatibile con il formato
            usato dal semantic mapper.
        """
        lang_map = {
            "italiano": "it", "italian": "it",
            "inglese": "en", "english": "en",
            "francese": "fr", "french": "fr",
            "spagnolo": "es", "spanish": "es",
            "tedesco": "de", "german": "de",
            "portoghese": "pt", "portuguese": "pt",
            "cinese": "zh", "chinese": "zh",
            "arabo": "ar", "arabic": "ar",
            "russo": "ru", "russian": "ru",
            "olandese": "nl", "dutch": "nl",
            "polacco": "pl", "polish": "pl",
            "svedese": "sv", "swedish": "sv",
            "rumeno": "ro", "romanian": "ro",
        }
        cefr_map = {
            "madrelingua": "native", "madre lingua": "native",
            "native": "native", "mother tongue": "native",
            "lingua madre": "native",
            "ottimo": "C1", "ottima": "C1", "fluente": "C1", "fluent": "C1",
            "avanzato": "C1", "advanced": "C1",
            "buono": "B2", "buona": "B2", "good": "B2",
            "intermedio": "B1", "intermediate": "B1",
            "base": "A2", "basic": "A2", "elementare": "A2",
            "c2": "C2", "c1": "C1", "b2": "B2",
            "b1": "B1", "a2": "A2", "a1": "A1",
        }

        found: dict[str, dict] = {}  # lang_code → primo match trovato

        for line in lines:
            line_low = line.lower()
            for lang_name, lang_code in lang_map.items():
                if lang_name not in line_low:
                    continue
                # Cerca il livello CEFR nella stessa riga
                cefr = None
                for kw, code in cefr_map.items():
                    if kw in line_low:
                        cefr = code
                        break
                # Livello di default: italiano senza livello = madrelingua
                if cefr is None:
                    cefr = "native" if lang_code == "it" else "B1"
                lang_id = f"lang_{lang_code}_{cefr}"
                # Teniamo solo il primo match per lingua (primo = più rilevante)
                if lang_code not in found:
                    found[lang_code] = {
                        "id":    lang_id,
                        "label": f"{lang_name.capitalize()} — {cefr}",
                        "score": 1.0,  # score fisso: match esatto per keyword
                    }
        return list(found.values())

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — SPLIT CANDIDATI SKILL
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _split_skill_candidates(lines: list[str]) -> list[str]:
        """
        Normalizza le righe della sezione skill in token individuali.

        Gestisce quattro pattern di layout che si trovano nei CV italiani reali:

        (a) Una skill per riga       → "Python", "SQL", "Docker"
            Passata direttamente come token.

        (b) Comma/punto-e-virgola    → "Python, SQL, Docker, Git"
            Divisa per [, ; / | •] → token separati.

        (c) Pattern "quali: X e Y"  → "Sistemi ERP quali: TeamSystem e SAP"
            I CV italiani usano spesso "quali:", "come:", "tra cui:" seguiti da
            un elenco di nomi. Estrae i nomi DOPO il marcatore, poi divide su
            " e " / " ed " per ottenere i singoli token.
            Esempio: "Sistemi ERP quali: TeamSystem e SAP" → ["TeamSystem", "SAP"]

        (d) Token tra parentesi      → "modellazione 3D (Solidworks)"
            Qualsiasi stringa tra parentesi tonde con 2–30 char è quasi sempre
            il nome esatto di uno strumento o tecnologia.
            Esempio: "modellazione 3D (Solidworks)" → ["Solidworks"] (extra token)
            Aggiunto IN AGGIUNTA alla riga originale per non perdere il contesto.

        I token vengono poi filtrati per lunghezza (≤ 60 char) in parse_cv()
        e deduplicati qui per efficienza.
        """
        sep_re   = re.compile(r"[,/;|]| \u2022 | - ")
        paren_re = re.compile(r"\(([^)]{2,30})\)")          # token in (parentesi)
        quali_re = re.compile(                               # "quali: X e Y"
            r"(?:quali|come|tra\s+cui)[:\s]+(.+)", re.IGNORECASE
        )
        conj_re  = re.compile(r"\s+(?:e|ed)\s+")            # congiunzione italiana

        out = []

        for line in lines:
            # ── Estrazione (d): token dentro parentesi ────────────────────
            # Li aggiungiamo PRIMA di processare la riga, così arrivano sempre
            # nell'output anche se la riga intera verrà esclusa per lunghezza.
            for m in paren_re.finditer(line):
                token = m.group(1).strip()
                if token:
                    out.append(token)

            # ── Estrazione (c): pattern "quali: X e Y" ────────────────────
            m_q = quali_re.search(line)
            if m_q:
                rest = m_q.group(1).strip()
                # Divide su virgola, poi su congiunzione
                for chunk in sep_re.split(rest):
                    chunk = chunk.strip()
                    for sub in conj_re.split(chunk):
                        sub = sub.strip().rstrip(".,;")
                        if 2 <= len(sub) <= 40:
                            out.append(sub)
                # La riga viene comunque aggiunta anche intera sotto (caso b/a)

            # ── Split su separatori (b) ────────────────────────────────────
            parts = [p.strip() for p in sep_re.split(line) if p.strip()]
            if len(parts) > 1:
                out.extend(parts)
            else:
                out.append(line)   # riga non separata → token singolo (a)

        # ── Deduplicazione e filtro rumore ────────────────────────────────
        seen, final = set(), []
        for p in out:
            if is_noise_line(p):
                continue
            key = p.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            final.append(p)
        return final

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — FILTRO EQUIPMENT POST-SEMANTIC
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _verify_skill_mentions(
        skill_matches: list[dict],
        all_text: str,
    ) -> list[dict]:
        """
        Filtro post-semantic minimo per le label di categoria "equipment/tools".

        MOTIVAZIONE
        ───────────
        Il semantic matcher opera sugli embedding di un modello multilingue
        (attualmente intfloat/multilingual-e5-base — vedi il default in
        SemanticMapper). Questo modello trova somiglianza concettuale anche
        tra lingue diverse (IT ↔ EN), il che è desiderabile per CV italiani
        con label ESCO inglesi.

        Tuttavia, alcune label ESCO appartengono alla categoria "equipment":
            "office apparatus", "industrial apparatus", "laboratory equipment"
        Queste tendono a fare match semantico di alta confidenza perché
        contengono parole comuni ("office", "industrial") che appaiono nel CV
        in contesti diversi (es. "Microsoft Office", "industrial engineering").

        SOLUZIONE
        ─────────
        Per le label contenenti termini equipment, richiediamo che la frase
        esatta compaia nel testo del CV. Questo è molto più restrittivo:
        "office apparatus" come frase letterale quasi certamente non appare
        in un CV standard.

        Per TUTTE LE ALTRE label NON applichiamo verifica testuale perché:
        - Il CV è spesso in italiano, le label ESCO sono in inglese
        - Verificare "thermoplastic" nel testo di un CV che usa "termoplastico"
          darebbe falso negativo (match legittimo eliminato per errore)
        - La soglia semantica 0.85 + filtri articolo/verbo già gestiscono
          la maggior parte del rumore

        Args:
            skill_matches: output di find_matches() già filtrato dai filtri 1-3
            all_text:      testo grezzo del CV (join di raw_lines)

        Returns:
            Lista filtrata: solo le label equipment con frase esatta nel testo
            + tutte le label non-equipment invariate.
        """
        _EQUIPMENT_TERMS = {"apparatus", "equipment", "device", "machinery", "appliance"}

        # Set di parole inglesi comuni che NON sono nomi propri di software.
        # Usato per distinguere "design" (concetto generico) da "Teradata" (brand).
        _COMMON_EN = {
            "design", "electronics", "management", "analysis", "planning",
            "production", "quality", "safety", "logistics", "research",
            "marketing", "accounting", "finance", "engineering", "science",
            "communication", "leadership", "teamwork", "reporting", "training",
            "consulting", "maintenance", "operations", "strategy", "development",
            "thermoplastic", "manufacturing", "administration", "procurement",
        }

        text_lower = all_text.lower()
        verified   = []
        for match in skill_matches:
            label      = match["label"]
            label_low  = label.lower()
            label_words = re.split(r"\W+", label_low)

            # ── Filtro equipment (invariato) ─────────────────────────────
            if set(label_words) & _EQUIPMENT_TERMS:
                if re.search(rf"\b{re.escape(label_low)}\b", text_lower):
                    verified.append(match)
                continue

            # ── Filtro proper noun (software/brand) ──────────────────────
            # Un label è "nome proprio di software/prodotto" se:
            #   (a) è una parola singola che inizia con maiuscola, oppure
            #   (b) contiene punteggiatura tipica di acronimi (punti, slash)
            # E NON è una parola inglese comune del dominio lavorativo.
            # Per queste label richiediamo che la radice del nome compaia
            # nel testo del CV (case-insensitive), altrimenti è quasi
            # certamente un falso positivo cross-domain.
            #
            # Esempi catturati:
            #   "Teradata"  → brand DB    → non nel CV → rimosso
            #   "Vyper"     → lang crypto → non nel CV → rimosso
            #   "M.U.G.E.N" → videogame   → non nel CV → rimosso
            #   "SAP R3"    → brand ERP   → "sap" nel CV → mantenuto
            #   "MS Excel"  → brand       → "excel" nel CV → mantenuto
            is_single_word    = len(label.split()) == 1
            starts_with_upper = label[0].isupper() if label else False
            has_inner_punct   = bool(re.search(r"[.\-/]", label))
            is_proper_noun    = (
                (is_single_word and starts_with_upper)
                or has_inner_punct
            ) and label_low not in _COMMON_EN

            if is_proper_noun:
                if has_inner_punct:
                    # Per etichette con punteggiatura interna (M.U.G.E.N, SAP R/3)
                    # usa la stringa de-punteggiata come radice di ricerca
                    root = re.sub(r"[.\-/]", "", label_low)
                else:
                    # Label CamelCase singola: usa la parola intera
                    root = label_low
                if len(root) >= 2 and root not in _COMMON_EN:
                    if root not in text_lower:
                        continue  # brand non trovato nel CV → scarta

            verified.append(match)
        return verified

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — ESSENTIAL vs OPTIONAL
    # ══════════════════════════════════════════════════════════════════════════

    def _split_skills_by_relation(
        self, occ_matches: list[dict], skill_matches: list[dict]
    ) -> tuple[list[str], list[str]]:
        """
        Classifica le skill trovate in essential / optional usando le
        relazioni definite da ESCO in occupation_skill_relations.json.

        Struttura del file:
            {
              "esco_occupation_id": {
                "essential": ["skill_id_1", "skill_id_2", ...],
                "optional":  ["skill_id_3", ...]
              }, ...
            }

        Algoritmo:
            1. Unisce i set essential e optional di TUTTE le occupazioni
               trovate (un candidato può aver coperto più ruoli).
            2. Classifica ogni skill matchata in essential, optional, o
               "other" (skill non prevista da ESCO per questi ruoli, va
               come optional extra).

        Returns:
            (essential_ids, optional_ids) — liste di ID ESCO.
        """
        rel_path  = os.path.join(self.src_dir, "occupation_skill_relations.json")
        skill_ids = [s["id"] for s in skill_matches]
        if not occ_matches or not os.path.exists(rel_path):
            return skill_ids, []
        try:
            with open(rel_path, "r", encoding="utf-8") as f:
                rels = json.load(f)
        except Exception:
            return skill_ids, []

        essential_set, optional_set = set(), set()
        for occ in occ_matches:
            target = rels.get(occ["id"])
            if not target:
                continue
            essential_set.update(target.get("essential", []))
            optional_set.update(target.get("optional",  []))

        if not essential_set and not optional_set:
            return skill_ids, []

        essential = [s for s in skill_ids if s in essential_set]
        optional  = [s for s in skill_ids if s in optional_set and s not in essential_set]
        others    = [s for s in skill_ids if s not in essential_set and s not in optional_set]
        return essential, optional + others

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER — RISULTATO VUOTO
    # ══════════════════════════════════════════════════════════════════════════

    def _empty_result(self, pdf_path: str) -> dict:
        """Restituisce un JSON vuoto compatibile con il formato output."""
        return {
            "cv_id": f"parsed_{os.path.basename(pdf_path)}",
            "cv": {
                "persona":       {"seniority": "junior", "years_of_experience": 0},
                "education":     {"degree_id": "deg_none", "candidates": []},
                "languages":     [],
                "skills":        {"essential_ids": [], "optional_ids": [], "all_matches": []},
                "work_experience": [],
                "certifications": [],
            },
            "debug": {"section_sizes": {}},
        }


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = MainParser()
    result = parser.parse_cv(os.path.join(parser.base_dir, "samples", "cv_test.pdf"))
    out_path = os.path.join(parser.base_dir, "outputs", "cv_parsed_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[main_parser] Parsing completato → {out_path}")
