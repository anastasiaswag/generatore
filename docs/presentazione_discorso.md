# Discussione — traccia del discorso (10 minuti)

**Filo conduttore:** la pipeline raccontata stadio per stadio. Per ciascuno:
il problema che poneva, come ho provato a risolverlo, e **che cosa ha
rivelato la misura**. Tre volte la misura ha smentito quello che credevo, ed
è quella la parte che vale.

**Regola generale di consegna:** un numero per stadio, non tutti. I numeri
che non dici restano disponibili per le domande — ed è meglio averne in
riserva che spararli tutti e restare senza.

---

## 0 · Apertura — 45 secondi

> «Un curriculum e un annuncio di lavoro descrivono la stessa realtà con
> parole scelte in modo indipendente. Un candidato scrive di aver progettato
> applicazioni per iOS; l'annuncio chiede esperienza di sviluppo mobile. Un
> lettore umano riconosce la corrispondenza, un confronto parola per parola
> no.»

Poi la scelta di fondo, in una frase: ancorare entrambi i documenti a un
vocabolario condiviso — **ESCO, 3.039 occupazioni e 13.939 competenze** — e
calcolare la compatibilità su quello, non sul testo.

E subito il patto con la commissione, che è la cosa che regge tutti i dieci
minuti:

> «Ho costruito quattro componenti. Ma la parte del lavoro che mi sembra più
> solida non sono i numeri che hanno funzionato: è che misurando ho scoperto
> che alcuni di quei numeri non misuravano ciò che sembravano misurare. Vi
> racconto la pipeline stadio per stadio, e ogni stadio ha avuto il suo
> difetto.»

**Perché dirlo all'inizio e non alla fine:** detto adesso, tutto ciò che
segue si legge come rigore. Detto in chiusura, suona come una confessione.

---

## 1 · Il dato di partenza — 1 minuto

**Il problema:** non avevo curriculum reali in quantità, e non avevo nulla di
annotato. Senza dati etichettati un approccio supervisionato è escluso in
partenza.

**Cosa ho fatto:** ho generato un dataset sintetico — **810 curriculum e 810
annunci** — campionando competenze da ESCO e facendoli scrivere a un modello
linguistico. 135 occupazioni bilanciate sui nove grandi gruppi ISCO.

**Cosa ha rivelato la misura:**

> «La ground truth di ogni documento non è l'elenco delle competenze presenti
> nel testo: è l'elenco che ho dato in input al generatore prima che
> scrivesse. Sono due cose diverse, e la differenza si paga in entrambe le
> direzioni.»

Il numero da dire: **Jaccard 0,640 fra le competenze di un CV e di un annuncio
della stessa occupazione, contro 0,0034 fra occupazioni diverse.** Il 93%
delle coppie di occupazioni diverse non condivide nemmeno una competenza.

> «È il vincolo che accompagna ogni numero che dirò dopo. Preferisco
> dichiararlo adesso, una volta, invece di doverlo aggiungere sette volte.»

---

## 2 · Il parser dei curriculum — 1 minuto e 30

**Il problema:** riconoscere concetti di una tassonomia chiusa dentro un
documento libero. Il curriculum ha però una struttura tipografica — sezioni,
elenchi — su cui si può contare, ed è il suo vantaggio sull'annuncio.

**Cosa ho fatto:** segmentazione per sezioni, confronto semantico con
l'indice ESCO bilingue, cinque filtri sulle etichette e percorsi dedicati per
lingue, titoli di studio e certificazioni — vocabolari chiusi, dove una
regola è più precisa di una soglia di similarità.

**Due salti, ciascuno con una causa precisa.** Da **F1 0,623** a **0,878**:

> «Il primo salto è sul Recall, da 0,547 a 0,860. La causa è un effetto
> collaterale: il filtro che elimina il 29% delle etichette ESCO perché
> formulate come attività scartava anche competenze legittime, che in ESCO
> sono semplicemente scritte così. Il rimedio non è stato indebolire il
> filtro — serviva per la ragione opposta — ma affiancargli un dizionario di
> alias italiani per recuperarle da una formulazione alternativa. **Una
> contromisura corretta che produce un effetto collaterale va compensata con
> un secondo intervento, non annullata.**»

**Cosa ha rivelato la misura, la prima volta — il caso francese.** Questo è il
gemello del `responsible` che dirai fra poco, ed è il momento migliore del
capitolo:

> «ESCO cataloga le lingue anche come competenze nominali. Una lingua
> dichiarata nel curriculum veniva quindi estratta due volte: dal percorso
> dedicato, con il livello CEFR, e di nuovo dal match generico. **Il francese
> compariva 183 volte come competenza, e nessuna era corretta. Zero su 183.**
> È riconoscibile come errore sistematico non per quanto è grande, ma per la
> sua **forma**: un errore casuale avrebbe dato novanta corrette e
> novantatré sbagliate. Un filtro mirato ha rimosso tutti e 489 i falsi
> positivi di questa famiglia senza perdere un solo vero positivo.»

**E la seconda volta, sui dati veri.** Quindici curriculum autentici, gli
unici documenti che nessuno strumento mio ha generato. Non una conferma: tre
difetti che il sintetico nascondeva per costruzione. Dì solo il più netto:

> «Le certificazioni usavano una soglia tarata sul sintetico. Misurata con la
> ground truth che avevo da sempre e non avevo mai applicato a quel percorso:
> **precisione 0,250**. Tre su quattro sbagliate, e nessuna metrica lo
> segnalava perché quel percorso non era mai stato valutato separatamente.»

La conclusione da consegnare:

> «Un componente valutato solo su dati sintetici va considerato non valutato,
> a meno di poter dimostrare che generazione e misura non condividono alcuna
> assunzione. Qui condividevano la lista delle certificazioni e il formato
> delle date.»

---

## 3 · Il parser degli annunci — 2 minuti · **il cuore**

Qui rallenta. È la parte migliore e va detta con calma.

**Il problema:** l'annuncio è prosa continua, senza struttura su cui
appoggiarsi. Partenza: **F1 0,391**, con il parser che estraeva **1,99 volte**
le competenze attese. Quasi il doppio.

**L'indagine.** Invece di cercare di migliorare il modello, ho guardato
*quali* candidati sbagliati ricorrevano. La risposta era netta:

> «Il candidato `responsible` compariva in **792 annunci su 810**, e generava
> **792 falsi positivi**. Non un errore occasionale: un errore che si ripeteva
> in quasi ogni documento.»

**La diagnosi — questa è la frase che deve arrivare:**

> «Per il candidato `responsible`, l'etichetta ESCO *comportarsi in modo
> responsabile* è il match **corretto**. Il modello aveva fatto esattamente il
> suo lavoro. Il difetto non era nel modello e non era nell'ontologia: era
> **nella domanda posta al sistema**. Il segmentatore aveva estratto un
> aggettivo isolato dal suo complemento — `responsible` senza *for
> coordinating technological activities* — e si stava chiedendo quale
> competenza somigliasse di più a un frammento che non diceva niente.»

*(pausa)*

**Cosa ho provato prima di capirlo:** quattro contromisure, tutte fallite.
Nominale veloci — stadio lessicale, correzione hubness, vincolo di
reciprocità, riuso dei filtri del parser CV — e una frase sola sulla più
istruttiva:

> «Il vincolo di reciprocità presupponeva che il rumore si ripetesse *dentro*
> il documento. Il fenomeno era *fra* documenti. Contromisura corretta,
> applicata a un problema con la forma sbagliata.»

**Il rimedio:** accettare dalla prosa solo candidati di almeno due parole.
Elimina il 45,5% dei candidati.

> «Bilancio completo: **334 veri positivi persi contro 10.076 falsi positivi
> eliminati**. Uno a trenta.»

**E la misura che mi ha smentito.** Dopo la denylist ho costruito un
classificatore addestrato, e volevo confrontarli:

> «La denylist, costruita osservando tutti gli 810 annunci, dava F1 **0,747**
> contro lo 0,734 del classificatore: vinceva la lista scritta a mano. Ma
> quella lista aveva visto in anticipo le occupazioni usate come test.
> Ricostruita sulle sole occupazioni di addestramento scende a **0,721**, e il
> classificatore vince. **Il confronto sbagliato non dava un risultato
> leggermente diverso: dava il risultato opposto.**»

Chiudi lo stadio: da 0,391 a **0,629**.

---

## 4 · Il motore di matching — 1 minuto e 30

**Il problema:** combinare copertura delle competenze, somiglianza
dell'occupazione e livello di esperienza in un punteggio unico.

**Cosa ha rivelato la misura, la prima volta:**

> «Il sistema proponeva posizioni junior a chiunque: **47 volte su 100**
> contro le 33 attese, e l'accuratezza sul livello era **37%**, appena sopra
> il caso. La causa non era nel candidato: gli annunci junior elencano in
> media **10,8 requisiti** contro i 16,2 dei senior, quindi la frazione
> coperta risultava più alta per pura aritmetica del denominatore.»

Corretto con un termine sul conteggio assoluto e l'allineamento del livello:
**dal 37% al 97%**.

**E la seconda volta, che è più interessante:**

> «Avevo tarato il peso del livello a 0,3, su un test che confrontava solo
> annunci della stessa occupazione — dove il contenuto è costante e un peso
> alto sembra sempre meglio. Misurato sul compito vero, un candidato senior
> abbinato al suo ruolo esatto veniva superato da un annuncio di *mask
> maker*, un mestiere manuale senza alcuna relazione, solo perché il livello
> combaciava per caso. **Un parametro ottimizzato su un test che isola una
> dimensione può peggiorare tutte le altre.**»

Numero di chiusura: **Precision@1 96,7% da CV a offerte, 90,0% nella
direzione opposta**, con baseline casuale 1,7%.

---

## 5 · Corsi e ordinamento del divario — 1 minuto e 30

**Il problema:** trasformare le competenze mancanti in un percorso.

**Cosa ha rivelato la misura, terza volta:**

> «La copertura del 43,1% dice che per quella competenza **esiste** un corso.
> Non dice che sia **quello giusto**. Ho controllato a mano trenta competenze
> e sessantacinque raccomandazioni: **pertinenti il 18,5%**, fuori bersaglio
> il 61,5%. La copertura effettiva scende al **23,3%**, con un intervallo di
> confidenza che non contiene il 43,1% nominale.»

La causa, in una frase: l'indice abbina i corsi ai **tag** della piattaforma,
non alle competenze, e solo quel primo anello era misurato.

**E l'ultimo componente, quello che era rimasto senza misura.** L'ordinamento
delle competenze mancanti usava tre fattori, uno dei quali stimava la
vicinanza concettuale per co-occorrenza — perché il dataset ESCO che avevo
scaricato non conteneva le relazioni fra competenze.

> «Le ho scaricate, e ho confrontato. Le coppie che la mia ricostruzione
> giudicava vicine lo sono davvero 2,5 volte più del caso: non era arbitraria.
> Ma la correlazione fra *quante volte* due competenze co-occorrono e la loro
> vicinanza reale è **0,033**, cioè nulla: l'informazione era binaria, e il
> codice la usava come se fosse graduata. E misurando i contributi ho trovato
> un errore di normalizzazione: quella componente pesava **l'1,6% invece del
> 20%** dichiarato.»

---

## 6 · Quanto conta il modello — 1 minuto

**La domanda:** tutto il sistema è costruito attorno a un solo modello di
embedding, scelto all'inizio e mai rimesso in discussione. Quanto dei
risultati dipende da lui?

**Cinque encoder, stessa pipeline, soglie ricalibrate per ciascuno.**

> «Sulle competenze lo scarto fra il migliore e il peggiore è **0,026**.
> Sull'occupazione è **0,336**, tredici volte tanto. Stesso modello, stessi
> documenti, stessa esecuzione.»

La spiegazione, che è il risultato:

> «La formulazione corretta non è che il modello conta poco, ma che **quanto
> conta il modello dipende da quanta pipeline lo circonda**. Sull'occupazione
> l'encoder decide da solo e la sua qualità passa intera. Sulle competenze ci
> sono segmentazione, vincoli, soglie e un classificatore, e ogni stadio
> assorbe parte dei suoi errori.»

Il numero che chiude: **il lavoro di pipeline vale +0,238 di F1; il miglior
cambio di modello ne vale +0,003.** Quasi ottanta volte.

Se hai tempo, aggiungi la scoperta collegata: **le soglie non sono
trasferibili fra encoder.** Con un modello diverso e le soglie del primo,
l'accuratezza risultava 0,047 — ma nei casi in cui il sistema si pronunciava
indovinava l'84,4%. Ricalibrando sale a 0,570. Un confronto a soglie fisse non
misura la qualità degli encoder: misura quanto ciascuno somigli al primo.

---

## 7 · Chiusura — 1 minuto

Lo screenshot del frontend qui, come immagine di sfondo mentre parli. Una
frase sola: *«Il sistema funziona end-to-end: questo è un curriculum
confrontato con un annuncio, con le competenze coperte, quelle mancanti e i
corsi suggeriti.»*

Poi i limiti, **detti da te per primo**:

> «Tutti i numeri che ho riportato stanno su dati che ho generato io. L'unica
> finestra sul reale sono quindici curriculum, e su quelli il sistema ha
> trovato tre difetti in un pomeriggio. Gli annunci reali non li ho ancora
> raccolti, e l'ordinamento del divario è fondato ma non validato: so che
> viene dall'ontologia ufficiale invece che da una ricostruzione, non so se
> l'ordine che produce sia più utile a chi deve studiare.»

E la frase finale, che è quella che devono ricordarsi:

> «Quello che porto non è il sistema. Sono quattro misure che dicono dove
> sostituire un modello addestrato con una regola costa poco e dove costa
> molto — e in tre casi su quattro il costo non era dove me lo aspettavo.»

---

## Note di consegna

**Il punto in cui rallentare** è uno solo: la diagnosi di `responsible`, nello
stadio 3. Tutto il resto può correre; lì fermati, e lascia due secondi di
silenzio dopo «*era nella domanda posta al sistema*».

**Non recitare le tabelle.** Un numero per stadio. Se ne dici sette, non se ne
ricordano nessuno.

**I fallimenti vanno detti al presente e in prima persona** — «ho tarato male»,
«mi ha smentito» — non con la forma impersonale. Detti in prima persona
suonano come controllo; detti in terza suonano come scuse.

**Se sfori**, i tagli in ordine: prima le soglie non trasferibili (stadio 6),
poi le quattro contromisure fallite (stadio 3), poi il secondo difetto del
motore di matching (stadio 4). Non tagliare mai la diagnosi di `responsible`
né la copertura effettiva dei corsi.

**Tempo totale:** 45s + 1m + 1m30 + 2m + 1m30 + 1m30 + 1m + 1m = **10 minuti e
15 secondi.** Provalo con il cronometro: la prima volta durerà tredici minuti.

**I due casi gemelli.** Il francese nello stadio 2 e `responsible` nello
stadio 3 sono la stessa scoperta vista da due lati: un errore riconosciuto
per la sua *forma* invece che per la sua dimensione. Se li colleghi
esplicitamente — «è lo stesso meccanismo del caso precedente, in un parser
diverso» — la commissione vede un metodo, non due aneddoti. È la singola
frase che fa più lavoro in tutta la presentazione.
