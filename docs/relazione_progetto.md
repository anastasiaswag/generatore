# SkillPath AI — Relazione tecnica del progetto
## Tirocinio di laurea triennale in Ingegneria Informatica

---

## Indice

1. [Obiettivo del progetto](#1-obiettivo-del-progetto)
2. [Struttura generale del sistema](#2-struttura-generale-del-sistema)
3. [Il dataset ESCO — mappatura e caricamento](#3-il-dataset-esco--mappatura-e-caricamento)
4. [Creazione del dataset sintetico](#4-creazione-del-dataset-sintetico)
5. [Il parser CV — architettura e logica](#5-il-parser-cv--architettura-e-logica)
6. [Il parser Job Description](#6-il-parser-job-description)
7. [Il Matching Engine](#7-il-matching-engine)
8. [Le librerie utilizzate](#8-le-librerie-utilizzate)
9. [Valutazione delle prestazioni del CV parser](#9-valutazione-delle-prestazioni-del-cv-parser)
   - 9-bis. [Valutazione del parser degli annunci](#9-bis-valutazione-del-parser-degli-annunci)
   - 9-ter. [Valutazione del matching engine](#9-ter-valutazione-del-matching-engine)
   - 9-quater. [Valutazione del raccomandatore di corsi](#9-quater-valutazione-del-raccomandatore-di-corsi)
   - 9-quinquies. [Il punteggio è una misura o solo un ordinamento?](#9-quinquies-il-punteggio-è-una-misura-o-solo-un-ordinamento)
10. [Problemi aperti e sviluppi futuri](#10-problemi-aperti-e-sviluppi-futuri)

---

## 1. Obiettivo del progetto

SkillPath AI è un sistema backend per il matching tra candidati e offerte di lavoro. Il sistema legge un curriculum vitae in formato PDF o DOCX, produce una struttura JSON con le competenze del candidato mappate sull'ontologia europea ESCO, legge un'offerta di lavoro in qualsiasi formato testuale e calcola un punteggio di compatibilità corredato da una lista di skill mancanti ordinata per priorità di apprendimento.

Il progetto segue lo **Scenario 2** definito con il relatore: il sistema non confronta il candidato direttamente con le occupazioni ESCO, ma parsa prima la job description reale (con i requisiti espliciti dell'azienda) e poi confronta semanticamente i due profili estratti.

Il progetto nasce da un problema pratico: non erano disponibili abbastanza CV reali su cui lavorare. Per questo motivo la prima parte del lavoro è consistita nel costruire un dataset sintetico di 810 curriculum verosimili, generati artificialmente con le skill già annotate secondo gli ID ESCO, da usare per sviluppare e valutare il parser.

---

## 2. Struttura generale del sistema

Il sistema è composto da sei moduli principali:

**`generate_dataset.py`** — genera i CV sintetici usando il modello Llama 3.3 70B (via API Groq), partendo dalle occupazioni ESCO e dalle skill associate. Ogni CV ha un `ground_truth` con gli ID ESCO esatti delle skill inserite.

**`render_cvs.py`** — converte i CV sintetici (strutture JSON) in file PDF realistici usando tre template grafici diversi (Classic, Europass, Modern), necessari per testare la robustezza del parser su layout eterogenei.

**`main_parser.py`** — il parser CV: legge un PDF o DOCX, lo segmenta per sezione, estrae candidati skill e li confronta semanticamente con il database ESCO usando embedding E5. Restituisce un JSON strutturato con skill, occupazione, istruzione, lingue e anni di esperienza.

**`job_parser.py`** — il parser per le offerte di lavoro: legge un file PDF, DOCX o testo grezzo e produce un profilo JSON con l'occupazione target e le skill richieste (distinte in required e preferred), senza dipendere da una struttura rigida dell'annuncio.

**`matching_engine.py`** — confronta i due profili JSON (CV e job) e produce un match score, una lista di skill coperte (per ID esatto o per similarità semantica) e uno skill gap ordinato per priorità di apprendimento.

**`semantic_mapper.py`** — modulo condiviso che gestisce il caricamento del modello E5, la costruzione degli indici di embedding e la ricerca per cosine similarity. Usato sia dal CV parser che dal job parser.

**`skill_graph.py`** — ordina lo skill gap in una roadmap di apprendimento combinando frequenza fra le occupazioni, `reuse_level` e prossimità concettuale. La prossimità viene dalla gerarchia ufficiale ESCO quando `dataset/source/skill_relations.json` è presente, altrimenti dalla co-occorrenza ricostruita; la fonte usata è dichiarata in ogni voce restituita.

**`esco_taxonomy.py`** — similarità di Wu-Palmer sulla gerarchia ufficiale ESCO. Quattro radici distinte, profondità calcolata come cammino più lungo (necessario: in ESCO un concetto può essere più generale di un altro senza stargli sopra di un livello).

**`build_skill_relations.py`** — converte i due CSV ufficiali delle relazioni fra competenze nel formato del progetto, verificando che gli identificativi coincidano con il dataset locale.

Il flusso completo del sistema è:

```
PDF/DOCX candidato  →  main_parser.py   →  cv_profile.json   ─┐
                                                                ├→  matching_engine.py  →  match_result.json
PDF/TXT job desc    →  job_parser.py    →  job_profile.json   ─┘
                                          (occupation + skills required/preferred)
```

---

## 3. Il dataset ESCO — mappatura e caricamento

### Cos'è ESCO

ESCO è un'ontologia pubblicata dalla Commissione Europea che classifica occupazioni e competenze in modo standardizzato e multilingue. Contiene:

- **3.039 occupazioni** (es. "software developer", "civil engineer"), ciascuna con UUID univoco e classificazione ISCO-08
- **13.939 skill** con label primaria e numerose etichette alternative (`alt_labels`)
- **Relazioni occupazione-skill**: per ogni occupazione, un insieme di skill "essential" e "optional"

### I file JSON del progetto

| File | Entries | Dimensione |
|------|---------|------------|
| `dataset/source/occupations.json` | 3.039 | 3,6 MB |
| `dataset/source/skills.json` | 13.939 | 11 MB |
| `dataset/source/occupation_skill_relations.json` | 3.039 | 6 MB |
| `dataset/supplementary/degree_programs.json` | 57 | 14 KB |
| `dataset/supplementary/language_levels.json` | 84 | 37 KB |
| `dataset/supplementary/certifications.json` | 45 | 13 KB |

La presenza delle `alt_labels` è importante: il semantic mapper le indicizza tutte, portando il numero totale di etichette per le competenze a **98.847** (13.939 denominazioni principali + 84.908 alternative), di cui 98.318 distinte. Le occupazioni ne contano altre 19.201. L'indice è inoltre bilingue, quindi ogni etichetta compare nella versione italiana e in quella inglese. Questo aumenta la probabilità di trovare un match anche quando il candidato usa una formulazione diversa dalla label principale.

### Come viene usato ESCO

Il parser non usa ESCO come dizionario (ricerca esatta per stringa), ma come **spazio di embedding**: le label ESCO vengono convertite in vettori numerici dal modello E5, e lo stesso viene fatto per le frasi estratte dal CV o dall'annuncio. Il match avviene confrontando la vicinanza geometrica nello spazio vettoriale, non la corrispondenza testuale letterale.

---

## 4. Creazione del dataset sintetico

### Il problema di partenza

Il parser ha bisogno di curriculum annotati per essere sviluppato e valutato. Per questioni di privacy e disponibilità, non erano presenti abbastanza CV reali. La soluzione è stata generare CV sintetici ma verosimili, con una caratteristica fondamentale: le skill presenti in ogni CV sono già annotate con i loro ID ESCO esatti, permettendo di valutare oggettivamente le prestazioni del parser.

### Selezione delle occupazioni

Sono state selezionate 135 occupazioni rappresentative del mercato del lavoro italiano dalle 3.039 disponibili in ESCO, distribuite proporzionalmente sulle 9 macro-categorie ISCO (circa 15 per categoria).

Ogni CV include un sottoinsieme casuale delle skill ESCO dell'occupazione, con una percentuale di copertura che dipende dalla seniority:

- **Junior**: copre il 35–55% delle skill essential
- **Mid**: copre il 55–75%
- **Senior**: copre il 75–92%

### Generazione tramite LLM

Per ogni combinazione occupazione-seniority viene chiamato **Llama 3.3 70B** (via API Groq) con un prompt che chiede di generare il testo realistico di un CV italiano, incorporando naturalmente le skill ESCO selezionate.

Configurazione finale del dataset:

- **810 CV sintetici totali** (135 occupazioni × 6 CV ciascuna)
- **Bilanciamento perfetto**: 270 junior, 270 mid, 270 senior
- Media di **14,5 skill per CV** (min 5, max 60)
- Ground truth con ID ESCO esatti per ogni CV

### Rendering in PDF (render_cvs.py)

I CV sintetici vengono convertiti in PDF realistici usando **ReportLab** con tre template grafici:

1. **Classic**: colonna singola, intestazioni capitalizzate italiane ("Esperienza professionale", "Competenze tecniche")
2. **Europass**: ispirato al formato europeo standard, layout a due colonne con righe "Titolo — Azienda — 2020–2024"
3. **Modern**: intestazioni in maiuscolo precedute dal simbolo ▸ ("▸ EXPERIENCE", "▸ SKILLS")

I tre template simulano la variabilità dei CV reali, necessaria per testare la robustezza del parser su layout eterogenei. Sono stati renderizzati **810 CV** (270 per template), uno per ogni CV sintetico.

---

## 5. Il parser CV — architettura e logica

### Pipeline generale

```
PDF / DOCX
    ↓
[FASE 1] Estrazione testo     →  lista di righe pulite (PyMuPDF / python-docx)
    ↓
[FASE 2] Segmentazione        →  blocchi per sezione (experience, education, skills, ...)
    ↓
[FASE 3] Filtro rumore        →  elimina righe troppo corte, sole date, senza lettere
    ↓
[FASE 4] Match semantico      →  skill, occupazione, istruzione, lingue, certificazioni
    ↓
[FASE 5] Essential/Optional   →  classifica le skill tramite relazioni ESCO
    ↓
[FASE 6] JSON output          →  struttura pronta per il matching_engine
```

### Fase 1 — Estrazione del testo

Il modulo `pdf_extractor.py` usa:

- **PyMuPDF (fitz)** per i PDF: legge ogni pagina e restituisce il testo come lista di righe
- **python-docx** per i DOCX: scorre paragrafi e celle delle tabelle (necessario per il template Europass che usa tabelle a due colonne)

PyMuPDF ha un problema con alcuni font: il carattere ▸ (U+25B8) viene estratto come "I" maiuscola. Questo viene gestito nella fase di rilevamento delle intestazioni.

### Fase 2 — Segmentazione per sezione

Il parser scansiona le righe cercando intestazioni di sezione. Le sezioni riconosciute sono: `experience`, `education`, `skills`, `languages`, `certifications`. Le righe prima della prima intestazione vanno nella sezione `summary`.

Il rilevamento funziona su due percorsi paralleli:

**Percorso A — Header in MAIUSCOLO** (template modern): la riga viene pulita dai simboli iniziali, poi confrontata con un dizionario precompilato in maiuscolo.

**Percorso B — Header misto** (template classic ed europass): la riga viene normalizzata in minuscolo e confrontata con le keyword bilingui per ogni sezione. Il dizionario copre le varianti più comuni:

```
"Esperienza professionale" / "Work experience"
"Competenze tecniche"      / "Technical skills"
"Lingue straniere"         / "Languages"
```

### Fase 4A — Match semantico delle skill

Il testo della sezione `skills` (più l'`experience`) viene prima normalizzato: le righe con elenchi comma-separated ("Python, SQL, Docker") vengono spezzate nei singoli token. I candidati vengono poi suddivisi in tre categorie e confrontati con soglie diverse:

- **Parole singole**: threshold 0.85
- **Frasi multi-parola**: threshold 0.88
- **Acronimi e CamelCase** (es. "SAP", "AutoCAD"): threshold 0.85

Questa strategia a doppia soglia è necessaria perché le parole singole sono più ambigue (qualsiasi parola comune può avere alta similarità con label ESCO generiche) mentre le frasi multi-parola sono più specifiche e ammettono soglie più rilassate.

Il confronto avviene tramite **cosine similarity** tra vettori normalizzati:

```
sim(u, v) = u · v   (con ‖u‖ = ‖v‖ = 1)
```

I candidati vengono confrontati con tutte le etichette ESCO indicizzate: 98.847 per le competenze, contando denominazione principale e alternative. Per ogni candidato viene mantenuto solo il match con score massimo, se supera la soglia.

### Il modello di embedding: intfloat/multilingual-e5-base

Il progetto usa il modello **`intfloat/multilingual-e5-base`** (E5-base), scelto dopo sperimentazione iniziale con `paraphrase-multilingual-MiniLM-L12-v2`.

E5-base produce embedding a **768 dimensioni** ed è ottimizzato per il recupero semantico cross-linguale con una tecnica di instruction tuning: richiede prefissi specifici per distinguere le query dai documenti.

```python
# Documenti ESCO (database, indicizzati come "passage")
"passage: mechanical engineer"
"passage: use spreadsheets"

# Candidati estratti dal CV (trattati come "query")
"query: INGEGNERE MECCANICO"
"query: ottimo utilizzo di Excel"
```

Questo approccio è formalmente identico al **transfer learning zero-shot**: si usa un modello pre-addestrato su corpus multilingui senza alcun fine-tuning sul dominio specifico dei CV. La scelta è giustificata dal contesto del tirocinio (assenza di dati annotati per il fine-tuning) e dall'elevata qualità del retrieval cross-linguale di E5 su benchmark pubblici (BEIR, MIRACL).

### Filtri post-semantici

Dopo il match vengono applicati quattro filtri in cascata:

**Filtro 1 — Label troppo corte (≤ 4 caratteri)**: elimina acronimi ambigui come "R" o "VB". Elimina 285 label (0,3% del totale).

**Filtro 2 — Label con articolo iniziale**: rimuove frammenti di frase come "a cosmetics ingredient" o "the study of Earth's surface". Elimina 259 label (0,3%).

**Filtro 3 — Label task-oriented (verbi e gerundi)**: circa il 29% delle label ESCO descrivono attività ("manage musical staff", "perform toxicological studies") piuttosto che competenze nominali. Una regex compilata le riconosce dal verbo iniziale. Elimina 29.093 label (29,0%).

**Filtro 4 — Equipment terms**: label che contengono termini di attrezzatura fisica ("apparatus", "equipment", "machinery") vengono accettate solo se la parola appare letteralmente nel testo del CV. Questo previene falsi positivi come "office apparatus" che matcha semanticamente un CV con "Microsoft Office".

### Filtri pre-candidati

Prima di inviare i candidati al modello semantico, un filtro di qualità rimuove:

- Dati anagrafici ("nato a Gaeta", "residente in Roma")
- Frammenti di date isolate
- Parole singole minuscole (rumore da estrazione PDF riga-per-riga)
- Codici di province, sigle aziendali (SPA, SRL) e preposizioni articolate

### Calcolo degli anni di esperienza

Il parser cerca nella sezione `experience` tutti i range di date nei formati:

- Anni semplici: `2020 – 2023`
- Mesi numerici: `01/2020 – 06/2023`
- Mesi per esteso (IT e EN): `Gennaio 2020 – March 2023`
- Indicatori di "in corso": `present`, `oggi`, `attuale`, `in corso`

La seniority viene derivata dagli anni calcolati: < 2 anni = junior, 2–4 = mid, ≥ 5 = senior.

### Rilevamento delle lingue

Le lingue usano una strategia a due livelli:

**Livello 1 (keyword)**: cerca il nome della lingua e il livello CEFR sulla stessa riga. Se trova "Italiano" senza livello esplicito, assegna automaticamente "native".

**Livello 2 (semantico, fallback)**: usato solo se il livello 1 non trova nulla, con threshold 0.72. I codici CEFR non hanno equivalenti semantici, quindi la ricerca per keyword è sempre preferita.

---

## 6. Il parser Job Description

### Motivazione (Scenario 2)

Il relatore ha specificato lo **Scenario 2**: il sistema non confronta il candidato direttamente con le occupazioni ESCO, ma analizza prima la job description reale dell'azienda. Questo approccio è più vicino alla realtà operativa: ogni azienda ha requisiti specifici che vanno oltre la classificazione ESCO generica.

### Architettura

Il modulo `job_parser.py` funziona sull'intero testo dell'annuncio senza dipendere da una struttura rigida, adattandosi a qualsiasi formato di offerta: PDF generato da Word, testo copiato dal browser, DOCX aziendale.

```
Testo grezzo (PDF/DOCX/TXT)
    ↓
[1] _split_into_lines()     →  righe pulite con filtro rumore web
    ↓
[2] _extract_title()        →  prima riga breve ≤ 80 char non-rumore
    ↓
[3] Occupation match        →  titolo + frasi chiave → ESCO occupations (threshold 0.72)
    ↓
[4] _detect_seniority()     →  livello richiesto da termini espliciti e anni
    ↓
[5] _extract_skill_candidates()  →  frasi → candidati (solo multi-parola dalla prosa)
    ↓
[6] _extract_acronyms()     →  ALL-CAPS e CamelCase
    ↓
[7] Skill match             →  E5 su ESCO skills (threshold 0.82/0.88/0.84)
    ↓
[8] Filtri                  →  articoli iniziali + etichette troppo generiche
    ↓
[9] Classificazione         →  required vs preferred (marcatori linguistici)
    ↓
[8] JSON output
```

### Gestione del rumore web

I PDF scaricati dai portali di lavoro (Hays, Monster, InfoJobs, LinkedIn) contengono inevitabilmente elementi dell'interfaccia web: navbar, form di login, footer GDPR, breadcrumb di navigazione, numeri di autorizzazione ministeriale. Il parser implementa un sistema di filtraggio a più livelli:

- **`_WEB_NOISE_RE`**: regex che riconosce pattern di rumore per contenuto (cookie, privacy policy, GDPR, navigazione, autorizzazioni ministeriali)
- **`_NAV_LINE_RE`**: regex che riconosce righe che sono interamente elementi di navigazione (Home, Login, Termini, codici job tipo ARPAR35273)
- **`_is_nav_or_noise()`**: funzione che combina i due pattern e filtra anche righe troppo brevi
- **Filtro URL inline**: strip degli URL all'interno delle righe prima dell'estrazione dei candidati
- **`_NON_SKILL_RE`**: rimuove candidati che sono requisiti personali o contrattuali ("residenza a Roma", "disponibilità alla mobilità", "assunzione iniziale", "esperienza almeno di X anni")

### Classificazione required / preferred

Il parser traccia il **contesto linguistico** riga per riga. Quando trova un marcatore di tipo "required" o "preferred", aggiorna il contesto corrente. Le skill estratte nelle righe successive vengono classificate di conseguenza.

Marcatori required: "richiesto/a", "necessario/a", "must have", "si richiede", "il candidato ideale", "competenze richieste"

Marcatori preferred: "preferibile", "gradito/a", "nice to have", "costituisce titolo", "completano il profilo", "rappresenta un plus"

### Limitazione nota: matching cross-linguistico per titoli di lavoro

Il matching dell'occupazione soffre di un gap cross-linguistico per alcuni titoli italiani. Per esempio, "INGEGNERE MECCANICO SENIOR" non mappa direttamente su "mechanical engineer" con il punteggio più alto, ma su "mechanical technology engineer" o "engineer in mechatronics" (score ~0.88). Questo è un limite documentato del retrieval zero-shot cross-linguale con E5: il modello gestisce bene le frasi descrittive ma può avere incertezza su titoli tecnici specifici per dominio.

Come mitigazione, il parser estrae anche pattern disciplinari dal testo (es. "ingegneria meccanica" da una riga di requisiti) e li usa come candidati aggiuntivi per l'occupation matching, migliorando la disambiguazione.

### Output JSON

```json
{
  "job_id": "offerta_ingegnere",
  "raw_title": "INGEGNERE MECCANICO SENIOR",
  "occupation": {
    "id": "...",
    "label": "mechanical technology engineer",
    "score": 0.883
  },
  "seniority": {
    "level": "senior",
    "years": null,
    "evidence": "SENIOR"
  },
  "skills": {
    "required_ids":  ["uuid1", "uuid2", "..."],
    "preferred_ids": ["uuid3"],
    "all_matches": [
      {"id": "uuid1", "label": "CAD software", "score": 0.912},
      {"id": "uuid2", "label": "lean manufacturing", "score": 0.891}
    ]
  }
}
```

Il blocco `seniority` è prodotto da `_detect_seniority()`, che combina termini espliciti nel titolo e nel testo con gli anni di esperienza richiesti. Il campo `evidence` conserva il frammento che ha determinato la decisione, utile per il debug e per motivare il risultato all'utente. Se nessun segnale è presente, `level` vale `null`: il matching engine sa gestire l'assenza omettendo il termine corrispondente, anziché ipotizzare un livello.

---

## 7. Il Matching Engine

### Architettura (Scenario 2)

La classe `JobMatchingEngine` in `matching_engine.py` confronta il profilo CV (output di `main_parser.py`) con il profilo job (output di `job_parser.py`).

Per ogni skill richiesta dalla job description, il motore esegue il matching in due passi:

**Passo 1 — Exact match per ID ESCO**: se la skill richiesta ha esattamente lo stesso UUID ESCO nel profilo del candidato, contribuisce con score 1.0.

**Passo 2 — Semantic match**: se non c'è match esatto, si calcola la cosine similarity tra l'embedding della skill richiesta e tutti gli embedding delle skill del candidato. Se il massimo supera la soglia (0.75), la skill è considerata coperta con score pari alla similarity.

Le skill che non superano nessuna delle due soglie entrano nello **skill gap**.

### Formula del match score

Il punteggio combina quattro contributi. Si parte dalla copertura delle competenze richieste:

```
skill_coverage = Σ contributo(skill_i) / total_weight

contributo(skill_i) = 1.0      se exact match
                    = sim       se semantic match ≥ 0.75
                    = 0.0       se skill nel gap

total_weight = n_required + 0.5 × n_preferred
```

Le skill preferred contribuiscono con peso dimezzato e non entrano nel gap, perché non sono requisiti bloccanti.

Alla copertura, che è una frazione, si affianca un termine sul numero **assoluto** di competenze coperte:

```
skill_score = (1 − β) × skill_coverage + β × n_coperte / (n_coperte + K)

β = count_weight = 0.15      K = count_k = 10
```

Serve a togliere il vantaggio strutturale degli annunci con pochi requisiti, per i quali la frazione risulta alta anche con poche corrispondenze reali (vedi Sezione 9-ter). Il termine è saturante per non premiare indefinitamente gli annunci più lunghi.

Il risultato viene combinato con la similarità fra il ruolo del candidato e quello cercato, e infine con l'allineamento del livello di esperienza:

```
base        = 0.75 × skill_score + 0.25 × occ_similarity
match_score = (1 − γ) × base + γ × seniority_alignment

γ = seniority_weight = 0.10

seniority_alignment = 1.0   livelli coincidenti
                    = 0.5   livelli adiacenti (junior↔mid, mid↔senior)
                    = 0.0   livelli distanti due passi
```

Se il livello di una delle due parti è ignoto, il termine viene omesso anziché penalizzare l'annuncio: l'assenza del dato non è un difetto della corrispondenza. Il livello richiesto è dedotto dal testo dell'annuncio dal job parser (`_detect_seniority`, accuratezza 92,3%), quindi la formula funziona anche su annunci reali privi di metadati.

Tutti i pesi sono parametri del costruttore (`JobMatchingEngine(seniority_weight=…, count_weight=…)`) e possono essere azzerati per riprodurre il comportamento precedente.

**Sul valore di γ.** Il valore iniziale era 0.3, tarato però su un test che confronta esclusivamente annunci della stessa occupazione, dove il contenuto è costante e un peso alto risulta sempre preferibile. Il test di monotonia (Sezione 9-quinquies) ha mostrato che a 0.3 un abbinamento perfetto per contenuto ma con livello disallineato veniva superato da un annuncio di tutt'altro settore. A 0.10 la sovrapposizione fra livelli scende dal 40% al 2,5% e l'accuratezza sul livello resta identica: il termine deve fare da spareggio, non da criterio dominante.

### Grading qualitativo

| Match score | Grade |
|------------|-------|
| ≥ 80% | ottimo |
| 60–79% | buono |
| 40–59% | discreto |
| < 40% | insufficiente |

### Skill gap e roadmap di apprendimento

Le skill mancanti vengono ordinate per priorità di apprendimento dal modulo `skill_graph.py`, che misura la **prossimità concettuale** fra la competenza mancante e quelle già possedute.

La prossimità può venire da due sorgenti, e il modulo usa la migliore disponibile dichiarando sempre quale nel campo `fonte_prossimita`:

- **Gerarchia ufficiale ESCO** (preferita): i file `broaderRelationsSkillPillar.csv` e `skillSkillRelations.csv`, convertiti da `src/build_skill_relations.py` in `dataset/source/skill_relations.json`. Danno una similarità di Wu-Palmer definita per tutte le 13.939 competenze.
- **Co-occorrenza ricostruita** (ripiego): usata finché i file ufficiali non erano stati scaricati. Per ogni coppia di skill che compaiono insieme nella stessa occupazione viene registrata una co-occorrenza. Resta disponibile con `build(usa_tassonomia=False)` per riprodurre i risultati precedenti.

In entrambi i casi le altre due componenti vengono da:

- **`occupation_skill_relations.json`**: la frequenza con cui una skill compare nel catalogo delle occupazioni (da 1 a 340) misura quanto è fondamentale.
- **`skills.json` (campo `reuse_level`)**: ESCO classifica ogni skill in quattro livelli di riutilizzabilità — `transversal`, `cross-sector`, `sector-specific`, `occupation-specific` — che definiscono una gerarchia di generalità.

La priorità di apprendimento di ogni skill nel gap è calcolata con la formula:

```
priority_score = 0.40 × freq_score
               + 0.40 × reuse_score
               + 0.20 × co_occurrence_score

freq_score        = occupation_frequency / max_frequency
reuse_score       = {transversal: 1.0, cross-sector: 0.75,
                     sector-specific: 0.40, occupation-specific: 0.10}
co_occurrence_score = media co-occorrenze con skill già note / max_frequency
```

La skill con `priority_score` più alto riceve `priority = 1` (da imparare per prima). La logica è che le skill fondamentali e trasversali (alta frequenza, `cross-sector`) devono essere acquisite prima delle skill di dominio specifico, e che le skill vicine a quelle già note sono concettualmente più accessibili.

**I pesi 40/40/20 sono stati scelti, non derivati.** Misurati su 787 divari reali i contributi effettivi sono molto diversi da quelli nominali — trasversalità 72,6%, frequenza 20,7%, prossimità 6,7% — perché le tre componenti si distribuiscono su scale diverse. Per la co-occorrenza ricostruita il contributo scendeva all'**1,6%** a causa di una normalizzazione che divide una media di co-occorrenze (tipicamente 0–3) per una frequenza massima (340): due grandezze diverse. Il difetto è documentato in `analysis/valida_skill_graph.py` e in `docs/validazione_skill_graph.md`.

Sul rapporto fra la ricostruzione e i dati ufficiali, la misura dice due cose distinte. Le coppie che la co-occorrenza giudica vicine sono **2,5 volte più vicine del caso** nella tassonomia ESCO (0,103 contro 0,040), quindi la ricostruzione non era arbitraria. Ma la correlazione di rango fra *numero* di co-occorrenze e similarità tassonomica è **ρ = 0,033**, cioè nulla: l'informazione contenuta era binaria, e veniva usata come misura graduata.

Una precisazione sull'ontologia, perché una versione precedente di questo documento affermava il contrario: ESCO **fornisce** relazioni esplicite fra competenze. `skillSkillRelations.csv` contiene 5.818 dipendenze orientate (189 `essential`, 5.629 `optional`), che però coprono solo il 41% delle competenze; `broaderRelationsSkillPillar.csv` contiene la gerarchia, e copre il 100%. È da quest'ultimo che viene la prossimità usata oggi.

### Output JSON

```json
{
  "candidate_id": "parsed_cv.pdf",
  "job_id": "offerta_ingegnere",
  "match_score": 0.657,
  "grade": "buono",
  "occupation_match": {
    "candidate_label": "engineering and quality control manager",
    "job_label": "mechanical technology engineer",
    "similarity": 0.87
  },
  "matched_skills": [
    {"id": "...", "label": "CAD software", "match_type": "exact", "score": 1.0},
    {"id": "...", "label": "lean manufacturing", "match_type": "semantic",
     "score": 0.812, "matched_by": "process optimization"}
  ],
  "skill_gap": [
    {
      "id": "...", "label": "GD&T", "priority": 1,
      "closest_known": {"label": "technical drawing", "similarity": 0.79}
    },
    {
      "id": "...", "label": "finite element analysis", "priority": 2,
      "closest_known": {"label": "structural analysis", "similarity": 0.74}
    }
  ]
}
```

### Uso da CLI

```bash
# Scenario 2: CV ↔ Job Description
python matching_engine.py job --cv cv_parsed_result.json --job job_parsed_result.json

# Scenario 1: CV ↔ Occupation profiles ESCO (modalità precedente)
python matching_engine.py rank --cv cv_parsed_result.json --top 5
```

---

## 8. Le librerie utilizzate

| Libreria | Versione approx. | Scopo |
|----------|-----------------|-------|
| `sentence-transformers` | ≥ 2.6 | Modello E5 per embedding e cosine similarity |
| `torch` (PyTorch) | ≥ 2.0 | Backend tensor per embedding e prodotti scalari |
| `PyMuPDF (fitz)` | ≥ 1.23 | Estrazione testo da PDF |
| `python-docx` | ≥ 1.1 | Estrazione testo da DOCX (paragrafi + tabelle) |
| `reportlab` | ≥ 4.0 | Rendering dei CV sintetici in PDF |
| `numpy` | ≥ 1.24 | Calcolo matriciale per cosine similarity |
| `requests` | standard | Chiamate API Groq per la generazione LLM |
| `re` (stdlib) | — | Regex per segmentazione, filtri, date, rumore web |
| `json` (stdlib) | — | Lettura/scrittura di tutti i database ESCO |

### Il modello di embedding

Il modello usato è **`intfloat/multilingual-e5-base`**:

- **768 dimensioni** (vs 384 del precedente MiniLM)
- Addestrato con instruction tuning specifico per il retrieval cross-linguale
- Richiede prefissi differenziati: `"passage: "` per i documenti indicizzati, `"query: "` per le query di ricerca
- Superiore a MiniLM su benchmark multilingui (BEIR, MIRACL) per compiti di information retrieval

Gli embedding del database ESCO vengono calcolati una sola volta e salvati su disco come cache (`_cache.pt` + `_meta.json`), riducendo il tempo di startup da ~3–4 minuti a pochi secondi.

---

## 9. Valutazione delle prestazioni del CV parser

### Metodo di valutazione

La valutazione avviene su **810 CV renderizzati** (tutti i CV sintetici), confrontando per ognuno le skill trovate dal parser (`found_ids`) con le skill nel ground truth (`gt_ids`):

- **TP**: skill trovata dal parser E presente nel ground truth
- **FP**: skill trovata ma non nel ground truth (rumore semantico)
- **FN**: skill nel ground truth ma non trovata (mancata rilevazione)

```
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × P × R / (P + R)
```

### Risultati su 810 CV (modello E5-base, soglie 0.85/0.88)

| Metrica | Valore |
|---------|--------|
| **Precision media** | **0.907** |
| **Recall media** | **0.860** |
| **F1 media** | **0.878** |
| True Positives | 9.822 |
| False Positives | 991 |
| False Negatives | 1.961 |

Per template di rendering:

| Template | Precision | Recall | F1 |
|---|---|---|---|
| classic | 0.936 | 0.885 | 0.905 |
| europass | 0.898 | 0.855 | 0.872 |
| modern | 0.885 | 0.841 | 0.858 |

Lo scarto fra il formato migliore e il peggiore resta sotto i 5 punti di F1: il parser è robusto alle variazioni di layout, pur beneficiando dei template più strutturati.

Riproducibile con:

```
python tests/batch_parse_cvs.py
python analysis/analisi_parser.py --section gt --from-batch
```

L'opzione `--from-batch` valuta tutti gli 810 CV riusando il batch già calcolato. Senza di essa la Sezione 4 ne riparsa un campione di dieci, numero insufficiente a stimare le metriche in modo stabile e non confrontabile con la valutazione degli annunci.

### Evoluzione delle prestazioni

| Versione | Precision | Recall | F1 |
|---|---|---|---|
| baseline iniziale | 0.760 | 0.547 | 0.623 |
| dopo dizionario supplementare e filtri | 0.865 | 0.860 | 0.857 |
| **dopo filtro sui nomi di lingua** | **0.907** | **0.860** | **0.878** |

Il recall è salito da 0.547 a 0.860 grazie al dizionario supplementare di alias italiani, che recupera le skill ESCO con label verb-start altrimenti rimosse dal filtro sui compiti.

### Il filtro sui nomi di lingua

ESCO cataloga le lingue come competenze ("francese", "neerlandese", "svedese"). Le lingue dichiarate nel CV venivano quindi estratte due volte: dal rilevatore dedicato, che le restituisce con il livello CEFR nel blocco `languages`, e di nuovo dal matching semantico come skill.

L'analisi dei falsi positivi ha quantificato il fenomeno: **489 su 1.480, circa un terzo del totale**, con "francese" a 183 occorrenze errate e nessuna corretta, "neerlandese" a 111 e "spagnolo" a 76. Aggiungere un filtro che scarta le label corrispondenti a nomi di lingua elimina tutti e 489 i falsi positivi senza perdere alcun vero positivo — la precision passa da 0.865 a 0.907 con recall invariata.

### Falsi negativi residui

Le skill sistematicamente non trovate appartengono a due categorie:

1. **Soft skill e competenze comunicative** — espresse con formule italiane standardizzate ("ottime doti comunicative", "forte orientamento al risultato") che hanno bassa similarità con le label ESCO inglesi corrispondenti ("communicate with customers", "use different communication channels")

2. **Skill di dominio specifico non presente in ESCO** — competenze come SolidWorks, AutoCAD specifico per versione, metodologie Kanban che ESCO non indicizza con quella terminologia esatta

Va inoltre considerato che le metriche sono un **limite inferiore**: la valutazione richiede l'identità dell'ID ESCO, quindi un match concettualmente corretto ma con identificativo diverso viene conteggiato come errore su entrambi i fronti.

### Sperimentazione comparativa sul modello

È stata condotta una sperimentazione comparativa tra il modello precedente (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dim) e l'attuale (`intfloat/multilingual-e5-base`, 768 dim):

- **MiniLM**: precision ~0.88, recall ~0.48 — penalizzato soprattutto su skill tecniche specifiche
- **E5-base**: precision ~0.92, recall ~0.55 — miglioramento su entrambe le metriche

Il confronto risale a una versione precedente della pipeline, quando il recall era limitato dall'assenza del dizionario supplementare. Il miglioramento resta attribuibile all'instruction tuning di E5 e alla dimensionalità maggiore degli embedding, ma il confronto andrebbe ripetuto sulla pipeline attuale per quantificare correttamente il contributo del solo modello, separandolo da quello delle correzioni successive.

### Analisi dei False Positives

Dopo il filtro sui nomi di lingua restano 991 falsi positivi su 10.813 skill estratte. Derivano principalmente da:

- **Skill ESCO troppo generiche** che matchano qualsiasi testo (es. "maintain customer service", "contattare i clienti")
- **Frammenti di testo non-skill** che superano la soglia per coincidenza semantica (dati anagrafici, indirizzi, date)
- **Relazioni ESCO task-oriented non filtrate** — alcune sfuggono ai filtri post-semantici

Il primo fenomeno è lo stesso che affligge il parser degli annunci, dove però ha un peso molto maggiore (Sezione 9-bis): nel CV le competenze sono elencate in modo discreto, quindi ogni candidato è già isolato e pulito, mentre nella prosa vengono generati frammenti privi di contenuto.

### Numeri chiave del progetto

| Metrica | Valore |
|---------|--------|
| Occupazioni ESCO disponibili | 3.039 |
| Skill ESCO primarie | 13.939 |
| Etichette indicizzate per le competenze (con alt_labels) | 98.847 |
| Etichette indicizzate per le occupazioni (con alt_labels) | 19.201 |
| Filtrate dal filtro verbi (task-oriented) | 29.093 (29%) |
| CV sintetici generati e valutati | 810 |
| Annunci sintetici con ground truth ESCO | 810 |
| Occupazioni distinte nel dataset | 135 |
| Media skill per CV (ground truth) | 14,5 |
| Media skill per annuncio (ground truth) | 13,5 |
| **Parser CV** — Precision / Recall / F1 | **0.907 / 0.860 / 0.878** |
| **Parser annunci** — Precision / Recall / F1 | **0.614 / 0.577 / 0.580** |
| Estrazione del livello di esperienza | 92,3% |
| Matching engine — Precision@1 (CV → offerte) | 96,7% |
| Matching engine — Precision@1 (offerta → candidati) | 90,0% |
| Matching engine — accuratezza sul livello | 97,0% |
| Copertura corsi sul gap (transizione di settore) | 43,1% |

---

## 9-bis. Valutazione del parser degli annunci

### Conferma indipendente della diagnosi (ESCOXLM-R)

La diagnosi secondo cui il difetto dominante stava nella generazione dei candidati — e non nel modello di embedding né nell'ontologia — è una spiegazione, non una verifica: resta compatibile con l'ipotesi che il problema sia intrinseco al testo in prosa. Per distinguere le due serve un estrattore che non condivida il difetto per costruzione.

`jjzha/escoxlmr_skill_extraction` (ESCOXLM-R, ACL 2023, affinato sul corpus SkillSpan) individua span di competenza senza segmentare sui confini delle parole funzionali. Sugli stessi 810 annunci con ground truth: **10.045 span prodotti** (12,4 per annuncio), di cui **7 — lo 0,07% — sono frammenti privi di contenuto** della famiglia `responsible` / `seeking`; span di una sola parola 2,97%; 0,7 s per annuncio in CPU. Nella pipeline locale il solo candidato `responsible` genera 792 falsi positivi, e il vincolo multi-parola deve eliminare il 45,5% dei candidati per contenere lo stesso fenomeno.

Tre precisazioni necessarie. **Non è un confronto di F1** e non potrebbe esserlo: la ground truth elenca le competenze che il generatore doveva inserire e che nel testo a volte non compaiono, e quel costo un estrattore di span lo pagherebbe per intero mentre le soglie locali vi sono state ottimizzate contro. **La lingua non entra in gioco**: gli annunci con ground truth sono in inglese, e SkillSpan pure. **Il modello non ha mai visto questi annunci**, mentre soglie e denylist sono tarate proprio osservandoli: la conferma arriva quindi in condizioni sfavorevoli.

Riproducibilità: `analysis/prova_escoxlmr.py --sorgente gt --annunci 810`, in un ambiente virtuale separato.

### Il dataset con ground truth

La valutazione del job parser richiedeva un dataset di annunci con le skill ESCO note. Il primo corpus disponibile, ricavato da annunci reali raccolti dal web, copriva solo tre aree professionali e non aveva annotazioni: rendeva verificabili 3 CV su 810 e non permetteva alcuna misura di precision e recall.

È stato quindi generato un secondo dataset sintetico (`src/generate_jobs.py`), con la stessa metodologia dei CV: 135 occupazioni ESCO × 3 livelli di seniority × 2 varianti = **810 annunci**, ciascuno con le skill di riferimento campionate dalle relazioni ESCO dell'occupazione.

### Risultati

| Metrica | Valore |
|---|---|
| Precision | 0.614 |
| Recall | 0.577 |
| F1 | 0.580 |
| Accuratezza occupazione (ID ESCO esatto) | 75,9% |
| Accuratezza occupazione (macro-settore ISCO) | 87,5% |

Il divario di trenta punti di F1 rispetto al parser CV non dipende dalla qualità del componente ma dalla natura dell'input. Il parser CV legge un PDF renderizzato con intestazioni di sezione ed elenchi; il job parser riceve prosa continua. La conseguenza è misurabile nel numero di skill prodotte: il parser CV ne estrae 0,96 volte quelle attese, il job parser prima delle correzioni ne estraeva 1,99 volte.

### La correzione decisiva

Il falso positivo dominante nasceva da un frammento grammaticale. Applicato a una frase come *"The successful candidate will be responsible for coordinating technological activities, using our ICT ticketing system"*, il segmentatore produceva sette candidati: tre competenze reali e quattro detriti (`successful`, `responsible`, `using`, `complying`).

La corrispondenza con gli errori è risultata esatta:

| candidato | annunci in cui compare | etichetta ESCO agganciata | falsi positivi |
|---|---|---|---|
| `responsible` | 792 su 810 | comportarsi in modo responsabile | 792 |
| `seeking` | 773 su 810 | motori di ricerca | 772 |

Il punto interessante è che per il candidato `responsible` l'etichetta *"comportarsi in modo responsabile"* è il match **corretto**: il difetto non stava nel modello di embedding né nell'ontologia, ma nella domanda posta al sistema. Accettare dalla prosa solo candidati di almeno due parole elimina il 45,5% dei candidati e con essi quasi tutti i falsi positivi sistematici, al costo di 3,5 punti di recall.

Il bilancio del filtro, ricalcolato sugli 810 annunci confrontando `outputs/ab_nodeny.json` (nessun rimedio) con `outputs/ab_multiword_nodeny.json` (solo vincolo multi-parola): **334 veri positivi persi contro 10.076 falsi positivi eliminati**, un rapporto di 1 a 30. I match rimossi erano corretti nel 3,2% dei casi.

> **Nota sulla correzione.** Una versione precedente di questo documento riportava 78 veri positivi persi contro 1.828 falsi positivi, rapporto 1 a 23. Quei valori non trovano riscontro in un ricalcolo sui file di ablazione attualmente presenti in `outputs/`, e provengono verosimilmente da un'esecuzione su un sottoinsieme di annunci o da una versione precedente della pipeline. I valori corretti sono più favorevoli al filtro, non meno.

### Contromisure valutate e scartate

Prima di individuare la causa reale sono state provate e misurate quattro contromisure alternative, tutte inefficaci:

| tentativo | esito | motivo |
|---|---|---|
| stadio di riconoscimento lessicale | scartato | contributo incrementale con precision 0.27, sotto lo 0.53 dello stadio semantico |
| correzione hubness | nessun effetto | 0.298 contro 0.297: penalizza le etichette, ma il problema era nelle query |
| vincolo di reciprocità | inefficace | presupponeva ripetizioni interne al documento, mentre le etichette problematiche comparivano una sola volta per annuncio in 792 annunci distinti |
| filtri sulle etichette del parser CV | nessun effetto | calibrati su un difetto diverso |

La diagnosi del perché la correzione hubness non funzionasse — il fenomeno era fra documenti, non dentro il documento — è ciò che ha portato a esaminare il segmentatore e a individuare la causa vera.

### Filtro residuo sulle etichette generiche

Restano alcune etichette ESCO formulate in modo tanto generico da essere abbinate a quasi qualsiasi annuncio ("lavorare indipendentemente", "prestare attenzione ai dettagli"). Sono escluse tramite una lista di 64 identificativi, ricostruita dopo la correzione al segmentatore e validata su holdout: lista costruita su 405 annunci, effetto misurato sui 405 mai visti, precision 0.543 → 0.585 e F1 0.551 → 0.570 con recall invariata.

**Limite dichiarato.** A differenza del vincolo multi-parola, questa lista è ricavata osservando quali predizioni erano sbagliate: è supervisionata e specifica del dominio, e su annunci reali andrebbe rimisurata. Il sistema funziona anche senza (F1 0.546), quindi non è un componente critico ed è disattivabile con `JobParser(use_denylist=False)`.

### Estrazione del livello di esperienza

Il parser deduce dall'annuncio il livello richiesto, combinando termini espliciti nel titolo e nel testo ("junior", "senior", "lead") e anni di esperienza richiesti. Accuratezza **92,3%** su 810 annunci, 4,3% di casi non rilevati, nessun errore da due livelli.

---

## 9-ter. Valutazione del matching engine

### Ritrovamento dell'occupazione

Per ogni CV si ordinano gli annunci di un pool per match score e si verifica in quale posizione compare il primo annuncio dell'occupazione corretta.

| Metrica | Valore |
|---|---|
| Precision@1 | 96,7% |
| Precision@10 | 100,0% |
| MRR | 0,971 |
| Baseline casuale | 2,0% |

### La direzione inversa: dato un annuncio, ordinare i candidati

Il sistema serve due utenti diversi — chi cerca lavoro e chi seleziona — quindi entrambe le direzioni vanno validate. La funzione di punteggio è la stessa, ma il suo comportamento non è simmetrico: nel verso candidato → offerta il denominatore della copertura cambia a ogni annuncio, mentre nel verso opposto è fisso.

Su 20 annunci contro 361 candidati:

| Metrica | Valore |
|---|---|
| Precision@1 | 90,0% |
| Precision@3 | 100,0% |
| Precision@10 | 100,0% |
| MRR | 0,950 |
| Baseline casuale | 1,7% |

*(misura con i pesi predefiniti, γ = 0,10 e β = 0,15. Una prima esecuzione con γ = 0,3 — il valore dichiarato tarato male — dava 85,0% e MRR 0,912: correggere γ ha migliorato di 5 punti anche questo compito.)*

La Precision@1 è più bassa che nel verso opposto perché scegliere fra candidati della stessa occupazione è più difficile che fra annunci: i CV variano per livello e per sottoinsieme di competenze possedute, mentre gli annunci di uno stesso ruolo sono fra loro più omogenei. In tutti i casi il candidato pertinente resta comunque entro i primi dieci.

**Verifica di un possibile effetto collaterale.** Il termine sul conteggio assoluto, introdotto per correggere la preferenza verso le posizioni junior, in questa direzione avrebbe potuto produrre una distorsione opposta: favorire i curriculum più lunghi, che coprono più requisiti per pura ampiezza. Il sospetto era concreto, dato che un CV del 90° percentile ha 23 competenze estratte contro le 7 del 10°.

La misura lo ha smentito:

| indicatore | con count_weight 0.15 | senza (0.0) |
|---|---|---|
| skill medie nel pool | 13,1 | 13,1 |
| Precision@1 | 90,0% | 90,0% |
| MRR | 0,950 | 0,950 |
| skill medie nei primi 10 | 14,2 | 14,1 |
| rapporto | 1,08× | 1,08× |
| correlazione punteggio↔lunghezza fra i NON pertinenti | +0,194 | +0,208 |

La correlazione fra punteggio e lunghezza del curriculum, sui soli candidati dell'occupazione sbagliata, è +0,194: debole ma non nulla. Il punto decisivo non è il suo valore bensì il fatto che **rimuovendo il termine sospetto non diminuisce** — sale a 0,208. Non è dunque causata dal termine di conteggio: resta perché i CV più lunghi elencano più competenze e hanno più occasioni di sovrapporsi a un annuncio qualsiasi, che è una proprietà dei dati e non della formula. L'ipotesi è quindi respinta per ablazione — rimuovo la causa sospetta, l'effetto resta — e non per assenza di segnale, che sarebbe stato un argomento più debole. Le due configurazioni coincidono inoltre su tutte le metriche di ordinamento, confermando la spiegazione teorica: con denominatore fisso il termine assoluto non altera l'ordine relativo fra candidati.

Questo controllo ha rilevanza anche etica: un sistema di selezione che premiasse la prolissità del curriculum invece della competenza introdurrebbe una discriminazione sistematica a favore di chi sa presentarsi meglio.

**Come va letto il risultato sul ritrovamento dell'occupazione.** Il valore sovrastima ampiamente la difficoltà del compito, perché CV e annunci della stessa occupazione sono generati campionando dalla medesima lista di skill ESCO:

| coppia CV ↔ annuncio | sovrapposizione media (Jaccard) |
|---|---|
| stessa occupazione | 0.640 |
| stesso settore ISCO, occupazione diversa | 0.0164 |
| settore diverso | 0.0034 |

Il 93% delle coppie di occupazioni diverse non condivide alcuna competenza: al motore basta rilevare "hanno qualcosa in comune" per vincere. Restringere il pool non aiuta, perché anche dentro lo stesso settore la separazione resta di 39 volte. Il valore va quindi riportato insieme a questa quantificazione, altrimenti suggerisce una capacità discriminativa che il test non ha verificato.

### Un difetto individuato: la preferenza per le posizioni junior

Il punteggio era definito come frazione dei requisiti dell'annuncio coperti dal candidato. Poiché gli annunci junior elencano meno requisiti, la frazione risultava sistematicamente più alta a prescindere dal candidato:

| livello dell'annuncio | skill richieste (media) |
|---|---|
| junior | 10,77 |
| mid | 13,54 |
| senior | 16,19 |

Su 100 CV il motore sceglieva un annuncio junior 47 volte (atteso 33), con un'accuratezza sul livello del 37,0% contro una baseline casuale del 33,3%. In pratica il sistema proponeva posizioni sotto-livello a chiunque avesse esperienza — un difetto funzionale rilevante per uno strumento di orientamento. Inoltre `JobMatchingEngine` non conteneva alcun termine legato all'esperienza: la logica sulla seniority presente nel modulo apparteneva al motore dello Scenario 1.

### Le due correzioni

**Termine sul conteggio assoluto** (`count_weight`, predefinito 0.15). Miscela alla copertura un termine saturante sul numero assoluto di competenze coperte, togliendo il vantaggio strutturale agli annunci corti. Taratura misurata su 100 CV, dove le colonne indicano quante volte viene scelto un annuncio di ciascun livello (atteso 33/33/33):

| peso | accuratezza | junior/mid/senior scelti |
|---|---|---|
| 0.00 | 37,0% | 47 / 29 / 24 |
| **0.15** | **44,0%** | **33 / 33 / 34** |
| 0.25 | 44,0% | 25 / 36 / 39 |
| 0.40 | 43,0% | 19 / 36 / 45 |

A 0.15 e 0.25 l'accuratezza coincide, ma solo a 0.15 le scelte sono equilibrate: a parità di errori è preferibile che siano rumore anziché una tendenza sistematica.

**Termine di allineamento del livello** (`seniority_weight`, predefinito 0.1). Confronta l'esperienza del candidato con il livello estratto dall'annuncio: 1.0 se coincidono, 0.5 se adiacenti, 0.0 se distano due passi. Se uno dei due livelli è ignoto il termine viene omesso anziché penalizzare l'annuncio.

Il valore inizialmente scelto era 0.3, tarato sul solo test della seniority. Quel test confronta però esclusivamente annunci della stessa occupazione, dove il contenuto è costante e varia solo il livello: un peso alto non ha contropartite e risulta sempre migliore. Verificando anche la monotonia del punteggio (Sezione 9-quinquies) è emerso che con 0.3 un abbinamento perfetto per contenuto ma con livello disallineato veniva superato da un annuncio di tutt'altro settore.

| peso | sovrapposizione occupazione↔settore | accuratezza sul livello |
|---|---|---|
| 0.30 | 40,0% | 97,0% |
| **0.10** | **2,5%** | **97,0%** |

Il valore basso è migliore su una dimensione e identico sull'altra: il termine deve funzionare da spareggio fra annunci altrimenti equivalenti, non da criterio dominante.

### Risultato

| | prima | dopo |
|---|---|---|
| Occupazione — Precision@1 | 96,7% | 96,7% |
| Occupazione — Precision@10 | 96,7% | 100,0% |
| Livello — accuratezza | 37,0% | 97,0% |
| Livello — accuratezza adiacente | 86,0% | 100,0% |
| Distorsione nelle scelte | 47/29/24 | 33/33/34 |

**Come leggere il 97%.** Non è una capacità emergente del motore: il livello gli viene passato esplicitamente dal job parser. Il numero che descrive una capacità è il **92,3%** dell'estrattore; il 97% dimostra che il collegamento regge ed è robusto agli errori sul singolo annuncio, perché ogni occupazione dispone di due annunci per livello e ne basta uno etichettato correttamente.

A differenza del ritrovamento dell'occupazione, questo test non è viziato dalla costruzione del dataset: i sei annunci di una stessa occupazione hanno competenze quasi identiche, quindi il segnale sul livello va davvero estratto dal testo.

---

## 9-quater. Valutazione del raccomandatore di corsi

### Scelta dello scenario

Confrontare un candidato con un annuncio del lavoro che già svolge non produce nulla da colmare: **0,17 competenze mancanti per confronto**, su circa 12 richieste. Chi cerca formazione lo fa per un lavoro che ancora non può ottenere, quindi sono stati provati tre scenari.

| scenario | confronto | skill mancanti distinte | copertura |
|---|---|---|---|
| stessa occupazione | CV ↔ annuncio dello stesso ruolo | 22 | 50,0% |
| avanzamento | CV junior/mid ↔ annuncio senior dello stesso ruolo | 8 | 37,5% |
| **transizione** | CV ↔ altra occupazione, stesso settore ISCO | **72** | **43,1%** |

Solo la transizione produce un campione utilizzabile.

### Un limite del dataset

Lo scenario di avanzamento avrebbe dovuto essere il più significativo — è la progressione di carriera, il caso d'uso naturale della formazione — e ha invece prodotto 10 occorrenze su 60 CV.

Il motivo è che nel dataset sintetico la seniority cambia **quanto** viene richiesto, non **che cosa**: i sei annunci di un'occupazione attingono tutti alla stessa lista ESCO, e passando da junior a senior il numero di competenze sale da 10,8 a 16,2 ma la loro natura resta identica. Un candidato junior possiede quindi già, qualitativamente, ciò che l'annuncio senior richiede. Nella realtà la progressione comporta competenze di tipo diverso — coordinamento, responsabilità di budget, specializzazione — che il generatore non ha modellato.

### Il limite è il catalogo, non l'algoritmo

Copertura dell'indice Coursera sull'intera ontologia ESCO:

| settore ISCO | skill | con almeno un corso |
|---|---|---|
| Professioni intellettuali | 7.538 | 32,4% |
| Dirigenti | 3.557 | 32,2% |
| Impiegati | 1.360 | 27,9% |
| Tecnici | 6.325 | 26,5% |
| Servizi e vendite | 2.234 | 22,0% |
| Artigiani | 3.542 | 19,5% |
| Agricoltura | 768 | 16,8% |
| Conduttori di impianti | 3.126 | 15,4% |
| Professioni non qualificate | 1.319 | 15,2% |
| **totale** | **13.475** | **23,7%** |

Il gradiente supera il doppio fra lavoro intellettuale e lavoro manuale: Coursera è un catalogo accademico, tecnologico e gestionale, e competenze come "tipi di pelle", "codice della strada" o "manage crop rotation" non vi compaiono.

Il 43,1% osservato nel test è quindi quasi il doppio del 23,7% medio dell'ontologia: le competenze che emergono come mancanti nei confronti reali risultano meglio coperte della media. Un sistema di orientamento che copra tutti i mestieri richiederebbe cataloghi diversi — formazione professionale, apprendistato, enti regionali. È un limite di dominio, non algoritmico.

**Non misurato.** La pertinenza qualitativa dei corsi suggeriti: gli strumenti verificano che un corso esista, non che sia quello adatto. Serve un controllo a campione manuale.

---

## 9-quinquies. Il punteggio è una misura o solo un ordinamento?

Le validazioni precedenti verificano che il candidato giusto finisca in cima alla classifica, non che il VALORE del punteggio significhi qualcosa. È una distinzione operativa: se l'interfaccia mostra "compatibilità 78%", quel numero deve corrispondere a un grado di affinità.

Il test (`analysis/valida_monotonia.py`) confronta ogni CV con tre annunci ad affinità decrescente e verifica che il punteggio degradi in modo ordinato.

| livello di affinità | media | mediana | min | max |
|---|---|---|---|---|
| stessa occupazione | 0.861 | 0.862 | 0.736 | 0.945 |
| stesso settore ISCO | 0.763 | 0.782 | 0.611 | 0.864 |
| settore diverso | 0.733 | 0.742 | 0.532 | 0.829 |

Sovrapposizione fra livelli contigui: 2,5% e 12,5%. Le distribuzioni sono separate, quindi il valore assoluto è informativo e può essere mostrato all'utente.

### Il difetto che questo test ha rivelato

Con il peso di seniority a 0.3 la situazione era ben diversa: sovrapposizione al 40% e 30%, con il minimo della stessa occupazione (0.573) sotto il massimo di un settore diverso (0.867). I casi tracciati hanno mostrato il meccanismo su un esempio verificabile:

| confronto | occupazione dell'annuncio | copertura skill | similarità ruolo | punteggio |
|---|---|---|---|---|
| stessa occupazione | telecommunications manager | 0.967 | 1.000 | **0.646** |
| settore diverso | mask maker | 0.881 | 0.805 | **0.711** |

Ricostruendo il calcolo, il CV era senior e l'annuncio della stessa occupazione era junior: allineamento nullo, trenta punti di punteggio azzerati, confronto ribaltato.

L'errore metodologico è istruttivo: il parametro era stato ottimizzato su un test che isolava una dimensione, e in quel contesto il valore alto era sempre preferibile. Solo misurando entrambe le dimensioni insieme è emerso che comprometteva il compito principale. È un esempio concreto del fatto che l'ottimo per componenti isolati non coincide con l'ottimo del sistema.

### Casi tracciati

`docs/casi_tracciati.md` riporta cinque confronti completi con la scomposizione del punteggio, le competenze coperte e quelle mancanti. Servono a rendere i risultati verificabili a mano: una metrica aggregata richiede fiducia, un caso ispezionabile no.

---

## 10. Problemi aperti e sviluppi futuri

### Recall del CV parser

Il recall, inizialmente fermo a 0.547, è salito a **0.860** grazie al dizionario supplementare di alias italiani costruito dall'analisi sistematica dei falsi negativi più frequenti. L'ipotesi iniziale di un limite strutturale del retrieval cross-linguistico zero-shot si è rivelata parzialmente errata: la barriera non era il modello ma la copertura lessicale, colmabile con un dizionario mirato.

Il residuo (1.961 falsi negativi) riguarda soft skill espresse con formule italiane molto distanti dalle label ESCO e competenze di dominio non indicizzate nell'ontologia. Un fine-tuning su coppie (espressione italiana, label ESCO) resta la strada per ridurlo ulteriormente, ma richiederebbe dati annotati che il progetto non possiede.

### Prosa contro documento strutturato

Il divario di trenta punti di F1 fra parser CV (0.878) e parser annunci (0.580) è il limite più rilevante del sistema. Non dipende dalla qualità dei componenti — condividono lo stesso motore di matching — ma dal fatto che il primo legge un PDF con intestazioni ed elenchi mentre il secondo riceve prosa continua.

La direzione più promettente è uno stadio che riconosca la struttura implicita dell'annuncio, distinguendo le sezioni di requisiti dal testo di contorno. Una prima misura ha stimato intorno al 15% la quota di candidati proveniente da frasi non-requisito, quindi il guadagno atteso è modesto: andrebbe valutato rispetto al costo di manutenzione dell'euristica.

### Differenziare le competenze per livello nel dataset sintetico

Il generatore fa variare con la seniority il numero di competenze richieste (10,8 per junior contro 16,2 per senior) ma non la loro natura, poiché tutte provengono dalla stessa lista ESCO dell'occupazione. Ne consegue che un candidato junior possiede già, qualitativamente, ciò che un annuncio senior richiede, e lo scenario di avanzamento di carriera non produce alcun divario formativo misurabile.

Modellare competenze qualitativamente diverse per livello — coordinamento, gestione di budget, specializzazione tecnica — renderebbe valutabile il caso d'uso principale del raccomandatore di corsi.

### Circolarità del dataset sintetico

CV e annunci della stessa occupazione condividono in media il 64% delle competenze perché entrambi campionati dalle medesime relazioni ESCO, contro lo 0,3% fra occupazioni diverse. Il ritrovamento dell'occupazione risulta quindi un compito quasi banale, e il 96,7% di Precision@1 va letto come limite superiore.

Una validazione realmente informativa richiede documenti reali, oppure un generatore che introduca variabilità lessicale e sovrapposizioni parziali fra occupazioni affini.

### Matching occupation per titoli italiani

Il job parser ha difficoltà a mappare titoli italiani composti (es. "INGEGNERE MECCANICO SENIOR") sulla giusta occupazione ESCO in inglese. La distanza cross-linguistica E5 per titoli tecnici specifici produce a volte match con occupazioni simili ma non identiche. Una soluzione sarebbe una piccola lookup table per i titoli più comuni del mercato italiano.

### Arricchimento del job parser

Il filtro rumore web è efficace ma necessita manutenzione: ogni portale di lavoro (Hays, LinkedIn, InfoJobs, Infojobs) ha elementi di navigazione propri non sempre coperti dai pattern attuali. In un sistema in produzione si userebbe scraping strutturato tramite le API dei portali, eliminando alla radice il problema del rumore.

### Validazione su CV reali

Il dataset sintetico è fondamentale per lo sviluppo ma non simula completamente i CV reali. CV autentici hanno irregolarità tipografiche, layout non standard, informazioni mancanti o ambigue. La raccolta di CV reali (anche in forma anonimizzata tramite Google Form con consenso informato) permetterebbe di validare il sistema in condizioni operative.

### Skill gap e roadmap

La prioritizzazione del gap usa `skill_graph.py`, che combina frequenza ESCO, `reuse_level` e prossimità concettuale. L'integrazione delle relazioni ufficiali — indicata come sviluppo futuro in una versione precedente di questo documento — **è stata fatta**: i file `broaderRelationsSkillPillar.csv` e `skillSkillRelations.csv` di ESCO v1.2.1 sono ora nel progetto, e la sostituzione cambia l'ordinamento nel 79,5% dei casi e la prima competenza raccomandata nel 14,2%.

Restano due cose da fare, entrambe dichiarate. La prima: la prossimità tassonomica è **fondata ma non validata** — sappiamo che viene da ESCO invece che da una ricostruzione, non che l'ordine che produce sia più utile a chi deve studiare. Servirebbe un giudizio umano su quale competenza convenga imparare prima, che non è stato raccolto. La seconda: i pesi 40/40/20 restano scelti, e `reuse_level` domina l'ordinamento pur assumendo solo tre valori distinti nel campione, quindi ordina per fasce larghe entro cui decide la frequenza.

Sul fronte dei corsi, il vincolo dominante è la copertura del catalogo: solo il 23,7% delle competenze ESCO ha almeno un corso Coursera associato, con un gradiente che va dal 32% delle professioni intellettuali al 15% di quelle non qualificate. Affiancare cataloghi di formazione professionale ed enti regionali è più promettente che raffinare l'algoritmo di raccomandazione, che già opera su un sottoinsieme più favorevole della media (43,1% di copertura sul gap osservato).

### Scalabilità del matching

L'attuale matching engine ricalcola gli embedding delle skill ad ogni chiamata. In un sistema multi-utente in produzione, gli embedding delle skill ESCO andrebbero precalcolati e serviti da un vector store (FAISS, Qdrant, Pinecone) per ridurre la latenza da secondi a millisecondi.
