"""
lexical_matcher.py  —  SkillPath AI
====================================
Stadio LESSICALE del riconoscimento skill: cerca nel testo le occorrenze
letterali delle etichette ESCO (label preferita + alt_labels), senza passare
per gli embedding.

PERCHÉ ESISTE
─────────────
Il matching semantico (semantic_mapper) è potente ma rumoroso: lavora per
similarità e sopra una soglia, quindi produce inevitabilmente falsi positivi.
Se però una skill è scritta nel testo *esattamente* come la nomina ESCO
("gestire i bioreattori", "Python", "project management"), non serve alcuna
inferenza: è un'informazione certa.

I sistemi industriali (es. la Skills Graph di LinkedIn) usano proprio questa
architettura a due stadi: un tagger lessicale velocissimo e ad altissima
precisione copre il grosso dei casi, e un secondo stadio semantico interviene
solo sulle formulazioni implicite che il primo non riesce a catturare.

Qui si replica lo stesso schema. Il guadagno atteso è sulla precision: le
skill riconosciute letteralmente non dipendono da alcuna soglia e non possono
essere vittime del fenomeno delle etichette-calamita.

COME FUNZIONA
─────────────
1. Si costruisce un indice {forma_normalizzata → id ESCO} a partire da label
   e alt_labels (ESCO ne fornisce in media ~4 per skill, in IT e EN).
2. Il testo viene normalizzato e tokenizzato.
3. Si scorrono gli n-gram del testo dal più lungo al più corto cercando
   corrispondenze esatte nell'indice (greedy longest-match: se "gestione dei
   progetti software" è una skill nota, non si estraggono anche i frammenti
   più corti contenuti al suo interno).

Non richiede dipendenze esterne: l'indice è un semplice dizionario e la
ricerca è O(n · MAX_NGRAM) sul numero di token.

USO
───
    from lexical_matcher import LexicalSkillMatcher

    lex = LexicalSkillMatcher(["dataset/source_it/skills.json",
                               "dataset/source/skills.json"])
    hits = lex.match("Cerchiamo un profilo esperto di gestione dei bioreattori")
    # → [{"id": "...", "label": "gestire i bioreattori", "score": 1.0,
    #     "source": "lexical", "matched_text": "gestione dei bioreattori"}]
"""

import json
import os
import re
import unicodedata

# Lunghezza massima (in token) di una etichetta ESCO cercata nel testo.
# Le label ESCO più lunghe superano di rado gli 8 token.
MAX_NGRAM = 8

# Un match di un solo token è accettato solo se il token è abbastanza lungo,
# altrimenti si rischiano corrispondenze accidentali su parole comuni.
MIN_SINGLE_TOKEN_LEN = 3

# Riconosce le forme "tecniche" a token singolo: sigle e nomi propri di
# tecnologie (Python, SQL, DNS, Maven, C++, SA8000…). Il criterio è la
# presenza di una maiuscola o di una cifra nella forma ORIGINALE.
#
# Serve perché ESCO usa come alt_labels anche parole comunissime a token
# singolo ("equipment", "data", "design", "processes", "planning"), che
# cercate letteralmente nel testo producono quasi solo falsi positivi: da
# sole non identificano una competenza. Misurato sugli 810 annunci di
# valutazione, i soli token generici causavano oltre metà dei falsi positivi
# dello stadio lessicale. Le sigle tecniche invece sono altamente
# discriminanti e vanno mantenute.
_TECHNICAL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+#.\-]*$")

# Parole troppo comuni per caratterizzare una competenza. Una forma
# composta ESCLUSIVAMENTE da queste parole non viene indicizzata: è
# fraseologia da annuncio, non una skill (es. "be responsible", alt_label di
# "comportarsi in modo responsabile", che compare nel boilerplate di quasi
# ogni annuncio — da sola era il singolo pattern più dannoso in assoluto).
_GENERIC_TOKENS = {
    # EN — funzionali e verbi/aggettivi di servizio
    "a", "an", "the", "to", "of", "in", "on", "at", "for", "with", "by",
    "and", "or", "be", "being", "is", "are", "as", "from", "into", "out",
    "able", "ability", "abilities", "skill", "skills", "skilled", "work",
    "working", "works", "worker", "task", "tasks", "duty", "duties",
    "responsible", "responsibility", "responsibilities", "ensure", "ensuring",
    "good", "strong", "high", "great", "excellent", "effective", "efficient",
    "use", "using", "used", "make", "making", "do", "doing", "have", "having",
    "get", "give", "take", "keep", "provide", "providing", "support",
    "supporting", "help", "helping", "general", "basic", "new", "other",
    "own", "own's", "self", "people", "person", "staff", "level", "levels",
    # IT — funzionali e verbi/aggettivi di servizio
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "del",
    "dei", "della", "delle", "dello", "degli", "da", "dal", "con", "per",
    "tra", "fra", "su", "sul", "sulla", "e", "ed", "o", "che", "essere",
    "avere", "fare", "usare", "uso", "capacita", "abilita", "competenza",
    "competenze", "attivita", "compito", "compiti", "lavoro", "lavorare",
    "buono", "buona", "ottimo", "ottima", "forte", "alto", "alta", "generale",
    "base", "nuovo", "nuova", "altro", "altra", "proprio", "propria",
    "persone", "persona", "personale", "livello", "livelli", "assicurare",
    "garantire", "fornire", "supporto", "aiuto", "responsabile",
    "responsabilita",
}

# Token che non possono da soli costituire una skill: parole funzionali,
# nomi di lingue (finiscono nella sezione "Lingue" del CV e non sono skill
# ESCO in quel contesto) e sostantivi generici da ufficio.
_SINGLE_TOKEN_STOP = {
    # funzionali IT/EN
    "and", "the", "for", "with", "from", "that", "this", "have", "has",
    "sono", "come", "delle", "degli", "della", "dello", "nella", "nello",
    "anche", "molto", "quale", "quali", "essere", "avere", "oltre", "presso",
    # nomi di lingue (IT)
    "italiano", "inglese", "francese", "spagnolo", "tedesco", "portoghese",
    "neerlandese", "olandese", "svedese", "danese", "norvegese", "finlandese",
    "irlandese", "greco", "polacco", "rumeno", "ungherese", "ceco", "russo",
    "cinese", "giapponese", "arabo", "turco", "croato", "sloveno", "slovacco",
    "bulgaro", "estone", "lettone", "lituano", "maltese",
    # nomi di lingue (EN)
    "italian", "english", "french", "spanish", "german", "portuguese",
    "dutch", "swedish", "danish", "norwegian", "finnish", "irish", "greek",
    "polish", "romanian", "hungarian", "czech", "russian", "chinese",
    "japanese", "arabic", "turkish", "croatian", "slovenian", "slovak",
    "bulgarian", "estonian", "latvian", "lithuanian", "maltese",
    # generici
    "team", "azienda", "company", "ruolo", "role", "lavoro", "work", "job",
    "anni", "years", "sede", "office", "contratto", "contract", "settore",
    "sector", "cliente", "clienti", "client", "clients", "progetto",
    "progetti", "project", "projects", "attivita", "activity", "obiettivi",
    "goals", "esperienza", "experience", "laurea", "degree", "diploma",
}

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """
    Forma canonica per il confronto lessicale: minuscole, senza accenti,
    senza punteggiatura, spazi normalizzati.

    L'eliminazione degli accenti evita che "attivita" e "attività" siano
    considerate diverse, cosa frequente nei testi estratti da PDF.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


class LexicalSkillMatcher:
    """
    Indice di ricerca esatta delle etichette ESCO nel testo.

    Attributi utili:
        index       dict {forma_normalizzata: (id, label_originale)}
        n_forms     numero di forme indicizzate (label + alt_labels)
    """

    def __init__(self, skills_paths: list[str], verbose: bool = True):
        self.index: dict[str, tuple[str, str]] = {}
        self._form_ids: dict[str, set] = {}
        self._load(skills_paths)
        n_ambiguous = self._drop_ambiguous_forms()
        self.n_forms = len(self.index)
        if verbose:
            print(
                f"[lexical_matcher] Indice lessicale: {self.n_forms} forme "
                f"da {len(skills_paths)} file "
                f"({n_ambiguous} forme ambigue scartate)"
            )

    # ──────────────────────────────────────────────────────────────────────
    def _drop_ambiguous_forms(self) -> int:
        """
        Rimuove le forme che in ESCO corrispondono a più skill diverse.

        Esempio: "help customers" è alt_label di tre skill distinte. Sceglierne
        una arbitrariamente introdurrebbe un falso positivo sicuro nei due casi
        sbagliati; è più corretto lasciare quei casi allo stadio semantico, che
        può disambiguare usando il contesto.
        """
        ambiguous = [f for f, ids in self._form_ids.items() if len(ids) > 1]
        for form in ambiguous:
            self.index.pop(form, None)
        self._form_ids.clear()
        return len(ambiguous)

    # ──────────────────────────────────────────────────────────────────────
    def _load(self, skills_paths: list[str]) -> None:
        for path in skills_paths:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = json.load(f)
            except Exception as e:
                print(f"[lexical_matcher] Impossibile leggere {path}: {e}")
                continue

            records = content.values() if isinstance(content, dict) else content
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                sid = rec.get("id")
                if not sid:
                    continue
                label = rec.get("label") or ""
                forms = [label] + list(rec.get("alt_labels") or [])
                for form in forms:
                    if not form or not isinstance(form, str):
                        continue
                    norm = normalize(form)
                    if not self._is_indexable(norm, form):
                        continue
                    self.index.setdefault(norm, (sid, label or form))
                    # Traccia le collisioni: una stessa forma che punta a più
                    # skill diverse verrà scartata da _drop_ambiguous_forms().
                    self._form_ids.setdefault(norm, set()).add(sid)

    @staticmethod
    def _is_indexable(norm: str, original: str = "") -> bool:
        """
        Decide se una forma ESCO può essere cercata letteralmente nel testo.

        Tre criteri, tutti motivati dall'analisi degli errori:

        1. Le forme a token singolo passano solo se "tecniche", cioè se la
           forma originale contiene una maiuscola o una cifra (Python, SQL,
           DNS, SA8000). Le parole comuni a token singolo che ESCO usa come
           alias ("equipment", "data", "design") vengono scartate.
        2. Le forme composte solo da parole di servizio ("be responsible")
           vengono scartate: sono fraseologia, non competenze.
        3. Le forme più lunghe di MAX_NGRAM token non sono cercabili con la
           finestra di n-gram usata da match().
        """
        if not norm:
            return False
        tokens = norm.split()
        if len(tokens) > MAX_NGRAM:
            return False

        if len(tokens) == 1:
            tok = tokens[0]
            if len(tok) < MIN_SINGLE_TOKEN_LEN or tok.isdigit():
                return False
            if tok in _SINGLE_TOKEN_STOP or tok in _GENERIC_TOKENS:
                return False
            # Solo sigle / nomi propri di tecnologie
            src = original or norm
            has_signal = any(c.isupper() for c in src) or any(
                c.isdigit() for c in src
            )
            if not (has_signal and _TECHNICAL_TOKEN_RE.match(src)):
                return False
            return True

        # Multi-token: scarta se è tutta fraseologia generica
        if all(t in _GENERIC_TOKENS for t in tokens):
            return False
        return True

    # ──────────────────────────────────────────────────────────────────────
    def match(self, text: str, max_results: int | None = None) -> list[dict]:
        """
        Cerca nel testo tutte le etichette ESCO presenti letteralmente.

        Strategia greedy longest-match: si scorre il testo da sinistra a
        destra e, in ogni posizione, si prova prima l'n-gram più lungo. Una
        volta consumato un match, i suoi token non vengono riutilizzati per
        match più corti — così "gestione dei progetti software" non genera
        anche il match parziale "progetti".

        Ritorna una lista di dict nello stesso formato di
        SemanticMapper.find_matches(return_scores=True), con score=1.0
        (corrispondenza esatta) e il campo aggiuntivo "source": "lexical".
        """
        norm = normalize(text)
        if not norm:
            return []

        tokens = norm.split()
        n = len(tokens)
        found: dict[str, dict] = {}

        i = 0
        while i < n:
            hit = None
            # Dal più lungo al più corto → longest-match
            max_len = min(MAX_NGRAM, n - i)
            for length in range(max_len, 0, -1):
                gram = " ".join(tokens[i : i + length])
                entry = self.index.get(gram)
                if entry is not None:
                    hit = (entry, gram, length)
                    break

            if hit is None:
                i += 1
                continue

            (sid, label), gram, length = hit
            if sid not in found:
                found[sid] = {
                    "id": sid,
                    "label": label,
                    "score": 1.0,
                    "source": "lexical",
                    "matched_text": gram,
                }
            i += length  # consuma i token del match

        results = list(found.values())
        if max_results:
            results = results[:max_results]
        return results

    # ──────────────────────────────────────────────────────────────────────
    def match_lines(self, lines: list[str], max_results: int | None = None) -> list[dict]:
        """Come match(), applicato a una lista di righe e deduplicato per id."""
        found: dict[str, dict] = {}
        for line in lines:
            for hit in self.match(line):
                found.setdefault(hit["id"], hit)
        results = list(found.values())
        if max_results:
            results = results[:max_results]
        return results
