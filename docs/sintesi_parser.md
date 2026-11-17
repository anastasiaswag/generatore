# SkillPath AI — Sintesi dei due parser

Documento di lavoro: come funzionano i due parser, che risultati danno e dove
sono i loro limiti. Pensato come base per la stesura della relazione.

---

## 1. Il problema comune

Entrambi i parser risolvono lo stesso compito: dato un documento in linguaggio
naturale, individuare quali competenze dell'ontologia **ESCO** (13.939 skill,
3.039 occupazioni) vi sono espresse, restituendo gli identificativi ESCO.

Il nucleo tecnico è condiviso (`src/semantic_mapper.py`): le etichette ESCO
vengono trasformate in vettori con `intfloat/multilingual-e5-base` (768
dimensioni), e i frammenti di testo estratti dal documento vengono confrontati
con esse tramite similarità del coseno. Un match è accettato se supera una
soglia calibrata.

L'indice è **bilingue**: contiene sia le etichette italiane sia quelle inglesi,
più i sinonimi (`alt_labels`), per un totale di circa 118.000 forme. Un
documento in inglese e uno in italiano si risolvono quindi sui medesimi ID.

Ciò che distingue i due parser non è il matching, ma **come arrivano ai
frammenti da confrontare**. È lì che si gioca tutta la differenza di qualità.

---

## 2. Parser dei CV (`src/main_parser.py`)

### Funzionamento

1. **Estrazione del testo** dal PDF, con rimozione delle righe di rumore
   (intestazioni, numeri di pagina).
2. **Segmentazione in sezioni** — riconosce le intestazioni tipiche
   (`Competenze`, `Esperienza`, `Istruzione`, `Lingue`, `Certificazioni`) e
   assegna ogni riga alla propria sezione.
3. **Estrazione dei candidati** dalle sole sezioni pertinenti, sfruttando la
   struttura tipografica: una skill per riga, elenchi separati da virgola,
   contenuti fra parentesi, costrutti come *"sistemi ERP quali: SAP e
   TeamSystem"*.
4. **Percorso separato per sigle e CamelCase** (`VBA`, `SolidWorks`), estratte
   direttamente dal testo grezzo perché spesso annegate in frasi lunghe.
5. **Match semantico** con soglie differenziate: 0.85 per i token singoli,
   0.88 per le frasi, 0.85 per le sigle.
6. **Pipeline di filtri** sull'output: etichette troppo corte, etichette che
   iniziano con articolo, etichette formulate come compito verbale, nomi di
   lingua, e verifica testuale per la categoria "attrezzature".
7. **Percorsi dedicati** per lingue (rilevamento a parole chiave con livello
   CEFR), titoli di studio e certificazioni.

### Risultati — 810 CV sintetici

| Metrica | Valore |
|---|---|
| Precision | 0.907 |
| Recall | 0.860 |
| F1 | 0.878 |

Per template: `classic` 0.905 · `europass` 0.872 · `modern` 0.858.

### Punti di forza

- **Sfrutta la struttura del documento.** Le sezioni permettono di cercare le
  competenze solo dove effettivamente stanno, e gli elenchi forniscono
  candidati già isolati e puliti.
- **Produzione calibrata.** Estrae in media 13,95 skill contro 14,55 attese:
  non sovra-genera, il che è la ragione principale dell'alta precisione.
- **Percorsi specializzati.** Lingue, titoli di studio e certificazioni non
  passano dal matching generico ma da logiche dedicate, più affidabili su
  categorie con vocabolario chiuso.
- **Robusto ai template.** Lo scarto fra il formato migliore e il peggiore è di
  meno di 5 punti di F1.

### Punti di debolezza

- **Dipende dal riconoscimento delle sezioni.** Se un CV non usa intestazioni
  riconoscibili, o le annida in modo inatteso, i candidati finiscono nella
  sezione sbagliata. Il caso già osservato: le lingue elencate sotto
  "Competenze" venivano trattate come skill.
- **Recall limitata dal formato.** Le competenze espresse solo in prosa dentro
  le descrizioni di esperienza vengono catturate peggio di quelle elencate.
- **Filtri specifici del dominio.** Diverse regole (elenco dei nomi di lingua,
  termini "attrezzatura", verbi inglesi) sono euristiche costruite osservando
  questo dataset: su CV reali andrebbero riviste.
- **Il 12% degli errori residui** proviene da etichette generiche del tipo
  "maintain customer service", lo stesso fenomeno che affligge il job parser
  ma in misura molto minore.

---

## 3. Parser degli annunci (`src/job_parser.py`)

### Funzionamento

1. **Nessuna segmentazione in sezioni**: gli annunci non hanno una struttura
   affidabile, quindi si lavora sull'intero testo.
2. **Divisione in frasi**, poi estrazione dei candidati spezzando ogni frase
   sui confini delle parole funzionali (approccio ispirato a RAKE): le
   sequenze di parole di contenuto fra due stopword diventano candidati.
3. **Vincolo multi-parola**: dalla prosa vengono accettati solo candidati di
   almeno due parole (vedi §5, è la correzione più importante del progetto).
4. **Marcatori linguistici** per distinguere requisiti obbligatori
   (*richiesto*, *must have*) da preferenziali (*gradito*, *nice to have*).
5. **Match semantico** con soglie 0.82 / 0.88 / 0.84.
6. **Filtro finale** su 64 etichette ESCO troppo generiche.

### Risultati — 810 annunci sintetici

| Metrica | Valore |
|---|---|
| Precision | 0.614 |
| Recall | 0.577 |
| F1 | 0.580 |
| Accuracy occupazione (ID esatto) | 0.759 |
| Accuracy occupazione (settore ISCO) | 0.875 |

### Punti di forza

- **Indipendente dal formato.** Funziona su qualsiasi annuncio senza
  presupporre intestazioni: è il requisito realistico, perché gli annunci veri
  non hanno struttura garantita.
- **Distingue requisiti da preferenze**, informazione che il matching engine a
  valle può pesare diversamente.
- **Riconoscimento dell'occupazione affidabile**: 76% di ID esatto e 88% di
  settore, su 3.039 occupazioni possibili.
- **Contromisure disattivabili**, il che rende ogni componente misurabile in
  isolamento (`--no-denylist`, `--no-hubness`…).

### Punti di debolezza

- **Trenta punti di F1 sotto il parser CV**, e la causa è strutturale: riceve
  prosa continua invece di un documento formattato. Non è un componente di
  qualità inferiore, è un problema più difficile.
- **Recall inferiore alla precisione.** Il vincolo multi-parola scarta anche
  qualche competenza legittima espressa con una sola parola nel mezzo di una
  frase.
- **La denylist è supervisionata.** Le 64 etichette sono state individuate
  guardando quali predizioni erano sbagliate su questo dataset: è quindi
  specifica del dominio e va rimisurata su annunci reali. Il sistema funziona
  anche senza (F1 0.546), quindi non è un componente critico.
- **Nessuna gestione delle sezioni dell'annuncio.** Il testo di contorno
  (presentazione aziendale, benefit) produce circa il 15% dei candidati.

---

## 4. Confronto diretto

| | Parser CV | Job parser |
|---|---|---|
| Input | PDF strutturato | prosa continua |
| Segmentazione | per sezioni tipografiche | per frasi e stopword |
| Skill estratte / attese | 0,96× | 1,09× |
| Precision | 0.907 | 0.614 |
| Recall | 0.860 | 0.577 |
| F1 | 0.878 | 0.580 |

Il divario si spiega quasi interamente con la **calibrazione della
produzione**. Prima delle correzioni il job parser estraeva 1,99 volte le
skill attese: quasi tutta la perdita di precisione veniva da lì.

---

## 5. Cosa si è imparato sperimentando

Sei contromisure provate, quattro fallite. I risultati negativi sono
documentati nel codice con i numeri e la spiegazione del meccanismo.

| tentativo | esito |
|---|---|
| Filtro nomi di lingua (CV) | **riuscito** — precision 0.865 → 0.907 |
| Vincolo multi-parola (annunci) | **riuscito** — F1 0.391 → 0.546 senza altri rimedi |
| Denylist etichette generiche | **riuscito** — da 232 a 64 voci dopo la ricostruzione |
| Stadio di match lessicale | fallito — contributo incrementale con precision 0.27 |
| Correzione hubness | fallito — nessun effetto misurabile |
| Vincolo di reciprocità | fallito — presupponeva un fenomeno inesistente |

**Il risultato concettualmente più utile** è la diagnosi che ha portato al
vincolo multi-parola. Il falso positivo dominante nasceva dal candidato
`responsible`, un frammento grammaticale estratto da frasi come *"the candidate
will be responsible for…"*. Per quel candidato l'etichetta ESCO "comportarsi in
modo responsabile" è in realtà il match **corretto**: il difetto non era nel
modello né nell'ontologia, ma nella domanda che veniva posta. La
corrispondenza era esatta — il candidato compariva in 792 annunci su 810, e
l'etichetta risultava falso positivo in esattamente 792.

Questo spiega anche perché le contromisure applicate al lato ontologia (la
correzione hubness) non potevano funzionare: nessuna penalizzazione delle
etichette rimedia a un frammento privo di contenuto semantico.

---

## 6. Limiti da dichiarare nella relazione

1. **Valutazione per ID ESCO esatto**: un match concettualmente corretto ma con
   ID leggermente diverso viene contato come errore. Le metriche sono un limite
   inferiore.
2. **Ground truth parziale**: le skill attese sono un campione di quelle ESCO
   dell'occupazione. Competenze davvero citate nel testo ma non campionate
   risultano falsi positivi. È il classico problema dei falsi negativi da
   *distant supervision*.
3. **Dati sintetici**: generati da un modello di linguaggio a partire
   dall'ontologia, condividono con essa il lessico. Su documenti reali le
   metriche sarebbero verosimilmente inferiori.
4. **Componenti tarati sui dati**: denylist ed euristiche sono state costruite
   osservando questo dataset. Dove possibile sono state validate su holdout,
   ma la generalizzazione a dati reali resta da verificare.
