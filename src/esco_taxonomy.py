"""
esco_taxonomy.py  —  SkillPath AI
==================================
Prossimità tassonomica fra competenze ESCO, calcolata sulla gerarchia
ufficiale prodotta da `build_skill_relations.py`.

CHE COSA MISURA
───────────────
Due competenze sono tanto più vicine quanto più in basso nella gerarchia si
trova il concetto più specifico che le contiene entrambe. «Python» e «Java»
condividono un antenato profondo — la programmazione — mentre «Python» e
«potatura delle viti» si incontrano solo alla radice, o non si incontrano
affatto perché appartengono a pilastri diversi.

La formula è quella di Wu e Palmer (1994), lo standard per le tassonomie:

    sim(a, b) = 2 · prof(antenato comune più profondo)
                ─────────────────────────────────────
                        prof(a) + prof(b)

FORMA DELLA GERARCHIA ESCO, E PERCHÉ CONTA
──────────────────────────────────────────
Misurata sui dati v1.2.1:

  · quattro radici distinte — `skills`, `knowledge`, `language skills and
    knowledge`, `transversal skills and competences`. Non esiste un nodo
    unico sopra di esse, quindi due competenze possono non avere alcun
    antenato in comune: la similarità è 0 e non è un errore.
  · profondità massima 4: le competenze stanno quasi tutte al livello 4
    (13.446 su 13.939), i gruppi ai livelli 1-3.
  · genitori multipli, in media 1,45 e fino a 9. È un grafo aciclico, non un
    albero, quindi l'antenato comune si cerca intersecando gli insiemi di
    antenati, non risalendo una catena.

La conseguenza pratica è che i valori possibili sono pochi — tipicamente
0, 0,25, 0,50 e 0,75 — e che il segnale è raro: su 20.000 coppie casuali il
38,5% non ha antenati in comune e il 48,2% ne condivide solo la radice. È
una misura discriminante proprio perché tace quasi sempre.

USO
───
    from esco_taxonomy import TaxonomiaESCO
    tax = TaxonomiaESCO()
    tax.carica()                       # dataset/source/skill_relations.json
    tax.similarita(id_a, id_b)         # 0.0 – 1.0
    tax.vicinanza_a_insieme(id, noti)  # media sulle competenze già possedute
"""

import json
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATH = BASE_DIR / "dataset" / "source" / "skill_relations.json"


class TaxonomiaESCO:
    """Gerarchia ufficiale delle competenze ESCO e distanze che se ne ricavano."""

    def __init__(self) -> None:
        self._genitori: dict[str, list[str]] = {}
        self._profondita: dict[str, int] = {}
        self._etichette: dict[str, str] = {}
        self._dipendenze: dict[str, dict] = {}
        self.versione: str = ""
        self.disponibile: bool = False

    # ── Caricamento ───────────────────────────────────────────────────────────

    def carica(self, path: str | Path = DEFAULT_PATH) -> bool:
        """
        Carica il file delle relazioni. Restituisce False se non esiste, senza
        sollevare eccezioni: l'assenza dei dati ufficiali è una condizione
        prevista, e chi chiama deve poter ripiegare sulla ricostruzione.
        """
        p = Path(path)
        if not p.exists():
            self.disponibile = False
            return False
        d = json.loads(p.read_text(encoding="utf-8"))
        self._genitori = d.get("genitori", {})
        self._profondita = d.get("profondita", {})
        self._etichette = d.get("etichette", {})
        self._dipendenze = d.get("dipendenze", {})
        self.versione = d.get("versione_esco", "")
        self.disponibile = bool(self._genitori and self._profondita)
        self._antenati.cache_clear()
        return self.disponibile

    # ── Struttura ─────────────────────────────────────────────────────────────

    @lru_cache(maxsize=None)
    def _antenati(self, key: str) -> frozenset:
        """
        Insieme di tutti i concetti che contengono `key`, incluso sé stesso.

        La visita è iterativa e non ricorsiva: con genitori multipli la
        ricorsione ripercorre le stesse diramazioni molte volte, e su 14.579
        concetti la differenza si sente. `visti` protegge anche dall'eventualità
        di un ciclo nei dati.
        """
        visti: set[str] = set()
        pila = [key]
        while pila:
            n = pila.pop()
            if n in visti:
                continue
            visti.add(n)
            pila.extend(self._genitori.get(n, ()))
        return frozenset(visti)

    def profondita(self, key: str) -> int:
        return self._profondita.get(key, 0)

    def etichetta(self, key: str) -> str:
        return self._etichette.get(key, key)

    # ── Misure ────────────────────────────────────────────────────────────────

    def antenato_comune(self, a: str, b: str) -> str | None:
        """Concetto più profondo che contiene entrambe le competenze."""
        comuni = self._antenati(a) & self._antenati(b)
        if not comuni:
            return None
        return max(comuni, key=lambda k: self._profondita.get(k, 0))

    def similarita(self, a: str, b: str) -> float:
        """
        Similarità di Wu-Palmer fra due competenze, fra 0 e 1.

        Vale 0 quando le due competenze appartengono a pilastri diversi o si
        incontrano solo alla radice; vale 1 solo se confrontate con sé stesse.
        Identificativi sconosciuti danno 0: è il comportamento giusto per un
        punteggio che verrà sommato ad altri.
        """
        if a == b:
            return 1.0
        if a not in self._profondita or b not in self._profondita:
            return 0.0
        lca = self.antenato_comune(a, b)
        if lca is None:
            return 0.0
        pa, pb = self._profondita.get(a, 0), self._profondita.get(b, 0)
        if pa + pb == 0:
            return 0.0
        return 2.0 * self._profondita.get(lca, 0) / (pa + pb)

    def vicinanza_a_insieme(self, skill_id: str, altre: list[str]) -> float:
        """
        Quanto una competenza è vicina a un insieme di competenze possedute.

        Si usa la MEDIA e non il massimo: il massimo premierebbe una singola
        coincidenza fortunata, mentre qui interessa se la competenza mancante
        appartiene alla stessa area di ciò che il candidato già sa.
        """
        if not altre:
            return 0.0
        tot = sum(self.similarita(skill_id, k) for k in altre if k != skill_id)
        n = sum(1 for k in altre if k != skill_id)
        return tot / n if n else 0.0

    # ── Dipendenze dichiarate ─────────────────────────────────────────────────

    def dipendenze(self, skill_id: str) -> dict:
        """
        Competenze di cui questa ha bisogno, secondo `skillSkillRelations`.

        Copre solo il 41% delle competenze, quindi un risultato vuoto significa
        quasi sempre «non dichiarato» e non «nessuna dipendenza».
        """
        return self._dipendenze.get(skill_id, {"essential": [], "optional": []})
