"""
analisi_cv_reali.py  —  SkillPath AI
======================================
Analizza il parsing di curriculum reali, dove la ground truth non esiste.

CHE COSA SI PUÒ MISURARE SENZA GROUND TRUTH
───────────────────────────────────────────
Non precision, recall e F1: richiedono di sapere quali competenze siano
davvero presenti, e nessuno lo ha annotato. Si possono però misurare tre cose
che dicono se il parser regge, e che sul dataset sintetico non erano
osservabili perché lì i documenti erano costruiti per essere leggibili.

  1. IL SISTEMA FUNZIONA
     Quanti documenti producono un risultato, quante competenze per documento,
     se qualcuno ne produce zero. Un parser che fallisce silenziosamente su un
     terzo dei file non è utilizzabile, e sul sintetico non si sarebbe visto.

  2. LA SEGMENTAZIONE TIENE
     Il parser dei CV dipende dal riconoscimento delle intestazioni di sezione:
     è il suo vantaggio sul parser degli annunci ed è anche la sua fragilità.
     Sui CV sintetici le intestazioni erano generate da tre template noti; qui
     sono quelle che ciascuno ha scelto per sé. Se le sezioni non vengono
     riconosciute, i candidati finiscono nel posto sbagliato.

  3. GLI ERRORI SISTEMATICI
     Un'etichetta ESCO che compare in quasi tutti i curriculum è sospetta:
     quindici persone diverse difficilmente condividono la stessa competenza.
     È lo stesso ragionamento che sul parser degli annunci ha portato a
     scoprire `responsible` — 792 comparse in 792 documenti. Qui il campione è
     piccolo, quindi il segnale è debole, ma il metodo è quello.

Il confronto con i valori del dataset sintetico è la parte più informativa:
uno scostamento grande indica che il sintetico non rappresenta il reale, ed è
esattamente ciò che la tesi deve dichiarare.

Uso (dalla radice del progetto):
    python analysis/analisi_cv_reali.py --in outputs/cv_reali_results.json
    python analysis/analisi_cv_reali.py --in ... --dettaglio
"""

import argparse
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

# Su Windows la console usa UTF-8, ma quando l'output viene rediretto o passato
# in pipe Python ricade sulla codifica di sistema (cp1252), che non contiene i
# caratteri di riquadro usati qui: lo script muore con UnicodeEncodeError prima
# ancora di fare il suo lavoro. Si forza UTF-8 sull'uscita.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
SINTETICI = BASE_DIR / "outputs" / "cv_batch_results.json"

SEP = "─" * 74

# Riferimenti misurati sugli 810 CV sintetici (docs/risultati_sessione.md)
RIF_SKILL_MEDIE = 13.95
RIF_PRECISION = 0.907


def carica(p: Path) -> list:
    if not p.exists():
        print(f"[ERRORE] File non trovato: {p}")
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def estrai(e: dict) -> dict:
    """Riduce un risultato del parser ai soli indicatori che interessano."""
    cv = e.get("cv", {})
    sk = cv.get("skills") or {}
    matches = sk.get("all_matches") or []
    sez = (e.get("debug") or {}).get("section_sizes") or {}
    return {
        "id": e.get("cv_id", "?"),
        "n_skill": len(matches),
        "punteggi": [m.get("score", 0) for m in matches],
        "etichette": [(m.get("id"), m.get("label", "")) for m in matches],
        "n_lingue": len(cv.get("languages") or []),
        "n_cert": len(cv.get("certifications") or []),
        "n_esperienze": len(cv.get("work_experience") or []),
        "ruolo": ((cv.get("work_experience") or [{}])[0]).get("label", "—"),
        "seniority": (cv.get("persona") or {}).get("seniority", "—"),
        "anni": (cv.get("persona") or {}).get("years_of_experience"),
        "anni_fonte": (cv.get("persona") or {}).get("years_source", "?"),
        "titolo_studio": bool((cv.get("education") or {}).get("degree_id")),
        "sezioni": sez,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — analisi qualitativa su curriculum reali")
    ap.add_argument("--in", dest="inp",
                    default=str(BASE_DIR / "outputs" / "cv_reali_results.json"))
    ap.add_argument("--dettaglio", action="store_true",
                    help="Elenca tutte le competenze estratte da ogni CV")
    ap.add_argument("--soglia-sospetto", type=float, default=0.30,
                    help="Quota di CV oltre la quale un'etichetta è sospetta "
                         "(default 0.30)")
    args = ap.parse_args()

    dati = [estrai(e) for e in carica(Path(args.inp))]
    n = len(dati)
    if not n:
        print("[ERRORE] Nessun risultato nel file.")
        sys.exit(1)

    # ══ 1. Funzionamento ═════════════════════════════════════════════════════
    print(f"\n{SEP}\n  1. IL SISTEMA FUNZIONA?\n{SEP}")
    skill_per_cv = [d["n_skill"] for d in dati]
    vuoti = [d for d in dati if d["n_skill"] == 0]
    poveri = [d for d in dati if 0 < d["n_skill"] < 4]

    print(f"  documenti parsati            {n}")
    print(f"  competenze estratte, media   {st.mean(skill_per_cv):.1f}"
          f"   (sintetici: {RIF_SKILL_MEDIE})")
    print(f"  competenze estratte, mediana {st.median(skill_per_cv):.1f}")
    print(f"  minimo / massimo             {min(skill_per_cv)} / {max(skill_per_cv)}")
    print(f"  documenti con zero competenze {len(vuoti)}")
    print(f"  documenti con meno di 4       {len(poveri)}")

    scarto = st.mean(skill_per_cv) - RIF_SKILL_MEDIE
    print()
    if vuoti:
        print(f"  [ATTENZIONE] {len(vuoti)} documenti non hanno prodotto nulla:")
        for d in vuoti:
            print(f"               {d['id']}")
        print("               Verificare a mano se il testo viene estratto.")
    if abs(scarto) > 5:
        verso = "più" if scarto > 0 else "meno"
        print(f"  [NOTA] Il parser estrae in media {abs(scarto):.1f} competenze "
              f"in {verso}\n         rispetto ai CV sintetici. Uno scostamento "
              f"di questa entità\n         indica che i due insiemi non sono "
              f"comparabili, e va detto.")

    # ══ 2. Segmentazione ═════════════════════════════════════════════════════
    print(f"\n{SEP}\n  2. LA SEGMENTAZIONE IN SEZIONI TIENE?\n{SEP}")
    nomi_sez = ["skills", "experience", "education", "languages",
                "certifications", "summary"]
    print(f"  {'sezione':<16}{'riconosciuta in':>18}{'righe medie':>14}")
    print(f"  {'-'*48}")
    for s in nomi_sez:
        presenti = [d["sezioni"].get(s, 0) for d in dati]
        con = sum(1 for v in presenti if v > 0)
        media = st.mean(presenti) if presenti else 0
        print(f"  {s:<16}{con:>10}/{n:<7}{media:>14.1f}")

    senza_skill = [d for d in dati if d["sezioni"].get("skills", 0) == 0]
    print()
    if senza_skill:
        print(f"  In {len(senza_skill)} documenti su {n} la sezione delle "
              f"competenze non è stata\n  riconosciuta. È la fragilità nota del "
              f"parser: senza intestazione\n  identificabile i candidati "
              f"finiscono nella sezione sbagliata.")
        for d in senza_skill:
            print(f"     {d['id']}  ({d['n_skill']} competenze estratte comunque)")
    else:
        print("  Tutte le sezioni delle competenze sono state riconosciute.")

    # ══ 3. Errori sistematici ════════════════════════════════════════════════
    print(f"\n{SEP}\n  3. ERRORI SISTEMATICI\n{SEP}")
    freq = Counter()
    for d in dati:
        for _, lab in set(d["etichette"]):
            freq[lab] += 1

    soglia = max(2, int(n * args.soglia_sospetto))
    sospette = [(lab, c) for lab, c in freq.most_common() if c >= soglia]

    print(f"  Etichette presenti in almeno {soglia} curriculum su {n}:\n")
    if sospette:
        print(f"  {'etichetta':<50}{'in quanti CV':>14}")
        print(f"  {'-'*64}")
        for lab, c in sospette:
            print(f"  {lab[:48]:<50}{c:>10}/{n}")
        print()
        print("  Da leggere a mano: alcune sono competenze davvero comuni")
        print("  (uso di un foglio di calcolo, comunicazione), altre sono")
        print("  etichette-calamita. Solo l'ispezione distingue i due casi.")
    else:
        print("  Nessuna etichetta ricorre con frequenza sospetta.")

    # ══ 4. Punteggi ══════════════════════════════════════════════════════════
    tutti = [s for d in dati for s in d["punteggi"]]
    if tutti:
        print(f"\n{SEP}\n  4. DISTRIBUZIONE DEI PUNTEGGI\n{SEP}")
        ordinati = sorted(tutti)
        print(f"  match totali {len(tutti)}   mediana {st.median(tutti):.3f}   "
              f"min {min(tutti):.3f}   max {max(tutti):.3f}")
        print(f"  decimo percentile {ordinati[len(ordinati)//10]:.3f}   "
              f"novantesimo {ordinati[9*len(ordinati)//10]:.3f}")
        print()
        print("  Confronto utile: se la mediana è più bassa che sul sintetico,")
        print("  i CV reali sono lessicalmente più distanti da ESCO — che è")
        print("  l'ipotesi da verificare in tesi.")

    # ══ 5. Il resto della pipeline ═══════════════════════════════════════════
    print(f"\n{SEP}\n  5. GLI ALTRI PERCORSI\n{SEP}")
    print(f"  {'indicatore':<32}{'documenti':>12}{'media':>10}")
    print(f"  {'-'*54}")
    for etichetta, chiave in (("lingue rilevate", "n_lingue"),
                              ("certificazioni", "n_cert"),
                              ("esperienze lavorative", "n_esperienze")):
        vals = [d[chiave] for d in dati]
        print(f"  {etichetta:<32}{sum(1 for v in vals if v):>8}/{n:<3}"
              f"{st.mean(vals):>10.1f}")
    con_titolo = sum(1 for d in dati if d["titolo_studio"])
    print(f"  {'titolo di studio':<32}{con_titolo:>8}/{n:<3}{'':>10}")

    sen = Counter(d["seniority"] for d in dati)
    print(f"\n  livello stimato: " +
          "  ".join(f"{k} {v}" for k, v in sen.most_common()))

    # Provenienza degli anni di esperienza. Un numero ricavato dal ripiego non
    # corrisponde ad alcun periodo dichiarato: ha l'aspetto di una misura ma è
    # una congettura, e va contato a parte.
    fonti = Counter(d["anni_fonte"] for d in dati)
    if fonti and set(fonti) != {"?"}:
        etichette = {"intervalli": "da periodi dichiarati",
                     "ripiego": "congettura da anno min-max",
                     "assente": "nessuna data riconosciuta",
                     "?": "campo non presente"}
        print(f"\n  provenienza degli anni di esperienza:")
        for k, v in fonti.most_common():
            print(f"     {etichette.get(k, k):<32}{v:>3}/{n}")
        if fonti.get("ripiego"):
            print(f"\n  I {fonti['ripiego']} valori da ripiego non vanno usati "
                  f"come misura:\n  vanno riportati separatamente o trattati "
                  f"come ignoti.")

    # ══ 6. Tabella per documento ═════════════════════════════════════════════
    print(f"\n{SEP}\n  6. RIEPILOGO PER DOCUMENTO\n{SEP}")
    print(f"  {'id':<16}{'skill':>7}{'ling':>6}{'cert':>6}{'esp':>5}"
          f"{'liv':>8}  ruolo riconosciuto")
    print(f"  {'-'*72}")
    for d in sorted(dati, key=lambda x: x["n_skill"]):
        print(f"  {d['id'][:15]:<16}{d['n_skill']:>7}{d['n_lingue']:>6}"
              f"{d['n_cert']:>6}{d['n_esperienze']:>5}{str(d['seniority']):>8}"
              f"  {d['ruolo'][:30]}")

    # ══ 7. Dettaglio ═════════════════════════════════════════════════════════
    if args.dettaglio:
        print(f"\n{SEP}\n  7. COMPETENZE ESTRATTE, DOCUMENTO PER DOCUMENTO\n{SEP}")
        print("  Da leggere segnando accanto a ciascuna: corretta, sbagliata,")
        print("  o dubbia. È questa lettura a produrre il dato qualitativo:")
        print("  lo script non può sostituirla.\n")
        for d in dati:
            print(f"  ── {d['id']}  ({d['n_skill']} competenze)")
            for _, lab in sorted(set(d["etichette"])):
                print(f"       {lab}")
            print()

    print(f"\n{SEP}")
    print("  Questi numeri dicono se il parser REGGE, non quanto sia accurato.")
    print("  L'accuratezza su dati reali richiede annotazione manuale: con 15")
    print("  documenti è fattibile, ed è il passo che dà alla tesi il suo")
    print("  risultato più difendibile.")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
