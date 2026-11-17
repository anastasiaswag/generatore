# Note del relatore — versione definitiva

Una voce per slide, da incollare nel campo note di PowerPoint.
Le correzioni rispetto alla versione precedente sono segnalate con ⚠️.

---

**1 · Frontespizio**
Buongiorno. Mi chiamo Samuele Miele e vi presento il mio lavoro di tesi: tecniche di intelligenza artificiale per il supporto ai percorsi di avanzamento professionale.

**2 · Sezione: Il problema**
Partiamo dal problema che volevo risolvere.

**3 · Chi cerca lavoro**
Immaginate una persona che cerca lavoro. Ha davanti decine di annunci e non sa quale sia il più adatto a lei. Leggerli tutti e confrontarli richiede moltissimo tempo.

**4 · Chi cerca lavoro — le percentuali**
Il sistema che ho progettato calcola, per ogni annuncio, una percentuale di compatibilità con il curriculum.

**5 · Chi cerca lavoro — la roadmap**
E una volta individuato l'annuncio più adatto, indica anche quali competenze mancano, in ordine di priorità, e quali corsi seguire. Il candidato non riceve un voto: riceve una strada.

**6 · Chi seleziona**
Pensate adesso a un selezionatore che riceve centinaia di curriculum per una sola posizione.

**7 · Chi seleziona — le percentuali**
Anche qui il sistema calcola una percentuale per ogni candidato e mette in evidenza il più adatto.

**8 · Chi seleziona — la formazione**
E mostra quali competenze mancano al candidato migliore, con i corsi corrispondenti. Stesso motore, due prodotti diversi: per il candidato è un percorso di crescita, per l'azienda un piano di formazione.

**9 · Obiettivo — 1**
Da qui i quattro compiti del sistema. Il primo: estrarre le competenze dal curriculum e dall'annuncio.

**10 · Obiettivo — 2**
Il secondo: confrontare le competenze del candidato con quelle richieste e produrre un punteggio.

**11 · Obiettivo — 3**
Il terzo: individuare lo *skill gap*, cioè le competenze richieste che il candidato non possiede.

**12 · Obiettivo — 4 e vincoli**
Il quarto: consigliare i corsi per colmare quel divario.
E due vincoli di progetto. I dati vanno elaborati **in locale**, senza inviarli a servizi esterni, perché sono dati personali. E il sistema deve funzionare su un normale computer da ufficio, senza schede grafiche dedicate.

**13 · Sezione: Stato dell'arte**
Vediamo come lavorano i sistemi esistenti e quali scelte ho fatto.

**14 · Sistemi industriali**
Il riferimento meglio documentato è LinkedIn, che lavora su oltre 41.000 competenze. La loro architettura ha due fasi: un confronto per somiglianza **propone** molti candidati, e un modello addestrato **decide** quali tenere.

**15 · Il nostro caso**
Io quei dati etichettati non li avevo. Quindi nel mio sistema a decidere resta la soglia di somiglianza: se due testi si assomigliano abbastanza, la competenza viene accettata.
Tenete a mente questa differenza, perché è all'origine di diversi problemi che vi racconterò.

**16 · Modello di embedding**
Per misurare la somiglianza di significato uso `multilingual-e5-base`, che trasforma una frase in un vettore di 768 numeri — quello che si chiama *embedding*. Lo uso **zero-shot**, cioè senza addestrarlo sul dominio dei curriculum: addestrarlo richiederebbe esattamente i dati che non ho.

**17 · Sezione: Il dataset**
Passiamo ai dati su cui ho lavorato.

**18 · ESCO**
Il vocabolario condiviso è ESCO, la classificazione europea di competenze e occupazioni: quasi 14.000 competenze, circa 3.000 occupazioni, quasi 99.000 etichette contando le denominazioni alternative. Ogni voce ha un identificativo stabile, ed è questo che permette di confrontare un curriculum e un annuncio scritti con parole diverse.

**19 · Il problema dei dati**
Qui ho incontrato il primo ostacolo: curriculum reali in quantità non erano reperibili, perché contengono dati personali.

**20 · La soluzione**
La soluzione è stata generare un dataset sintetico: curriculum e annunci finti, ma realistici.

**21 · Dataset sintetico**
Ho generato 810 curriculum, resi in PDF con tre impaginazioni diverse, e 810 annunci. I testi li ha scritti un modello linguistico, Llama 3.3. Ho scelto 135 occupazioni da ESCO, bilanciate sui nove settori professionali, e per ciascuna ho prodotto documenti a tre livelli di esperienza.

**22 · Come si valuta — 1**
Il procedimento è in tre passi. Primo: per ogni documento campiono alcune competenze da ESCO.

**23 · Come si valuta — 2**
Secondo: chiedo al modello linguistico di scrivere un curriculum o un annuncio che le contenga.

**24 · Come si valuta — 3**
Terzo: faccio leggere il documento al mio sistema e confronto ciò che estrae con le competenze campionate. Così so quali risposte sono giuste e quali sbagliate, senza annotare nulla a mano.

**25 · Cosa succede davvero** ⚠️
C'è però un dettaglio che condiziona ogni numero. Prendiamo un cuoco: campiono otto competenze — salse, HACCP, gestione della dispensa. Il modello, per scrivere un testo realistico, ne nomina anche altre: il lavoro in brigata, la gestione dei tempi. Il mio sistema le riconosce correttamente, ma non erano nella lista iniziale, quindi **vengono contate come errori**.
Le mie metriche sono perciò un **limite inferiore**: il valore vero è quello misurato o migliore, mai peggiore.

**26 · Sezione: L'architettura**
Vediamo come è costruito il sistema.

**27 · Architettura — parser**
Il primo blocco sono i parser: i programmi che leggono un curriculum o un annuncio — PDF, Word o testo — e ne estraggono le informazioni.

**28 · Architettura — nucleo**
Il cuore è il nucleo semantico: trasforma i testi in vettori e li collega alle competenze ESCO.

**29 · Architettura — matching**
Poi il matching, che confronta il profilo del candidato con quello dell'annuncio e produce il punteggio.

**30 · Architettura — corsi**
Infine il raccomandatore, che parte dalle competenze mancanti e propone i corsi.
Il punto chiave è che tutti i componenti condividono lo stesso nucleo semantico: per questo le competenze sono confrontabili fra loro.

**31 · Sezione: Parser dei curriculum**
Entriamo nel dettaglio, partendo dal parser dei curriculum.

**32 · Parser dei curriculum** ⚠️
Su 810 curriculum: precision 0,907, recall 0,860, F1 0,878. Il risultato regge su tutte e tre le impaginazioni, con uno scarto contenuto fra la migliore e la peggiore.

**33 · Evoluzione del parser**
Non ci sono arrivato subito. Il grafico mostra le tre versioni successive: dalla prima all'ultima la precision sale di quasi 15 punti e l'F1 di oltre 25. Ora vi mostro le due correzioni che hanno prodotto quei salti.

**34 · I filtri del parser**
Prima però i filtri. Dopo il confronto per significato alcune etichette vengono accettate perché *suonano* simili ma sono sbagliate: sigle di due lettere, frammenti di frase, nomi di attrezzature mai citate. I filtri le eliminano.
L'ultimo della lista — quello che scarta le etichette formulate come attività — è il più ampio: elimina il 29% dell'ontologia. Ed è proprio lui a creare il primo problema.

**35 · Due correzioni**
Le due correzioni principali sono queste.
La prima nasce da quel filtro: eliminando tutte le etichette in forma di attività scartava anche competenze legittime, che in ESCO sono semplicemente scritte così. Invece di indebolire il filtro ho aggiunto un dizionario di espressioni italiane che le recupera per un'altra via. La recall passa da 0,547 a 0,860.
La seconda: le lingue venivano estratte due volte, una dal rilevatore dedicato e una come competenza. Togliendo il doppione ho eliminato 489 errori in un colpo solo.

**36 · Il caso francese** ⚠️
Il caso più netto è il francese: 183 estrazioni, **nessuna corretta**. Questi 489 doppioni erano circa un terzo di tutti i **falsi positivi** del parser.
E la cosa importante è **come** l'ho riconosciuto: non perché fosse un errore grande, ma perché era sempre uguale. Zero giuste su 183 non è un modello impreciso — è un meccanismo che sbaglia sempre.

**37 · Sezione: Parser degli annunci**
Passiamo al parser degli annunci, che è stata la parte più difficile.

**38 · Parser degli annunci**
Un annuncio è prosa libera: niente sezioni, niente elenchi su cui appoggiarsi. I risultati iniziali erano scarsi — F1 0,391, precision 0,297 — e la ragione è una sola: il sistema estraeva **quasi il doppio** delle competenze attese.

**39 · Il difetto** ⚠️
Cercando la causa ho trovato questo. Da una frase come *«the successful candidate will be responsible for coordinating technological activities»*, il segmentatore isolava la sola parola «responsible» e la collegava alla competenza ESCO «comportarsi in modo responsabile». È accaduto in 792 annunci su 810, con 792 errori.
E qui sta il punto: **quel collegamento era corretto**. Il modello aveva fatto il suo lavoro. Era sbagliata la domanda — gli stavamo chiedendo di interpretare un aggettivo isolato dal suo complemento, che da solo non significa niente.

**40 · Quattro tentativi falliti**
Prima di arrivare alla soluzione ho progettato e misurato quattro contromisure, e nessuna ha funzionato: un confronto lessicale aggiuntivo, che peggiorava i risultati; una correzione statistica sulle etichette, che non ha avuto effetto perché il problema era nelle domande, non nelle etichette; un controllo sulle ripetizioni dentro il documento, che presupponeva una forma del problema diversa da quella reale; e il riuso dei filtri del parser dei curriculum, tarati su un difetto diverso.
Le racconto perché un tentativo fallito di cui si capisce il meccanismo insegna quanto uno riuscito.

**41 · Il vincolo multi-parola** ⚠️
La contromisura efficace è stata questa: dalla prosa accetto solo candidati di almeno due parole. Elimina il 45,5% dei candidati e quasi tutti gli errori sistematici.
La precision sale da 0,297 a 0,540, la recall scende da 0,615 a 0,581. Il bilancio completo: 334 veri positivi persi contro 10.076 falsi positivi eliminati, uno a trenta.

**42 · Il classificatore appreso**
Poi ho aggiunto un classificatore: un piccolo modello che impara a decidere se tenere o scartare una competenza. È, in scala ridotta, la seconda fase dell'architettura di LinkedIn.
Lo addestro su 11.071 esempi già etichettati dal confronto con la ground truth — senza lavoro manuale — e lo provo su 27 occupazioni mai viste in addestramento, non su altri annunci degli stessi mestieri.
Ho scelto una regressione logistica di proposito, perché i pesi si possono leggere. E leggendoli: il segnale più forte, con il segno meno perché spinge a rifiutare, è il tasso di errore storico dell'etichetta. La somiglianza semantica pesa un nono. È la conferma numerica di quello che vi ho appena raccontato con «responsible».

**43 · Classificatore contro denylist**
Qui confronto il classificatore con una denylist, cioè una lista di etichette troppo generiche da scartare sempre.
Il confronto va fatto con attenzione: la lista va costruita **solo** sulle 81 occupazioni di addestramento. Costruita invece su tutte, vedrebbe in anticipo i dati di test e sembrerebbe migliore del classificatore. Fatto correttamente, vince il classificatore.

**44 · La soluzione** ⚠️
Ecco il percorso completo. Senza rimedi F1 0,391; con il vincolo multi-parola e il classificatore si arriva a 0,629, con una precision finale di 0,807.

**45 · Sezione: Matching engine**
Passiamo al calcolo della compatibilità.

**46 · Matching** ⚠️
Il punteggio è una **media pesata** di tre parti — non una somma: il risultato resta fra zero e uno.
La più importante, con il 67,5% del peso, è la copertura dei requisiti. Poi l'occupazione, con il 22,5%: quanto il mestiere del candidato somiglia a quello richiesto. Infine il livello, con il 10%.
In questo esempio due competenze coincidono esattamente, due vengono riconosciute come sinonimi — il candidato scrive «uso della centralina diagnostica» dove l'annuncio chiede «strumenti diagnostici elettronici» — e due mancano. Si arriva a 0,559 sulle competenze, 0,654 aggiungendo l'occupazione, **0,689** con il livello allineato. Cioè **69% di compatibilità**.

**47 · Il difetto del matching**
Anche qui ho trovato un difetto. Il sistema sceglieva troppo spesso annunci junior: 47 volte su 100 contro le 33 attese, e indovinava il livello solo nel 37% dei casi.
La causa non era nel candidato: gli annunci junior elencano meno requisiti, quindi la frazione coperta risulta più alta **per pura aritmetica del denominatore**.

**48 · La correzione**
Due interventi: ho aggiunto al punteggio il numero assoluto di competenze coperte, non solo la percentuale, e il confronto esplicito fra il livello del candidato e quello dell'annuncio. L'accuratezza sul livello passa dal 37% al 97%.

**49 · Il peso del livello**
Ma attenzione. Il peso del livello era 0,3, scelto perché migliorava quel test — un test che però confronta solo annunci della stessa occupazione, dove il contenuto è costante e un peso alto non può che aiutare.
Misurato su un altro compito, lo stesso parametro ribaltava i confronti: un candidato senior veniva abbinato a un creatore di maschere teatrali invece che al suo stesso mestiere, solo perché il livello coincideva per caso.
Abbassandolo a 0,10 la sovrapposizione fra livelli scende dal 40% al 2,5% e l'accuratezza resta al 97%. La lezione: un parametro ottimizzato su un test che isola una sola dimensione può peggiorare tutte le altre.

**50 · Il limite del test sull'occupazione**
Un altro numero da leggere con attenzione: il sistema riconosce l'occupazione giusta nel 96,7% dei casi.
Sembra ottimo, ma nel dataset sintetico curriculum e annuncio della stessa occupazione condividono il 64% delle competenze, mentre il 93% delle coppie di occupazioni diverse non ne condivide **nessuna**. Al sistema basta accorgersi che due profili hanno qualcosa in comune per vincere. Il numero è vero, ma il compito è più facile di quanto sarebbe nella realtà — e lo dico io prima che me lo chiediate.

**51 · Sezione: Raccomandatore di corsi**
Arriviamo all'ultimo modulo.

**52 · Il catalogo Coursera**
Per i corsi uso il catalogo Coursera. Ogni corso ha dei tag, cioè parole chiave. Io collego ogni competenza ESCO a un tag, e propongo i corsi con quel tag.
Primo limite: solo il 23,7% delle competenze ESCO ha almeno un corso associato. Coursera è un catalogo accademico e tecnologico, e molti mestieri manuali non sono coperti.

**53 · Copertura nominale**
Nel mio test, per il 43,1% delle competenze mancanti il sistema trova almeno un corso. La chiamo copertura **nominale**: sulla carta, un corso esiste.

**54 · Copertura effettiva**
Ma un corso che esiste non è per forza un corso utile. Ho controllato a mano trenta competenze: la copertura **effettiva**, cioè con almeno un corso davvero pertinente, è il 23,3%.

**55 · La pertinenza**
E guardando le singole raccomandazioni, solo 12 su 65 — il 18,5% — erano pertinenti.
La causa è precisa: l'indice collega i corsi ai **tag**, non alle competenze. Quindi il punteggio misura quanto una competenza somiglia a un tag, non se quel corso la insegni. È il difetto che ho misurato invece di dichiararlo, ed è il primo da correggere.

**56 · Sezione: Risultati**
Vediamo i risultati nel loro insieme.

**57 · Quadro delle metriche**
Questa tabella riassume tutto, sempre con un termine di confronto accanto: il valore di partenza o la baseline casuale.
Nessuno di questi numeri va letto da solo: ognuno porta un limite che ne cambia il significato, e ve li ho mostrati uno per uno.

**58 · Quindici curriculum reali**
Infine la prova sui primi documenti che nessuno strumento mio ha generato: quindici curriculum veri. Non ha confermato i risultati — ha fatto emergere **tre difetti che i dati sintetici nascondevano per costruzione**.
Le certificazioni venivano assegnate con una precisione di 0,25, tre su quattro sbagliate: risolto, ora 0,837. Gli anni di esperienza: sette curriculum su quindici davano zero, e quei candidati venivano classificati junior per errore — risolto, con i casi residui dichiarati invece che indovinati. E il riconoscimento delle sezioni, su due curriculum su quindici: questo è **aperto, e lo dichiaro**.

**59 · Sezione: Confronto multimodello**
Un'ultima domanda: quanto conta il modello che ho scelto all'inizio?

**60 · Il disegno sperimentale**
Ho confrontato due famiglie di modelli per due taglie, sugli stessi dati, misurando due compiti diversi: l'estrazione delle competenze, che attraversa tutta la pipeline, e il riconoscimento dell'occupazione, dove il modello decide quasi da solo.
Primo risultato: più grande non vuol dire migliore. mpnet ha il doppio delle dimensioni di MiniLM e riconosce **peggio** le occupazioni. L'effetto della taglia dipende dalla famiglia — ed è un'interazione visibile solo perché ho variato i due fattori insieme.

**61 · Il confronto a soglie fisse** ⚠️
Il confronto ha fatto emergere anche due errori miei.
Uno nel codice: un file di appoggio condiviso fra modelli diversi, che produceva **1.765 punteggi sopra 1** — valori impossibili per un coseno, ed è esattamente per questo che sono stati facili da trovare.
L'altro di impostazione: usavo le stesse soglie per tutti, ma ogni modello ha una sua scala. MiniLM superava la soglia solo in 45 annunci su 810. Le soglie fisse misuravano quanto un modello somiglia a E5, non la sua qualità. Le ho ricalibrate per ciascuno.

**62 · Cinque modelli a confronto**
Con le soglie calibrate: sulle competenze i cinque modelli sono **equivalenti**, 0,026 fra il primo e l'ultimo. Sull'occupazione lo scarto sale a 0,336, tredici volte tanto, e vince bge-m3 con 0,861.
Lo stesso bge-m3, però, sulle competenze **perde** due millesimi. Stesso modello, stessi documenti, due conclusioni opposte a seconda del compito.

**63 · Quanto conta il modello**
Questa è la lezione più importante.
Sulle competenze il lavoro di pipeline — i filtri e le correzioni che vi ho mostrato — vale 0,238 di F1. Passare a un modello più grande della stessa famiglia vale 0,003. Passare a bge-m3 vale meno due millesimi.
La formulazione corretta non è «il modello conta poco», ma che **quanto conta dipende da quanta pipeline lo circonda**: dove ci sono stadi a valle, questi assorbono le differenze; dove il modello è nudo, la sua qualità passa intera. È una regola pratica: dice dove conviene investire e dove no.

**64 · Sezione: Conclusioni**
Arrivo alle conclusioni.

**65 · Limiti**
Il lavoro ha dei limiti, ed è giusto dichiararli.
I dati sono sintetici e condividono il lessico con l'ontologia. La valutazione richiede l'identificativo ESCO esatto, quindi conta come errore anche una competenza concettualmente giusta: i numeri sono prudenti. Il collegamento fra competenze e corsi passa per i tag ed è debole. E i pesi del punteggio sono stati scelti, non ottimizzati.

**66 · Sviluppi futuri**
Da questi limiti nascono gli sviluppi futuri, in quest'ordine.
Dati reali annotati, per annunci e curriculum: lo strumento di annotazione è già costruito e il costo per documento l'ho misurato.
Il confronto completo con ESCOXLM-R, un modello addestrato apposta per estrarre competenze: in una prima prova produce sette frammenti privi di contenuto su diecimila, contro i 792 falsi positivi del solo «responsible».
Scegliere i corsi confrontando la competenza con la **descrizione**, non con il tag.
E un dataset in cui le competenze cambino davvero con il livello di esperienza, perché oggi cambia solo quante sono.

**67 · Grazie**
Riassumendo: ho costruito un sistema che legge curriculum e annunci, ne misura la compatibilità, individua le competenze mancanti e propone dei corsi — tutto in locale, su un normale computer.
Ma la parte del lavoro che mi sembra più solida non sono i numeri riusciti: è che misurando ho scoperto che alcuni di quei numeri non misuravano ciò che sembravano misurare, e li ho rifatti.
Grazie per l'attenzione, resto a disposizione per le domande.

---

## Correzioni applicate

| slide | cosa ho cambiato |
|---|---|
| 25 | tolto il «quindi» ripetuto; esplicitato cosa significa «limite inferiore» |
| 32 | «grafiche» → «impaginazioni» |
| 36 | «un terzo di tutti gli errori» → «dei **falsi positivi**» (489 su 1.480) |
| 39 | frase sgrammaticata riscritta; aggiunta la frase inglese completa |
| 41 | aggiunto il bilancio 334 contro 10.076 |
| 44 | «arrivamo» → «arriviamo»; precision 0,807 invece di «circa 0,81» |
| **46** | **pesi 67,5 / 22,5 / 10 e punteggio finale 0,689 — da correggere anche sulla slide** |
| 49 | «mask maker» reso in italiano come «creatore di maschere teatrali» |
| 61 | «più di 1000» → 1.765; tolta la virgoletta di troppo in coda |
| 67 | chiusura riscritta sul filo conduttore della presentazione |
