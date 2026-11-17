# SkillPath AI — Log sessione di lavoro (17 luglio 2026)

Riepilogo cronologico delle attività svolte in questa sessione sul progetto, da usare come nota di supporto per l'incontro con il relatore.

---

## 1. Pulizia della cartella di progetto

Analizzati tutti i file nella cartella `generatore/` per distinguere codice/dati attivi da residui di sviluppo. Rimossi:

- `skillpath/`, `skillpathAI/` — due cloni git vuoti (solo `.git`, nessun sorgente), residui di esperimenti
- `__pycache__/` — bytecode rigenerabile
- `test.py`, `debug_esco_api.py`, `inspect_match.py`, `test_integration.py` — script di debug one-off superati dal refactor verso `main_parser.py` e il dataset ESCO italiano
- `offerta2.txt` — file vuoto

**Scoperta rilevante:** `cv_parser.py`, citato nello stack del progetto, non esiste più come file separato — è stato rinominato/fuso in `main_parser.py` (classe `MainParser`). Il progetto usa due parser paralleli: `job_parser.py` (classe `JobParser`, annunci) e `main_parser.py` (classe `MainParser`, CV).

## 2. Riorganizzazione in cartelle

Struttura precedente: ~35 file sciolti nella radice. Nuova struttura:

| Cartella | Contenuto |
|---|---|
| `src/` | codice core (parser, matching engine, semantic mapper, build script) |
| `analysis/` | `analisi_parser.py`, `estrai_fn.py` |
| `tests/` | script di batch/test end-to-end |
| `outputs/` | tutti i JSON/CSV generati dalle run |
| `samples/` | CV e annunci di prova |
| `config/` | `weights.json`, `course_index.json`, `Coursera.csv` |
| `docs/` | relazione, documenti di visione |
| `dataset/`, `job_descriptions/` | invariati |

Aggiornati manualmente `BASE_DIR`, `sys.path.insert` e i default degli argomenti CLI in tutti i 19 script Python spostati, così da continuare a risolvere correttamente i path verso `dataset/`, `config/`, `samples/`, `outputs/` lanciando i comandi dalla radice del progetto.

**Incidenti tecnici durante la riorganizzazione** (causati da un mount di rete instabile, non da errori di logica):
- corruzione dell'indice git durante un `git mv` → risolta con `git reset` (indice ricostruito da HEAD)
- troncamento silenzioso di 2 file durante la scrittura (`analisi_parser.py`, `batch_parse_cvs.py`) → rilevato con `py_compile` su tutti gli script, corretto riscrivendo i file
- azzeramento completo di `outputs/batch_job_results.json` (1000 annunci parsati, persi) → rilevato, verificato che il resto del progetto fosse intatto, rigenerato rilanciando `tests/batch_test_job_parser.py` (i 1000 file sorgente in `job_descriptions/` erano intatti, nessuna perdita di dati sorgente)

## 3. Frontend Streamlit

Creato `app/streamlit_app.py` su richiesta del relatore ("anche brutto va bene"). Scelto Streamlit per riuso diretto dei moduli in `src/` senza dover scrivere un layer API.

**Tre modalità:**
1. **1 CV ↔ 1 annuncio** — confronto singolo con punteggio, skill coperte/mancanti, roadmap corsi
2. **1 annuncio ↔ più CV** (ranking candidati, scenario recruiter) — equivalente UI di `tests/test_job_to_candidates.py`
3. **1 CV ↔ più annunci** (ranking annunci, scenario candidato) — equivalente UI di `tests/test_end_to_end.py`

Per i confronti multipli: possibilità di usare il dataset sintetico già elaborato (istantaneo, nessun re-parsing) oppure caricare più file reali dal vivo. Aggiunta anche la scelta di un **singolo CV direttamente dal dataset sintetico** (810 CV già pronti), utile per demo rapide senza dover caricare un file reale.

Aggiunti: theming leggero (`.streamlit/config.toml`), `requirements.txt` (non esisteva nel progetto), gestione robusta di file JSON corrotti (avviso invece di crash).

## 4. Debug import lento

Segnalato blocco apparente all'avvio di `job_parser.py`: non un bug, ma il tempo di import di `scipy`/`scikit-learn` (dipendenza di `sentence-transformers`), che su Windows può richiedere alcuni minuti alla prima esecuzione. Non ancora verificato a fondo se il problema persiste sistematicamente — da tenere d'occhio.

---

## Stato attuale — numeri disponibili per il relatore

| File | Contenuto | Data |
|---|---|---|
| `outputs/analisi_risultati.json` | Precision 0.865 / Recall 0.86 / F1 0.857 (media su CV valutati, 3 template) | 25 maggio |
| `outputs/batch_job_stats.json` | 1000/1000 annunci elaborati, 0 errori, avg 3.33 skill richieste/annuncio, avg occupation score 0.856 | 13 luglio (rigenerato oggi) |
| `outputs/fn_analysis.json` | Classifica delle skill più frequentemente mancate dal parser CV | 4 maggio |
| `outputs/end_to_end_results.json`, `outputs/job_to_candidates_results.json` | Run complete della pipeline (CV→job e job→CV) | 25 maggio |

**⚠️ Da verificare prima dell'incontro:** `docs/relazione_progetto.md` (sezione 9) riporta Precision ~0.92 / Recall ~0.55 / F1 ~0.69, numeri diversi da quelli in `outputs/analisi_risultati.json` (0.865/0.86/0.857). Il file del report è del 12 maggio, l'analisi con i numeri migliori è del 25 maggio — il parser è stato probabilmente migliorato nel frattempo (coerente con l'azione "dizionario supplementare" suggerita nella sezione 10 del report) ma il testo del report non è stato aggiornato di conseguenza. Consigliato rilanciare `python analysis/analisi_parser.py --section gt` poco prima dell'incontro per avere numeri certi e freschi, e allineare il testo della relazione ai risultati attuali.
