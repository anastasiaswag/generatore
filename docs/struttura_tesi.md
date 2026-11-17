# Struttura della tesi

Nove capitoli, più introduzione e conclusioni che capitoli non sono ma vanno
comunque scritte. Circa 100 pagine di corpo.

**Ordine di stesura**: si comincia dal capitolo 6 (il parser degli annunci), che
ha la narrazione più chiara, e si scrivono introduzione e conclusioni per
ultime. L'introduzione deve promettere esattamente ciò che il resto mantiene, e
finché il lavoro non è scritto non si sa con precisione cosa sia.

**Il filo argomentativo**, da tenere presente ovunque: non «ecco cosa ho
costruito» ma **come si valuta un sistema di matching semantico quando la
ground truth è sintetica**. Il capitolo 4 lo imposta, i capitoli 5–8 lo
applicano componente per componente, il capitolo 9 lo chiude.

**Il secondo filo**, che attraversa tutti i capitoli sui componenti: la
similarità semantica *propone*, non *decide*. Nei sistemi industriali la
decisione è affidata a uno stadio addestrato a valle; qui è stata inizialmente
affidata a una soglia, ed è la causa di quasi tutte le difficoltà incontrate.

---

## Impaginazione complessiva

| | Parte | Pagine |
|---|---|---|
| — | Introduzione | 4 |
| 1 | SkillPath AI: il progetto | 5 |
| 2 | Stato dell'arte | 12 |
| 3 | Architettura del sistema | 7 |
| 4 | Il dataset sintetico e la metodologia di valutazione | 11 |
| 5 | Il parser dei curriculum | 13 |
| 6 | Il parser degli annunci | 17 |
| 7 | Il matching engine | 11 |
| 8 | Il raccomandatore di corsi | 8 |
| 9 | Metriche finali e confronto multimodello | 10 |
| — | Conclusioni e sviluppi futuri | 4 |
| | **totale corpo** | **100** |
| — | Appendici | 8–12 |
| — | Bibliografia | 3–4 |

---

## Introduzione — 4 pagine
*(da scrivere per ultima, non numerata come capitolo)*

Il problema dell'incontro fra domanda e offerta di lavoro, e perché il matching
per parole chiave non basta. Un esempio concreto in apertura: «progettazione di
applicazioni iOS» contro «esperienza di sviluppo mobile».

L'approccio adottato: ESCO come vocabolario condiviso, embedding multilingue per
collegare il linguaggio naturale alle etichette dell'ontologia.

Il vincolo che ha determinato tutto il lavoro: l'indisponibilità di curriculum
reali in quantità sufficiente, e la conseguente scelta di generare un dataset
sintetico.

**La domanda di ricerca**, formulata esplicitamente: se la ground truth è
generata artificialmente, che cosa misurano davvero le metriche?

Struttura del documento e contributi.

---

## Capitolo 1 — SkillPath AI: il progetto — 5 pagine

**1.1 Obiettivo** — cosa deve fare il sistema: dato un curriculum e un annuncio,
stabilire quanto il primo risponda al secondo, individuare le competenze
mancanti e suggerire come colmarle.

**1.2 Lo Scenario 2** — la specifica del relatore. Il sistema non confronta il
candidato direttamente con le occupazioni ESCO, ma analizza prima l'annuncio
reale dell'azienda. È più vicino alla realtà operativa e più difficile: gli
annunci non hanno struttura garantita. Va detto qui perché condiziona ogni
scelta successiva.

**1.3 I quattro compiti** — estrazione dai curriculum, estrazione dagli annunci,
abbinamento nelle due direzioni, raccomandazione formativa.

**1.4 Il contesto e i suoi vincoli** — tirocinio, assenza di dati annotati,
nessun segnale di interazione, calcolo su CPU. Non sono scuse: definiscono
l'ambito entro cui i risultati vanno letti, e vanno dichiarati prima dei numeri
anziché dopo.

**1.5 Contributi** — elenco puntuale di ciò che il lavoro aggiunge, con rimando
al capitolo che lo sviluppa.

---

## Capitolo 2 — Stato dell'arte — 12 pagine

**2.1 Il problema e la risposta dei sistemi industriali** — sezione di
inquadramento, senza gergo. Il compito; le quattro fasi dell'architettura di
LinkedIn (segmentazione, doppio riconoscitore, espansione, punteggio
multitask); l'osservazione che orienta tutta la tesi: il confronto semantico
propone, non decide. *(già scritta)*

**2.2 L'ontologia ESCO** — struttura, occupazioni, competenze, `alt_labels`,
`reuse_level`, `skill_type`, collegamento a ISCO. I numeri verificati: 3.039
occupazioni, 13.939 competenze, 98.847 etichette per le competenze e 19.201 per
le occupazioni.

**2.3 Estrazione di competenze da testo** — il compito, la sua difficoltà,
approcci lessicali contro semantici e il compromesso fra precisione e
robustezza.

**2.4 Modelli di embedding per il retrieval** — rappresentazioni dense,
similarità del coseno, la famiglia E5 e i prefissi query/passage, il fenomeno
dell'hubness (va introdotto qui perché nel capitolo 6 se ne misura una
contromisura fallita).

**2.5 L'architettura a due stadi, e dove si colloca questo lavoro** — il
dettaglio tecnico ora che il lettore ha gli strumenti, e il confronto esplicito:
cosa hanno i sistemi industriali che qui manca.

**2.6 Distant supervision e annotazioni incomplete** — il compromesso soglia/
falsi positivi, i falsi negativi da annotazione incompleta. I fenomeni osservati
nei capitoli successivi sono documentati in letteratura: presentarli come
scoperte isolate sarebbe un errore.

---

## Capitolo 3 — Architettura del sistema — 7 pagine

**3.1 Visione d'insieme** — lo schema completo, dai due ingressi al
raccomandatore. Una figura a piena pagina, richiamata poi da tutti i capitoli
sui componenti.

**3.2 Il nucleo condiviso** — `semantic_mapper.py`: l'indice bilingue IT+EN, la
costruzione degli embedding, la cache, la ricerca per similarità. Entrambi i
parser usano lo stesso modello e lo stesso indice.

**3.3 Ciò che distingue i due parser** — non il matching, ma come arrivano ai
frammenti da confrontare. È qui che si gioca la differenza di trenta punti di
F1, e anticiparlo evita che il lettore attribuisca il divario alla qualità dei
componenti.

**3.4 Il formato dei dati** — le strutture JSON scambiate fra i moduli, con un
esempio ridotto. Serve a rendere leggibili i capitoli successivi.

**3.5 Scelte implementative** — librerie, perché sentence-transformers, perché
niente base di dati vettoriale, l'interfaccia Streamlit.

---

## Capitolo 4 — Il dataset sintetico e la metodologia di valutazione — 11 pagine

**4.1 Perché sintetico** — il vincolo di partenza, e cosa si guadagna: una
ground truth completa e gratuita per 810 documenti.

**4.2 Come è costruito** — selezione delle 135 occupazioni, campionamento delle
competenze da ESCO, generazione tramite modello di linguaggio, rendering in tre
template (classic, europass, modern) e tre livelli di seniority.

**4.3 Che cosa la ground truth è davvero** — le competenze «vere» sono quelle
campionate dal generatore, non quelle presenti nel testo. È distant supervision,
con tutto ciò che ne segue.

**4.4 Le metriche** — precision, recall, F1; macro-media e perché non la micro;
Precision@k e MRR per l'abbinamento; le baseline casuali, senza le quali un
numero non significa niente.

**4.5 Il protocollo sperimentale** — ablazione, holdout, divisione per
occupazione e non per documento, riproducibilità dei comandi.

**4.6 La circolarità del dataset** — la quantificazione con l'indice di Jaccard:
0,640 fra CV e annuncio della stessa occupazione, 0,003 fra settori diversi. Va
introdotta qui, prima dei risultati, perché è la chiave per leggerli.

---

## Capitolo 5 — Il parser dei curriculum — 13 pagine

**5.1 Il vantaggio del documento strutturato** — un curriculum ha sezioni,
elenchi, una skill per riga. È il caso favorevole, e capirlo qui prepara il
contrasto del capitolo 6.

**5.2 La pipeline** — estrazione del testo (PyMuPDF, python-docx per le tabelle
Europass), segmentazione per sezione sui due percorsi header, estrazione dei
candidati, percorso separato per sigle e CamelCase.

**5.3 Il match semantico** — soglie 0,85 / 0,88 / 0,85 e perché differenziate.

**5.4 I filtri, uno per uno** — etichette corte, articolo iniziale, etichette
task-oriented (29.093, il 29% dell'ontologia), termini di attrezzatura, filtro
pre-candidati. Ogni filtro con il difetto che risolve.

**5.5 I percorsi dedicati** — lingue con livello CEFR, titoli di studio,
certificazioni. Vocabolari chiusi trattati con logiche dedicate anziché
semantiche.

**5.6 L'evoluzione, con i numeri** — 0,760/0,547/0,623 → 0,865/0,860/0,857 →
0,907/0,860/0,878. I due salti: il dizionario supplementare di alias italiani
che recupera il richiamo perduto per via del filtro sui verbi, e il filtro sui
nomi di lingua.

**5.7 Il caso «francese»** — 183 occorrenze errate e nessuna corretta, 489 falsi
positivi su 1.480. Un errore sistematico riconoscibile perché *sistematico*, non
per la sua dimensione.

**5.8 I falsi negativi residui** — soft skill in formule italiane
standardizzate, competenze di dominio assenti da ESCO.

*Nota per la stesura: questo capitolo non va compresso. Il parser dei
curriculum sembra aver funzionato subito, ma anche qui ci sono state molte
prove; la baseline 0,760/0,547/0,623 lo documenta.*

---

## Capitolo 6 — Il parser degli annunci — 17 pagine

Il capitolo più lungo, e giustamente: ha la narrazione più completa del lavoro.

**6.1 Perché la prosa è più difficile** — nessuna struttura affidabile, niente
sezioni, niente elenchi. Segmentazione in frasi ed estrazione dei candidati sui
confini delle stopword.

**6.2 Il punto di partenza** — F1 0,391, precisione 0,297, competenze estratte
1,99 volte quelle attese.

**6.3 L'indagine** — la frase di esempio, i sette candidati, i quattro detriti.
La tabella della corrispondenza esatta: `responsible` in 792 annunci, 792 falsi
positivi.

**6.4 La diagnosi** — per `responsible` l'etichetta «comportarsi in modo
responsabile» è il match **corretto**. Il difetto non era nel modello né
nell'ontologia, ma nella domanda posta. È il risultato concettuale più
importante del progetto e va scritto come tale.

**6.5 Il vincolo multi-parola** — la soluzione, il 45,5% di candidati eliminati,
i 3,5 punti di richiamo persi.

**6.6 Le quattro contromisure fallite** — stadio lessicale, correzione hubness,
vincolo di reciprocità, filtri riusati dal parser CV. Ognuna con la diagnosi del
meccanismo. Il caso della reciprocità è il più istruttivo: era la risposta
giusta a una domanda diversa.

**6.7 La denylist e il suo limite** — da 232 a 64 etichette, validazione su
holdout, e la dichiarazione esplicita che è supervisionata e specifica del
dominio. È il punto metodologicamente più debole della pipeline, ed è la ragione
del paragrafo seguente.

**6.8 Il classificatore appreso** — la motivazione, la divisione per occupazione
e non per documento, gli undici attributi e perché nessuno guarda l'identità
della competenza, la regressione logistica in numpy e i pesi leggibili.

**6.9 Il confronto onesto** — perché la denylist va ricostruita sulle sole
occupazioni di training: 0,747 contaminato contro 0,721 corretto, e il
classificatore che vince con 0,734. Il confronto sbagliato dava il risultato
opposto.

**6.10 L'estrazione del livello di esperienza** — le espressioni riconosciute,
la matrice di confusione, il 92,3%.

**6.11 L'ablazione completa** — la tabella dei sei stadi, da 0,391 a 0,629.

**6.12 L'identificazione dell'occupazione** — il secondo compito dello stesso
parser: 75,9% sull'identificativo ESCO esatto, 87,5% sul macro-settore ISCO.
Alimenta il Capitolo 7 e il confronto del Capitolo 9, dove è il compito su cui
lo scarto fra encoder è massimo.

**6.13 I falsi negativi residui** — dove finisce il 46% di competenze mai
trovate. Conteggi grezzi TP 5.589 · FP 1.280 · FN 5.345, e la separazione in
tre cause disgiunte: 378 (7,1%) scartate dal classificatore, 4.158 (77,8%)
presenti nel testo ma non isolate dal segmentatore, 809 (15,1%) mai comparse
nel testo generato. Dichiarare che il primo numero viene da un confronto
esatto fra file e gli altri due da un'euristica lessicale. Nota necessaria: i
conteggi danno la micro-media (0,511), leggermente inferiore alla macro-media
0,539 della tabella, perché gli annunci hanno un numero diverso di competenze
attese.

**6.14 La conferma indipendente: ESCOXLM-R** — la diagnosi del §6.4 è una
spiegazione, non una verifica: resta compatibile con l'ipotesi che il problema
sia intrinseco al compito. Un riconoscitore addestrato che non segmenta sui
confini delle parole funzionali produce, sugli stessi 810 annunci, **7
frammenti senza contenuto su 10.045 span (0,07%)** contro i 792 falsi positivi
del solo `responsible`. Dichiarare che non è un confronto di F1 e perché non
potrebbe esserlo.

---

## Capitolo 7 — Il matching engine — 11 pagine

**7.1 La formula** — copertura pesata, termine sul conteggio assoluto,
similarità di occupazione, allineamento del livello. Ogni termine con la sua
motivazione.

**7.2 Il difetto scoperto: la preferenza per le posizioni junior** — gli annunci
junior elencano meno requisiti (10,77 contro 16,19), quindi la frazione coperta
risulta più alta a prescindere. 47 scelte junior su 100 contro le 33 attese.

**7.3 Le due correzioni e la loro taratura** — la tabella dei pesi provati; il
criterio per scegliere 0,15: a parità di accuratezza è preferibile che gli
errori siano rumore anziché tendenza sistematica.

**7.4 Il peso della seniority: un parametro tarato male** — da 0,3 a 0,10, il
caso tracciato del *telecommunications manager* battuto dal *mask maker*. Un
parametro ottimizzato su un test che isola una dimensione può compromettere il
compito principale.

**7.5 I risultati nelle due direzioni** — CV → offerte e offerta → candidati,
con la spiegazione dello scarto fra 96,7% e 90,0%.

**7.6 Un'ipotesi formulata e smentita** — il sospetto che il termine sul
conteggio premiasse i curriculum più lunghi. Correlazione +0,194 con il
termine e +0,208 senza: l'ipotesi è respinta per **ablazione**, non per
assenza di segnale. Va raccontata proprio perché smentita, e perché la forma
della smentita è più solida di un valore vicino a zero.

**7.7 Il punteggio è una misura o solo un ordinamento?** — le tre distribuzioni
per affinità decrescente, le sovrapposizioni al 2,5% e 12,5%, i casi tracciati.

**7.8 Il limite del test sull'occupazione** — il 96,7% letto insieme al Jaccard.
Senza quella quantificazione il numero suggerisce una capacità che il test non
ha verificato.

---

## Capitolo 8 — Il raccomandatore di corsi — 6 pagine

**8.1 Dal divario alla formazione** — come si passa dalle competenze mancanti a
un percorso.

**8.2 La scelta dello scenario** — stessa occupazione, avanzamento, transizione.
Solo la terza produce un campione utilizzabile: 0,17 competenze mancanti nel
primo scenario non misurano niente.

**8.3 Un limite del dataset scoperto qui** — nel dataset sintetico la seniority
cambia *quanto* viene richiesto, non *che cosa*. È un limite del generatore, non
del raccomandatore, e una direzione concreta per un lavoro successivo.

**8.4 Il limite è il catalogo** — la copertura Coursera sull'ontologia: 23,7%
medio, con un gradiente che supera il doppio fra lavoro intellettuale e manuale.
Il 43,1% osservato è quasi il doppio della media.

**8.5 La pertinenza, misurata a mano** — revisione manuale su 30 competenze e 65
raccomandazioni: 18,5% pertinenti, 61,5% fuori bersaglio, copertura effettiva
23,3% con un intervallo che non contiene il 43,1% nominale. La causa: l'indice
abbina i *tag* alle competenze, non i corsi.

**8.6 L'ordinamento del divario** — il componente che decide quale competenza
imparare per prima, e l'unico rimasto a lungo senza una misura. Tre cose da
raccontare: che ESCO distribuisce le relazioni fra competenze e che il file
utile è la gerarchia (copertura 100%) e non `skillSkillRelations` (41%); che la
ricostruzione per co-occorrenza conteneva informazione binaria ma non graduata
(ρ = 0,033 fra numero di co-occorrenze e vicinanza reale); e che una
normalizzazione sbagliata riduceva una componente dal 20% nominale all'1,6%
effettivo. Effetto della sostituzione: τ di Kendall 0,791, prima competenza
raccomandata cambiata nel 14,2% dei casi. Chiudere dichiarando che
l'ordinamento è **fondato ma non validato**. Tabelle pronte in
`docs/latex/tabelle/tab_skill_graph.tex`.

---

## Capitolo 9 — Metriche finali e confronto multimodello — 10 pagine

**9.1 Il quadro complessivo** — la tabella di tutti i componenti, e per ciascun
numero il vincolo che ne cambia il significato. Nessun valore va letto
isolatamente.

**9.2 La domanda del confronto** — quanto del risultato dipende dal modello e
quanto dalla pipeline. La conseguenza pratica: se un encoder più grande guadagna
poco, un fine-tuning renderà poco.

**9.3 Il disegno sperimentale** — sette encoder, due famiglie, tre taglie:
confrontare e5-small con e5-base isola l'effetto della dimensione, confrontare
MiniLM con e5-small isola quello della famiglia.

**9.4 Due errori che il confronto ha rivelato** — le cache non separate per
modello, e il profilo di background con lo stesso difetto. Il secondo è stato
scoperto da un coseno maggiore di 1: un valore fisicamente impossibile. Un
errore che produce numeri plausibili è più pericoloso di uno che fa esplodere il
programma.

**9.5 Le soglie non sono trasferibili fra encoder** — MiniLM indovina l'84,4%
delle volte quando propone, ma propone in 45 annunci su 810. Un confronto a
soglie fisse misura quanto ciascun modello somigli a E5 nella scala dei
punteggi, non quanto sia capace.

**9.6 La calibrazione per modello** — il metodo (parsing unico a soglie basse,
ricerca fuori linea, taratura e riporto su insiemi disgiunti) e la validazione:
tre ricerche indipendenti ritrovano 0,88, il valore scelto a mano.

**9.7 I risultati del confronto** — la tabella finale. Lo schema atteso: scarto
minimo sulle competenze, ampio sull'occupazione. **Quanto conta il modello
dipende da quanto la pipeline lo circonda.**

**9.8 Pipeline contro modello** — +0,238 di F1 dal lavoro di pipeline, +0,019
dal passaggio a un encoder più grande. Circa dodici volte tanto.

**9.9 Un errore di ragionamento da dichiarare** — la previsione sbagliata
sull'accuratezza di MiniLM dopo la calibrazione: l'84,4% era misurato sui casi
che il sistema stesso aveva selezionato, cioè i più facili. Una percentuale
calcolata su un sottoinsieme autoselezionato non è confrontabile con una
calcolata su tutto. È lo stesso meccanismo che rende il 96,7% ottimistico.

---

## Conclusioni e sviluppi futuri — 4 pagine
*(non numerate come capitolo)*

**Cosa è stato costruito e cosa è stato imparato.** Distinguere le due cose: il
sistema funzionante da un lato, i risultati metodologici dall'altro.

**I risultati negativi.** Quattro contromisure fallite con diagnosi, tre errori
metodologici individuati e corretti. Non sono incidenti: sono il contenuto
scientifico del lavoro.

**I limiti, ripresi in modo compatto.** Valutazione per identificativo esatto,
ground truth parziale, dati sintetici, componenti tarati sui dati, numerosità
dei campioni.

**Sviluppi futuri**, in ordine di valore:

1. validazione su documenti reali — la direzione più importante di tutte;
2. differenziare le competenze per livello nel dataset sintetico, non solo la
   loro quantità;
3. lo stadio lessicale fatto bene, come nei sistemi industriali, invece che come
   aggiunta incrementale;
4. fine-tuning del modello, ma solo dopo aver verificato che l'encoder incida
   abbastanza da giustificarlo;
5. cataloghi formativi oltre Coursera, per i mestieri manuali.

---

## Appendici — 8–12 pagine

**A. Casi tracciati** — cinque confronti CV↔annuncio scomposti per intero.
Contro l'obiezione «questi risultati sono costruiti», un esempio ispezionabile
vale più di una tabella.

**B. Comandi per la riproducibilità** — ogni risultato con lo script che lo
genera.

**C. Tabelle estese** — matrici di confusione complete, copertura per settore
ISCO, pesi del classificatore.

**D. Estratti di codice** — le funzioni chiave, non interi file.

---

## Corrispondenza con i file LaTeX

I file in `docs/latex/capitoli/` sono ancora impostati sulla struttura
precedente a sette capitoli e vanno rinominati e riorganizzati su questa. Le
tabelle in `docs/latex/tabelle/` restano valide, ma cambiano i capitoli in cui
vengono richiamate:

| tabella | capitolo di destinazione |
|---|---|
| `tab_cv_parser`, `tab_cv_template` | 5 |
| `tab_job_parser`, `tab_candidati_detriti` | 6 |
| `tab_classificatore`, `tab_pesi_classificatore` | 6 |
| `tab_monotonia` | 7 |
| `tab_copertura_corsi` | 8 |
| `tab_riepilogo` | 9 |
