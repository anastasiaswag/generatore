"""
prova_modello.py  —  SkillPath AI
==================================
Verifica che un encoder si carichi e produca embedding della forma attesa,
prima di spendere ore a costruire gli indici.

PERCHÉ
──────
`batch_parse_jobs_gt.py` cattura le eccezioni documento per documento e ne
registra solo il messaggio: un modello incompatibile produce quindi 810 righe
di errore identiche, senza traccia di stack e senza indicare dove il problema
sia nato. È accaduto con Alibaba-NLP/gte-multilingual-base, che ha fallito su
tutti gli annunci con «index ... is out of bounds for dimension 0 with size
47» — un messaggio che non dice nulla su cosa fosse andato storto.

Questo script fa il minimo indispensabile e stampa tutto: carica il modello,
codifica tre frasi, controlla la forma del risultato, costruisce un indice
giocattolo e ci esegue una ricerca. Dura meno di un minuto e dice subito se
vale la pena procedere.

COSA CI SI ASPETTA
──────────────────
`encode` di N frasi deve restituire un tensore di forma (N, D), con D la
dimensione dell'encoder, e i vettori devono essere normalizzati. Se il numero
di righe non è N, il modello non sta aggregando i token in un vettore per
frase: restituisce embedding per token, e ogni ricerca per similarità che ne
segue è priva di senso. È il difetto più frequente dei modelli che richiedono
`trust_remote_code`, il cui codice di pooling non sempre è compatibile con la
versione di sentence-transformers installata.

Uso (dalla radice del progetto):
    python analysis/prova_modello.py --modello Alibaba-NLP/gte-multilingual-base
    python analysis/prova_modello.py --modello intfloat/multilingual-e5-base
"""

import argparse
import sys
import traceback
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

SEP = "─" * 74

FRASI = [
    "gestione di progetti software",
    "project management",
    "saldatura ad arco",
]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SkillPath AI — verifica di compatibilità di un encoder")
    ap.add_argument("--modello", required=True)
    args = ap.parse_args()

    print(f"\n{SEP}\n  PROVA DI COMPATIBILITÀ — {args.modello}\n{SEP}")

    # ── 1. Caricamento ───────────────────────────────────────────────────────
    print("\n  [1/4] Caricamento del modello…")
    try:
        from semantic_mapper import SemanticMapper
        mapper = SemanticMapper(args.modello)
        print(f"        caricato: {mapper.model_name}")
        print(f"        tag cache: {getattr(mapper, '_tag', '?')}")
    except Exception:
        print("\n  [FALLITO] Il modello non si carica.\n")
        traceback.print_exc()
        sys.exit(1)

    # ── 2. Codifica ──────────────────────────────────────────────────────────
    print(f"\n  [2/4] Codifica di {len(FRASI)} frasi…")
    try:
        emb = mapper.model.encode(FRASI, convert_to_tensor=True,
                                  normalize_embeddings=True)
    except Exception:
        print("\n  [FALLITO] La codifica solleva un'eccezione.\n")
        traceback.print_exc()
        sys.exit(1)

    forma = tuple(emb.shape)
    print(f"        forma del risultato: {forma}")
    print(f"        tipo: {emb.dtype}")

    if len(forma) != 2 or forma[0] != len(FRASI):
        print(f"\n  [INCOMPATIBILE] Attese {len(FRASI)} righe, ottenute "
              f"{forma[0] if forma else '?'}.")
        print("                  Il modello non aggrega i token in un vettore")
        print("                  per frase: restituisce embedding per token.")
        print("                  Ogni ricerca per similarità costruita su questi")
        print("                  vettori sarebbe priva di senso, ed è la causa")
        print("                  degli errori di indice fuori intervallo.")
        print("\n  Possibili rimedi, in ordine di costo:")
        print("    - aggiornare sentence-transformers e transformers;")
        print("    - verificare che il repository del modello includa un")
        print("      modulo di pooling compatibile;")
        print("    - rinunciare a questo encoder e dichiararlo in tesi.\n")
        sys.exit(2)

    # ── 2-bis. Determinismo ──────────────────────────────────────────────────
    # Un modello che a volte funziona e a volte no non è utilizzabile, e il
    # caso peggiore non è il crash: è l'esecuzione che riesce con dati
    # sbagliati. L'errore osservato con gte-multilingual-base nasceva da
    # memoria non inizializzata in `position_ids`; memoria non inizializzata
    # può contenere un numero enorme, e allora il programma si ferma, oppure
    # numeri piccoli, e allora prosegue con posizioni sbagliate producendo
    # embedding privi di senso ma dall'aspetto normale.
    # Codificare più volte le stesse frasi e confrontare i risultati distingue
    # i due casi.
    import torch
    print(f"\n  [2-bis] Determinismo: cinque codifiche delle stesse frasi…")
    stabile = True
    for tentativo in range(4):
        try:
            emb2 = mapper.model.encode(FRASI, convert_to_tensor=True,
                                       normalize_embeddings=True)
        except Exception as e:
            print(f"        tentativo {tentativo + 2}: ECCEZIONE — {e}")
            stabile = False
            continue
        if tuple(emb2.shape) != forma:
            print(f"        tentativo {tentativo + 2}: forma diversa "
                  f"{tuple(emb2.shape)}")
            stabile = False
            continue
        scarto = (emb2 - emb).abs().max().item()
        print(f"        tentativo {tentativo + 2}: scarto massimo {scarto:.2e}")
        if scarto > 1e-4:
            stabile = False

    if not stabile:
        print("\n  [INAFFIDABILE] Il modello non produce risultati stabili.")
        print("                 Non va usato: anche le esecuzioni che riescono")
        print("                 possono contenere valori sbagliati, e nulla")
        print("                 nell'output lo segnalerebbe.\n")
        sys.exit(3)
    print("        stabile su cinque esecuzioni.")

    # ── 3. Normalizzazione ───────────────────────────────────────────────────
    norme = torch.linalg.norm(emb, dim=1)
    print(f"\n  [3/4] Norme dei vettori: "
          f"{', '.join(f'{v:.4f}' for v in norme.tolist())}")
    if not torch.allclose(norme, torch.ones_like(norme), atol=1e-3):
        print("        [ATTENZIONE] I vettori non sono normalizzati: il prodotto")
        print("        scalare non coincide con il coseno e le soglie perdono")
        print("        significato.")

    # ── 4. Ricerca su un indice giocattolo ───────────────────────────────────
    print(f"\n  [4/4] Ricerca per similarità su un indice di prova…")
    try:
        from sentence_transformers import util
        db = mapper.model.encode(
            ["project management", "arc welding", "cucina professionale",
             "contabilità generale"],
            convert_to_tensor=True, normalize_embeddings=True)
        punteggi = util.cos_sim(emb, db)
        print(f"        forma della matrice punteggi: {tuple(punteggi.shape)}")
        migliori = punteggi.argmax(dim=1)
        for frase, idx, val in zip(FRASI, migliori.tolist(),
                                   punteggi.max(dim=1).values.tolist()):
            print(f"        «{frase}» → indice {idx}, similarità {val:.3f}")
    except Exception:
        print("\n  [FALLITO] La ricerca per similarità solleva un'eccezione.\n")
        traceback.print_exc()
        sys.exit(1)

    print(f"\n{SEP}")
    print("  Il modello è compatibile. Si può procedere alla costruzione")
    print("  degli indici, che è la parte costosa.")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
