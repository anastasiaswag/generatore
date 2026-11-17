"""
filtro_skill.py  —  SkillPath AI
=================================
Applica in fase di esecuzione il classificatore addestrato da
analysis/addestra_filtro_skill.py, che decide se una skill ESCO proposta dal
job parser è corretta o è un falso positivo.

COSA SOSTITUISCE
────────────────
La denylist di etichette scritta a mano. Quella era ricavata osservando quali
predizioni fossero sbagliate sull'intero dataset di valutazione: efficace ma
supervisionata e specifica di quei dati. Il classificatore usa invece
attributi generali e una stima del comportamento storico di ciascuna
etichetta, ed è stato validato su 27 occupazioni tenute fuori
dall'addestramento.

Confronto sul test, entrambi costruiti sulle stesse occupazioni di training:

    nessun filtro              P 0.532  R 1.000  F1 0.694
    denylist (41 etichette)    P 0.567  R 0.988  F1 0.721
    classificatore appreso     P 0.643  R 0.856  F1 0.734

ATTENZIONE ALL'ORDINE DEGLI ATTRIBUTI
─────────────────────────────────────
Il vettore costruito qui deve corrispondere esattamente, per ordine e
significato, a quello di analysis/addestra_filtro_skill.py. Modificando gli
attributi in un file va aggiornato anche l'altro, altrimenti i pesi vengono
applicati alle grandezze sbagliate senza che nulla segnali l'errore. Il
caricamento verifica almeno che il numero di attributi coincida.
"""

import json
import math
import re
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELLO = BASE_DIR / "config" / "filtro_skill.json"
SKILLS_FILE = BASE_DIR / "dataset" / "source" / "skills.json"
RELAZIONI = BASE_DIR / "dataset" / "source" / "occupation_skill_relations.json"

REUSE = ["transversal", "cross-sector", "sector-specific", "occupation-specific"]

_STOP = set(
    "a an the to of in on at for and or with by from is are be as that this you we "
    "will your our their it its not have has can must should may all any more most "
    "il lo la i gli le un uno una di del dei della delle dello degli da dal con per "
    "tra fra su sul sulla e ed o che non sono essere avere come anche piu molto".split()
)


def _normalizza(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", t)


class FiltroSkillAppreso:
    """
    Filtro appreso. Se il modello o i dati ESCO non sono disponibili, resta
    inattivo e `disponibile` vale False: il parser continua a funzionare con
    le regole precedenti invece di fallire.
    """

    def __init__(self, percorso: str | Path | None = None, verbose: bool = True):
        self.disponibile = False
        percorso = Path(percorso) if percorso else MODELLO
        if not percorso.exists():
            if verbose:
                print(f"[filtro_skill] Modello non trovato ({percorso.name}): "
                      "filtro appreso disattivo.")
            return

        try:
            m = json.loads(percorso.read_text(encoding="utf-8"))
            self.pesi = m["pesi_produzione"]
            self.bias = m["bias_produzione"]
            self.media = m["media_produzione"]
            self.dev = m["deviazione_produzione"]
            self.soglia = m["soglia"]
            self.tassi = m["tasso_fp_per_skill"]
            self.tasso_default = m["tasso_fp_default"]
            self.attributi = m["attributi"]
        except (KeyError, ValueError) as e:
            if verbose:
                print(f"[filtro_skill] Modello illeggibile ({e}): filtro disattivo.")
            return

        if not (len(self.pesi) == len(self.media) == len(self.dev)
                == len(self.attributi)):
            if verbose:
                print("[filtro_skill] Numero di attributi incoerente fra pesi e "
                      "normalizzazione: filtro disattivo.")
            return

        # Metadati ESCO necessari agli attributi
        self._freq: dict[str, int] = {}
        self._meta: dict[str, tuple] = {}
        try:
            relazioni = json.loads(RELAZIONI.read_text(encoding="utf-8"))
            for r in relazioni.values():
                if isinstance(r, dict):
                    for sid in set((r.get("essential") or []) + (r.get("optional") or [])):
                        self._freq[sid] = self._freq.get(sid, 0) + 1
            skills = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            for s in skills.values():
                if s.get("id"):
                    self._meta[s["id"]] = (s.get("reuse_level"), s.get("skill_type"))
        except Exception as e:
            if verbose:
                print(f"[filtro_skill] Dati ESCO non caricabili ({e}): filtro disattivo.")
            return

        self._freq_max = max(self._freq.values()) if self._freq else 1
        self.disponibile = True
        if verbose:
            print(f"[filtro_skill] Attivo — {len(self.tassi)} etichette con "
                  f"storico, soglia {self.soglia:.2f}")

    # ──────────────────────────────────────────────────────────────────────
    def _attributi(self, m: dict, pos: int, n_doc: int,
                   parole_testo: set, is_req: bool) -> list[float]:
        sid, label = m.get("id", ""), m.get("label", "")
        cw = [w for w in _normalizza(label).split()
              if w not in _STOP and len(w) > 2]
        grounding = (sum(1 for w in cw if w in parole_testo) / len(cw)) if cw else 0.0
        reuse, stipo = self._meta.get(sid, (None, None))

        v = [
            m.get("score", 0.0),
            len(label.split()) / 10.0,
            len(label) / 100.0,
            self._freq.get(sid, 0) / self._freq_max,
        ]
        v += [1.0 if reuse == r else 0.0 for r in REUSE]
        v += [
            1.0 if stipo == "knowledge" else 0.0,
            grounding,
            pos / max(n_doc, 1),
            n_doc / 50.0,
            1.0 if is_req else 0.0,
            self.tassi.get(sid, self.tasso_default),
        ]
        return v

    def probabilita(self, m: dict, pos: int, n_doc: int,
                    parole_testo: set, is_req: bool) -> float:
        v = self._attributi(m, pos, n_doc, parole_testo, is_req)
        z = self.bias + sum(
            ((x - mu) / sd) * w
            for x, mu, sd, w in zip(v, self.media, self.dev, self.pesi)
        )
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    # ──────────────────────────────────────────────────────────────────────
    def filtra(self, matches: list[dict], testo: str,
               required_ids: set | None = None) -> list[dict]:
        """
        Ritorna i soli match che il classificatore giudica corretti.

        `matches` va passato completo per un singolo annuncio: alcuni attributi
        (posizione nella classifica, numero di skill del documento) dipendono
        dal contesto e non sono calcolabili su un match isolato.
        """
        if not self.disponibile or not matches:
            return matches

        parole = set(_normalizza(testo).split())
        req = required_ids or set()
        ordinati = sorted(matches, key=lambda m: -m.get("score", 0.0))
        n = len(ordinati)

        tenuti = []
        for pos, m in enumerate(ordinati):
            p = self.probabilita(m, pos, n, parole, m.get("id") in req)
            if p >= self.soglia:
                m = dict(m)
                m["p_corretta"] = round(p, 4)
                tenuti.append(m)
        return tenuti
