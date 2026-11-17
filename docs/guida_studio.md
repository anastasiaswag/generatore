# SkillPath AI — Guida allo studio

Documento di ripasso su tutto il lavoro svolto: i concetti, le scelte, gli
errori e i numeri. Serve a ricostruire il ragionamento dall'inizio, non solo a
ricordare i risultati.

Ogni sezione si chiude con **"Cosa devi saper spiegare"**: sono le domande che
un relatore o un commissario può fare, e a cui conviene arrivare preparati.

---

## Indice

1. [Il problema](#1-il-problema)
2. [Stato dell'arte](#2-stato-dellarte)
3. [L'architettura del sistema](#3-larchitettura-del-sistema)
4. [Storia del parser dei CV](#4-storia-del-parser-dei-cv)
5. [Storia del parser degli annunci](#5-storia-del-parser-degli-annunci)
6. [Il classificatore appreso](#6-il-classificatore-appreso)
7. [Il matching engine](#7-il-matching-engine)
8. [Il raccomandatore di corsi](#8-il-raccomandatore-di-corsi)
8-bis. [L'ordinamento del divario formativo](#8-bis-lordinamento-del-divario-formativo)
9. [Le metriche e come si leggono](#9-le-metriche-e-come-si-leggono)
10. [Il confronto multimodello](#10-il-confronto-multimodello)
11. [Limiti da dichiarare](#11-limiti-da-dichiarare)
12. [Glossario](#12-glossario)
13. [La prova su curriculum reali](#13-la-prova-su-curriculum-reali)

---

## 1. Il problema

Un curriculum e un annuncio di lavoro descrivono le due facce della stessa
realtà — ciò che una persona sa fare, ciò che un'organizzazione cerca — ma con
parole scelte in modo indipendente. Un candidato scrive di aver progettato
applicazioni per iOS; l'annuncio chiede esperienza di sviluppo mobile. Un
lettore umano riconosce la corrispondenza. Un sistema che confronti i due testi
parola per parola non ne trova alcuna.

Il compito è quindi ricondurre testo libero a un insieme di competenze
appartenenti a un **vocabolario condiviso**, così che documenti scritti da
autori diversi diventino confrontabili.

Perché serve un vocabolario di riferimento e non bastano le parole del testo:

1. **Sinonimia.** «analisi dei dati» e *data analytics* designano la stessa
   capacità, e nulla nella loro forma superficiale lo segnala.
2. **Formulazione implicita.** Una competenza può non essere mai nominata e
   risultare comunque descritta: «saper ricavare informazioni da insiemi di
   dati e comunicarle con rappresentazioni grafiche» non contiene la parola che
   la riassume.
3. **Ciò che viene dopo.** Se ogni competenza ha un identificativo stabile
   invece di essere una stringa, si può calcolare cosa manca a un candidato
   rispetto a una posizione, e da quel divario derivare percorsi formativi. Con
   il confronto fra stringhe nessuna di queste operazioni è possibile.

### Cosa devi saper spiegare

- Perché il confronto lessicale fra CV e annuncio non funziona, con un esempio.
- Perché serve una tassonomia e non solo un buon modello di similarità.

---

## 2. Stato dell'arte

### 2.1 L'architettura dei sistemi industriali

Il riferimento è il sistema con cui LinkedIn alimenta il proprio *Skills
Graph*. Il vocabolario è proprietario e conta oltre **41.000 competenze**. La
pipeline ha quattro fasi:

| Fase | Cosa fa |
|---|---|
| **Segmentazione** | divide il documento nelle sue parti (descrizione azienda, mansioni, requisiti, benefici): una competenza nei requisiti pesa diversamente da una nella presentazione aziendale |
| **Tagging** | due riconoscitori affiancati — uno per corrispondenza esatta su struttura trie, uno semantico a due torri basato su BERT multilingue |
| **Espansione** | aggiunge competenze imparentate attraverso le relazioni del grafo |
| **Punteggio multitask** | un modello addestrato assegna a ogni coppia documento-competenza un punteggio, usando contesto testuale, relazioni fra entità e tipo di documento |

**L'osservazione che orienta tutta la tesi.** In quell'architettura il
confronto semantico **non decide: propone**. I due riconoscitori generano
candidati con criterio inclusivo, e quali conservare lo stabilisce lo stadio
successivo, addestrato su dati etichettati e su segnali raccolti in produzione
(correzioni dei selezionatori, segnalazioni dei candidati, esiti delle prove di
valutazione). La misura di similarità non è mai il criterio finale di
accettazione.

Questo separa un sistema costruito con risorse industriali da uno costruito
senza. Chi non ha dati etichettati né segnali d'uso è portato ad adottare la
similarità *come* decisione, per mancanza di alternative: si fissa una soglia e
si accetta ciò che la supera. È esattamente la scelta fatta in questo progetto,
ed è la causa diretta della difficoltà principale incontrata (§5).

Accanto a LinkedIn operano parser commerciali come Textkernel, che normalizzano
verso tassonomie proprietarie o standard (O\*NET, ISCO). Anche in quel caso il
vocabolario è distinto da ESCO, e la riconciliazione fra tassonomie diverse è
un problema a sé: allineare le competenze di un parser commerciale a ESCO ha
richiesto, in un lavoro dedicato, misure di somiglianza approssimata fra
stringhe.

### 2.2 ESCO

**ESCO** (*European Skills, Competences, Qualifications and Occupations*) è la
tassonomia multilingue mantenuta dalla Commissione Europea. Nel progetto:

| Elemento | Quantità |
|---|---|
| Occupazioni | 3.039 |
| Competenze | 13.939 |
| Etichette indicizzate per le competenze (denominazione + alternative) | 98.847 |
| Etichette indicizzate per le occupazioni | 19.201 |

> **Nota.** La relazione riporta 100.393 etichette totali. Il conteggio
> ricalcolato sui file del progetto dà 98.847 per le competenze e 19.201 per le
> occupazioni. Prima della consegna va deciso quale cifra usare e resa
> coerente ovunque.

Attributi che tornano più avanti:

- **`alt_labels`** — denominazioni alternative. Sono ciò che rende praticabile
  anche il riconoscimento per corrispondenza esatta.
- **`reuse_level`** — quanto una competenza è trasversale: *transversal*,
  *cross-sector*, *sector-specific*, *occupation-specific*. Diventa un
  attributo del classificatore (§6).
- **`skill_type`** — distingue conoscenza (*knowledge*) da competenza
  (*skill/competence*).
- **Collegamento a ISCO** — la classificazione internazionale delle
  professioni, usata per definire i «settori» nella validazione della
  monotonia (§7).

Una proprietà di ESCO che ha avuto conseguenze concrete: **circa il 29% delle
etichette descrive attività invece che competenze nominali** («manage musical
staff», «perform toxicological studies»). Sono 29.093 etichette, filtrate via
espressione regolare sul verbo iniziale.

### 2.3 Estrazione di competenze da testo

Il compito: dato un testo libero, individuare i concetti di una tassonomia
chiusa. Due famiglie di approcci:

| | Lessicale | Semantico |
|---|---|---|
| Come | dizionari, trie, espressioni regolari | rappresentazioni dense e similarità |
| Pregi | preciso, veloce, spiegabile | robusto alle riformulazioni |
| Difetti | fragile: riconosce solo forme previste | rumoroso: accetta somiglianze spurie |

I sistemi industriali usano **entrambi**. Questo progetto implementa il solo
stadio semantico. Uno stadio lessicale è stato provato e scartato (§5).

### 2.4 Modelli di embedding

Un *embedding* è la rappresentazione di un testo come vettore di numeri, tale
che testi di significato simile finiscano vicini. La vicinanza si misura con la
**similarità del coseno**: con vettori normalizzati (‖u‖ = ‖v‖ = 1) coincide
con il prodotto scalare, e vale al massimo 1.

Il progetto usa **`intfloat/multilingual-e5-base`**, 768 dimensioni. La
famiglia E5 è addestrata con obiettivo contrastivo debolmente supervisionato e
richiede **prefissi** per distinguere le interrogazioni dai documenti:

```
passage: mechanical engineer          ← etichette ESCO (il database)
query:   INGEGNERE MECCANICO          ← candidati estratti dal documento
```

L'uso è **zero-shot**: nessun fine-tuning sul dominio, giustificato
dall'assenza di dati annotati.

Una proprietà di questa famiglia risulta decisiva nel confronto multimodello
(§10): l'addestramento contrastivo **concentra le similarità in alto**. Con
e5-base nessun match del sistema scende sotto 0,789. Un coseno non ha
significato assoluto: dipende da come il modello è stato addestrato.

**Hubness.** Nelle rappresentazioni dense alcuni vettori compaiono fra i vicini
di quasi tutti gli altri. È un fenomeno noto, e nel progetto è stata provata
una contromisura — sottrarre a ogni etichetta la sua similarità media contro un
corpus di background. Non ha funzionato, e il perché è istruttivo (§5).

### 2.5 Distant supervision

Quando non ci sono annotazioni manuali, le etichette si ricavano da una fonte
indiretta. Qui: le competenze «vere» di un annuncio sono quelle che il
generatore ha campionato da ESCO per quell'occupazione.

Ne discendono due conseguenze da dichiarare sempre:

- **Compromesso soglia/falsi positivi** — abbassare la soglia aumenta il
  richiamo e peggiora la precisione.
- **Falsi negativi da annotazione incompleta** — una competenza realmente
  citata nel testo, ma non campionata dal generatore, viene contata come
  errore. Le metriche sono un **limite inferiore**.

### Cosa devi saper spiegare

- Le quattro fasi dell'architettura di LinkedIn e perché ne servono due di
  riconoscimento invece di una.
- Perché la similarità là propone e non decide, e cosa comporta non averlo
  fatto qui.
- Cosa sono `reuse_level` e `alt_labels` e dove ricompaiono nel sistema.
- Perché i prefissi `query:` / `passage:` non sono un dettaglio.
- Perché un coseno di 0,85 non significa la stessa cosa per due modelli diversi.

---

## 3. L'architettura del sistema

```
CV (PDF/DOCX)                          Annuncio (testo libero)
     │                                          │
     ▼                                          ▼
 main_parser.py                            job_parser.py
 segmentazione per sezioni             segmentazione per frasi
 estrazione candidati                  estrazione candidati (RAKE-like)
     │                                          │
     └──────────────► semantic_mapper.py ◄──────┘
                  indice bilingue IT+EN
                  similarità del coseno
                  soglie calibrate
                            │
                            ▼
                    matching_engine.py
              copertura + similarità + livello
                            │
                            ▼
                  course_recommender
              corsi per le competenze mancanti
```

### I moduli, e due dettagli che sfuggono

| modulo | ruolo |
|---|---|
| `main_parser.py` | parser dei curriculum |
| `job_parser.py` | parser degli annunci |
| `semantic_mapper.py` | nucleo condiviso: indice bilingue, embedding, cache, ricerca |
| `matching_engine.py` | confronto fra i due profili, punteggio e skill gap |
| `skill_graph.py` | ordina lo skill gap per priorità di apprendimento |
| `course_recommender.py` | raccomandazione dei corsi sul gap |
| `filtro_skill.py` | classificatore appreso, inferenza (§6) |
| `pdf_extractor.py` | estrazione testo da PDF e DOCX |
| `generate_dataset.py` | genera gli 810 curriculum sintetici |
| `generate_jobs.py` | genera gli 810 annunci sintetici |
| `render_cvs.py` | rende i curriculum in PDF su tre template |

**Due generatori, non uno, e due fornitori diversi.** È un dettaglio che sfugge
facilmente e che va detto giusto in tesi: i curriculum sono generati da
`generate_dataset.py` con Llama 3.3 70B via **Groq**; gli annunci da
`generate_jobs.py` con lo stesso modello ma via **OpenRouter**. Il cambio di
fornitore ha una ragione pratica documentata nel codice — il tetto di 100.000
token al giorno del piano gratuito di Groq avrebbe richiesto circa venti giorni
per generare gli 810 annunci. Il modello resta lo stesso, quindi i due dataset
restano coerenti fra loro.

**Il nucleo è condiviso**: entrambi i parser usano lo stesso indice e lo stesso
modello. Ciò che li distingue non è il matching, ma **come arrivano ai
frammenti da confrontare**. È lì che si gioca tutta la differenza di qualità —
trenta punti di F1.

L'indice è **bilingue**: contiene etichette italiane e inglesi più i sinonimi.
Un documento in italiano e uno in inglese si risolvono sui medesimi
identificativi.

### Cosa devi saper spiegare

- Perché due parser distinti e non uno solo con due modalità.
- Cosa condividono esattamente e cosa no.

---

## 4. Storia del parser dei CV

Il parser dei CV è arrivato ai suoi numeri per gradi, e la sua storia è
importante quanto quella del job parser: il risultato finale sembra ovvio solo
a posteriori.

### 4.1 Come funziona

1. **Estrazione del testo** — PyMuPDF per i PDF, python-docx per i DOCX
   (necessario per il template Europass, che usa tabelle a due colonne).
2. **Segmentazione per sezione** — riconosce le intestazioni (`Competenze`,
   `Esperienza`, `Istruzione`, `Lingue`, `Certificazioni`) su due percorsi
   paralleli: header in maiuscolo per il template *modern*, header misto per
   *classic* ed *europass*.
3. **Estrazione dei candidati** dalle sole sezioni pertinenti, sfruttando la
   struttura tipografica: una skill per riga, elenchi separati da virgola,
   contenuti fra parentesi.
4. **Percorso separato per sigle e CamelCase** (`VBA`, `SolidWorks`), estratte
   dal testo grezzo perché spesso annegate in frasi lunghe.
5. **Match semantico** con soglie 0,85 (parola singola) / 0,88 (frase) / 0,85
   (sigle).
6. **Filtri post-semantici** in cascata.
7. **Percorsi dedicati** per lingue (parole chiave + livello CEFR), titoli di
   studio e certificazioni.

### 4.2 I filtri, e perché ciascuno esiste

| Filtro | Cosa elimina | Quante etichette |
|---|---|---|
| 1 — etichette ≤ 4 caratteri | sigle ambigue: «R», «VB» | 285 (0,3%) |
| 2 — etichette con articolo iniziale | frammenti di frase: «a cosmetics ingredient» | 259 (0,3%) |
| 3 — etichette task-oriented | attività invece di competenze: «manage musical staff» | 29.093 (29,0%) |
| 3-bis — nomi di lingua | «francese», «neerlandese» già estratti dal rilevatore dedicato | — |
| 4 — termini di attrezzatura | «office apparatus» accettato solo se la parola compare nel testo | — |

Il filtro 4 merita attenzione: previene un falso positivo insidioso, «office
apparatus» che aggancia semanticamente un CV contenente «Microsoft Office».

Esiste anche un **filtro pre-candidati** che rimuove dati anagrafici, date
isolate, parole singole minuscole e sigle societarie prima di interrogare il
modello.

### 4.3 L'evoluzione, con i numeri

| Versione | Precision | Recall | F1 |
|---|---|---|---|
| baseline iniziale | 0,760 | 0,547 | 0,623 |
| dopo dizionario supplementare di alias e filtri | 0,865 | 0,860 | 0,857 |
| **dopo filtro sui nomi di lingua** | **0,907** | **0,860** | **0,878** |

**Il primo salto è sul richiamo**, da 0,547 a 0,860. La causa: il filtro 3
eliminava il 29% delle etichette ESCO perché formulate come attività, ma fra
quelle c'erano competenze legittime. Il **dizionario supplementare di alias
italiani** le recupera. È il caso in cui una contromisura ha effetti
collaterali che vanno compensati, non un errore da annullare.

**Il secondo salto è sulla precisione**, da 0,865 a 0,907. ESCO cataloga le
lingue come competenze, quindi le lingue dichiarate nel CV venivano estratte
**due volte**: dal rilevatore dedicato con il livello CEFR, e di nuovo come
skill dal matching semantico. L'analisi ha quantificato il fenomeno:

- 489 falsi positivi su 1.480 totali, **circa un terzo**
- «francese»: 183 occorrenze errate e **nessuna corretta**
- «neerlandese» 111, «spagnolo» 76

Il filtro elimina tutti e 489 senza perdere alcun vero positivo.

### 4.4 Risultati finali

| | Precision | Recall | F1 |
|---|---|---|---|
| Complessivo (810 CV) | 0,907 | 0,860 | 0,878 |

Per template: `classic` 0,905 · `europass` 0,872 · `modern` 0,858.
Per livello: junior 0,885 · mid 0,877 · senior 0,873.

TP 9.822 · FP 991 · FN 1.961.

### 4.5 I falsi negativi residui

Due categorie:

1. **Soft skill** espresse con formule italiane standardizzate («ottime doti
   comunicative») che hanno bassa similarità con le etichette ESCO inglesi
   corrispondenti («use different communication channels»). La competenza più
   mancata in assoluto è proprio questa: assente in 98 CV su 810 (12,1%).
2. **Competenze di dominio non presenti in ESCO** con quella terminologia:
   SolidWorks, AutoCAD per versione, metodologie Kanban.

### Cosa devi saper spiegare

- Perché il richiamo è salito da 0,547 a 0,860 e cosa c'entra il filtro sui verbi.
- Il caso «francese»: 183 errori e zero successi. Perché è un errore
  *sistematico* e non rumore.
- Perché il parser CV va molto meglio del job parser, senza dire «è migliore».

---

## 5. Storia del parser degli annunci

È la parte con la narrazione più chiara del progetto: un problema misurato,
un'indagine, quattro tentativi falliti e una soluzione che nasce dal capire
perché il terzo non funzionava.

### 5.1 Perché è più difficile

Gli annunci non hanno struttura affidabile. Non si può segmentare per sezioni,
quindi si lavora sull'intero testo: divisione in frasi, poi estrazione dei
candidati spezzando ogni frase sui confini delle parole funzionali (approccio
ispirato a **RAKE**): le sequenze di parole di contenuto fra due stopword
diventano candidati.

Non è un componente di qualità inferiore. È un problema più difficile.

### 5.2 Il punto di partenza: F1 0,391

Senza alcun rimedio: Precision 0,297 · Recall 0,615 · F1 0,391. Il parser
estraeva **1,99 volte** le competenze attese. Quasi tutta la perdita di
precisione veniva dalla sovraproduzione.

### 5.3 L'indagine

Applicando il segmentatore a una frase come

> *«The successful candidate will be responsible for coordinating technological
> activities, using our ICT ticketing system»*

si ottengono sette candidati: tre competenze reali e quattro detriti —
`successful`, `responsible`, `using`, `complying`.

La corrispondenza con gli errori è **esatta**:

| candidato | annunci in cui compare | etichetta agganciata | falsi positivi |
|---|---|---|---|
| `responsible` | 792 | comportarsi in modo responsabile | 792 |
| `seeking` | 773 | motori di ricerca | 772 |

**Il punto concettuale più importante del progetto.** Per il candidato
`responsible`, l'etichetta ESCO *«comportarsi in modo responsabile»* è il match
**corretto**. Il difetto non era nel modello né nell'ontologia: era **nella
domanda che veniva posta**. Si stava chiedendo al modello di trovare la
competenza più simile a un frammento grammaticale privo di contenuto, e il
modello rispondeva bene a una domanda malposta.

Da qui si capisce anche perché le contromisure sul lato ontologia non potevano
funzionare: nessuna penalizzazione delle etichette rimedia a un candidato
privo di contenuto semantico.

### 5.4 La soluzione

Accettare dalla prosa **solo candidati di almeno due parole**. Elimina il 45,5%
dei candidati e quasi tutti i falsi positivi sistematici, al costo di 3,5 punti
di richiamo.

### 5.5 L'ablazione completa

| configurazione | Precision | Recall | F1 |
|---|---|---|---|
| nessun rimedio | 0,297 | 0,615 | 0,391 |
| denylist 232 etichette | 0,529 | 0,607 | 0,551 |
| vincolo multi-parola | 0,540 | 0,581 | 0,546 |
| multi-parola + denylist 232 | 0,600 | 0,575 | 0,572 |
| multi-parola + denylist 64 | 0,614 | 0,577 | 0,580 |
| **multi-parola + classificatore appreso** | **0,807** | 0,539 | **0,629** |

Occupazione: 75,9% di identificativo esatto, 87,5% di macro-settore ISCO.

### 5.6 Le quattro contromisure fallite

Vanno raccontate, non nascoste. Un risultato negativo con la diagnosi del
meccanismo vale quanto uno positivo.

| tentativo | esito | perché |
|---|---|---|
| **stadio di match lessicale** | scartato | il contributo *incrementale* aveva precisione 0,27, sotto lo 0,53 dello stadio semantico: peggiorava invece di aiutare |
| **correzione hubness** | nessun effetto | 0,298 contro 0,297. Il problema era nelle query, non nelle etichette |
| **vincolo di reciprocità** | inefficace | presupponeva ripetizioni *dentro* il documento; le etichette problematiche comparivano una sola volta per annuncio, in 792 annunci distinti. Il fenomeno è **fra** documenti, non dentro |
| **filtri del parser CV riusati** | nessun effetto | calibrati su un difetto diverso (nomi di lingua, verbi inglesi) |

Il caso della reciprocità è il più istruttivo: la contromisura era corretta in
sé, ma applicata a un fenomeno che aveva la forma sbagliata. Verificare la
*forma* del problema prima di scegliere il rimedio è la lezione.

### 5.7 La denylist

Elenco di etichette ESCO troppo generiche, ricostruito dopo la correzione al
segmentatore: **da 232 a 64**, perché 137 delle originali nascevano da
candidati ormai inesistenti.

Validata su holdout: lista costruita su 405 annunci, effetto misurato sugli
altri 405 mai visti — Precision 0,543 → 0,585, F1 0,551 → 0,570.

**Limite dichiarato.** A differenza del vincolo multi-parola, la lista è
ricavata osservando *quali predizioni erano sbagliate*: è supervisionata e
specifica del dominio. È il punto metodologicamente più debole della pipeline,
ed è la ragione per cui è stato costruito il classificatore.

### La conferma indipendente — ESCOXLM-R

La diagnosi «il difetto sta nella generazione dei candidati» è una
**spiegazione**, non una verifica: resta compatibile con l'ipotesi che il
problema sia intrinseco alla prosa e non a questa implementazione. Per
distinguerle serve un estrattore che non condivida il difetto per costruzione.

`jjzha/escoxlmr_skill_extraction` (ESCOXLM-R, ACL 2023, affinato su SkillSpan)
individua span di competenza senza tagliare sui confini delle parole
funzionali. Sugli stessi 810 annunci:

| | |
|---|---|
| span prodotti | 10.045 (12,4 per annuncio) |
| frammenti senza contenuto | **7 · lo 0,07%** |
| span di una sola parola | 2,97% |
| velocità | 0,7 s per annuncio in CPU |

Da confrontare con i **792** falsi positivi del solo `responsible`, e con il
45,5% di candidati che il vincolo multi-parola deve eliminare per contenere lo
stesso fenomeno.

**Le tre cose da dire se te lo chiedono.** Primo: non è un confronto di F1 e
non può esserlo — la ground truth elenca competenze che il generatore doveva
inserire e che a volte nel testo non ci sono, e quel costo un estrattore di
span lo pagherebbe per intero mentre le soglie locali vi sono state ottimizzate
contro. Secondo: la lingua non c'entra, gli annunci con ground truth sono in
inglese e SkillSpan pure. Terzo: il modello non ha mai visto questi annunci,
mentre soglie e denylist sì — quindi la conferma arriva in condizioni
sfavorevoli, ed è per questo che vale.

### Il resto del capitolo

**Riconoscimento dell'occupazione:** 75,9% sull'identificativo ESCO esatto,
87,5% sul macro-settore ISCO. È il compito su cui, nel confronto multimodello,
lo scarto fra encoder è massimo (0,336 contro 0,026) — perché lì non c'è
pipeline che assorba le differenze.

**Dove finisce il 46% di richiamo mancante.** TP 5.589 · FP 1.280 · FN 5.345,
separati in tre cause: 378 (7,1%) scartate dal classificatore per alzare la
precisione, 4.158 (77,8%) presenti nel testo ma non isolate dal segmentatore,
809 (15,1%) mai comparse nel testo generato — queste ultime colpa del
generatore, non del parser. Il primo numero viene da un confronto esatto fra
file, gli altri due da un'euristica lessicale: **dillo**, è la differenza fra
una misura e una stima.

### Cosa devi saper spiegare

- La catena `responsible` → 792 annunci → 792 falsi positivi, e perché il match
  era *corretto*.
- Perché la correzione hubness non poteva funzionare, dato quel difetto.
- Perché il vincolo di reciprocità era la risposta giusta a una domanda diversa.
- Perché la denylist è metodologicamente debole anche se funziona.
- Perché ESCOXLM-R è una **conferma** e non un confronto, e le tre ragioni per
  cui un confronto di F1 sarebbe stato scorretto.
- Le tre destinazioni dei falsi negativi, e quale delle tre non è colpa del
  parser.

---

## 6. Il classificatore appreso

### 6.1 La motivazione

Sostituire una regola scritta a mano osservando gli errori con una decisione
**appresa da attributi generali**, valutabile con la procedura standard
train/validation/test. È anche il modo in cui il progetto ricostruisce, con i
mezzi disponibili, lo stadio di decisione che l'architettura industriale colloca
a valle della similarità (§2.1).

### 6.2 I dati

Ogni competenza estratta è già etichettata dal confronto con la ground truth:
**11.071 esempi, 54,3% positivi**. Nessuna annotazione manuale.

### 6.3 La divisione, che è il punto metodologico decisivo

La divisione avviene **per occupazione, non per documento**. Addestrare su
alcuni annunci da «pizzaiolo» e testare su altri annunci dello stesso ruolo
significherebbe testare su competenze già viste. Con la divisione per
occupazione — 81 mestieri per addestrare, 27 per validare, 27 per il test — si
misura se il classificatore generalizza a **mestieri mai incontrati**, che è
ciò che accadrebbe in uso reale.

### 6.4 Gli attributi

Nessuno guarda l'identità della competenza, per evitare che il modello impari a
memoria una denylist:

`score` · `n_parole` · `lunghezza` · `freq_occupazioni` · `reuse_level`
(one-hot) · `è_conoscenza` · `grounding` (quota di parole dell'etichetta
presenti nel testo) · `rango` nel documento · `n_skill_documento` ·
`è_required` · `tasso_fp_storico`.

`tasso_fp_storico` è l'equivalente appreso e continuo della denylist, ma
**stimato solo sulle occupazioni di training**: non costituisce conoscenza del
test. Le etichette mai viste ricevono il valore medio, cioè nessun pregiudizio.

### 6.5 Il modello

**Regressione logistica** con discesa del gradiente, implementata in numpy. La
scelta è deliberata: i pesi restano leggibili.

| Attributo | Peso |
|---|---|
| Tasso di errore storico dell'etichetta | −2,943 |
| Competenza trasversale | −0,391 |
| Punteggio di similarità | +0,321 |
| Classificata come requisito | −0,172 |
| Competenza settoriale | +0,150 |

Da leggere così: il predittore dominante è la storia di errore dell'etichetta,
seguito dalla trasversalità — le competenze generiche sono più spesso sbagliate.
La similarità conta, ma **meno della metà** del tasso di errore storico. È la
conferma quantitativa che la similarità da sola non è un buon criterio di
decisione.

### 6.6 Il confronto onesto

Su 27 occupazioni mai viste, con entrambi i filtri costruiti sulle stesse 81 di
training:

| Filtro | Precision | Recall | F1 |
|---|---|---|---|
| Nessuno | 0,532 | 1,000 | 0,694 |
| Denylist (41 etichette) | 0,567 | 0,988 | 0,721 |
| **Classificatore appreso** | **0,643** | 0,856 | **0,734** |

**Perché la denylist qui ha 41 voci e non 64.** Quella di produzione era stata
costruita su tutti gli 810 annunci, incluse le occupazioni di test: confrontarla
così avrebbe dato 0,747, un numero contaminato. Ricostruita sulle sole
occupazioni di training scende a 0,721, e il classificatore vince.

Questo è il tipo di dettaglio che vale la pena raccontare: il confronto
sbagliato dava il risultato opposto.

### Cosa devi saper spiegare

- Perché la divisione è per occupazione e non per documento.
- Perché `tasso_fp_storico` non è imbroglio, e cosa lo distingue dalla denylist.
- Perché il primo confronto (0,747) era contaminato.

---

## 7. Il matching engine

### 7.1 La formula

```
skill_coverage = Σ contributo(skill_i) / total_weight
   contributo = 1,0 se corrispondenza esatta
              = sim se corrispondenza semantica ≥ 0,75
              = 0,0 se la competenza è nel gap
   total_weight = n_required + 0,5 × n_preferred

skill_score = (1 − β) × skill_coverage + β × n_coperte/(n_coperte + K)
   β = count_weight = 0,15      K = 10

base        = 0,75 × skill_score + 0,25 × occ_similarity
match_score = (1 − γ) × base + γ × seniority_alignment
   γ = seniority_weight = 0,10

seniority_alignment = 1,0 coincidenti · 0,5 adiacenti · 0,0 distanti due passi
```

> **Attenzione:** la sezione 7 di `relazione_progetto.md` riporta ancora
> γ = 0,3. Il valore corretto è **0,10** (vedi §7.3). Va corretto prima della
> consegna.

Se il livello di una delle due parti è ignoto, il termine viene **omesso**
anziché penalizzare: l'assenza del dato non è un difetto della corrispondenza.

### 7.2 Il difetto scoperto: la preferenza per le posizioni junior

Il punteggio era la sola frazione di requisiti coperti. Ma gli annunci junior
elencano meno requisiti:

| livello | competenze richieste (media) |
|---|---|
| junior | 10,77 |
| mid | 13,54 |
| senior | 16,19 |

Quindi la frazione risultava più alta a prescindere dal candidato. Misura su
100 CV: il motore sceglieva un annuncio junior **47 volte su 100** (atteso 33),
e l'accuratezza sul livello era 37,0% contro una baseline casuale del 33,3%. Il
sistema proponeva posizioni sotto-livello a chiunque avesse esperienza.

### 7.3 Le due correzioni, e la taratura del secondo peso

**Termine sul conteggio assoluto** (β = 0,15):

| peso | accuratezza | junior/mid/senior scelti |
|---|---|---|
| 0,00 | 37,0% | 47 / 29 / 24 |
| **0,15** | **44,0%** | **33 / 33 / 34** |
| 0,25 | 44,0% | 25 / 36 / 39 |
| 0,40 | 43,0% | 19 / 36 / 45 |

A 0,15 e 0,25 l'accuratezza coincide, ma solo a 0,15 le scelte sono
equilibrate. **A parità di errori è preferibile che siano rumore anziché una
tendenza sistematica.**

**Termine di allineamento del livello** (γ). Il valore iniziale era 0,3, tarato
sul solo test della seniority — che però confronta esclusivamente annunci della
*stessa occupazione*, dove il contenuto è costante. Il test di monotonia ha
rivelato il problema:

| confronto | occupazione | copertura | similarità | punteggio |
|---|---|---|---|---|
| stessa occupazione | telecommunications manager | 0,967 | 1,000 | **0,646** |
| settore diverso | mask maker | 0,881 | 0,805 | **0,711** |

Il CV era senior, l'annuncio della stessa occupazione junior: allineamento
nullo, trenta punti azzerati, confronto ribaltato. **Un parametro ottimizzato
su un test che isola una sola dimensione può compromettere il compito
principale.** A 0,10 la sovrapposizione fra livelli scende dal 40% al 2,5% e
l'accuratezza sul livello resta identica: il termine deve fare da spareggio,
non da criterio dominante.

### 7.4 I risultati

| | prima | dopo |
|---|---|---|
| Occupazione — Precision@1 | 96,7% | 96,7% |
| Occupazione — Precision@10 | 96,7% | 100,0% |
| Livello — accuratezza | 37,0% | 97,0% |
| Livello — accuratezza adiacente | 86,0% | 100,0% |
| Distorsione nelle scelte | 47/29/24 | 33/33/34 |

**Come leggere il 97%.** Non è una capacità emergente: il livello viene passato
esplicitamente dal job parser. Il numero che descrive una capacità è il
**92,3%** dell'estrattore di seniority. Il 97% dimostra che il collegamento
regge ed è robusto agli errori sul singolo annuncio, perché ogni occupazione ha
due annunci per livello e ne basta uno etichettato correttamente.

### 7.5 La direzione inversa

`analysis/valida_recruiter.py` — 20 annunci × 361 candidati, con i pesi
predefiniti (γ = 0,10, β = 0,15).

| Metrica | Valore |
|---|---|
| Precision@1 | 90,0% |
| Precision@3 | 100,0% |
| Precision@10 | 100,0% |
| MRR | 0,950 |
| Baseline casuale | 1,7% |

> **Da sapere se te lo chiedono.** Una prima misura era stata presa con
> γ = 0,3 — il valore dichiarato tarato male in §7.4 — e dava 85,0% e MRR
> 0,912. Correggere γ ha migliorato di **5 punti** anche questo compito, che
> non era quello per cui la correzione era stata fatta.

Più bassa che nel verso opposto (90% contro 96,7%): scegliere fra candidati
della stessa occupazione è più difficile che fra annunci, perché i CV variano
per livello e per sottoinsieme di competenze, mentre gli annunci di uno stesso
ruolo sono più omogenei.

**Un'ipotesi formulata e smentita — per ablazione, non per assenza.** Il
termine sul conteggio assoluto avrebbe potuto, in questa direzione, premiare i
curriculum più lunghi. La correlazione fra punteggio e lunghezza del CV, sui
soli candidati dell'occupazione sbagliata, è **+0,194**: debole, ma non nulla.

Il punto decisivo non è quel valore: è che **togliendo il termine sospetto la
correlazione non scende** — diventa 0,208. Non è quindi causata dal termine di
conteggio; resta perché i CV più lunghi elencano più competenze e hanno più
occasioni di sovrapporsi a un annuncio qualunque. Proprietà dei dati, non della
formula.

È più solido dell'argomento precedente. A γ = 0,3 la correlazione era +0,012 e
l'ipotesi veniva respinta per *assenza* di segnale — ma un valore basso può
sempre essere un caso. Respingerla per *ablazione* — rimuovo la causa sospetta,
l'effetto resta — è un argomento di natura diversa.

E a γ = 0,10 le due configurazioni coincidono su tutte le metriche di
ordinamento (90,0 · 100,0 · 0,950), mentre a γ = 0,3 differivano: conferma
esattamente la spiegazione teorica, cioè che in questa direzione il
denominatore della copertura è fisso e il termine assoluto non può alterare
l'ordine relativo fra candidati.

### 7.6 Il punteggio è una misura o solo un ordinamento?

| livello di affinità | media | mediana | min | max |
|---|---|---|---|---|
| stessa occupazione | 0,861 | 0,862 | 0,736 | 0,945 |
| stesso settore ISCO | 0,763 | 0,782 | 0,611 | 0,864 |
| settore diverso | 0,733 | 0,742 | 0,532 | 0,829 |

Sovrapposizione fra livelli contigui 2,5% e 12,5%: le distribuzioni sono
separate, quindi **il valore assoluto è informativo**, non solo l'ordinamento.
Conta perché se l'interfaccia mostra «compatibilità 72%», quel numero deve
significare qualcosa.

### 7.7 Il limite del test sull'occupazione

Il 96,7% sovrastima ampiamente la difficoltà. CV e annunci della stessa
occupazione sono generati campionando dalla **medesima** lista ESCO:

| coppia | sovrapposizione media (Jaccard) |
|---|---|
| stessa occupazione | 0,640 |
| stesso settore ISCO, occupazione diversa | 0,0164 |
| settore diverso | 0,0034 |

Il 93% delle coppie di occupazioni diverse non condivide **alcuna** competenza.
Al motore basta rilevare «hanno qualcosa in comune» per vincere. Il valore va
sempre riportato insieme a questa quantificazione.

Il test sulla seniority **non** ha questo problema: i sei annunci di una stessa
occupazione hanno competenze quasi identiche, quindi il segnale sul livello non
è replicato dalla costruzione del dataset.

### Cosa devi saper spiegare

- Perché gli annunci junior vincevano, e come si è corretto.
- Perché γ = 0,3 sembrava giusto e non lo era.
- Perché il 97% sul livello non è merito del matching engine.
- Perché il 96,7% va accompagnato dai numeri di Jaccard.

---

## 8. Il raccomandatore di corsi

### 8.1 La scelta dello scenario

Confrontare un candidato con un annuncio del lavoro che già svolge non produce
nulla da colmare: **0,17 competenze mancanti** per confronto, su circa 12
richieste.

| scenario | competenze mancanti distinte | copertura |
|---|---|---|
| stessa occupazione | 22 | 50,0% |
| avanzamento (junior/mid → senior stesso ruolo) | 8 | 37,5% |
| **transizione** (altra occupazione, stesso settore) | **72** | **43,1%** |

Solo la transizione produce un campione utilizzabile.

### 8.2 Un limite del dataset scoperto qui

Lo scenario di **avanzamento** avrebbe dovuto essere il più significativo — è
la progressione di carriera. Ha prodotto 10 occorrenze su 60 CV.

Il motivo: nel dataset sintetico la seniority cambia **quanto** viene
richiesto, non **che cosa**. I sei annunci di un'occupazione attingono alla
stessa lista ESCO; da junior a senior il numero sale da 10,8 a 16,2 ma la
natura resta identica. Un candidato junior possiede quindi già,
qualitativamente, ciò che l'annuncio senior richiede.

Nella realtà la progressione comporta competenze di tipo diverso —
coordinamento, responsabilità di budget, specializzazione. **È un limite del
dataset, non del raccomandatore**, e una direzione concreta per un lavoro
successivo.

### 8.3 Il limite è il catalogo, non l'algoritmo

Copertura dell'indice Coursera sull'intera ontologia:

| settore ISCO | competenze | con corso |
|---|---|---|
| Professioni intellettuali | 7538 | 32,4% |
| Dirigenti | 3557 | 32,2% |
| Impiegati | 1360 | 27,9% |
| Tecnici | 6325 | 26,5% |
| Servizi e vendite | 2234 | 22,0% |
| Artigiani | 3542 | 19,5% |
| Agricoltura | 768 | 16,8% |
| Conduttori di impianti | 3126 | 15,4% |
| Professioni non qualificate | 1319 | 15,2% |
| **totale** | **13475** | **23,7%** |

Il gradiente supera il doppio fra lavoro intellettuale e manuale. Coursera è un
catalogo accademico e tecnologico: «tipi di pelle» o «manage crop rotation» non
vi compaiono.

**Il 43,1% osservato è quasi il doppio del 23,7% medio**: le competenze che
emergono come mancanti sono meglio coperte della media. È un limite di dominio,
non algoritmico.

### 8.4 La pertinenza, misurata a mano

Il 43,1% verifica che per una competenza mancante **esista** un corso. Non che
sia pertinente. Sono due domande diverse, ed era stata verificata solo la prima.

Trenta competenze estratte a caso, 65 raccomandazioni giudicate una per una:

| indicatore | conteggio | valore | IC 95% |
|---|---|---|---|
| corsi pertinenti | 12/65 | 18,5% | 10,9% – 29,6% |
| corsi non pertinenti | 40/65 | **61,5%** | 49,4% – 72,4% |
| copertura nominale | — | 43,1% | — |
| **copertura effettiva** | 7/30 | **23,3%** | 11,8% – 40,9% |

L'intervallo della copertura effettiva arriva al 40,9% e **non contiene il
43,1%**: la differenza non è attribuibile al caso. Un primo campione di dieci
competenze non lo permetteva — l'intervallo andava dal 5,7% al 51% — ed è la
ragione per cui è stato ampliato a trenta.

**Il difetto sta nella costruzione dell'indice.** I corsi non vengono abbinati
alle competenze: vengono abbinati i **tag**, e poi tutti i corsi che portano
quel tag finiscono attribuiti alla competenza.

```
competenza ESCO ──(similarità)── tag ──(appartenenza)── corso
```

Solo il primo anello è misurato. Il campo `esco_match_score` nell'indice ha
l'aspetto di un punteggio di pertinenza, ma quantifica quanto il *tag* somigli
alla competenza e non dice niente sul *corso*.

**Quattro modi di sbagliare, tutti osservati nel campione:**

| modo | esempio |
|---|---|
| omonimia del tag | «richieste di preventivi» → tag «quotation» (anche: citazione) → corsi di scrittura |
| tag giusto, corso sbagliato | «debug di un software» → tag «debugging» corretto, corsi per maestri di scuola primaria |
| tag errato sul corso | «carne halal» → «I/O-efficient algorithms» via tag «daging» (carne in indonesiano) |
| concetto fuori contesto | «tecnologia di laboratorio medico» → corsi di informatica |

Nei casi riusciti il tag era specifico e tecnico: «cataract surgery»,
«test-driven development». **Il tag generico distrugge la pertinenza, quello
specifico la conserva.**

Il limite non è nell'algoritmo, che fa correttamente ciò che gli si chiede
sull'indice che riceve: è nell'indice. La direzione di lavoro che ne discende è
precisa — calcolare la similarità fra la **descrizione del corso** e la
competenza, non fra il tag e la competenza.

### Cosa devi saper spiegare

- Perché lo scenario «stessa occupazione» non serviva a niente.
- Perché il 43,1% va confrontato con il 23,7% e non con il 100%.
- La differenza fra copertura **nominale** ed **effettiva**, e perché la prima
  sembrava una misura di qualità senza esserlo.
- Perché dieci competenze non bastavano e trenta sì: con dieci l'intervallo
  conteneva il valore nominale, quindi non permetteva alcuna conclusione.
- I quattro modi di sbagliare, con un esempio ciascuno.

---

## 8-bis. L'ordinamento del divario formativo

Prima di consigliare un corso il sistema deve decidere **quale competenza
mancante imparare per prima**. Se ne occupa `skill_graph.py` con un punteggio
composito: 40% frequenza fra le occupazioni, 40% trasversalità (`reuse_level`),
20% prossimità con quello che il candidato già sa.

Per mesi è stato l'unico componente della pipeline **senza una misura**. I pesi
erano stati scelti, non derivati, e la componente di prossimità si stimava
contando quante volte due competenze comparivano nella stessa occupazione —
un surrogato, adottato perché il dataset scaricato all'inizio non conteneva le
relazioni fra competenze.

### Che cosa contiene davvero ESCO

Scaricati i file ufficiali, la struttura si è rivelata diversa dall'attesa.

| file | contenuto | copertura |
|---|---|---|
| `skillSkillRelations.csv` | 5.818 **dipendenze** orientate (189 `essential`, 5.629 `optional`) | 41% delle competenze |
| `broaderRelationsSkillPillar.csv` | 20.183 righe di **gerarchia** | **100%** |

Il file utile è il secondo, non quello dal nome più promettente: da 5.818
dipendenze non si può ordinare un divario qualsiasi, perché sei volte su dieci
non dicono nulla.

Dalla gerarchia si ricava la similarità di **Wu-Palmer**: due competenze sono
tanto più vicine quanto più in basso sta il concetto che le contiene entrambe.
Python e Java danno 0,800; Python e «tecniche di potatura» danno 0,000, perché
si incontrano solo alla radice.

Due trappole che vale la pena saper raccontare. ESCO ha **quattro radici**
distinte, non una, quindi due competenze possono non avere alcun antenato in
comune. E la profondità va calcolata come cammino **più lungo**, non più corto:
«programmazione informatica» e «Python» pendono dallo stesso gruppo e al tempo
stesso la prima è dichiarata più generale della seconda — contando i passi
minimi risultavano alla stessa profondità e la formula restituiva 1,000, cioè
identità, per Python e Java.

### I due risultati della validazione

**La ricostruzione non era arbitraria, ma veniva usata male.** Le coppie che la
co-occorrenza giudica vicine sono 2,5 volte più vicine del caso (0,103 contro
0,040). Però la correlazione di rango fra *quante volte* due competenze
co-occorrono e la loro vicinanza reale è **ρ = 0,033**, cioè nulla:
l'informazione era binaria, il codice la trattava come graduata.

**Un difetto di normalizzazione, trovato misurando.** I contributi effettivi
delle tre componenti non somigliano ai pesi nominali:

| componente | peso nominale | contributo reale |
|---|---|---|
| trasversalità | 40% | **72,6%** |
| frequenza | 40% | 20,7% |
| co-occorrenza | 20% | **1,6%** |

`co_occurrence_score` normalizza dividendo una media di co-occorrenze (0–3) per
la frequenza massima (340). Sono grandezze diverse: la componente pesava un
ventesimo di quanto dichiarato.

Sostituendola con la prossimità tassonomica, a pesi invariati: **tau di Kendall
0,791**, ordine invariato nel 20,5% dei casi, prima competenza raccomandata
cambiata nel **14,2%**.

### L'errore di campionamento, da raccontare

Il primo tentativo dava τ = 1,000 e zero cambiamenti — apparentemente la prova
che la sostituzione fosse inutile. Era invece il campione a essere degenere:
proveniva da `job_to_candidates_results.json`, che è il confronto di **un solo**
annuncio contro 810 candidati, quindi i 755 divari pescavano da **5 competenze
distinte**. Il campione definitivo — competenze `essential` dell'occupazione
meno quelle estratte dal parser, per ogni CV — ne ha 1.346.

È lo stesso schema delle certificazioni e dei corsi: una misura che sembrava
dire qualcosa sul sistema e diceva qualcosa sul campione.

### Cosa devi saper spiegare

- Perché il file dal nome più promettente (`skillSkillRelations`) è quello meno
  utile, e quello utile è la gerarchia.
- Che cos'è la similarità di Wu-Palmer, in una frase.
- Perché la profondità si conta come cammino più lungo — e cosa succedeva
  contandola come cammino più corto.
- La differenza fra «la co-occorrenza conteneva segnale» (vero) e «il numero di
  co-occorrenze misurava la vicinanza» (falso, ρ = 0,033).
- Perché un peso nominale del 20% valeva l'1,6%.
- Perché il primo campione dava il risultato sbagliato, e come te ne sei accorto.
- Che la prossimità nuova è **fondata, non validata**: viene da ESCO, ma nessuno
  ha verificato che l'ordine sia più utile a chi studia.

---

## 9. Le metriche e come si leggono

### 9.1 Le definizioni

```
Precision = TP / (TP + FP)     quanto di ciò che trovo è giusto
Recall    = TP / (TP + FN)     quanto di ciò che c'è riesco a trovare
F1        = 2PR / (P + R)      media armonica: penalizza gli squilibri
```

**Macro-media**: si calcola la metrica per ogni documento e poi si fa la media.
Ogni documento pesa uguale, indipendentemente da quante competenze contiene.

**Precision@k**: la risposta giusta è fra le prime k proposte.
**MRR**: media dei reciproci della posizione della risposta giusta. Premia
l'avere la risposta giusta *in alto*, non solo *dentro* la lista.

### 9.2 Il quadro d'insieme

| componente | metrica | valore |
|---|---|---|
| Parser CV | F1 | 0,878 |
| Parser annunci (denylist) | F1 | 0,580 |
| Parser annunci (classificatore) | F1 | **0,629** |
| Estrattore seniority | accuratezza | 92,3% |
| Matching CV → offerte | Precision@1 | 96,7% |
| Matching offerta → candidati | Precision@1 | 90,0% |
| Livello | accuratezza | 97,0% |
| Raccomandatore corsi | copertura del gap | 43,1% |

**Nessuno va letto isolatamente.** Ognuno ha un vincolo metodologico che ne
cambia il significato, e vanno riportati insieme:

- il 97% sul livello dipende dal 92,3% dell'estrattore;
- il 96,7% va accompagnato dal Jaccard 0,640 contro 0,003;
- il 43,1% va confrontato con il tetto del 23,7%;
- lo 0,629 è su dati sintetici che condividono il lessico con l'ontologia.

### 9.3 Le baseline

Un numero senza baseline non dice niente.

| compito | risultato | baseline |
|---|---|---|
| Livello | 97,0% | 33,3% (casuale su tre livelli) |
| Offerta → candidati | 90,0% | 1,7% |
| Copertura corsi | 43,1% | 23,7% (tetto del catalogo) |

### Cosa devi saper spiegare

- Differenza fra macro-media e micro-media, e perché qui si usa la prima.
- Perché F1 e non la media aritmetica di P e R.
- Per ogni numero del quadro, il suo vincolo.

---

## 10. Il confronto multimodello

### 10.1 La domanda

Quanto del risultato dipende dal **modello** e quanto dalla **pipeline**
costruita attorno? Ha una conseguenza pratica: se un encoder più grande guadagna
poco, investire in un fine-tuning renderà poco, e conviene lavorare altrove.

### 10.2 Il disegno sperimentale

Sette candidati, cinque valutati, stessa pipeline e stessi dati:

| Modello | Dim | Famiglia | esito |
|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | sentence-transformers | valutato |
| paraphrase-multilingual-mpnet-base-v2 | 768 | sentence-transformers | valutato |
| intfloat/multilingual-e5-small | 384 | E5 | valutato |
| intfloat/multilingual-e5-base | 768 | E5 (in uso) | valutato |
| BAAI/bge-m3 | 1024 | BGE | valutato |
| intfloat/multilingual-e5-large | 1024 | E5 | escluso per costo |
| Alibaba-NLP/gte-multilingual-base | 768 | GTE | escluso, §10.9 |

Il nucleo è un **fattoriale due per due** — due famiglie per due taglie — che
permette di separare l'effetto della dimensione da quello della famiglia
invece di descriverli insieme:

| | 384 dim | 768 dim | effetto della taglia |
|---|---|---|---|
| **E5** | e5-small 0,609 / 0,622 | e5-base 0,612 / 0,759 | +0,003 F1 · **+0,137 occ** |
| **sentence-transformers** | MiniLM 0,586 / 0,570 | mpnet 0,598 / 0,525 | +0,012 F1 · **−0,045 occ** |
| **effetto della famiglia** | +0,023 F1 · +0,052 occ | +0,014 F1 · **+0,234 occ** | |

*(primo numero: F1 competenze; secondo: accuratezza occupazione)*

Da leggere così: **raddoppiare le dimensioni non aiuta sempre.** Dentro
sentence-transformers il passaggio da 384 a 768 migliora appena le competenze e
peggiora l'occupazione di quattro punti e mezzo. mpnet ha il doppio dei
parametri di MiniLM e riconosce peggio le occupazioni. Chi sceglie un encoder
guardando solo la dimensione sbaglia, e ora hai il dato per dirlo.

bge-m3 sta fuori dal fattoriale ed è il punto di controllo esterno: una terza
famiglia, addestrata diversamente da entrambe, che verifica se le conclusioni
reggono al di fuori delle due confrontate.

### 10.3 Il primo errore: le cache condivise

Cambiando encoder si sarebbero ricaricati silenziosamente gli embedding del
precedente. Risolto facendo comparire il nome del modello nel nome del file di
cache.

### 10.4 Il secondo errore: il profilo di background

Stesso difetto, sfuggito su un file. Il profilo per la correzione hubness si
chiamava `skills_bg_profile.pt`, senza il nome del modello. La sua lunghezza
dipende solo dal numero di etichette, **identico fra modelli**: quello di
e5-base si è caricato su MiniLM senza il minimo errore.

Due sintomi:

- **1.765 punteggi sopra 1,0.** Impossibile per un coseno.
- **Nessuna occupazione riconosciuta in 765 annunci su 810.**

Un solo difetto, due sintomi opposti: la correzione gonfiava i punteggi delle
competenze sopra le soglie (facendo passare tutto) e deprimeva quelli delle
occupazioni sotto la soglia (facendo cadere tutto).

**Lezione.** Un errore che produce numeri plausibili è più pericoloso di uno che
fa esplodere il programma. Qui a salvare è stato un valore **fisicamente
impossibile**. Lo script ora controlla da solo entrambe le sentinelle.

### 10.5 Il terzo problema, che non era un bug

Corretto il profilo, il 94,4% di occupazioni mancanti è rimasto identico. Le
due anomalie avevano cause diverse.

**Il dato decisivo:** MiniLM, quando propone un'occupazione, indovina l'**84,4%**
delle volte — meglio di e5-base, che si ferma al 75,9%. Il suo ordinamento è
ottimo. Semplicemente non supera quasi mai la soglia: propone in 45 annunci su
810.

La soglia per le occupazioni è 0,72, fissata guardando E5. I modelli E5
producono coseni assoluti alti (0,83–0,89 sull'occupazione); MiniLM lavora fra
0,72 e 0,79. **Stessa soglia, significato completamente diverso.**

Sulle competenze accade il contrario: i punteggi di MiniLM hanno media 0,979
contro 0,919, quindi le soglie sono troppo permissive e la precisione scende.
**Lo stesso difetto sposta le occupazioni sotto la soglia e le competenze
sopra.**

Conclusione: un confronto a soglie fisse **non misura la qualità degli
encoder**. Misura quanto ciascuno somiglia a E5 nella scala dei punteggi. È
viziato in favore della famiglia su cui il sistema è stato tarato.

### 10.6 La calibrazione per modello

La soluzione: le soglie sono un filtro applicato *dopo* il calcolo dei
punteggi. Se il parsing avviene una volta sola con soglie molto basse, tutti i
match deboli restano nel file e qualunque soglia più alta può essere applicata
a posteriori. Cercare le soglie migliori diventa una scansione su dati salvati:
**secondi invece di ore**.

Gli annunci si dividono in due parti disgiunte: le soglie si scelgono sulla
prima (202 annunci), le metriche si riportano sulla seconda (608). Lo scarto fra
i due valori dice quanto la scelta si sia adattata al rumore.

**La validazione su e5-base.** La ricerca automatica ha ritrovato **0,88** per i
candidati di più parole — identico al valore scelto a mano mesi prima. Due
procedure indipendenti convergono sullo stesso numero. Il guadagno in F1 è
+0,002, cioè nullo.

Doppia conclusione: la procedura è validata, **e** la taratura originale era già
all'ottimo.

Si è anche scoperto che con e5-base la soglia sull'occupazione è **inattiva**:
ogni titolo produce un punteggio sopra 0,82, quindi quel parametro non filtra
nulla.

### 10.7 Il risultato finale

Cinque encoder, tre famiglie, ciascuno con le proprie soglie calibrate dalla
stessa procedura.

| modello | fam. | dim | Prec | Rec | F1 | occupazione |
|---|---|---|---|---|---|---|
| multilingual-e5-base | E5 | 768 | 0,764 | 0,533 | **0,612** | 0,759 |
| bge-m3 | BGE | 1024 | 0,741 | 0,543 | 0,610 | **0,861** |
| multilingual-e5-small | E5 | 384 | 0,691 | 0,570 | 0,609 | 0,622 |
| mpnet-base-v2 | S-T | 768 | 0,683 | 0,558 | 0,598 | 0,525 |
| MiniLM-L12-v2 | S-T | 384 | 0,708 | 0,526 | 0,586 | 0,570 |

**Scarto sulle competenze: 0,026. Scarto sull'occupazione: 0,336. Tredici volte
tanto.**

### 10.8 Il caso che dimostra la tesi: bge-m3

bge-m3 è il caso più netto perché è **il migliore sull'occupazione di dieci
punti** — 0,861 contro lo 0,759 di e5-base — e allo stesso tempo
**indistinguibile sulle competenze**, dove chiude a 0,610 contro 0,612, cioè due
millesimi.

Lo stesso encoder, gli stessi documenti, la stessa esecuzione. Su un compito è
nettamente superiore, sull'altro non si distingue. La differenza fra i due
compiti non sta nel modello: sta in **quanto sistema c'è attorno al modello.**

Sull'occupazione il titolo dell'annuncio viene confrontato con le etichette
ESCO e vince la più simile: l'encoder decide da solo, e la sua qualità si
trasferisce interamente sul risultato. Sulle competenze ci sono la
segmentazione, il vincolo multi-parola, le soglie per tipo di candidato e il
classificatore appreso: ogni stadio assorbe una parte degli errori dell'encoder,
e alla fine cinque modelli molto diversi arrivano quasi allo stesso punto.

**Ne discende la formulazione da portare in tesi:** non «il modello conta poco»,
ma **quanto conta il modello dipende da quanta pipeline lo circonda.** È una
formulazione più precisa, verificata su cinque encoder e due compiti, e ha una
conseguenza operativa immediata: dove il sistema è nudo conviene investire
nell'encoder, dove è strutturato conviene investire nella struttura.

Confronto di riferimento sul lato competenze: il lavoro di pipeline vale
**+0,238 di F1**; passare da e5-small a e5-base ne vale **+0,003**, e passare al
modello più grande e recente del confronto ne vale **−0,002**.

### 10.9 Un encoder escluso

`Alibaba-NLP/gte-multilingual-base` non compare in tabella. La sua
implementazione, distribuita come codice remoto sul repository del modello,
fallisce in fase di codifica: `position_ids` contiene memoria non
inizializzata e l'indicizzazione delle rotary embeddings va fuori intervallo.

Il dettaglio che conta: **l'errore non è deterministico.** Memoria non
inizializzata può contenere un numero enorme, e allora il programma si ferma,
oppure numeri piccoli, e allora prosegue con posizioni sbagliate producendo
embedding privi di senso ma dall'aspetto normale. Il crash è l'esito fortunato.

Da qui `analysis/prova_modello.py`, che prima di spendere ore a costruire indici
verifica forma, normalizzazione e **stabilità su cinque esecuzioni**. Un modello
che a volte funziona non è utilizzabile: la riga che avrebbe prodotto in tabella
sarebbe stata indistinguibile da un dato vero.

### Cosa devi saper spiegare

- Perché due famiglie × due taglie e non sette modelli a caso.
- Il bug del profilo di background, e perché è stato un coseno > 1 a rivelarlo.
- Perché le soglie non sono trasferibili fra encoder.
- Perché il confronto a soglie fisse era impari, e come si è reso equo.
- Perché la calibrazione su e5-base «non serve a niente» ed è comunque il
  risultato più importante della procedura.

---

## 11. Limiti da dichiarare

1. **Valutazione per identificativo ESCO esatto.** Un match concettualmente
   corretto ma con identificativo diverso conta come errore: le metriche sono un
   limite inferiore.
2. **Ground truth parziale.** Le competenze attese sono un campione di quelle
   ESCO dell'occupazione; quelle davvero citate ma non campionate risultano
   falsi positivi. È il problema dei falsi negativi da distant supervision.
3. **Dati sintetici.** CV e annunci sono generati dallo stesso modello di
   linguaggio a partire dalla stessa ontologia, con cui condividono il lessico.
   Su documenti reali le metriche sarebbero verosimilmente inferiori. **È
   l'obiezione più prevedibile: preparala.**
4. **Componenti tarati sui dati.** Denylist ed euristiche sono costruite
   osservando questo dataset. Dove possibile validate su holdout.
5. **Numerosità dei campioni.** Le validazioni del matching engine girano su
   30–100 CV: differenze di pochi punti percentuali sono entro il rumore.
6. **Circolarità del dataset.** Quantificata con il Jaccard (§7.7): va
   riportata insieme ai risultati del matching, non in una nota a piè di
   pagina.
7. **Pesi scelti, non derivati.** Il 40/40/20 dell'ordinamento del divario
   (§8-bis) non viene da un'ottimizzazione. Ora il suo effetto è misurato — i
   contributi reali sono 72,6 / 20,7 / 6,7 — ma i pesi restano una scelta.
8. **Ordinamento fondato, non validato.** La prossimità viene dalla gerarchia
   ufficiale ESCO invece che da una ricostruzione, e cambia l'ordine nel 79,5%
   dei casi. Nessuno ha verificato che l'ordine nuovo sia *migliore* per chi
   deve studiare: servirebbe un giudizio umano, non raccolto.

---

## 12. Glossario

| Termine | Significato |
|---|---|
| **ESCO** | tassonomia europea di occupazioni e competenze, multilingue |
| **ISCO** | classificazione internazionale delle professioni; qui definisce i «settori» |
| **alt_labels** | denominazioni alternative di un concetto ESCO |
| **reuse_level** | quanto una competenza è trasversale (4 livelli) |
| **embedding** | rappresentazione di un testo come vettore |
| **similarità del coseno** | misura di vicinanza fra vettori; con vettori normalizzati è il prodotto scalare, max 1 |
| **zero-shot** | uso di un modello pre-addestrato senza adattamento al dominio |
| **instruction tuning** | addestramento che richiede prefissi (`query:`, `passage:`) |
| **hubness** | fenomeno per cui alcuni vettori compaiono fra i vicini di quasi tutti |
| **trie** | struttura ad albero per ricerca rapida di prefissi |
| **RAKE** | estrazione di frasi chiave spezzando il testo sulle stopword |
| **distant supervision** | etichette ricavate da una fonte indiretta invece che da annotazione |
| **ablazione** | disattivare un componente per misurarne il contributo |
| **holdout** | porzione di dati tenuta da parte e mai usata per costruire il modello |
| **Jaccard** | rapporto fra intersezione e unione di due insiemi |
| **MRR** | media dei reciproci del rango della risposta corretta |
| **regressione logistica** | classificatore lineare che stima una probabilità |
| **macro-media** | media delle metriche per documento; ogni documento pesa uguale |

---

## 13. La prova su curriculum reali

Documento completo: [`prova_cv_reali.md`](prova_cv_reali.md).

Quindici curriculum autentici, i primi documenti del progetto che nessuno ha
generato. La prova doveva misurare quanto il parser perdesse passando al reale;
ha invece **trovato tre difetti che il dataset sintetico nascondeva**.

| difetto | prima | dopo |
|---|---|---|
| Certificazioni: soglia 0,75 invece di 0,86 | P 0,250 · 125 assegnazioni su 15 CV | P 0,837 · 11 assegnazioni |
| Anni di esperienza: mesi scartati, em-dash ignorato, intervalli sommati | 7 CV su 15 a zero, uno con 48 anni | 8 stime fondate, causa nota per ogni residuo |
| Segmentazione delle sezioni | — | 2 CV senza sezione esperienza (non affrontato) |

**Il secondo rimedio alle certificazioni, misurato dopo.** Oltre ad alzare la
soglia esisteva un'alternativa strutturale: cercare le certificazioni **solo
nella sezione dedicata** invece che in tutto il documento. Misurata sullo
stesso insieme di riporto di 567 CV:

| configurazione | P | R | F1 |
|---|---|---|---|
| tutto il documento, soglia 0,75 | 0,250 | 0,779 | 0,364 |
| tutto il documento, soglia 0,86 *(in uso)* | 0,837 | 0,781 | 0,799 |
| solo sezione dedicata, soglia 0,75 | 0,841 | 0,780 | 0,801 |

**Equivalenti, e sostituti — non si sommano.** E nella terza configurazione la
soglia smette di contare: da 0,75 a 0,88 i risultati sono identici, perché il
punteggio minimo osservato è 0,891. Guardare solo dentro la sezione giusta
impedisce che i candidati spuri vengano generati, quindi non resta nulla da
filtrare.

Se te lo chiedono, il ragionamento interessante è questo: sul sintetico
pareggiano, ma uno è **un numero calibrato** e l'altro **un vincolo
strutturale** — e il §10 dimostra che i numeri calibrati non si trasferiscono.
Il costo del vincolo è che un quinto delle certificazioni vere sta fuori dalla
sezione dedicata, e che dipende dal riconoscimento delle sezioni, debole su 2
CV reali su 15.

**Il punto che vale per la tesi.** In due casi su tre il dataset sintetico non
si limitava a nascondere il problema: lo rendeva **invisibile per
costruzione**, perché generazione e valutazione condividevano la stessa
convenzione — la lista delle certificazioni, il formato delle date, la
convenzione sulla somma dei periodi.

Da cui la raccomandazione operativa: **un componente valutato solo su dati
sintetici va considerato non valutato**, a meno di poter dimostrare che
generazione e misura non condividono alcuna assunzione.

### Il caso più netto: un solo formato di data

`render_cvs.py` genera i periodi lavorativi con `f"{start_year} – 2024"`. Tutti
e 810 i CV usano quella sola formattazione. L'87,2% di stime esatte non
misurava la capacità di leggere le date: misurava la capacità di sottrarre due
numeri in un formato noto. Sui documenti veri la stessa funzione falliva su
metà dei casi.

E c'è un secondo strato: il generatore rende due ruoli come `2022 – 2024` e
`2021 – 2024`, periodi che si sovrappongono, ma la ground truth li somma —
5 anni invece dei 3 che leggerebbe una persona. Riguarda 540 CV su 810. La
vecchia funzione otteneva l'87,2% *perché sommava senza unire*, replicando
l'aritmetica del generatore.

### Cosa devi saper spiegare

- Perché «abilitazione muletto in 10 curriculum su 15» è stato più utile di
  qualunque metrica aggregata.
- Perché il percorso delle certificazioni aveva precisione 0,250 da mesi senza
  che nessuno se ne accorgesse.
- Perché l'87,2% sulle date era un numero privo di significato.
- Che cos'è il campo `years_source` e perché una congettura va marcata invece
  che cancellata.

---

## Appendice — i tre errori metodologici da raccontare

Non sono incidenti: sono il contenuto scientifico del lavoro. Ognuno ha la
stessa forma — un numero plausibile che nascondeva un difetto.

**1. Il peso della seniority a 0,3.** Tarato su un test che teneva costante il
contenuto, quindi il valore alto sembrava sempre migliore. Solo misurando due
dimensioni insieme è emerso che compromettteva il compito principale.
*Lezione: un parametro ottimizzato su un test che isola una dimensione può
peggiorare tutto il resto.*

**2. Il confronto contaminato della denylist.** Costruita su tutti gli 810
annunci e confrontata su 27 occupazioni che erano fra quegli 810: dava 0,747 e
vinceva. Ricostruita sulle sole occupazioni di training: 0,721, e perde.
*Lezione: il confronto sbagliato dava il risultato opposto.*

**3. Il profilo di background non taggato.** Caricato senza errori perché la
dimensione coincideva, ha prodotto coseni maggiori di 1.
*Lezione: un errore che produce numeri plausibili è più pericoloso di uno che
fa esplodere il programma.*

A questi si aggiunge il caso opposto, altrettanto utile: **il 100% sulla
seniority**, riconosciuto come impossibile e ricondotto a una circolarità (il
motore leggeva l'etichetta del generatore invece dell'estrazione del parser).
*Lezione: un risultato troppo bello va indagato con la stessa cura di uno
troppo brutto.*
