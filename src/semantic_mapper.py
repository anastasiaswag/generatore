"""
semantic_mapper.py
Mapping semantico fra testo libero (righe di CV) e le ontologie di SkillPath AI
(ESCO occupations/skills, lauree, certificazioni, lingue+CEFR).

Punti chiave rispetto alla versione precedente:
- Gestione CORRETTA di language_levels.json (usa "entries", non "cefr_levels").
- Supporto a "top-k" con soglia: una singola riga può avere più match,
  e una stessa label può avere più alias che confluiscono sullo stesso id.
- Filtro anti-rumore sulle query (righe troppo corte/vuote).
- Cache torch compatibile con PyTorch 2.6+ (weights_only=False).
- Restituisce opzionalmente gli score per debug / matching_engine.
"""

import json
import os
import random
import re
from typing import Iterable

import torch
from sentence_transformers import SentenceTransformer, util


_MIN_QUERY_LEN = 3
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÿ]")

# Peso della correzione hubness (0 = disattiva, 1 = sottrae l'intera deviazione
# di background). Vedi build_background_profile() per la spiegazione.
_HUBNESS_BETA = 1.0

# Modelli instruction-tuned che richiedono prefisso "query: " / "passage: "
# per il retrieval cross-linguistico (multilingual-e5-*)
_E5_MODELS = {
    "intfloat/multilingual-e5-small",
    "intfloat/multilingual-e5-base",
    "intfloat/multilingual-e5-large",
    "intfloat/multilingual-e5-large-instruct",
}


def _tag_modello(nome: str) -> str:
    """
    Identificativo compatto del modello, usato nei nomi dei file di cache.

    Senza questo, cache costruite con encoder diversi condividerebbero lo
    stesso file: cambiando modello si ricaricherebbero silenziosamente gli
    embedding del precedente, producendo risultati plausibili ma privi di
    significato. È un errore che non emette alcun avviso, quindi va prevenuto
    nel nome del file.
    """
    return re.sub(r"[^A-Za-z0-9]+", "-", nome.split("/")[-1]).strip("-").lower()


def _is_meaningful(text: str) -> bool:
    if not text:
        return False
    if len(text.strip()) < _MIN_QUERY_LEN:
        return False
    # Serve almeno qualche lettera
    return bool(_ALPHA_RE.search(text))


class SemanticMapper:
    """
    Mapper generico riutilizzabile su diversi database di label.
    Usa `load_database` una volta per ogni file; la cache su disco
    evita di rigenerare gli embedding ad ogni esecuzione.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[semantic_mapper] Modello '{model_name}' su {self.device}")
        # Alcuni encoder (gte-multilingual-base, jina, nomic) distribuiscono
        # l'architettura come codice nel repository invece di usare una classe
        # già presente in transformers, e richiedono trust_remote_code=True.
        # Si tenta prima senza: attivarlo indiscriminatamente significherebbe
        # eseguire codice arbitrario scaricato dalla rete, quindi lo si fa solo
        # quando il caricamento standard fallisce per quel motivo.
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
        except (ValueError, KeyError, OSError) as e:
            if "trust_remote_code" not in str(e):
                raise
            print(f"[semantic_mapper] '{model_name}' richiede codice remoto: "
                  "lo carico con trust_remote_code=True")
            self.model = SentenceTransformer(model_name, device=self.device,
                                             trust_remote_code=True)
        self.db_data: list[dict] = []
        self.db_embeddings: torch.Tensor | None = None
        self.current_db: str | None = None
        # Flag per modelli E5 instruction-tuned (richiedono prefisso query:/passage:)
        self.model_name = model_name
        self._tag = _tag_modello(model_name)
        self._is_e5 = model_name in _E5_MODELS
        # Label preferite per output bilingue (None = modalità mono-lingua)
        self._preferred_labels: dict[str, str] | None = None
        # Profilo di background per la correzione hubness (None = non calcolato)
        self.bg_deviation: torch.Tensor | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Estrazione (id, label) da un file JSON
    # ─────────────────────────────────────────────────────────────────────
    def _extract_entries(self, content) -> list[tuple[str, str]]:
        """
        Ritorna una lista di tuple (id, label) a partire dal contenuto JSON.
        Supporta tutti i formati usati nel progetto.
        """
        entries: list[tuple[str, str]] = []

        # Caso 1: dict top-level (occupations.json / skills.json)
        # chiavi = UUID, valori = {id, label, alt_labels, ...}
        if isinstance(content, dict) and all(
            isinstance(v, dict) and ("label" in v or "name" in v)
            for v in list(content.values())[:5]
        ):
            for _, v in content.items():
                self._collect_labels(v, entries)
            return entries

        # Caso 2: dict con una chiave "programs" / "certifications" / "entries"
        if isinstance(content, dict):
            for key in ("programs", "certifications", "entries"):
                if key in content and isinstance(content[key], dict):
                    for _, v in content[key].items():
                        self._collect_labels(v, entries)
                    return entries

            # Caso speciale language_levels.json: fallback su "languages" se
            # "entries" non è presente (es. vecchio schema)
            if "languages" in content and isinstance(content["languages"], list):
                for lang in content["languages"]:
                    label = lang.get("label") or lang.get("name")
                    code = lang.get("code") or lang.get("id")
                    if label and code:
                        entries.append((f"lang_{code}", label))
                return entries

            # Caso 3: dict di cefr_levels lista (ultimo fallback)
            if "cefr_levels" in content and isinstance(content["cefr_levels"], list):
                for lvl in content["cefr_levels"]:
                    if lvl.get("label") and lvl.get("code"):
                        entries.append((lvl["code"], lvl["label"]))
                return entries

        # Caso 4: lista di dict
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    self._collect_labels(item, entries)
            return entries

        return entries

    @staticmethod
    def _collect_labels(item: dict, out: list[tuple[str, str]]) -> None:
        """Aggiunge (id, label) + alias in `out` per un singolo record."""
        item_id = (
            item.get("id")
            or item.get("code")
            or item.get("uri")
            or item.get("label")
        )
        if not item_id:
            return
        label = item.get("label") or item.get("name") or item.get("language_label")
        if label:
            out.append((item_id, str(label)))
        for alt in item.get("alt_labels", []) or []:
            if alt:
                out.append((item_id, str(alt)))
        # Alcuni record (es. language entries) hanno anche "cefr_label"
        cefr_label = item.get("cefr_label")
        if cefr_label and item.get("language_label"):
            out.append(
                (item_id, f"{item['language_label']} {cefr_label}")
            )

    # ─────────────────────────────────────────────────────────────────────
    # Caricamento DB con cache
    # ─────────────────────────────────────────────────────────────────────
    def load_database(self, json_path: str) -> bool:
        if not os.path.exists(json_path):
            print(f"[semantic_mapper] File non trovato: {json_path}")
            return False

        if self.current_db == json_path and self.db_embeddings is not None:
            return True  # già caricato
        # Caricamento singolo: disabilita modalità bilingue
        self._preferred_labels = None
        # Il DB cambia → il profilo di background non è più valido
        self.bg_deviation = None

        cache_path = json_path.replace(".json", f"_{self._tag}_cache.pt")
        meta_path = json_path.replace(".json", f"_{self._tag}_meta.json")

        if os.path.exists(cache_path) and os.path.exists(meta_path):
            try:
                self.db_embeddings = torch.load(
                    cache_path, map_location=self.device, weights_only=False
                )
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.db_data = json.load(f)
                self.current_db = json_path
                return True
            except Exception as e:
                print(f"[semantic_mapper] Cache corrotta ({e}), rigenero.")

        with open(json_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        pairs = self._extract_entries(content)
        if not pairs:
            print(f"[semantic_mapper] Nessuna entry estratta da {json_path}")
            return False

        self.db_data = [{"id": pid, "label": lbl} for pid, lbl in pairs]
        texts = [lbl for _, lbl in pairs]

        # I modelli E5 richiedono il prefisso "passage: " per i documenti del DB
        if self._is_e5:
            texts = [f"passage: {t}" for t in texts]

        print(
            f"[semantic_mapper] Generazione embeddings per "
            f"{os.path.basename(json_path)} ({len(texts)} labels)"
        )
        self.db_embeddings = self.model.encode(
            texts,
            convert_to_tensor=True,
            show_progress_bar=True,
            batch_size=128,
            normalize_embeddings=True,
        )

        try:
            torch.save(self.db_embeddings, cache_path)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(self.db_data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[semantic_mapper] Impossibile salvare cache: {e}")

        self.current_db = json_path
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Caricamento bilingue (es. IT + EN nello stesso indice)
    # ─────────────────────────────────────────────────────────────────────
    def load_databases_bilingual(
        self, primary_path: str, fallback_path: str
    ) -> bool:
        """
        Costruisce un indice combinato da due dataset (es. IT + EN).

        Vantaggio: un termine inglese nel CV matcha la label EN nello stesso
        indice in cui un termine italiano matcha la label IT. Entrambi si
        risolvono al medesimo ID ESCO.  L'output di find_matches() mostra
        sempre la label del dataset primary (IT) se disponibile, altrimenti
        quella del fallback (EN).

        Cache: <primary>_bilingual_cache.pt / _meta.json / _pref.json.
        """
        cache_key = f"{primary_path}||{fallback_path}"
        if self.current_db == cache_key and self.db_embeddings is not None:
            return True

        # Il DB cambia → il profilo di background non è più valido
        self.bg_deviation = None

        cache_path = primary_path.replace(".json", f"_{self._tag}_bilingual_cache.pt")
        meta_path  = primary_path.replace(".json", f"_{self._tag}_bilingual_meta.json")
        pref_path  = primary_path.replace(".json", f"_{self._tag}_bilingual_pref.json")

        if (os.path.exists(cache_path) and os.path.exists(meta_path)
                and os.path.exists(pref_path)):
            try:
                self.db_embeddings = torch.load(
                    cache_path, map_location=self.device, weights_only=False
                )
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.db_data = json.load(f)
                with open(pref_path, "r", encoding="utf-8") as f:
                    self._preferred_labels = json.load(f)
                self.current_db = cache_key
                print(
                    f"[semantic_mapper] Cache bilingue caricata "
                    f"({len(self.db_data)} entries)"
                )
                return True
            except Exception as e:
                print(f"[semantic_mapper] Cache bilingue corrotta ({e}), rigenero.")

        # ── Carica i due dataset ────────────────────────────────────────────
        primary_pairs: list[tuple[str, str]] = []
        if os.path.exists(primary_path):
            with open(primary_path, "r", encoding="utf-8") as f:
                primary_pairs = self._extract_entries(json.load(f))
            print(
                f"[semantic_mapper] Primary ({os.path.basename(primary_path)}): "
                f"{len(primary_pairs)} labels"
            )

        fallback_pairs: list[tuple[str, str]] = []
        if os.path.exists(fallback_path):
            with open(fallback_path, "r", encoding="utf-8") as f:
                fallback_pairs = self._extract_entries(json.load(f))
            print(
                f"[semantic_mapper] Fallback ({os.path.basename(fallback_path)}): "
                f"{len(fallback_pairs)} labels"
            )

        if not primary_pairs and not fallback_pairs:
            print("[semantic_mapper] Nessuna entry nei dataset bilingue.")
            return False

        # ── Preferred labels: IT sovrascrive EN per gli ID comuni ──────────
        preferred: dict[str, str] = {}
        for pid, lbl in fallback_pairs:          # EN: prima occorrenza per ID
            if pid not in preferred:
                preferred[pid] = lbl
        for pid, lbl in primary_pairs:           # IT: sovrascrive EN
            preferred[pid] = lbl                 # prima occorrenza IT = label principale
            break                                # trick: vogliamo solo la PRIMA per ID
        # Ricostruisci correttamente: prima IT (prima occ. per ID), poi EN come fallback
        preferred = {}
        it_seen: set[str] = set()
        for pid, lbl in primary_pairs:
            if pid not in it_seen:
                preferred[pid] = lbl             # prima (= principale) label IT
                it_seen.add(pid)
        for pid, lbl in fallback_pairs:
            if pid not in preferred:
                preferred[pid] = lbl             # EN solo se nessuna label IT

        # ── Unione pairs (rimuove coppie (id, label) duplicate) ────────────
        seen_pairs: set[tuple[str, str]] = set()
        all_pairs: list[tuple[str, str]] = []
        for pair in primary_pairs + fallback_pairs:
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                all_pairs.append(pair)

        self.db_data           = [{"id": pid, "label": lbl} for pid, lbl in all_pairs]
        self._preferred_labels = preferred

        # ── Encoding ────────────────────────────────────────────────────────
        texts = [lbl for _, lbl in all_pairs]
        if self._is_e5:
            texts = [f"passage: {t}" for t in texts]

        print(
            f"[semantic_mapper] Generazione embeddings bilingue "
            f"({len(texts)} labels)…"
        )
        self.db_embeddings = self.model.encode(
            texts,
            convert_to_tensor=True,
            show_progress_bar=True,
            batch_size=128,
            normalize_embeddings=True,
        )

        # ── Salva cache ─────────────────────────────────────────────────────
        try:
            torch.save(self.db_embeddings, cache_path)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(self.db_data, f, ensure_ascii=False)
            with open(pref_path, "w", encoding="utf-8") as f:
                json.dump(self._preferred_labels, f, ensure_ascii=False)
        except Exception as e:
            print(f"[semantic_mapper] Impossibile salvare cache bilingue: {e}")

        self.current_db = cache_key
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Correzione hubness (profilo di background)
    # ─────────────────────────────────────────────────────────────────────
    def build_background_profile(
        self,
        bg_texts: list[str],
        cache_path: str | None = None,
        force: bool = False,
    ) -> bool:
        """
        Calcola, per ogni entry del DB, quanto quella label è "attrattiva" in
        generale, cioè quanto somiglia a un testo qualunque del dominio.

        PROBLEMA
        ────────
        Negli spazi di embedding ad alta dimensionalità alcune label si
        comportano da "hub": hanno similarità alta con quasi qualsiasi query,
        indipendentemente dal contenuto. Sono la causa principale dei falsi
        positivi sistematici osservati nel parser degli annunci (poche label
        responsabili di una larga quota degli errori).

        SOLUZIONE
        ─────────
        Si stima per ogni label L la sua similarità media contro un corpus di
        background B (testo di dominio, NON etichettato):

            bg_mean[L] = media over b in B di cos(L, b)

        e la si confronta con la media globale su tutte le label:

            bg_deviation[L] = bg_mean[L] - media(bg_mean)

        In fase di matching si sottrae questa deviazione dal punteggio:

            score_corretto = score - beta * bg_deviation[L]

        Una label "normale" ha deviazione ~0 e resta invariata; una label-hub
        ha deviazione positiva e viene penalizzata in proporzione a quanto è
        indiscriminata.

        NOTA sulla scala: si sottrae la DEVIAZIONE dalla media, non il valore
        assoluto di background. Questo mantiene i punteggi sulla stessa scala
        di prima, quindi le soglie già calibrate (0.82 / 0.85 / 0.88 …)
        restano valide e la modifica è retrocompatibile.

        SCELTA DEL CORPUS DI BACKGROUND — punto critico
        ───────────────────────────────────────────────
        Il corpus B deve avere la stessa distribuzione delle query che il
        parser produrrà davvero, cioè i frammenti di testo estratti dai
        documenti in ingresso. Usare un corpus della distribuzione sbagliata
        rende la correzione inefficace.

        Verificato sperimentalmente: costruendo B dalle descrizioni ESCO,
        l'etichetta "comportarsi in modo responsabile" NON risulta attrattiva
        (rispetto al linguaggio dell'ontologia non lo è) e la correzione la
        lascia intatta — nella valutazione restava presente in 792 annunci su
        810, esattamente come senza correzione. È invece attrattiva rispetto
        alla fraseologia degli annunci ("sarà responsabile di…"), che è la
        distribuzione da cui provengono le query reali.

        Da qui la regola: costruire B dai candidati estratti da un corpus di
        documenti dello stesso tipo di quelli da analizzare.
        Vedi analysis/costruisci_profilo_background.py.

        NOTA metodologica: il corpus di background è testo NON etichettato —
        non contiene ground truth. La correzione resta quindi non
        supervisionata, a differenza di una denylist ricavata osservando quali
        predizioni erano sbagliate. Per escludere del tutto effetti
        transduttivi, calibrare su documenti diversi da quelli di valutazione
        (lo script citato supporta lo split).

        Parametri:
            bg_texts    testi di background (frasi di dominio qualsiasi).
            cache_path  se indicato, salva/ricarica il profilo da questo file.
            force       ricalcola anche se la cache esiste.
        """
        if self.db_embeddings is None or not self.db_data:
            print("[semantic_mapper] Nessun DB caricato: profilo background saltato.")
            return False

        n_db = self.db_embeddings.size(0)

        # ── Tentativo di ricarica da cache ──────────────────────────────────
        if cache_path and os.path.exists(cache_path) and not force:
            try:
                dev = torch.load(
                    cache_path, map_location=self.device, weights_only=False
                )
                if dev.numel() == n_db:
                    self.bg_deviation = dev
                    print(
                        f"[semantic_mapper] Profilo background caricato da cache "
                        f"({n_db} label)"
                    )
                    return True
                print(
                    "[semantic_mapper] Cache background non allineata al DB, rigenero."
                )
            except Exception as e:
                print(f"[semantic_mapper] Cache background corrotta ({e}), rigenero.")

        bg_texts = [t for t in bg_texts if _is_meaningful(t)]
        if len(bg_texts) < 50:
            print(
                f"[semantic_mapper] Corpus background troppo piccolo "
                f"({len(bg_texts)} testi): profilo non calcolato."
            )
            return False

        encode_bg = (
            [f"query: {t}" for t in bg_texts] if self._is_e5 else bg_texts
        )

        print(
            f"[semantic_mapper] Calcolo profilo background "
            f"({len(bg_texts)} testi × {n_db} label)…"
        )

        # Somma incrementale a blocchi: evita di materializzare una matrice
        # (n_bg × n_db) che per 3000 × 28000 sarebbe di ~340 MB in float32.
        acc = torch.zeros(n_db, device=self.db_embeddings.device)
        block = 256
        for start in range(0, len(encode_bg), block):
            chunk = encode_bg[start : start + block]
            emb = self.model.encode(
                chunk,
                convert_to_tensor=True,
                batch_size=64,
                normalize_embeddings=True,
            )
            acc += util.cos_sim(emb, self.db_embeddings).sum(dim=0)

        bg_mean = acc / len(encode_bg)
        self.bg_deviation = bg_mean - bg_mean.mean()

        top = torch.topk(self.bg_deviation, k=min(5, n_db))
        print("[semantic_mapper] Label più 'attrattive' (deviazione background):")
        for val, idx in zip(top.values.tolist(), top.indices.tolist()):
            print(f"    +{val:.4f}  {self.db_data[idx]['label'][:60]}")

        if cache_path:
            try:
                torch.save(self.bg_deviation, cache_path)
            except Exception as e:
                print(f"[semantic_mapper] Impossibile salvare profilo background: {e}")

        return True

    @staticmethod
    def sample_background_from_ontology(
        json_paths: list[str],
        n: int = 3000,
        seed: int = 42,
    ) -> list[str]:
        """
        Costruisce un corpus di background campionando descrizioni e label
        dall'ontologia ESCO stessa.

        Vantaggio metodologico: il background è ricavato dalla sola ontologia,
        non dai CV/annunci di valutazione, quindi il profilo hubness è
        indipendente dai dati su cui poi si misurano le metriche.
        """
        pool: list[str] = []
        for path in json_paths:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = json.load(f)
            except Exception:
                continue
            records = (
                content.values() if isinstance(content, dict) else content
            )
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                desc = rec.get("description")
                if desc and isinstance(desc, str) and len(desc) > 30:
                    pool.append(desc)
                lbl = rec.get("label")
                if lbl and isinstance(lbl, str):
                    pool.append(lbl)

        if not pool:
            return []
        rng = random.Random(seed)
        rng.shuffle(pool)
        return pool[:n]

    # ─────────────────────────────────────────────────────────────────────
    # Matching
    # ─────────────────────────────────────────────────────────────────────
    def find_matches(
        self,
        text_list: Iterable[str],
        threshold: float = 0.65,
        top_k: int = 1,
        max_results: int | None = None,
        return_scores: bool = False,
        hubness_correction: bool = False,
        mutual_only: bool = False,
    ):
        """
        Trova match semantici fra le righe in `text_list` e il DB corrente.

        Parametri:
            threshold   soglia minima di cosine similarity (0..1).
            top_k       quanti match considerare per OGNI riga (default 1).
            max_results se impostato, limita il numero totale di id distinti
                        restituiti (ordinati per score decrescente).
            return_scores se True, ritorna lista di dict {id,label,score}.
            hubness_correction
                        se True e il profilo di background è stato calcolato
                        (build_background_profile), penalizza le label che
                        somigliano indiscriminatamente a qualsiasi testo.
                        Vedi build_background_profile() per i dettagli.
            mutual_only se True applica il vincolo di reciprocità: una label
                        ESCO viene assegnata solo alla query che le somiglia
                        di più nel batch corrente. Una label-calamita, che
                        altrimenti verrebbe agganciata da molte frasi diverse
                        dello stesso documento, ne può così catturare al
                        massimo una. Senza effetto se il batch ha una sola
                        query.

        Ritorna: list[str] di id ESCO (o dict se return_scores=True).
        """
        if self.db_embeddings is None or not self.db_data:
            return []

        queries = [q for q in text_list if _is_meaningful(q)]
        if not queries:
            return []

        # I modelli E5 richiedono il prefisso "query: " per le query di ricerca
        encode_queries = (
            [f"query: {q}" for q in queries] if self._is_e5 else queries
        )

        q_emb = self.model.encode(
            encode_queries,
            convert_to_tensor=True,
            batch_size=64,
            normalize_embeddings=True,
        )
        # db_embeddings già normalizzato → il prodotto scalare è cosine
        scores = util.cos_sim(q_emb, self.db_embeddings)

        # ── Correzione hubness ──────────────────────────────────────────────
        # Sottrae a ogni colonna (= label ESCO) la sua deviazione di
        # background: le label che somigliano a tutto vengono penalizzate,
        # quelle specifiche restano invariate.
        if hubness_correction and self.bg_deviation is not None:
            if self.bg_deviation.numel() == scores.size(1):
                scores = scores - _HUBNESS_BETA * self.bg_deviation.unsqueeze(0)
            else:
                print(
                    "[semantic_mapper] Profilo background non allineato: "
                    "correzione hubness ignorata."
                )

        # ── Reciprocità ─────────────────────────────────────────────────────
        # Per ogni label, quale query del batch le somiglia di più.
        best_query_per_label = (
            scores.argmax(dim=0) if (mutual_only and scores.size(0) > 1) else None
        )

        best_per_id: dict[str, float] = {}
        label_per_id: dict[str, str] = {}
        # Frase di partenza che ha prodotto il match migliore per ogni id.
        # Serve all'annotazione manuale dei curriculum reali
        # (app/annota_cv.py), dove chi giudica deve poter vedere da dove
        # nasce una proposta. È informazione già disponibile qui e finora
        # scartata: registrarla non altera né i punteggi né la selezione.
        query_per_id: dict[str, str] = {}

        k = min(top_k, scores.size(1))
        top_vals, top_idxs = torch.topk(scores, k=k, dim=1)

        for q_i, (row_vals, row_idxs) in enumerate(
            zip(top_vals.tolist(), top_idxs.tolist())
        ):
            for v, idx in zip(row_vals, row_idxs):
                if v < threshold:
                    continue
                # Vincolo di reciprocità: questa label deve "preferire" a sua
                # volta la query corrente.
                if (best_query_per_label is not None
                        and int(best_query_per_label[idx]) != q_i):
                    continue
                entry = self.db_data[idx]
                eid = entry["id"]
                if v > best_per_id.get(eid, 0.0):
                    best_per_id[eid] = v
                    label_per_id[eid] = entry["label"]
                    query_per_id[eid] = queries[q_i]

        if not best_per_id:
            return []

        ordered = sorted(best_per_id.items(), key=lambda x: x[1], reverse=True)
        if max_results:
            ordered = ordered[:max_results]

        # In modalità bilingue usa la label preferita (IT > EN); altrimenti
        # usa la label dell'embedding che ha fatto il miglior match.
        _pref = self._preferred_labels or {}

        if return_scores:
            return [
                {
                    "id":    i,
                    "label": _pref.get(i, label_per_id[i]),
                    "score": round(s, 4),
                    # Aggiunta additiva: i consumatori esistenti leggono le
                    # chiavi per nome e non sono toccati dalla presenza di
                    # questa in più.
                    "query": query_per_id.get(i, ""),
                }
                for i, s in ordered
            ]
        return [i for i, _ in ordered]
