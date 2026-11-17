"""
skill_graph.py  —  SkillPath AI
================================
Grafo delle relazioni tra skill ESCO.

PROSSIMITÀ CONCETTUALE: DUE SORGENTI
────────────────────────────────────
La vicinanza fra due competenze può venire da due fonti, e questo modulo usa
la migliore fra quelle disponibili dichiarando sempre quale:

  1. GERARCHIA UFFICIALE ESCO  (preferita)
     `dataset/source/skill_relations.json`, prodotto da
     `src/build_skill_relations.py` a partire dai CSV ufficiali. Dà una
     similarità di Wu-Palmer definita per tutte le 13.939 competenze.

  2. CO-OCCORRENZA RICOSTRUITA  (ripiego)
     Usata finché i file ufficiali non erano stati scaricati: due competenze
     sono vicine se compaiono spesso nella stessa occupazione. Resta come
     ripiego perché il progetto deve funzionare anche senza i CSV ESCO.

Il confronto fra le due è misurato in `analysis/valida_skill_graph.py`: la
ricostruzione seleziona coppie 2,5 volte più vicine del caso — quindi non era
arbitraria — ma il NUMERO di co-occorrenze non predice la vicinanza reale
(ρ = 0,033). Funzionava come indicatore binario, non come misura graduata,
che è invece il modo in cui veniva usata.

Le altre due componenti del punteggio restano invariate e vengono da:

  1. occupation_skill_relations.json
       → co-occorrenza: quante volte due skill compaiono nella stessa occupazione
       → frequenza: in quante occupazioni è richiesta ogni skill (breadth)

  2. skills.json (campo reuse_level)
       → gerarchia di trasversalità:
           transversal     (livello 4) — "pensiero critico", "comunicazione"
           cross-sector    (livello 3) — "gestione team", "uso PC"
           sector-specific (livello 2) — "saldatura MIG", "Python"
           occupation-specific (livello 1) — "calibrare tornio CNC modello X"

LOGICA DI RANKING DEL GAP
--------------------------
Una skill mancante deve essere imparata PRIMA se:
  a) appare in molte occupazioni (è fondamentale)  → occupation_freq alto
  b) ha reuse_level alto (è trasversale)           → livello 3-4
  c) è co-requisito di skill già possedute         → co_score alto

Formula (normalizzata 0-1):
    priority_score = 0.4 * freq_score
                   + 0.4 * reuse_score
                   + 0.2 * co_score

Le skill con priority_score più alto hanno priorità 1 nella roadmap.

USO
---
    from skill_graph import SkillGraph
    sg = SkillGraph()
    sg.build(relations_path, skills_path)
    ordered_gap = sg.rank_gap(gap_ids, known_ids)
"""

import json
import math
from pathlib import Path
from collections import defaultdict


# Mappa reuse_level → punteggio (0-1)
_REUSE_SCORES = {
    "transversal":         1.00,   # competenze trasversali assolute
    "cross-sector":        0.75,   # utili in molti settori
    "sector-specific":     0.40,   # specifiche di un settore
    "occupation-specific": 0.10,   # specifiche di un singolo ruolo
}

_DEFAULT_REUSE = 0.20   # fallback per skill senza reuse_level


class SkillGraph:
    """
    Grafo di prossimità concettuale tra skill ESCO.

    Costruito da:
      - occupation_skill_relations.json  (co-occorrenza + frequenza)
      - skills.json                      (reuse_level)
    """

    def __init__(self):
        # skill_id → numero di occupazioni che la richiedono
        self._freq: dict[str, int] = {}
        # (skill_a, skill_b) → numero di co-occorrenze in occupazioni essential
        self._cooccur: dict[tuple[str, str], int] = defaultdict(int)
        # skill_id → reuse_level score (0-1)
        self._reuse: dict[str, float] = {}
        # skill_id → label (per output leggibile)
        self._labels: dict[str, str] = {}
        self._built = False
        self._max_freq: int = 1
        # Gerarchia ufficiale ESCO, se disponibile
        self._tax = None
        self.fonte_prossimita: str = "co-occorrenza ricostruita"

    # ── Build ──────────────────────────────────────────────────────────────────

    def build(
        self,
        relations_path: str | Path,
        skills_path:    str | Path,
        usa_tassonomia: bool = True,
    ) -> None:
        """
        Costruisce il grafo leggendo i file JSON locali.
        Da chiamare una sola volta; i dati vengono tenuti in memoria.

        `usa_tassonomia=False` forza il ripiego sulla co-occorrenza anche
        quando i file ufficiali ci sono: serve a riprodurre i risultati
        prodotti prima che la gerarchia fosse disponibile.
        """
        relations_path = Path(relations_path)
        skills_path    = Path(skills_path)

        # ── 0. Gerarchia ufficiale ESCO, se presente ──────────────────────────
        # L'importazione è qui e non in testa al modulo perché l'assenza del
        # file è una condizione prevista: il grafo deve costruirsi comunque.
        if usa_tassonomia:
            try:
                from esco_taxonomy import TaxonomiaESCO
                tax = TaxonomiaESCO()
                if tax.carica():
                    self._tax = tax
                    self.fonte_prossimita = f"gerarchia ESCO {tax.versione}"
            except ImportError:
                pass

        # ── 1. Carica skills.json → reuse_level e label ───────────────────────
        with open(skills_path, encoding="utf-8") as f:
            skills_data = json.load(f)

        for sid, item in skills_data.items():
            self._labels[sid] = item.get("label", sid)
            rl = item.get("reuse_level") or ""
            self._reuse[sid] = _REUSE_SCORES.get(rl, _DEFAULT_REUSE)

        # ── 2. Carica occupation_skill_relations → freq e co-occorrenza ───────
        with open(relations_path, encoding="utf-8") as f:
            relations = json.load(f)

        for occ_id, rel in relations.items():
            essential = rel.get("essential", [])
            optional  = rel.get("optional",  [])
            all_skills = essential + optional

            # Aggiorna frequenza
            for sid in all_skills:
                self._freq[sid] = self._freq.get(sid, 0) + 1

            # Co-occorrenza solo su essential (più significativa)
            for i, a in enumerate(essential):
                for b in essential[i + 1:]:
                    key = (min(a, b), max(a, b))
                    self._cooccur[key] += 1

        self._max_freq = max(self._freq.values(), default=1)
        self._built = True
        print(
            f"[SkillGraph] Costruito: {len(self._freq)} skill, "
            f"{len(self._cooccur)} coppie co-occorrenti, "
            f"freq_max={self._max_freq}, "
            f"prossimità da {self.fonte_prossimita}"
        )

    # ── Query ──────────────────────────────────────────────────────────────────

    def occupation_frequency(self, skill_id: str) -> int:
        """Numero di occupazioni che richiedono questa skill."""
        return self._freq.get(skill_id, 0)

    def reuse_score(self, skill_id: str) -> float:
        """Punteggio reuse_level (0-1): 1 = transversal, 0.1 = occupation-specific."""
        return self._reuse.get(skill_id, _DEFAULT_REUSE)

    def co_occurrence_score(
        self,
        gap_skill_id:  str,
        known_skill_ids: list[str],
    ) -> float:
        """
        Punteggio di co-occorrenza tra la skill nel gap e le skill già note.
        Restituisce la media normalizzata delle co-occorrenze con le skill note.
        """
        if not known_skill_ids:
            return 0.0

        total = 0
        for kid in known_skill_ids:
            key = (min(gap_skill_id, kid), max(gap_skill_id, kid))
            total += self._cooccur.get(key, 0)

        avg = total / len(known_skill_ids)
        # Normalizza: il massimo teorico è self._max_freq occupazioni.
        # ATTENZIONE — questa normalizzazione divide una media di
        # co-occorrenze (tipicamente 0-3) per una FREQUENZA massima (340):
        # sono grandezze diverse, e il risultato è schiacciato verso zero.
        # Misurato su 787 divari reali il contributo di questa componente al
        # punteggio finale è l'1,6%, contro il 20% nominale del suo peso.
        # Il difetto è documentato in analysis/valida_skill_graph.py e non
        # viene corretto qui: la componente è sostituita dalla prossimità
        # tassonomica quando i dati ufficiali sono disponibili, e questo
        # metodo resta com'era per poter riprodurre i risultati precedenti.
        return min(avg / max(self._max_freq, 1), 1.0)

    def prossimita(
        self,
        gap_skill_id:    str,
        known_skill_ids: list[str],
    ) -> float:
        """
        Vicinanza fra una competenza mancante e quelle già possedute.

        Usa la gerarchia ufficiale ESCO se caricata, altrimenti ripiega sulla
        co-occorrenza ricostruita. Il chiamante non deve sapere quale delle
        due: la fonte è dichiarata in `self.fonte_prossimita` e riportata in
        ogni voce restituita da `rank_gap`.
        """
        if self._tax is not None:
            return self._tax.vicinanza_a_insieme(gap_skill_id, known_skill_ids)
        return self.co_occurrence_score(gap_skill_id, known_skill_ids)

    def priority_score(
        self,
        gap_skill_id:    str,
        known_skill_ids: list[str],
    ) -> float:
        """
        Score composito per ordinare il gap (0-1, più alto = imparare prima).

        Pesi:
          40% occupation_frequency  (skill fondamentali prima)
          40% reuse_level           (skill trasversali prima)
          20% prossimità            (skill vicine a quelle note prima)

        I pesi sono stati scelti, non derivati da dati. Misurati su 787
        divari reali i contributi effettivi sono però molto diversi da quelli
        nominali — trasversalità 72,6%, frequenza 20,7%, prossimità 6,7% —
        perché le tre componenti si distribuiscono su scale diverse. È un
        limite noto e dichiarato, non una taratura.
        """
        freq_score = self._freq.get(gap_skill_id, 0) / self._max_freq
        reuse      = self.reuse_score(gap_skill_id)
        vicinanza  = self.prossimita(gap_skill_id, known_skill_ids)

        return 0.40 * freq_score + 0.40 * reuse + 0.20 * vicinanza

    def rank_gap(
        self,
        gap_ids:   list[str],
        known_ids: list[str],
    ) -> list[dict]:
        """
        Ordina le skill nel gap per priorità di apprendimento.

        Args:
            gap_ids:   ESCO ID delle skill mancanti
            known_ids: ESCO ID delle skill già possedute dal candidato

        Returns:
            Lista ordinata di dict con:
              id, label, priority (1=prima), priority_score,
              occupation_freq, reuse_level_label, co_occurrence_score
        """
        if not self._built:
            raise RuntimeError("Chiama build() prima di rank_gap()")

        # Mappa reuse_score → label testuale
        _reuse_label = {
            1.00: "transversal",
            0.75: "cross-sector",
            0.40: "sector-specific",
            0.10: "occupation-specific",
        }

        scored = []
        for sid in gap_ids:
            ps = self.priority_score(sid, known_ids)
            rs = self.reuse_score(sid)
            vic = self.prossimita(sid, known_ids)
            scored.append({
                "id":                 sid,
                "label":              self._labels.get(sid, sid),
                "priority_score":     round(ps, 4),
                "occupation_freq":    self._freq.get(sid, 0),
                "reuse_level":        _reuse_label.get(rs, "sector-specific"),
                "prossimita_score":   round(vic, 4),
                "fonte_prossimita":   self.fonte_prossimita,
                # Mantenuto per compatibilità: matching_engine.py legge questa
                # chiave. Ora contiene la prossimità effettivamente usata, che
                # può non essere la co-occorrenza — il campo accanto dice quale.
                "co_occurrence_score": round(vic, 4),
            })

        scored.sort(key=lambda x: x["priority_score"], reverse=True)
        for rank, item in enumerate(scored, start=1):
            item["priority"] = rank

        return scored
