# SkillPath AI — passaggio di consegne

Documento per chi prende in mano il progetto. Contiene: cos'è, com'è
organizzato, come si fa girare, cosa è già stato misurato e — soprattutto —
**le trappole**, perché sono la parte che fa perdere più tempo.

Aggiornato a ottobre 2026 · Samuele Miele

---

## 1. Che cos'è

Un sistema che mette in relazione **curriculum** e **annunci di lavoro**
attraverso l'ontologia europea **ESCO**.

Dati un CV e un annuncio, il sistema: estrae le competenze da entrambi, calcola
una compatibilità, individua le competenze mancanti (*skill gap*) e propone
corsi per colmarle. Funziona nelle due direzioni — un candidato cerca
l'annuncio migliore, un selezionatore cerca il candidato migliore.

**Due vincoli di progetto, da rispettare:**

- tutto gira **in locale**, nessun dato esce dalla macchina (i documenti
  contengono dati personali);
- deve funzionare su un normale PC **senza GPU**.

**La scelta che spiega tutto il resto:** non esistevano dati etichettati, quindi
non c'è nessuno stadio di decisione addestrato nel senso pieno. A decidere sono
soglie di similarità — tranne nel parser degli annunci, dove c'è un
classificatore addestrato per *distant supervision*. Gran parte dei difetti
documentati nasce da questa mancanza.

---

## 2. Com'è organizzato

```
generatore/
├── src/           il sistema vero e proprio
├── analysis/      script di misura e validazione (non fanno parte del sistema)
├── tests/         esecuzioni in batch e verifiche di regressione
├── app/           interfacce Streamlit
├── dataset/       dati: ESCO, dataset sintetico, risorse supplementari
├── config/        indice dei corsi, pesi, filtro appreso
├── outputs/       TUTTI i risultati delle misure (vedi §6, attenzione)
├── job_descriptions/  1.000 annunci sintetici in .txt (usati dal frontend)
├── docs/          documentazione e risultati scritti
└── samples/       esempi sparsi
```

### `src/` — il sistema

| file | cosa fa |
|---|---|
| `semantic_mapper.py` | **il cuore.** Carica il modello di embedding e l'indice ESCO, calcola le similarità. Tutto passa di qui |
| `main_parser.py` | parser dei **curriculum**: segmenta per sezioni, estrae competenze, lingue, titoli, certificazioni, anni di esperienza |
| `job_parser.py` | parser degli **annunci**: prosa libera, estrazione candidati, denylist, classificatore |
| `matching_engine.py` | calcola la compatibilità fra due profili e produce lo skill gap |
| `skill_graph.py` | ordina lo skill gap per priorità di apprendimento |
| `esco_taxonomy.py` | similarità tassonomica sulla gerarchia ESCO ufficiale (Wu-Palmer) |
| `course_recommender.py` | dalle competenze mancanti ai corsi Coursera |
| `filtro_skill.py` | i filtri sulle etichette ESCO candidate |
| `lexical_matcher.py` | stadio di confronto lessicale (valutato e **scartato**, vedi §5) |
| `pdf_extractor.py` | estrazione testo da PDF/DOCX |
| `generate_dataset.py` · `generate_jobs.py` · `render_cvs.py` | generazione del dataset sintetico |
| `build_italian_esco.py` · `build_skill_relations.py` · `build_course_index.py` · `build_companies.py` | costruzione delle risorse dati |

### `app/`

- **`streamlit_app.py`** — il frontend dimostrativo, tre modalità: 1 CV ↔ 1
  annuncio, 1 annuncio ↔ più CV, 1 CV ↔ più annunci.
- **`annota_cv.py`** — strumento di **annotazione manuale** dei curriculum
  reali. Non è una demo: è lo strumento che produce la ground truth su dati
  veri (vedi §7).

### `dataset/`

| cartella | contenuto | peso |
|---|---|---|
| `source/` | ESCO v1.2.1: occupazioni, competenze, relazioni, cache embedding | 329 MB |
| `source_it/` · `source_en/` | le stesse, separate per lingua (indice bilingue) | 2,2 GB · 21 MB |
| `synthetic/` | i 810 CV e 810 annunci generati, più i PDF renderizzati | 11 MB |
| `supplementary/` | certificazioni, titoli di studio, livelli linguistici, alias | 1,8 MB |
| `materialized/` | strutture precalcolate | 32 MB |

⚠️ `source_it/` pesa 2,2 GB per via delle cache di embedding. Non va su Git.

---

## 3. Come si fa partire

```bash
pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py
```

Il modello di embedding (`intfloat/multilingual-e5-base`, ~1 GB) viene
scaricato da Hugging Face alla **prima** esecuzione e poi resta in cache
locale. Dopo di che tutto funziona **senza rete**: le embedding dell'indice
ESCO sono già precalcolate in `dataset/source/`.

Per verificarlo: `$env:HF_HUB_OFFLINE=1` prima di lanciare.

### Le misure principali

```bash
# parser dei CV sugli 810 sintetici
python tests/batch_parse_cvs.py
python analysis/analisi_parser.py --section gt --from-batch

# parser degli annunci
python tests/batch_parse_jobs_gt.py
python analysis/analisi_job_parser.py

# matching, nelle due direzioni
python analysis/valida_matching_engine.py --max-cvs 30 --max-jobs 300
python analysis/valida_recruiter.py

# raccomandatore di corsi
python analysis/valida_course_recommender.py --scenario transizione --n-cv 60

# ordinamento del divario
python analysis/valida_skill_graph.py
```

**Usa sempre `--out` con un nome diverso per ogni configurazione.** È già
capitato due volte di perdere risultati perché due esecuzioni scrivevano sullo
stesso file.

---

## 4. Dove siamo arrivati

| componente | metrica | valore | confronto |
|---|---|---|---|
| Parser CV | F1 | **0,878** | 0,623 iniziale |
| Parser annunci | F1 | **0,629** | 0,391 iniziale |
| Parser annunci — occupazione | accuratezza | 75,9% | 87,5% a livello ISCO |
| Estrattore seniority | accuratezza | 92,3% | 33,3% caso |
| Matching CV → offerte | Precision@1 | 96,7% | — |
| Matching offerta → candidati | Precision@1 | **90,0%** | 1,7% caso |
| Livello di esperienza | accuratezza | 97,0% | 37,0% prima della correzione |
| Corsi | copertura effettiva | **23,3%** | 43,1% nominale |

**Nessuno di questi numeri va letto da solo.** Ognuno porta un vincolo
metodologico che ne cambia il significato, documentato in
`docs/risultati_sessione.md`.

Il più importante: la ground truth del dataset sintetico è **l'elenco di
competenze dato in input al generatore**, non quelle che ha davvero scritto.
Quindi tutte le metriche sono un **limite inferiore**.

---

## 5. Cosa è stato provato e scartato

Non rifarle: sono state misurate e documentate.

| tentativo | esito | perché |
|---|---|---|
| Stadio di match lessicale | scartato | precisione incrementale 0,27 contro 0,53 del semantico |
| Correzione hubness sul parser annunci | nessun effetto | il problema era nelle query, non nelle etichette |
| Vincolo di reciprocità | inefficace | presupponeva ripetizioni *dentro* il documento; il fenomeno era *fra* documenti |
| Filtri del parser CV riusati sugli annunci | nessun effetto | tarati su un difetto diverso |
| Encoder `gte-multilingual-base` | escluso | difetto non deterministico nel codice remoto del modello |
| Encoder `multilingual-e5-large` | escluso | costo di calcolo sproporzionato |

---

## 6. ⚠️ Le trappole — leggere prima di toccare qualsiasi cosa

**`outputs/INDICE.md` è fermo al 20 agosto.** Doveva servire proprio a
distinguere i risultati attuali da quelli superati, e non conosce i dieci file
prodotti dopo. **Aggiornalo come prima cosa.**

**Non fidarti dei nomi dei file.** `recruiter_attuale.json` contiene la misura
con il peso del livello **sbagliato** (γ = 0,3): quella valida è
`recruiter_sw010.json`. `batch_job_results.json` è del **16 luglio** e precede
tre tornate di modifiche: lo usa solo il frontend, nessun numero della tesi.

**Due ambienti Python.** Quello normale ha tutto il progetto. `.venv-esco` ha
solo `transformers` e `torch`, e serve **unicamente** per
`analysis/prova_escoxlmr.py`. Non mescolarli: `valida_recruiter.py` lanciato
nel secondo fallisce perché manca numpy.

**`requirements-bloccato.txt` è in UTF-16** (effetto di `pip freeze >` in
PowerShell) e `pip install -r` non lo legge. Riconvertilo in UTF-8 prima di
usarlo. Quello buono per installare è `requirements.txt`.

**I 15 curriculum reali contengono dati personali veri.** Vanno sempre parsati
con `--anonimo`, e il file `*_nomi.json` con la corrispondenza **non va mai**
allegato, pubblicato o messo sotto controllo di versione.

**Le soglie non sono trasferibili fra modelli.** Se cambi l'encoder devi
ricalibrarle con `analysis/calibra_soglie.py`, altrimenti i risultati non
significano niente. Succede silenziosamente: il modello sembra pessimo e non lo è.

**Le cache di embedding sono per modello.** Il nome del file contiene il nome
del modello. Se togli quel suffisso, un modello carica la cache di un altro e
produce punteggi impossibili (sopra 1,0). È già successo.

---

## 7. Da dove ripartire

In ordine di rapporto fra valore e costo.

### a) Finire l'annotazione dei curriculum reali — **già cominciata**

Lo strumento è pronto e il pool è generato: **334 candidati su 15 documenti**.
Sono stati giudicati **35 candidati su un solo documento** — quindi manca il
resto.

```bash
python -m streamlit run app/annota_cv.py        # annotazione
python analysis/valuta_annotazione.py           # metriche su dati reali
```

Produce la prima misura di precision e recall **non contaminata** dal
generatore. È il limite principale di tutto il lavoro.

Lo strumento tiene nascosta la frase da cui nasce ogni proposta — per non
influenzare chi giudica — e registra quando viene rivelata, così l'effetto si
può misurare. E permette di **aggiungere** competenze che il sistema non ha
proposto: è l'unico modo di misurare il richiamo invece di assumerlo.

### b) Completare il confronto con ESCOXLM-R

È l'unica casella vuota del disegno sperimentale: al riconoscimento dei
candidati è stato misurato il *difetto* dell'approccio a regole, mai
l'*alternativa*.

Il primo stadio è già verificato — 7 frammenti privi di contenuto su 10.045
span, contro i 792 falsi positivi del solo `responsible`. Gli span sono già
estratti in `outputs/span_escoxlmr.json`, lo script di valutazione è scritto.

```bash
# nell'ambiente .venv-esco
python analysis/prova_escoxlmr.py --sorgente gt --annunci 810 --out outputs/span_escoxlmr.json
# nell'ambiente normale
python analysis/valuta_escoxlmr.py
```

⚠️ Non presentarlo come un confronto di F1 alla pari: le soglie e la denylist
locali sono tarate su quegli stessi annunci, e la ground truth penalizza un
estrattore di span. Le asimmetrie sono documentate in testa allo script.

### c) Corsi: usare la descrizione invece del tag

Oggi l'indice collega i corsi ai **tag** della piattaforma, non alle
competenze: il punteggio misura la somiglianza fra competenza e tag, non se il
corso insegni quella competenza. Da qui il crollo da 43,1% a 23,3%.

La correzione è un cambio di ingresso, non di algoritmo: calcolare la
similarità con la **descrizione del corso**. Ed è già misurabile — i giudizi
manuali su 65 raccomandazioni sono un banco di prova pronto.

### d) Generatore: competenze diverse per livello

Nel dataset sintetico la seniority cambia **quante** competenze sono richieste
(10,8 junior → 16,2 senior) ma non **quali**. Per questo lo scenario di
avanzamento di carriera non produce divari misurabili.

È l'intervento più costoso: rigenerare il dataset obbliga a rifare ogni misura
a valle. Da fare per ultimo.

### Altre cose aperte, minori

- Riconoscimento delle intestazioni di sezione: 2 CV reali su 15 senza sezione
  esperienze riconosciuta.
- Tre formati di data non coperti dall'estrattore degli anni.
- I venti annunci reali non sono mai stati raccolti (cartella predisposta in
  `Desktop/mine/annunci_reali`).

---

## 8. Dove leggere cosa

| documento | contenuto |
|---|---|
| `relazione_progetto.md` | descrizione completa del sistema, modulo per modulo |
| `risultati_sessione.md` | **tutti i risultati misurati**, con i comandi per riprodurli |
| `guida_studio.md` | i concetti spiegati uno per uno, con «cosa devi saper spiegare» |
| `validazione_skill_graph.md` | l'ordinamento del divario, misurato contro la gerarchia ESCO |
| `prova_cv_reali.md` | la prova sui 15 curriculum veri |
| `revisione_corsi.md` | la revisione manuale delle raccomandazioni |
| `struttura_tesi.md` | la mappa della tesi, capitolo per capitolo |
| `casi_tracciati.md` · `log_sessione_*.md` | registri di sessioni specifiche, **datati**: non aggiornati |

La tesi completa è in una cartella separata. I risultati che contiene
corrispondono a `risultati_sessione.md`.

---

## 9. Il principio che ha guidato il lavoro

Vale la pena dirlo, perché è quello che distingue questo progetto da un sistema
costruito e basta.

Ogni numero è stato riportato **insieme al vincolo che ne cambia il
significato**. Applicato con rigore, questo ha funzionato da strumento
diagnostico: ha trovato difetti reali che un confronto meno attento avrebbe
lasciato passare, e in almeno un caso avrebbe fatto concludere l'esatto
contrario di ciò che era vero.

Tre esempi, tutti documentati:

- un componente valutato solo su dati sintetici va considerato **non valutato**
  (le certificazioni avevano precisione 0,250 da mesi, e nessuna metrica lo
  segnalava);
- un parametro ottimizzato su un test che isola una dimensione può **peggiorare
  tutte le altre** (il peso del livello a 0,3);
- un confronto fra due metodi va fatto con **separazione rigorosa** fra dati di
  costruzione e di test, altrimenti dà il risultato opposto (denylist contro
  classificatore: 0,747 contaminato, 0,721 corretto).

Se aggiungi un componente, misuralo **separatamente** e cerca il modo in cui la
misura potrebbe ingannarti. È lì che il lavoro ha prodotto i risultati
migliori.

Buon lavoro.
