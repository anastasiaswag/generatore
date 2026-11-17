"""
esco_lang_config.py  —  SkillPath AI
=====================================
Configura quale versione del dataset ESCO usare: inglese (EN) o italiano (IT).

Viene importato da main_parser.py, job_parser.py e matching_engine.py.
Scegli la lingua impostando ESCO_LANG o passando --lang alla CLI.

Logica di selezione:
  1. Variabile d'ambiente ESCO_LANG  (es. export ESCO_LANG=it)
  2. File .esco_lang nella cartella del progetto
  3. Default: "en"

Se la lingua selezionata è "it" ma source_it/ non esiste o è incompleto,
torna silenziosamente alla versione EN.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)

_LANG_FILE = BASE_DIR / ".esco_lang"   # file di configurazione locale


def get_active_lang() -> str:
    """Ritorna la lingua ESCO attiva: 'it' o 'en'."""
    # 1. Variabile d'ambiente
    env = os.environ.get("ESCO_LANG", "").strip().lower()
    if env in ("it", "en"):
        return env

    # 2. File .esco_lang
    if _LANG_FILE.exists():
        content = _LANG_FILE.read_text(encoding="utf-8").strip().lower()
        if content in ("it", "en"):
            return content

    return "en"


def get_data_source_dir(lang: str | None = None) -> Path:
    """
    Ritorna la cartella del dataset ESCO da usare.

    Args:
        lang: 'it' | 'en' | None (usa get_active_lang())

    Returns:
        Path a dataset/source_it/ se IT disponibile, altrimenti dataset/source/
    """
    if lang is None:
        lang = get_active_lang()

    if lang == "it":
        it_dir = BASE_DIR / "dataset" / "source_it"
        # Verifica che il dataset IT sia effettivamente disponibile
        if (it_dir / "skills.json").exists() and (it_dir / "occupations.json").exists():
            return it_dir
        else:
            print("[esco_lang] ⚠ Dataset IT non trovato — uso dataset EN")
            print("[esco_lang]   Esegui: python build_italian_esco.py")

    return BASE_DIR / "dataset" / "source"


def set_lang(lang: str) -> None:
    """
    Imposta la lingua attiva scrivendola nel file .esco_lang.

    Args:
        lang: 'it' | 'en'
    """
    if lang not in ("it", "en"):
        raise ValueError(f"Lingua non supportata: {lang}. Usa 'it' o 'en'.")
    _LANG_FILE.write_text(lang, encoding="utf-8")
    print(f"[esco_lang] Lingua impostata: {lang.upper()}")
    print(f"[esco_lang] Dataset: {get_data_source_dir(lang)}")


def status() -> None:
    """Stampa lo stato attuale della configurazione lingua."""
    lang  = get_active_lang()
    src   = get_data_source_dir(lang)
    it_ok = (BASE_DIR / "dataset" / "source_it" / "skills.json").exists()
    en_ok = (BASE_DIR / "dataset" / "source"    / "skills.json").exists()

    print("=" * 50)
    print(f"  Lingua attiva  : {lang.upper()}")
    print(f"  Dataset usato  : {src.name}/")
    print(f"  Dataset EN     : {'✓' if en_ok else '✗'} dataset/source/")
    print(f"  Dataset IT     : {'✓' if it_ok else '✗ (non ancora scaricato)'} dataset/source_it/")
    if not it_ok:
        print()
        print("  Per scaricare IT:")
        print("    python build_italian_esco.py")
        print("  Poi attiva con:")
        print("    python esco_lang_config.py set it")
    print("=" * 50)


# ── CLI minimale ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        status()
    elif cmd == "set" and len(sys.argv) > 2:
        set_lang(sys.argv[2])
    elif cmd in ("it", "en"):
        set_lang(cmd)
    else:
        print("Uso:")
        print("  python esco_lang_config.py status      # stato attuale")
        print("  python esco_lang_config.py set it      # attiva italiano")
        print("  python esco_lang_config.py set en      # attiva inglese")
        print("  python esco_lang_config.py it          # shorthand per 'set it'")
