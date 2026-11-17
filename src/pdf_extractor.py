"""
pdf_extractor.py
Estrazione testo da file CV (PDF e DOCX) per SkillPath AI.

Obiettivi:
- Estrarre testo preservando la struttura a righe/paragrafi.
- Normalizzare caratteri "rumore" (bullet, caratteri di controllo, spazi multipli).
- Fornire utilità per filtrare righe inutili (numeri isolati, date, righe troppo corte).
- Supportare PDF (PyMuPDF) e DOCX (python-docx) con un dispatcher unico.
"""

import os
import re

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False

try:
    import docx  # python-docx
    _HAS_DOCX = True
except ImportError:
    _HAS_DOCX = False


# Caratteri bullet / separatori "rumore" comuni nei CV
_BULLETS = "\u2022\u25cf\u25cb\u25aa\u25a0\uf0b7\xb7•◦▪■·"
_BULLET_RE = re.compile(f"[{re.escape(_BULLETS)}\\*]")
_WHITESPACE_RE = re.compile(r"\s+")
_DATE_ONLY_RE = re.compile(
    r"^\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{4}\s*[-–/]\s*(\d{4}|present|oggi|attuale|in\s*corso)"
    r"|\d{4}"
    r"|(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{2,4})\s*$",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    """Normalizza una stringa: rimuove bullet, caratteri di controllo e spazi multipli."""
    if not text:
        return ""
    text = _BULLET_RE.sub(" ", text)
    # Rimuove caratteri di controllo (tab, form-feed, ecc.) ma mantiene spazi normali
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip(" ,;:-·|")


def get_full_text(pdf_path: str) -> list[str]:
    """
    Estrae il testo dal PDF mantenendo la struttura per righe.

    Ritorna una lista di righe pulite (vuote escluse).
    """
    if not _HAS_FITZ:
        print("[pdf_extractor] PyMuPDF (fitz) non disponibile. Installa con: pip install pymupdf")
        return []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"[pdf_extractor] Errore apertura PDF: {e}")
        return []

    lines: list[str] = []
    try:
        for page in doc:
            # "text" preserva meglio l'ordine rispetto a "blocks" per CV semplici
            raw = page.get_text("text")
            for raw_line in raw.split("\n"):
                cleaned = clean_text(raw_line)
                if cleaned:
                    lines.append(cleaned)
    finally:
        doc.close()
    return lines


def get_text_from_pdf(pdf_path: str) -> list[str]:
    """Alias retro-compatibile (usato da test_integration.py)."""
    return get_full_text(pdf_path)


def get_full_text_docx(docx_path: str) -> list[str]:
    """
    Estrae il testo da un file .docx mantenendo la struttura per righe.
    Include anche il contenuto delle tabelle (usate spesso nei CV Europass).
    """
    if not _HAS_DOCX:
        print("[pdf_extractor] python-docx non installato: impossibile leggere DOCX.")
        return []
    try:
        document = docx.Document(docx_path)
    except Exception as e:
        print(f"[pdf_extractor] Errore apertura DOCX: {e}")
        return []

    lines: list[str] = []

    # Paragrafi normali
    for para in document.paragraphs:
        cleaned = clean_text(para.text)
        if cleaned:
            lines.append(cleaned)

    # Tabelle (spesso usate nei CV Europass per la struttura a due colonne)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    cleaned = clean_text(para.text)
                    if cleaned and (not lines or lines[-1] != cleaned):
                        lines.append(cleaned)

    return lines


def get_text(path: str) -> list[str]:
    """
    Dispatcher: estrae testo da PDF o DOCX in base all'estensione.
    Questa è la funzione che dovrebbero usare i parser.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return get_full_text(path)
    if ext in (".docx", ".docm"):
        return get_full_text_docx(path)
    print(f"[pdf_extractor] Estensione non supportata: {ext}")
    return []


def is_noise_line(line: str) -> bool:
    """
    True se la riga è 'rumore' e non deve essere data in pasto al matcher semantico:
    - righe troppo corte (< 3 caratteri)
    - righe composte solo da date / range di anni
    - righe composte solo da numeri / punteggiatura
    """
    if not line or len(line) < 3:
        return True
    if _DATE_ONLY_RE.match(line):
        return True
    alnum = sum(ch.isalnum() for ch in line)
    letters = sum(ch.isalpha() for ch in line)
    if alnum == 0 or letters < 2:
        return True
    return False


def filter_lines(lines: list[str]) -> list[str]:
    """Rimuove righe rumore mantenendo l'ordine."""
    return [l for l in lines if not is_noise_line(l)]
