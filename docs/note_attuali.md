# Note del relatore — testo attuale, trascritto come nel file


## Slide 1 — UNIVERSITÀ DEGLI STUDI ROMA TRE

salve a tutti. Mi chiamo Samuele Miele e oggi vi presento il mio lavoro di tesi. Tecniche di intelligenza artificiale per il supporto ai percorsi di avanzamento professionale.

## Slide 2 — Il problema

Partiamo dal problema che volevo risolvere.

## Slide 3 — Chi cerca lavoro

Immaginate una persona che cerca lavoro. Ha davanti tanti annunci e non sa a quale sia il piu adatto.
Leggerli tutti e confrontarli, richiede tantissimo tempo

## Slide 4 — Chi cerca lavoro

Il sistema che ho progettato per ogni annuncio quindi calcola una percentuale di compatibilità con il curriculum.

## Slide 5 — Chi cerca lavoro: la roadmap

E, una volta trovato l'annuncio più adatto, il sistema dice anche quali competenze mancano in ordine di priorità,
il candidato quindi non riceve solo un voto, ma una strada da seguire.

## Slide 6 — Chi seleziona

Pensate adesso a un selezionatore delle risorse umane che riceve centinaia di curriculum per una sola posizione.

## Slide 7 — Chi seleziona

Anche qui il sistema calcola, per ogni candidato, una percentuale di compatibilità con l'annuncio e mette in evidenza il più adatto.

## Slide 8 — Chi seleziona: la formazione

E mostra al selezionatore quali competenze mancano al candidato migliore e quali corsi potrebbe seguire.
È utile per quanto riguarda la formazione.

## Slide 9 — Obiettivo

Nella creazione del progetto quindi individuiamo 4 obbiettivi principali:
Il primo è estrarre le competenze dal curriculum o dall’annuncio

## Slide 10 — Obiettivo

Il secondo passo è quindi confrontare le competenze del candidato con quelle richieste e dare un punteggio.

## Slide 11 — Obiettivo

Il terzo passo è trovare lo «skill gap», cioè l'elenco delle competenze richieste che il candidato non ha.

## Slide 12 — Obiettivo

Il quarto passo è consigliare i corsi per colmare quel divario.
C'erano poi due vincoli importanti. Primo: i dati devono essere elaborati in locale, senza inviarli a servizi esterni, perché si parla di dati personali.
 Secondo: il sistema deve funzionare su un normale computer da ufficio.

## Slide 13 — Stato dell'arte e scelte

Vediamo ora come lavorano i sistemi già esistenti e quali scelte ho fatto io.

## Slide 14 — Sistemi industriali

Il riferimento più conosciuto è LinkedIn, che usa un elenco di oltre 41.000 competenze.
Il loro sistema lavora in due fasi. Prima, un confronto per somiglianza propone tante competenze, poi un modello addestrato che decide quali tenere.

## Slide 15 — Il nostro caso

Nel mio caso però mancavano dei dati etichettati.
Quindi nel mio sistema decide una soglia di somiglianza.   Se due testi si somigliano allora la competenza è accettata
Questa differenza tornerà più volte, perché è all'origine di diversi problemi che ho dovuto risolvere.

## Slide 16 — Modello di embedding

Per misurare la somiglianza di significato uso un modello chiamato multilingual-e5-base.
Questo modello trasforma una frase in un vettore, questo si chiama embedding.
Lo uso "zero-shot", senza addestrarlo sul mondo dei curriculum.

## Slide 17 — Il dataset

Passiamo ai dati su cui ho lavorato.

## Slide 18 — ESCO

Il vocabolario di riferimento è ESCO, la classificazione europea di competenze e occupazioni.
Contiene quasi 14.000 competenze, circa 3.000 occupazioni e quasi 99.000 etichette,.
Ogni competenza ha un codice, e questo permette di confrontare curriculum e annunci in modo stabile.

## Slide 19 — Il problema dei dati

Qui ho incontrato il primo grande problema: non era possibile trovare curriculum reali online, perché protetti dalla privacy.

## Slide 20 — Il problema dei dati

La soluzione è stata creare un dataset sintetico: curriculum e annunci finti, ma realistici.

## Slide 21 — Dataset sintetico

Ho generato quindi 810 curriculum, in PDF con tre layout diversi, e 810 annunci di lavoro.
I testi li ha scritti un modello linguistico ovvero Llama 3.3
Ho scelto 135 occupazioni da ESCO, bilanciate tra i vari settori, e per ognuna ho creato documenti per vari livelli di esperienza.

## Slide 22 — Come si valuta

Come si genera e si valuta il dataset.
Primo: per ogni documento scelgo a caso alcune competenze da ESCO.

## Slide 23 — Come si valuta

Secondo: chiedo al modello linguistico di scrivere un curriculum e un annuncio che contengano quelle competenze.

## Slide 24 — Come si valuta

Terzo: faccio leggere il documento al mio sistema e confronto le competenze che trova con quelle scelte all'inizio. Così so esattamente quali risposte sono giuste e quali sbagliate.

## Slide 25 — Cosa succede davvero

C'è però un dettaglio importante. Prendiamo un cuoco: scelgo otto competenze, come creazione salse, HACCP e gestione della dispensa.
Il modello, per scrivere un curriculum realistico, aggiunge anche altre cose, come il lavoro in brigata o la gestione dei tempi. Il mio sistema le riconosce, ma siccome non erano nella lista iniziale vengono contate come errori.
Quindi i numeri che vedrete quindi sono un limite inferiore.

## Slide 26 — L’architettura

Vediamo come è costruito il sistema.

## Slide 27 — Architettura

Il primo blocco sono i parser, cioè i programmi che leggono un curriculum o un annuncio, in PDF, Word o testo semplice, e ne estraggono le informazioni.

## Slide 28 — Architettura

Il cuore del sistema è il nucleo semantico: la parte che trasforma i testi in numeri con il modello di embedding e li collega alle competenze di ESCO.

## Slide 29 — Architettura

Poi c'è il matching, cioè il confronto tra il profilo del candidato e quello dell'annuncio, che produce il punteggio di compatibilità.

## Slide 30 — Architettura

Infine il raccomandatore, che parte dalle competenze mancanti e propone i corsi.
Il punto chiave è che tutti i componenti, usano lo stesso nucleo semantico. Così le competenze si possono confrontare direttamente.

## Slide 31 — Parser dei curriculum

Entriamo nel dettaglio, partendo dal parser dei curriculum.

## Slide 32 — Parser dei curriculum

Su 810 curriculum la precision è 0,907, La recall è 0,860 e l'F1 0,878. Il risultato è stabile su tutte e tre le grafiche.

## Slide 33 — Evoluzione del parser dei curriculum

Non ci sono arrivato subito. Il grafico mostra come il parser è migliorato versione dopo versione.
Dalla prima versione all'ultima la precision è salita di quasi 15 punti e l'F1 di oltre 25. Tra poco vi spiego le due correzioni principali.

## Slide 34 — I filtri del parser

Prima però vi mostro i filtri. Dopo il confronto per significato, alcune competenze vengono accettate perché suonano simili, ma sono sbagliate. I filtri le eliminano.

## Slide 35 — Curriculum: due correzioni

Le due correzioni principali sono queste.
La prima: il filtro sulle attività eliminava anche competenze giuste. Invece di toglierlo, ho aggiunto un dizionario di sinonimi in italiano che le recupera. Così la recall è passata da 0,547 a 0,860.
La seconda: le lingue venivano estratte due volte, una come lingua e una come competenza. Togliendo il doppione ho eliminato 489 errori in un colpo solo.

## Slide 36 — Il caso «francese»

Il caso più evidente è il francese: ogni volta che compariva era un doppione. 183 estrazioni, nessuna corretta.
Questi 489 errori erano circa un terzo di tutti gli errori del parser.
L'errore si riconosceva perché era sempre uguale, non perché fosse grande: zero giuste su 183 è il segnale di un problema sistematico.

## Slide 37 — Parser degli annunci

Passiamo al parser degli annunci, che è stata la parte più difficile.

## Slide 38 — Parser degli annunci

Un annuncio è scritto in prosa libera, senza sezioni ordinate come in un curriculum.
All'inizio i risultati erano scarsi: F1 poco sotto il 40% e precision che non arriva nemmeno al 30%,
Il motivo è che il sistema trovava quasi il doppio delle competenze attese.

## Slide 39 — Il difetto

Cercando la causa ho trovato questo. In una frase come contenente il frammento «responsible», il sistema isolava la sola parola "responsible" e la collegava alla competenza "comportarsi in modo responsabile". È successo in 792 annunci, con 792 errori.
il modello però  non sbagliava, Era sbagliata la domanda: gli chiedevamo di interpretare una parola isolata, senza contesto.

## Slide 40 — Quattro tentativi falliti

Prima di trovare la soluzione ho provato quattro strade, e nessuna ha funzionato.
Un confronto parola per parola in più, che peggiorava i risultati. Una correzione statistica sulle etichette, Un controllo sulle ripetizioni dentro lo stesso documento E il riuso dei filtri del parser dei curriculum.
Li racconto perché anche un tentativo fallito, se si capisce perché fallisce, insegna qualcosa.

## Slide 41 — Il vincolo multi-parola

La soluzione che ha prodotto piu risultati alla fine è stata questa: dalla prosa accetto solo candidati di almeno due parole.
Così elimino il 45,5% dei candidati e quasi tutti gli errori sistematici.
La precision sale da 0,297 a 0,540, mentre la recall scende di poco.

## Slide 42 — Il classificatore appreso

Poi ho aggiunto un classificatore, cioè un piccolo modello che impara a decidere se tenere o scartare una competenza. È, in piccolo, la seconda fase di LinkedIn.
Lo addestro su 11.071 esempi già etichettati dal dataset, senza lavoro manuale, e lo provo su 27 occupazioni che non ha mai visto.
Ho scelto una regressione logistica perché si può leggere: vediamo, per esempio, che il segnale più forte per scartare una competenza è il tasso di errore storico.

## Slide 43 — Classificatore contro denylist

Qui confronto il classificatore con una denylist, cioè una lista nera di competenze troppo generiche da scartare sempre.
Per un confronto onesto, la lista nera è costruita solo sulle occupazioni di addestramento, senza vedere quelle di test. Così il classificatore vince.

## Slide 44 — La soluzione

Ecco il risultato finale. Senza correzioni l'F1 era 0,391; con il vincolo delle due parole e il classificatore arrivamo al risultato migliore a 0,629.
Con una precision finale di circa 0,81.

## Slide 45 — Matching engine

Passiamo al matching, cioè al calcolo della compatibilità.

## Slide 46 — Matching

Il punteggio è una media pesata di tre parti.
La più importante, con il 72% del peso, è la copertura: quante competenze richieste il candidato possiede.
Poi l'occupazione, con il 18%: ovvero la pertinenza del mestiere.
Infine il livello, con il 10%: se junior, mid o senior coincidono.
In questo esempio il candidato ottiene un punteggio finale di 0,672, cioè il 67% di compatibilità.

## Slide 47 — Il difetto del matching

Anche qui ho trovato un difetto. Il sistema sceglieva troppo spesso annunci junior: 47 volte su 100, quando ci si aspetterebbe circa 33. E indovinava il livello giusto solo nel 37% dei casi.
Il motivo: gli annunci junior chiedono meno competenze, quindi è più facile coprirle tutte.

## Slide 48 — La correzione

Per correggerlo ho fatto due cose. Ho aggiunto al punteggio anche il numero di competenze coperte, non solo la percentuale. E ho aggiunto il confronto tra il livello del candidato e quello dell'annuncio.
Così l'accuratezza sul livello è passata dal 37% al 97%.

## Slide 49 — Il peso del livello

Ma attenzione. All'inizio il peso del livello era 0,3, scelto perché migliorava quel test.
In un altro confronto però creava problemi: un candidato senior finiva abbinato a un annuncio di un settore completamente diverso, solo perché il livello coincideva.
Abbassando il peso a 0,10, la confusione tra livelli scende dal 40% al 2,5%, e l'accuratezza sul livello resta al 97%.

## Slide 50 — Il limite del test sull’occupazione

Un altro numero da leggere con attenzione: il sistema riconosce l'occupazione giusta nel 96,7% dei casi.
Sembra ottimo, ma nel dataset sintetico il 93% delle coppie di occupazioni diverse non ha nessuna competenza in comune. Quindi distinguere un mestiere dall'altro è più facile di quanto sarebbe nella realtà.

## Slide 51 — Raccomandatore di corsi

Arriviamo all'ultimo modulo: il raccomandatore di corsi.

## Slide 52 — Il catalogo Coursera

Per i corsi uso il catalogo di Coursera. Ogni corso ha dei tag, cioè delle parole chiave.
Collego ogni competenza ESCO a un tag, e propongo i corsi con quel tag.
Il problema è che solo il 23,7% delle competenze ESCO ha almeno un corso. Coursera è un catalogo soprattutto accademico e tecnologico, e molti mestieri manuali non sono coperti.

## Slide 53 — Raccomandatore di corsi

Nel mio test, per il 43,1% delle competenze mancanti il sistema trova almeno un corso. La chiamo copertura nominale: sulla carta, un corso esiste.

## Slide 54 — Raccomandatore di corsi

Ma un corso che esiste non è per forza un corso utile. Ho controllato a mano trenta competenze: la copertura effettiva, cioè con un corso davvero adatto, è solo il 23,3%.

## Slide 55 — Raccomandatore di corsi

E guardando i singoli corsi proposti, solo 12 su 65, cioè il 18,5%, erano davvero pertinenti.
La conclusione è che il catalogo c'è, ma il collegamento tra competenza, tag e corso è debole. È uno dei punti da migliorare.

## Slide 56 — Risultati

Vediamo ora i risultati nel loro insieme.

## Slide 57 — Quadro delle metriche

Questa tabella riassume tutti i numeri. 
E come avete potuto vedere nessuno di questi numeri va letto da solo: ognuno ha un limite che ne cambia il significato, come vi ho mostrato.

## Slide 58 — Quindici curriculum reali

Infine ho provato il sistema su quindici curriculum veri. Non ha semplicemente confermato i risultati: ha fatto emergere tre difetti che i dati sintetici nascondevano.
Primo, le certificazioni venivano assegnate troppo facilmente, con una precisione di 0,25; alzando la soglia è salita a 0,837.
Secondo, gli anni di esperienza: in 7 curriculum su 15 risultavano zero; ora ci sono 8 stime corrette.
Terzo, in 2 curriculum la sezione esperienza non viene riconosciuta: questo problema è ancora aperto.

## Slide 59 — Confronto multimodello

Un'ultima domanda: quanto conta il modello di embedding che ho scelto?

## Slide 60 — Il disegno sperimentale

Ho confrontato modelli di due famiglie e due taglie, sugli stessi dati, misurando competenze e occupazione. Primo risultato: più grande non vuol dire migliore. mpnet è più grande di MiniLM, ma riconosce peggio le occupazioni

## Slide 61 — Il confronto a soglie fisse

Il confronto ha anche fatto emergere un errore di metodo: usavo le stesse soglie per tutti, ma ogni modello ha una sua scala di punteggi.
Ho riconosciuto questo errore trovando piu di 1000 punteggi sopra l’uno, e MiniLM, per esempio, rispondeva solo su 45 annunci su 810. Le soglie fisse misuravano quanto un modello somiglia a E5, non la sua qualità. Così le ho tarate per ciascun modello."

## Slide 62 — Cinque modelli a confronto

Con le soglie tarate, sulle competenze i modelli sono quasi pari: appena 0,026 di scarto. Sull'occupazione lo scarto sale a 0,336, e vince bge-m3 con 0,861

## Slide 63 — Quanto conta il modello

Questa è forse la lezione più importante.
Sulle competenze, il lavoro sulla pipeline, cioè le correzioni e i filtri che vi ho mostrato, ha fatto guadagnare 0,238 di F1. Passare a un modello più grande della stessa famiglia ha fatto guadagnare 0,003, e passare a bge-m3 addirittura -0,002.
Quindi, dove il sistema ha una struttura ben costruita, conviene investire nella struttura più che in un modello più grande.

## Slide 64 — Conclusioni

Arrivo alle conclusioni.

## Slide 65 — Limiti

Il lavoro ha dei limiti, ed è giusto dichiararli.
Primo: i dati sono sintetici e usano lo stesso vocabolario di ESCO.
Secondo: la valutazione conta come errore anche una competenza giusta ma con un codice ESCO diverso, quindi i numeri sono prudenti.
Terzo: il collegamento tra competenze e corsi è debole.
Quarto: i pesi del punteggio di compatibilità sono stati scelti a mano, non ottimizzati.

## Slide 66 — Sviluppi futuri

Da questi limiti nascono gli sviluppi futuri.
Provare il sistema su annunci e curriculum reali, controllati a mano.
Confrontarlo con ESCOXLM-R, un modello addestrato apposta per estrarre competenze, che in una prima prova evita quasi del tutto le parole isolate come "responsible".
Scegliere i corsi confrontando la competenza con la descrizione del corso, non solo con i tag.
E creare un dataset in cui le competenze cambiano davvero con il livello di esperienza.

## Slide 67 — Grazie

Riassumendo: ho costruito un sistema che legge curriculum e annunci, ne misura la compatibilità, trova le competenze mancanti e propone dei corsi, tutto in locale e su un normale PC.
E ho imparato che misurare con attenzione ogni risultato è importante quanto costruire il sistema.
Grazie per l'attenzione, sono a disposizione per le domande.