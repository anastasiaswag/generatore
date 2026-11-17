"""
addestra_filtro_skill.py  —  SkillPath AI
==========================================
Addestra un classificatore che decide se una skill ESCO proposta dal parser
degli annunci è corretta o è un falso positivo.

PERCHÉ
──────
Il job parser scarta i falsi positivi con due regole scritte a mano: accettare
dalla prosa solo candidati di almeno due parole, ed escludere 64 etichette
ESCO troppo generiche. Funzionano — insieme portano l'F1 da 0.391 a 0.580 — ma
sono euristiche, e la seconda è stata ricavata guardando quali predizioni
erano sbagliate su questo stesso dataset. È il punto metodologicamente più
debole della pipeline.

Un classificatore addestrato sostituisce quelle regole con una decisione
appresa da attributi generali, valutabile con la procedura standard
train/validation/test.

I DATI SONO GIÀ DISPONIBILI
───────────────────────────
Ogni skill estratta dal parser è etichettata dal confronto con la ground truth
degli annunci sintetici: 11.071 esempi, 54,3% positivi. Non serve annotare
nulla a mano.

DIVISIONE PER OCCUPAZIONE, NON PER DOCUMENTO
────────────────────────────────────────────
Punto decisivo. Se si addestrasse su alcuni annunci da "pizzaiolo" e si
testasse su altri annunci dello stesso ruolo, il modello avrebbe già visto
quelle competenze e il test sarebbe compromesso. La divisione avviene quindi
per OCCUPAZIONE: un blocco di mestieri per addestrare, un blocco disgiunto per
validare e un terzo per il test finale. Così si misura se il classificatore
generalizza a mestieri mai incontrati, che è ciò che accadrebbe in uso reale.

ATTRIBUTI
─────────
Nessuno di essi guarda l'identità della skill, per evitare che il modello
impari a memoria una denylist:

  score               similarità coseno del match
  n_parole            parole nell'etichetta ESCO
  lunghezza           caratteri nell'etichetta
  freq_occupazioni    quante occupazioni ESCO richiedono questa skill: le
                      etichette generiche compaiono ovunque
  reuse_level         quanto la skill è trasversale (4 livelli, one-hot)
  è_conoscenza        skill_type = knowledge invece di skill/competence
  grounding           quota di parole-contenuto dell'etichetta presenti nel
                      testo dell'annuncio
  rango               posizione per punteggio dentro il documento
  n_skill_documento   quante skill sono state estratte da quell'annuncio
  è_required          se il parser l'ha classificata come requisito
  tasso_fp_storico    quota di volte in cui QUESTA etichetta è risultata
                      sbagliata, calcolata SOLO sulle occupazioni di training.
                      È l'equivalente appreso e continuo della denylist scritta
                      a mano, ma qui il valore è stimato su un insieme
                      disgiunto da quello di test, quindi non costituisce
                      conoscenza del test. Le etichette mai viste in training
                      ricevono il valore medio globale, cioè nessun pregiudizio.

MODELLO
───────
Regressione logistica con discesa del gradiente, implementata in numpy. La
scelta è deliberata: i pesi restano leggibili, quindi si può mostrare quali
attributi contano e in che direzione — informazione che un modello opaco non
darebbe, e che qui è parte del risultato.

Uso (dalla radice del progetto):
    python analysis/addestra_filtro_skill.py
    python analysis/addestra_filtro_skill.py --epoche 400 --lr 0.5
"""

import argparse
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

IN_FILE = BASE_DIR / "outputs" / "ab_multiword_nodeny.json"
JOBS_RAW = BASE_DIR / "dataset" / "synthetic" / "jobs_gt" / "jobs.json"
SKILLS_FILE = BASE_DIR / "dataset" / "source" / "skills.json"
RELAZIONI = BASE_DIR / "dataset" / "source" / "occupation_skill_relations.json"
OUT_MODEL = BASE_DIR / "config" / "filtro_skill.json"

SEP = "─" * 68

REUSE = ["transversal", "cross-sector", "sector-specific", "occupation-specific"]

_STOP = set(
    "a an the to of in on at for and or with by from is are be as that this you we "
    "will your our their it its not have has can must should may all any more most "
    "il lo la i gli le un uno una di del dei della delle dello degli da dal con per "
    "tra fra su sul sulla e ed o che non sono essere avere come anche piu molto".split()
)


def normalizza(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", t)


def parole_contenuto(t: str) -> list[str]:
    return [w for w in normalizza(t).split() if w not in _STOP and len(w) > 2]


# ══════════════════════════════════════════════════════════════════════════════
# Costruzione degli esempi
# ══════════════════════════════════════════════════════════════════════════════

def costruisci_dataset() -> tuple[np.ndarray, np.ndarray, list[str], list[str], list[str]]:
    """Ritorna (X, y, occupazione, nomi_attributi, id_skill di ogni esempio)."""
    for f in (IN_FILE, JOBS_RAW, SKILLS_FILE, RELAZIONI):
        if not f.exists():
            print(f"[ERRORE] File mancante: {f}")
            sys.exit(1)

    risultati = json.loads(IN_FILE.read_text(encoding="utf-8"))
    testi = {j["job_id"]: j["job"].get("raw_text", "")
             for j in json.loads(JOBS_RAW.read_text(encoding="utf-8"))}
    skills = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
    relazioni = json.loads(RELAZIONI.read_text(encoding="utf-8"))

    # Quante occupazioni richiedono ciascuna skill
    freq: dict[str, int] = {}
    for r in relazioni.values():
        if not isinstance(r, dict):
            continue
        for sid in set((r.get("essential") or []) + (r.get("optional") or [])):
            freq[sid] = freq.get(sid, 0) + 1
    freq_max = max(freq.values()) if freq else 1

    meta_skill = {}
    for s in skills.values():
        sid = s.get("id")
        if sid:
            meta_skill[sid] = (s.get("reuse_level"), s.get("skill_type"))

    nomi = (["score", "n_parole", "lunghezza", "freq_occupazioni"]
            + [f"reuse_{r}" for r in REUSE]
            + ["e_conoscenza", "grounding", "rango", "n_skill_doc", "e_required"])

    X, y, occ, id_skill = [], [], [], []
    for e in risultati:
        gt = set(e["expected_skills"]["required_ids"]
                 + e["expected_skills"]["preferred_ids"])
        req = set(e["skills"]["required_ids"])
        estratte = req | set(e["skills"]["preferred_ids"])
        occupazione = (e.get("ground_truth") or {}).get("target_occupation_id", "")

        parole_testo = set(normalizza(testi.get(e["job_id"], "")).split())

        match = [m for m in e["skills"]["all_matches"] if m["id"] in estratte]
        match.sort(key=lambda m: -m.get("score", 0))
        n_doc = len(match)

        for pos, m in enumerate(match):
            sid, label = m["id"], m.get("label", "")
            cw = parole_contenuto(label)
            grounding = (sum(1 for w in cw if w in parole_testo) / len(cw)) if cw else 0.0
            reuse, stipo = meta_skill.get(sid, (None, None))

            riga = [
                m.get("score", 0.0),
                len(label.split()) / 10.0,
                len(label) / 100.0,
                freq.get(sid, 0) / freq_max,
            ]
            riga += [1.0 if reuse == r else 0.0 for r in REUSE]
            riga += [
                1.0 if stipo == "knowledge" else 0.0,
                grounding,
                pos / max(n_doc, 1),
                n_doc / 50.0,
                1.0 if sid in req else 0.0,
            ]
            X.append(riga)
            y.append(1.0 if sid in gt else 0.0)
            occ.append(occupazione)
            id_skill.append(sid)

    return (np.array(X, dtype=np.float64), np.array(y, dtype=np.float64),
            occ, nomi, id_skill)


# ══════════════════════════════════════════════════════════════════════════════
# Regressione logistica
# ══════════════════════════════════════════════════════════════════════════════

def sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def addestra(X, y, epoche: int, lr: float, l2: float) -> np.ndarray:
    """Discesa del gradiente su entropia incrociata con regolarizzazione L2."""
    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])          # colonna del bias
    w = np.zeros(d + 1)
    for ep in range(epoche):
        p = sigmoide(Xb @ w)
        grad = Xb.T @ (p - y) / n
        grad[:-1] += l2 * w[:-1]                  # il bias non si regolarizza
        w -= lr * grad
        if (ep + 1) % max(epoche // 5, 1) == 0:
            perdita = -np.mean(y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9))
            print(f"    epoca {ep+1:>4}  perdita {perdita:.4f}")
    return w


def prevedi(X, w) -> np.ndarray:
    return sigmoide(np.hstack([X, np.ones((len(X), 1))]) @ w)


def metriche(y, p, soglia: float) -> dict:
    pred = (p >= soglia).astype(float)
    tp = float(((pred == 1) & (y == 1)).sum())
    fp = float(((pred == 1) & (y == 0)).sum())
    fn = float(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1,
            "tp": int(tp), "fp": int(fp), "fn": int(fn)}


# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — classificatore dei falsi positivi del job parser")
    ap.add_argument("--epoche", type=int, default=800)
    ap.add_argument("--lr", type=float, default=1.0)
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(OUT_MODEL))
    args = ap.parse_args()

    print(f"\n{SEP}\n  COSTRUZIONE DEL DATASET\n{SEP}")
    X, y, occ, nomi, id_skill = costruisci_dataset()
    print(f"  esempi: {len(y)}   attributi: {X.shape[1]}   "
          f"positivi: {y.mean():.1%}")

    # ── Divisione per occupazione ────────────────────────────────────────────
    occupazioni = sorted(set(occ))
    rng = random.Random(args.seed)
    rng.shuffle(occupazioni)
    n_tr = int(len(occupazioni) * 0.60)
    n_va = int(len(occupazioni) * 0.20)
    tr_occ = set(occupazioni[:n_tr])
    va_occ = set(occupazioni[n_tr:n_tr + n_va])
    te_occ = set(occupazioni[n_tr + n_va:])

    idx = {"train": [], "val": [], "test": []}
    for i, o in enumerate(occ):
        idx["train" if o in tr_occ else ("val" if o in va_occ else "test")].append(i)

    print(f"\n  occupazioni: {len(tr_occ)} train / {len(va_occ)} validation / "
          f"{len(te_occ)} test  (insiemi disgiunti)")
    for k in ("train", "val", "test"):
        print(f"    {k:<6} {len(idx[k]):>6} esempi")

    # ── Attributo "tasso di errore storico dell'etichetta" ───────────────────
    # Stimato ESCLUSIVAMENTE sulle occupazioni di training: applicarlo a
    # validation e test non introduce conoscenza dei loro dati, esattamente
    # come una denylist costruita su un insieme e usata su un altro.
    conteggi: dict[str, list] = {}
    for i in idx["train"]:
        c = conteggi.setdefault(id_skill[i], [0, 0])
        c[int(y[i])] += 1
    globale = 1.0 - y[idx["train"]].mean()
    tasso = np.array([
        (conteggi[s_][0] / (conteggi[s_][0] + conteggi[s_][1]))
        if s_ in conteggi and sum(conteggi[s_]) >= 3 else globale
        for s_ in id_skill
    ]).reshape(-1, 1)
    X = np.hstack([X, tasso])
    nomi = nomi + ["tasso_fp_storico"]
    visti = sum(1 for s_ in id_skill if s_ in conteggi and sum(conteggi[s_]) >= 3)
    print(f"\n  attributo storico: {visti}/{len(id_skill)} esempi hanno "
          f"un'etichetta osservata almeno 3 volte in training")

    Xtr, ytr = X[idx["train"]], y[idx["train"]]
    Xva, yva = X[idx["val"]], y[idx["val"]]
    Xte, yte = X[idx["test"]], y[idx["test"]]

    # ── Standardizzazione (statistiche dal solo train) ───────────────────────
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    Xtr_s, Xva_s, Xte_s = (Xtr - mu) / sd, (Xva - mu) / sd, (Xte - mu) / sd

    print(f"\n{SEP}\n  ADDESTRAMENTO\n{SEP}")
    w = addestra(Xtr_s, ytr, args.epoche, args.lr, args.l2)

    # ── Soglia scelta sulla validation, mai sul test ─────────────────────────
    pva = prevedi(Xva_s, w)
    migliore = max(
        ((s, metriche(yva, pva, s)["f1"]) for s in np.arange(0.20, 0.81, 0.01)),
        key=lambda t: t[1],
    )
    soglia = float(migliore[0])
    print(f"\n  soglia scelta sulla validation: {soglia:.2f}  "
          f"(F1 validation {migliore[1]:.3f})")

    # ── Risultato sul test, mai toccato ──────────────────────────────────────
    pte = prevedi(Xte_s, w)
    m_te = metriche(yte, pte, soglia)

    # Confronto: nessun filtro (tutto accettato), come fa il parser senza denylist
    m_base = metriche(yte, np.ones_like(yte), 0.5)

    # Confronto EQUO con la regola scritta a mano: la denylist va ricostruita
    # sulle sole occupazioni di training, con lo stesso criterio di
    # analysis/ricostruisci_denylist.py. Quella presente in job_parser.py è
    # stata derivata da TUTTI gli annunci, quindi sulle occupazioni di test ha
    # già visto le risposte: confrontarcisi sopravvaluterebbe la regola.
    deny_tr = {s_ for s_, (fp_, tp_) in conteggi.items()
               if fp_ + tp_ >= 10 and fp_ / (fp_ + tp_) >= 0.85}
    pred_deny = np.array([0.0 if id_skill[i] in deny_tr else 1.0
                          for i in idx["test"]])
    m_deny = metriche(yte, pred_deny, 0.5)

    print(f"\n{SEP}\n  RISULTATI SUL TEST (occupazioni mai viste)\n{SEP}")
    print(f"  {'configurazione':<34}{'Prec':>8}{'Rec':>8}{'F1':>8}{'FP':>8}")
    print(f"  {'-'*66}")
    print(f"  {'nessun filtro':<34}{m_base['precision']:>8.3f}"
          f"{m_base['recall']:>8.3f}{m_base['f1']:>8.3f}{m_base['fp']:>8}")
    print(f"  {f'denylist da training ({len(deny_tr)} etichette)':<34}"
          f"{m_deny['precision']:>8.3f}{m_deny['recall']:>8.3f}"
          f"{m_deny['f1']:>8.3f}{m_deny['fp']:>8}")
    print(f"  {'classificatore appreso':<34}{m_te['precision']:>8.3f}"
          f"{m_te['recall']:>8.3f}{m_te['f1']:>8.3f}{m_te['fp']:>8}")
    print(f"  {'-'*66}")
    print(f"  {'appreso - regola a mano':<34}"
          f"{m_te['precision']-m_deny['precision']:>+8.3f}"
          f"{m_te['recall']-m_deny['recall']:>+8.3f}"
          f"{m_te['f1']-m_deny['f1']:>+8.3f}{m_te['fp']-m_deny['fp']:>+8}")
    print()
    if m_te["f1"] > m_deny["f1"]:
        print("  Il componente appreso supera la regola scritta a mano su")
        print("  occupazioni mai viste. Entrambi sono stati costruiti sullo")
        print("  stesso insieme di training, quindi il confronto è equo.")
    else:
        print("  La regola scritta a mano regge il confronto: il classificatore")
        print("  non aggiunge valore e non conviene sostituirla.")

    # ── Pesi appresi ─────────────────────────────────────────────────────────
    print(f"\n{SEP}\n  ATTRIBUTI PIÙ INFLUENTI\n{SEP}")
    print("  (peso positivo = spinge verso 'skill corretta')\n")
    ordine = sorted(zip(nomi, w[:-1]), key=lambda t: -abs(t[1]))
    for nome, peso in ordine:
        barra = "█" * min(int(abs(peso) * 12), 30)
        print(f"  {nome:<22}{peso:>+8.3f}  {barra}")

    # ── Modello di produzione ────────────────────────────────────────────────
    # Le metriche riportate sopra vengono dalla divisione train/val/test ed è
    # quello il numero da citare. Il modello che viene poi usato in produzione
    # si riaddestra però su TUTTE le occupazioni: altrimenti i 46 mestieri
    # esclusi dal training resterebbero privi di tasso storico e riceverebbero
    # il valore medio, perdendo l'informazione più utile. È la prassi standard
    # — si stima l'errore su dati trattenuti, si consegna il modello addestrato
    # su tutto il disponibile.
    print(f"\n{SEP}\n  MODELLO DI PRODUZIONE (riaddestrato su tutte le occupazioni)\n{SEP}")
    cont_all: dict[str, list] = {}
    for i in range(len(y)):
        c = cont_all.setdefault(id_skill[i], [0, 0])
        c[int(y[i])] += 1
    glob_all = 1.0 - y.mean()
    tasso_all = np.array([
        (cont_all[s_][0] / (cont_all[s_][0] + cont_all[s_][1]))
        if sum(cont_all[s_]) >= 3 else glob_all
        for s_ in id_skill
    ]).reshape(-1, 1)
    X_all = np.hstack([X[:, :-1], tasso_all])
    mu_all, sd_all = X_all.mean(axis=0), X_all.std(axis=0)
    sd_all[sd_all == 0] = 1.0
    w_all = addestra((X_all - mu_all) / sd_all, y, args.epoche, args.lr, args.l2)

    tabella = {s_: round(c[0] / (c[0] + c[1]), 4)
               for s_, c in cont_all.items() if sum(c) >= 3}
    print(f"  tabella tassi storici: {len(tabella)} etichette osservate ≥3 volte")

    modello = {
        "descrizione": "Filtro appreso dei falsi positivi del job parser",
        "nota": ("pesi addestrati su tutte le occupazioni; le metriche in "
                 "'test' provengono dalla divisione per occupazione"),
        "pesi_produzione": [float(v) for v in w_all[:-1]],
        "bias_produzione": float(w_all[-1]),
        "media_produzione": [float(v) for v in mu_all],
        "deviazione_produzione": [float(v) for v in sd_all],
        "tasso_fp_default": float(glob_all),
        "tasso_fp_per_skill": tabella,
        "attributi": nomi,
        "pesi": [float(v) for v in w[:-1]],
        "bias": float(w[-1]),
        "media": [float(v) for v in mu],
        "deviazione": [float(v) for v in sd],
        "soglia": soglia,
        "test": {k: (round(v, 4) if isinstance(v, float) else v)
                 for k, v in m_te.items()},
        "test_denylist_equa": {k: (round(v, 4) if isinstance(v, float) else v)
                               for k, v in m_deny.items()},
        "test_nessun_filtro": {k: (round(v, 4) if isinstance(v, float) else v)
                               for k, v in m_base.items()},
        "n_occupazioni": {"train": len(tr_occ), "val": len(va_occ), "test": len(te_occ)},
    }
    Path(args.out).write_text(json.dumps(modello, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\n  Modello salvato in {args.out}")


if __name__ == "__main__":
    main()
