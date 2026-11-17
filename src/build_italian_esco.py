"""
build_italian_esco.py  —  SkillPath AI
=======================================
Scarica le label ufficiali italiane dall'API ESCO (ec.europa.eu/esco/api)
e costruisce dataset/source_it/ con le versioni IT di skills.json e
occupations.json, mantenendo invariati tutti gli altri campi (id, uri,
reuse_level, skill_type, ecc.).

Il file occupation_skill_relations.json viene copiato identico perché
contiene solo ID numerici, senza label.

STRATEGIA
---------
  - Chiama l'API in batch (BATCH_SIZE URI per richiesta) per ridurre
    il numero di chiamate HTTP da ~17.000 a ~850 (con batch=20).
  - Salva un file di cache JSON intermedio (progress_cache.json) dopo
    ogni batch: lo script può essere interrotto e ripreso senza perdere
    il lavoro già fatto.
  - Rate limiting: pausa DELAY_SEC tra i batch per rispettare i limiti
    dell'API pubblica EU (max ~10 req/s).

STIMA TEMPI
-----------
  13.939 skill  / 20 per batch = ~697 chiamate
  3.039  occup. / 20 per batch = ~152 chiamate
  Totale ~849 chiamate × 0.15s pausa = ~2 minuti

USO (dalla radice del progetto)
---
  python src/build_italian_esco.py                   # tutto
  python src/build_italian_esco.py --only skills     # solo skill
  python src/build_italian_esco.py --only occs       # solo occupazioni
  python src/build_italian_esco.py --resume          # riprende da dove ha smesso
  python src/build_italian_esco.py --test 5          # testa su 5 item per tipo
"""

import argparse
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ── Configurazione ────────────────────────────────────────────────────────────

ESCO_API       = "https://ec.europa.eu/esco/api"
LANG           = "it"
BATCH_SIZE     = 20      # URI per richiesta (max consigliato: 20-50)
DELAY_SEC      = 0.15    # pausa tra batch (rispetta rate limit API pubblica)
MAX_RETRIES    = 3       # tentativi per batch in caso di errore
RETRY_WAIT     = 5.0     # attesa prima del retry

BASE_DIR   = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)
SRC_EN     = BASE_DIR / "dataset" / "source_en"
SRC_IT     = BASE_DIR / "dataset" / "source_it"
CACHE_FILE = BASE_DIR / "dataset" / "source_it" / "_progress_cache.json"


# ── Helpers HTTP ──────────────────────────────────────────────────────────────

def _api_get_single(uri: str, endpoint: str) -> dict:
    """
    Fetcha UN singolo URI dall'API ESCO con il parametro 'uri=' (singolo).
    L'API ESCO v1 restituisce HTTP 500 con 'uris=' multipli — usiamo
    richieste singole sequenziali, più lente ma affidabili.
    """
    params = {"uri": uri, "language": LANG}
    url    = f"{ESCO_API}/{endpoint}?{urlencode(params)}"
    req    = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_batch(uris: list[str], endpoint: str) -> dict[str, dict]:
    """
    Fetcha un batch di URI dall'API ESCO (lingua IT) con richieste singole.
    Ritorna {uri: {"label": ..., "alt_labels": [...], "description": ...}}.

    Nota: l'API ESCO restituisce HTTP 500 sul parametro 'uris=' (multipli),
    quindi iteriamo con 'uri=' singolo per ogni elemento del batch.
    """
    result = {}

    for uri in uris:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = _api_get_single(uri, endpoint)
                fields = _extract_fields(data)
                if fields.get("label"):
                    result[uri] = fields
                break
            except HTTPError as e:
                if e.code == 404:
                    break   # URI non trovato — salta senza retry
                if attempt == MAX_RETRIES:
                    pass    # errore silenzioso per non spammare
                else:
                    time.sleep(RETRY_WAIT)
            except (URLError, Exception):
                if attempt == MAX_RETRIES:
                    pass
                else:
                    time.sleep(RETRY_WAIT)

        time.sleep(DELAY_SEC)   # rate limiting tra chiamate singole

    return result


def _extract_fields(item: dict) -> dict:
    """
    Estrae label, alt_labels e description da un oggetto API ESCO v1.

    Struttura reale della risposta (verificata empiricamente):
      "title"            → label nella lingua richiesta (stringa diretta)
      "preferredLabel"   → dict {lang_code: label_string, ...}  (tutte le lingue)
      "alternativeLabel" → dict {lang_code: [str, ...], ...}
      "description"      → dict {lang_code: {"literal": "...", "mimetype": "..."}}
    """
    # Usa "title" come label principale: è già nella lingua richiesta
    label = item.get("title", "")
    if not label:
        # Fallback su preferredLabel dict
        pref  = item.get("preferredLabel", {})
        label = pref.get(LANG, pref.get("en", "")) if isinstance(pref, dict) else str(pref)

    # alternativeLabel: dict {lang: [str, ...]}  — campo corretto (non "altLabels")
    alt_raw = item.get("alternativeLabel", {})
    if isinstance(alt_raw, dict):
        alt = alt_raw.get(LANG, alt_raw.get("en", []))
    else:
        alt = []

    # description: dict {lang: {"literal": "...", "mimetype": "..."}}
    desc_raw = item.get("description", {})
    desc = ""
    if isinstance(desc_raw, dict):
        lang_block = desc_raw.get(LANG) or desc_raw.get("en") or {}
        if isinstance(lang_block, dict):
            desc = lang_block.get("literal", "")
        elif isinstance(lang_block, str):
            desc = lang_block

    return {"label": label, "alt_labels": alt, "description": desc}


# ── Logica principale ─────────────────────────────────────────────────────────

def load_cache() -> dict:
    """Carica la cache di progresso se esiste."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"skills": {}, "occupations": {}}


def save_cache(cache: dict) -> None:
    SRC_IT.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def process_type(
    source_file:  Path,
    api_endpoint: str,
    cache_key:    str,
    cache:        dict,
    limit:        int | None = None,
    verbose:      bool = True,
) -> dict:
    """
    Carica il file sorgente EN, fetcha le label IT per ogni item,
    aggiorna la cache e ritorna il dizionario completo IT.
    """
    with open(source_file, encoding="utf-8") as f:
        source_data = json.load(f)

    all_ids   = list(source_data.keys())
    cached_it = cache.get(cache_key, {})  # {uri: {label, alt_labels, description}}

    if limit:
        all_ids = all_ids[:limit]

    # Filtra quelli già in cache
    to_fetch_ids = [eid for eid in all_ids
                    if source_data[eid].get("uri", "") not in cached_it]

    if verbose:
        total   = len(all_ids)
        already = total - len(to_fetch_ids)
        print(f"  Totale: {total}  |  già in cache: {already}  |  da fetchare: {len(to_fetch_ids)}")

    # Fetch in gruppi (BATCH_SIZE = quante URI per salvataggio cache)
    uris_to_fetch = [source_data[eid]["uri"] for eid in to_fetch_ids
                     if "uri" in source_data[eid]]

    batches = [uris_to_fetch[i:i + BATCH_SIZE]
               for i in range(0, len(uris_to_fetch), BATCH_SIZE)]

    fetched_total = 0
    t0 = time.time()

    for b_idx, batch in enumerate(batches, start=1):
        done_so_far = (b_idx - 1) * BATCH_SIZE
        pct = done_so_far / max(len(uris_to_fetch), 1) * 100
        eta_s = ""
        if b_idx > 1:
            elapsed = time.time() - t0
            rate    = done_so_far / elapsed          # URI/s
            remaining = (len(uris_to_fetch) - done_so_far) / max(rate, 0.001)
            eta_s   = f"  ETA {remaining/60:.1f}min"

        if verbose:
            print(f"  [{done_so_far}/{len(uris_to_fetch)}  {pct:.0f}%{eta_s}]",
                  end="\r", flush=True)

        fetched = _fetch_batch(batch, api_endpoint)

        if fetched:
            cached_it.update(fetched)
            fetched_total += len(fetched)
            cache[cache_key] = cached_it
            save_cache(cache)

    if verbose:
        elapsed = time.time() - t0
        print(f"  [{len(uris_to_fetch)}/{len(uris_to_fetch)}  100%]  "
              f"✓ {fetched_total} label IT in {elapsed:.0f}s          ")

    # Costruisce il dizionario IT completo
    result = {}
    fallback_count = 0
    for eid in all_ids:
        item_en  = source_data[eid].copy()
        uri      = item_en.get("uri", "")
        it_data  = cached_it.get(uri, {})

        if it_data.get("label"):
            item_en["label"]      = it_data["label"]
            item_en["alt_labels"] = it_data.get("alt_labels", [])
            if it_data.get("description"):
                item_en["description"] = it_data["description"]
        else:
            # Fallback: mantieni label EN e aggiungi flag
            item_en["_label_lang"] = "en"
            fallback_count += 1

        result[eid] = item_en

    if verbose and fallback_count:
        pct = fallback_count / max(len(all_ids), 1) * 100
        print(f"  ⚠ {fallback_count} item senza label IT ({pct:.1f}%) — mantenuta label EN")

    return result


def build_italian_dataset(
    only:     str | None = None,
    resume:   bool = False,
    test:     int | None = None,
    activate: bool = False,
) -> None:
    """
    Orchestratore principale.

    Args:
        activate: se True, dopo il download copia source_it/ → source/
                  (sovrascrive il dataset attivo con la versione IT).
                  Il backup EN rimane intatto in source_en/.
    """

    SRC_IT.mkdir(parents=True, exist_ok=True)

    # Carica cache di progresso
    cache = load_cache() if resume else {"skills": {}, "occupations": {}}
    if not resume and CACHE_FILE.exists():
        print("[build_it] Cache esistente ignorata (usa --resume per riprendere)")

    print(f"[build_it] Lingua target: {LANG.upper()} | Batch: {BATCH_SIZE} | Delay: {DELAY_SEC}s")
    if test:
        print(f"[build_it] MODALITÀ TEST: solo {test} item per tipo")

    # ── Skills ────────────────────────────────────────────────────────────────
    if only in (None, "skills"):
        print("\n── Skills ──────────────────────────────────────────────────────")
        skills_it = process_type(
            source_file  = SRC_EN / "skills.json",
            api_endpoint = "resource/skill",
            cache_key    = "skills",
            cache        = cache,
            limit        = test,
        )
        out_path = SRC_IT / "skills.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(skills_it, f, indent=2, ensure_ascii=False)
        print(f"  → {out_path}  ({len(skills_it)} skill)")

    # ── Occupations ───────────────────────────────────────────────────────────
    if only in (None, "occs"):
        print("\n── Occupazioni ─────────────────────────────────────────────────")
        occs_it = process_type(
            source_file  = SRC_EN / "occupations.json",
            api_endpoint = "resource/occupation",
            cache_key    = "occupations",
            cache        = cache,
            limit        = test,
        )
        out_path = SRC_IT / "occupations.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(occs_it, f, indent=2, ensure_ascii=False)
        print(f"  → {out_path}  ({len(occs_it)} occupazioni)")

    # ── Copia occupation_skill_relations (solo ID, nessuna label) ─────────────
    rel_src = SRC_EN / "occupation_skill_relations.json"
    rel_dst = SRC_IT / "occupation_skill_relations.json"
    if rel_src.exists() and not rel_dst.exists():
        shutil.copy2(rel_src, rel_dst)
        print(f"\n  → {rel_dst}  (copiato — contiene solo ID)")

    print("\n[build_it] ✓ Dataset IT pronto in dataset/source_it/")

    # ── Attiva il dataset IT copiandolo in source/ ────────────────────────────
    if activate:
        _activate_dataset(SRC_IT)
    else:
        print("[build_it]   Per attivarlo: python build_italian_esco.py --activate")
        print("[build_it]   Oppure copia manualmente source_it/ → source/")


def _activate_dataset(src_dir: Path) -> None:
    """
    Copia src_dir → dataset/source/, sovrascrivendo il dataset attivo.
    Elimina le cache .pt (vanno ricalcolate con le nuove label).
    """
    dst = BASE_DIR / "dataset" / "source"
    print(f"\n[build_it] Attivazione: {src_dir.name}/ → source/")

    for fname in ("skills.json", "occupations.json", "occupation_skill_relations.json"):
        src_file = src_dir / fname
        dst_file = dst / fname
        if src_file.exists():
            shutil.copy2(src_file, dst_file)
            print(f"  ✓ {fname}")

    # Invalida le cache embedding (.pt) — verranno ricalcolate al primo avvio
    for pt in (dst / "skills_cache.pt", dst / "occupations_cache.pt",
               dst / "skills_meta.json", dst / "occupations_meta.json"):
        if pt.exists():
            pt.unlink()
            print(f"  ✓ cache invalidata: {pt.name}")

    print(f"[build_it] ✓ Dataset attivo aggiornato → {dst}")
    print("[build_it]   Gli embedding verranno ricalcolati al primo avvio del parser.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="SkillPath AI — Scarica ESCO in italiano dall'API ufficiale EU")
    ap.add_argument("--only",     choices=["skills", "occs"], default=None,
                    help="Processa solo skill o solo occupazioni")
    ap.add_argument("--resume",   action="store_true",
                    help="Riprende dal punto in cui lo script era stato interrotto")
    ap.add_argument("--test",     type=int, default=None,
                    help="Testa su N item per tipo (es. --test 5)")
    ap.add_argument("--activate", action="store_true",
                    help="Dopo il download copia source_it/ → source/ (attiva IT)")
    ap.add_argument("--batch",    type=int, default=BATCH_SIZE,
                    help=f"URI per batch (default: {BATCH_SIZE})")
    ap.add_argument("--delay",    type=float, default=DELAY_SEC,
                    help=f"Pausa tra batch in secondi (default: {DELAY_SEC})")
    # Comando standalone per attivare senza ri-scaricare
    ap.add_argument("--activate-only", action="store_true",
                    help="Attiva source_it/ senza ri-scaricare (se già costruito)")
    args = ap.parse_args()

    BATCH_SIZE = args.batch
    DELAY_SEC  = args.delay

    if args.activate_only:
        if not (SRC_IT / "skills.json").exists():
            print("[build_it] ERRORE: source_it/ non esiste. Esegui prima senza --activate-only.")
        else:
            _activate_dataset(SRC_IT)
    else:
        build_italian_dataset(
            only     = args.only,
            resume   = args.resume,
            test     = args.test,
            activate = args.activate,
        )
