"""
ricostruisci_denylist.py  —  SkillPath AI
==========================================
Ricostruisce _GENERIC_ATTRACTOR_IDS (la lista di etichette ESCO troppo
generiche per essere assegnate in modo affidabile) a partire dagli errori
del parser, con validazione su holdout.

PERCHÉ RIFARLA
──────────────
La lista attualmente nel codice (232 ID) è stata ricavata quando il
segmentatore produceva ancora candidati di una parola sola dalla prosa
("responsible", "seeking", "able"…). Eliminata quella sorgente di rumore, la
distribuzione degli errori è cambiata: 137 dei 232 ID non compaiono più mai,
cioè il 59% della lista è peso morto che sopravvive solo perché scritto nel
sorgente.

Rifarla sulla distribuzione attuale produce una lista più corta, più
giustificabile e — soprattutto — che non porta con sé decisioni prese su un
comportamento del parser che non esiste più.

METODO
──────
Per ogni etichetta si contano le volte che il parser la assegna correttamente
(TP) e quelle in cui sbaglia (FP). Finiscono in denylist le etichette con
abbastanza occorrenze da non essere un caso e con una quota di errori così
alta da renderle inutilizzabili.

LIMITE, da dichiarare in tesi
─────────────────────────────
Questo procedimento USA la ground truth: guarda quali predizioni erano
sbagliate. È quindi supervisionato e specifico del dataset su cui è costruito
— l'esatto contrario della correzione nel segmentatore, che agisce a monte e
non consulta le etichette.
Per questo lo script calcola la lista su metà annunci e ne misura l'effetto
sull'altra metà, mai vista: se il guadagno regge sull'holdout, l'effetto
generalizza almeno all'interno di questo dominio. Su annunci reali andrebbe
comunque rimisurato.

USO
───
    python analysis/ricostruisci_denylist.py
    python analysis/ricostruisci_denylist.py --min-occorrenze 8 --min-errore 0.80

Lo script NON modifica job_parser.py: stampa la lista e la salva in
outputs/denylist_nuova.py, da incollare a mano dopo aver letto i numeri.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IN_FILE = BASE_DIR / "outputs" / "ab_multiword_nodeny.json"
OUT_FILE = BASE_DIR / "outputs" / "denylist_nuova.py"


def skill_ids(entry: dict) -> set:
    s = entry.get("skills", {})
    return set(s.get("required_ids", []) + s.get("preferred_ids", []))


def gt_ids(entry: dict) -> set:
    ex = entry.get("expected_skills", {})
    return set(ex.get("required_ids", []) + ex.get("preferred_ids", []))


def costruisci(annunci: list, min_occ: int, min_err: float) -> tuple[set, dict]:
    """Conta TP/FP per etichetta e seleziona quelle da escludere."""
    stat = defaultdict(lambda: [0, 0])       # id -> [fp, tp]
    etichette = {}
    for e in annunci:
        gt = gt_ids(e)
        trovate = skill_ids(e)
        for m in e.get("skills", {}).get("all_matches", []):
            if m["id"] not in trovate:
                continue
            etichette[m["id"]] = m.get("label", "")
            stat[m["id"]][1 if m["id"] in gt else 0] += 1

    lista = {
        sid for sid, (fp, tp) in stat.items()
        if (fp + tp) >= min_occ and fp / (fp + tp) >= min_err
    }
    return lista, etichette


def metriche(annunci: list, escludi: set) -> tuple:
    P = R = F = 0.0
    n = tp_t = fp_t = 0
    for e in annunci:
        gt = gt_ids(e)
        found = {i for i in skill_ids(e) if i not in escludi}
        if not gt and not found:
            continue
        n += 1
        a, b, c = len(found & gt), len(found - gt), len(gt - found)
        tp_t += a
        fp_t += b
        p = a / (a + b) if a + b else 0.0
        r = a / (a + c) if a + c else 0.0
        P += p
        R += r
        F += (2 * p * r / (p + r)) if p + r else 0.0
    return P / n, R / n, F / n, tp_t, fp_t


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — ricostruzione della denylist con validazione holdout"
    )
    ap.add_argument("--in", dest="in_file", default=str(IN_FILE),
                    help="Output del parser SENZA denylist")
    ap.add_argument("--min-occorrenze", type=int, default=10,
                    help="Occorrenze minime perché un'etichetta sia valutabile")
    ap.add_argument("--min-errore", type=float, default=0.85,
                    help="Quota minima di falsi positivi per l'esclusione")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    percorso = Path(args.in_file)
    if not percorso.exists():
        print(f"[ERRORE] File non trovato: {percorso}")
        print("  Genera prima l'output senza denylist:")
        print("  python tests/batch_parse_jobs_gt.py --no-denylist "
              "--out outputs/ab_multiword_nodeny.json")
        return

    annunci = json.loads(percorso.read_text(encoding="utf-8"))
    print(f"\n  Annunci caricati: {len(annunci)}")

    # ── Validazione su holdout ──────────────────────────────────────────────
    rng = random.Random(args.seed)
    mescolati = annunci[:]
    rng.shuffle(mescolati)
    meta = len(mescolati) // 2
    train, holdout = mescolati[:meta], mescolati[meta:]

    lista_train, _ = costruisci(train, args.min_occorrenze, args.min_errore)

    print(f"\n{'═'*70}")
    print("  VALIDAZIONE — lista costruita sul train, misurata sull'holdout")
    print(f"{'═'*70}")
    print(f"  train {len(train)} annunci → {len(lista_train)} etichette escluse")
    print(f"  holdout {len(holdout)} annunci (mai visti in costruzione)\n")
    print(f"  {'':<22}{'Prec':>8}{'Rec':>8}{'F1':>8}{'FP':>8}")
    print(f"  {'-'*54}")
    p0, r0, f0, _, fp0 = metriche(holdout, set())
    p1, r1, f1, _, fp1 = metriche(holdout, lista_train)
    print(f"  {'senza denylist':<22}{p0:>8.3f}{r0:>8.3f}{f0:>8.3f}{fp0:>8}")
    print(f"  {'con  denylist':<22}{p1:>8.3f}{r1:>8.3f}{f1:>8.3f}{fp1:>8}")
    print(f"  {'differenza':<22}{p1-p0:>+8.3f}{r1-r0:>+8.3f}{f1-f0:>+8.3f}{fp1-fp0:>+8}")

    if f1 <= f0:
        print("\n  ATTENZIONE: sull'holdout la denylist NON migliora l'F1.")
        print("  Non generalizza: meglio non adottarla.")

    # ── Sensibilità ai parametri ────────────────────────────────────────────
    print(f"\n{'═'*70}")
    print("  SENSIBILITÀ (lista dal train, effetto sull'holdout)")
    print(f"{'═'*70}")
    print(f"  {'occ':>5}{'errore':>9}{'n.etich':>9}{'Prec':>8}{'Rec':>8}{'F1':>8}")
    print(f"  {'-'*47}")
    for occ in (5, 10, 20):
        for err in (0.75, 0.85, 0.95):
            L, _ = costruisci(train, occ, err)
            p, r, f, _, _ = metriche(holdout, L)
            print(f"  {occ:>5}{err:>9.2f}{len(L):>9}{p:>8.3f}{r:>8.3f}{f:>8.3f}")

    # ── Lista definitiva su tutti gli annunci ───────────────────────────────
    lista, etichette = costruisci(annunci, args.min_occorrenze, args.min_errore)
    print(f"\n{'═'*70}")
    print(f"  LISTA DEFINITIVA — {len(lista)} etichette (su tutti gli annunci)")
    print(f"{'═'*70}")

    stat = defaultdict(lambda: [0, 0])
    for e in annunci:
        gt = gt_ids(e)
        trovate = skill_ids(e)
        for m in e.get("skills", {}).get("all_matches", []):
            if m["id"] in trovate:
                stat[m["id"]][1 if m["id"] in gt else 0] += 1

    ordinate = sorted(lista, key=lambda i: -stat[i][0])
    print(f"\n  {'FP':>6}{'TP':>5}  etichetta")
    print(f"  {'-'*60}")
    for sid in ordinate[:20]:
        fp, tp = stat[sid]
        print(f"  {fp:>6}{tp:>5}  {etichette.get(sid,'?')[:48]}")
    if len(ordinate) > 20:
        print(f"  … e altre {len(ordinate)-20}")

    righe = ["_GENERIC_ATTRACTOR_IDS = {"]
    for i in range(0, len(ordinate), 3):
        gruppo = ", ".join(f'"{s}"' for s in ordinate[i:i+3])
        righe.append(f"    {gruppo},")
    righe.append("}")
    OUT_FILE.write_text("\n".join(righe) + "\n", encoding="utf-8")

    print(f"\n  Snippet salvato in {OUT_FILE}")
    print("  Da incollare in src/job_parser.py SOLO se i numeri "
          "sull'holdout convincono.")


if __name__ == "__main__":
    main()
