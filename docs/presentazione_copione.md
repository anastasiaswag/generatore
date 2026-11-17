# Copione — 10 minuti esatti

Tempo totale **10:11** con le pause. Parla a ritmo normale, non veloce: il
copione è già tarato perché tu non debba correre.

**Le tre pause vere** sono segnate con *(pausa)*. Sono alla slide 11, alla 26 e
alla 32. In quei tre punti il silenzio lavora più delle parole.

**Se sei in ritardo**, i tagli in ordine: slide 17 (modello), slide 29
(matching, le tre componenti), slide 22 (architettura). Non tagliare mai la 26.

---

## 1 · Frontespizio — 15"

> Buongiorno. Sono Samuele Miele, e vi presento il lavoro svolto durante il
> tirocinio di tesi: un sistema che mette in relazione curriculum e annunci di
> lavoro attraverso l'intelligenza artificiale semantica.

⚠️ *Le note di questa slide contengono ancora il testo di un'altra tesi —
«AetherSense, telemetria IoT». Cancellale.*

## 2 · Sezione 1 — 3"

> Partiamo dal problema.

## 3 · Chi cerca lavoro — 8"

> Questo è un candidato davanti a un elenco di annunci. Per ciascuno si pone la
> stessa domanda: quanto sono adatto?

## 4 · Chi cerca lavoro — 10"

> Il primo obiettivo è trasformare quei punti interrogativi in un numero. Non
> un parere: una stima di compatibilità, calcolata allo stesso modo per tutti.

## 5 · La roadmap — 16"

> Ma un punteggio da solo non serve a chi cerca lavoro. Se l'annuncio più
> compatibile è al 92%, la domanda successiva è: che cosa mi manca per il
> restante 8%? Il sistema individua le competenze mancanti e le ordina per
> priorità, poi associa a ciascuna un corso. Da un numero a un percorso.

## 6 · Chi seleziona — 5"

> Lo stesso problema esiste dall'altra parte.

## 7 · Chi seleziona — 6"

> Un selezionatore ha un annuncio e una pila di curriculum, e gli serve lo
> stesso punteggio nella direzione opposta.

## 8 · La formazione — 10"

> E il divario, qui, cambia significato: non è ciò che manca al candidato per
> candidarsi, è il piano di formazione se decidi di assumerlo. **Stesso motore,
> due prodotti diversi.**

## 9 · Parole diverse — 7"

> Perché il problema è difficile. Un curriculum dice: ho progettato
> applicazioni per iOS.

## 10 · Parole diverse — 7"

> L'annuncio chiede: esperienza di sviluppo mobile.

## 11 · Zero parole in comune — 9"

> Per un lettore umano è la stessa cosa. Per un confronto parola per parola,
> **zero**.
>
> *(pausa)*

## 12 · Obiettivo — 18"

> Da qui i quattro compiti del sistema: estrarre le competenze dai due
> documenti, stimare la compatibilità, individuare il divario, e consigliare i
> corsi per colmarlo. Quattro componenti, ciascuno misurato separatamente.

## 13 · Sezione 2 — 3"

> Come lo risolve chi lo fa su scala industriale.

## 14 · Sistemi industriali — 25"

> Il riferimento meglio documentato è LinkedIn, che lavora su un grafo di oltre
> quarantunomila competenze. La loro architettura ha due stadi, ed è la
> distinzione che orienta tutto il mio lavoro: **la similarità semantica
> propone i candidati, ma non decide**. A decidere quali tenere è un modello
> addestrato a valle, su dati etichettati e segnali raccolti in produzione.

## 15 · Il nostro caso — 28"

> Io quei dati non li avevo. Nessun curriculum annotato, nessun segnale d'uso,
> nessuno storico di selezioni andate a buon fine.
>
> La conseguenza è precisa, e non è un dettaglio implementativo: **senza lo
> stadio di decisione, a decidere resta la soglia di similarità**. Lo strumento
> che nei sistemi industriali propone soltanto, qui propone e decide insieme.
>
> Gran parte dei difetti che vi racconto nascono da lì — e il lavoro di tesi è
> in buona parte il tentativo di ricostruire quello stadio mancante con i mezzi
> disponibili.

## 16 · ESCO — 15"

> Il vocabolario condiviso è ESCO, la tassonomia europea delle occupazioni:
> tremila occupazioni, quasi quattordicimila competenze, e quasi centomila
> etichette contando le denominazioni alternative. Multilingue, ed è la ragione
> per cui un curriculum italiano e un annuncio inglese si possono confrontare.

## 17 · Modello di embedding — 12"

> Il modello che traduce il testo in vettori è multilingual-E5, usato
> **zero-shot**: nessun addestramento sul dominio, perché addestrare richiede
> esattamente i dati che non ho.

## 18 · Sezione 3 — 3"

> Il dataset.

## 19 · Dataset sintetico — 22"

> Non avendo documenti reali in quantità, ne ho generati ottocentodieci per
> parte con un modello linguistico, campionando competenze e occupazioni da
> ESCO. I curriculum sono resi in PDF su tre template grafici diversi, perché
> il parser dovesse affrontare anche impaginazioni differenti.

## 20 · Come si valuta — 27"

> E qui sta la scelta metodologica che condiziona ogni numero che dirò.
>
> La verità di riferimento è **l'elenco di competenze dato in input al
> generatore**, non ciò che il generatore ha poi effettivamente scritto. Se il
> modello cita una competenza che non era stata campionata, il sistema che la
> estrae correttamente viene conteggiato come se avesse sbagliato.
>
> **Tutte le mie metriche sono quindi un limite inferiore.** Ho preferito
> dichiararlo una volta all'inizio piuttosto che giustificarlo ogni volta.

## 21 · Sezione 4 — 3"

> L'architettura.

## 22 · Architettura — 20"

> Due parser con strategie diverse — il curriculum ha sezioni su cui
> appoggiarsi, l'annuncio è prosa continua — ma con un nucleo semantico
> condiviso. A valle, il motore di matching e il raccomandatore di corsi.

## 23 · Parser dei curriculum — 13"

> Il parser dei curriculum arriva a F1 zero virgola ottocentosettantotto, con
> precisione superiore a novanta. Ma il numero interessante non è questo: è
> **come ci è arrivato**.

## 24 · Due correzioni — 30"

> Due interventi, ciascuno con una causa diagnosticata.
>
> Il richiamo passa da 0,55 a 0,86 grazie a un dizionario di alias italiani —
> serviva a compensare un effetto collaterale di un filtro precedente, non ad
> annullarlo.
>
> Il secondo è più interessante. ESCO cataloga le lingue anche come competenze,
> quindi ogni lingua dichiarata veniva estratta due volte: una dal percorso
> dedicato, una come competenza duplicata. Quattrocentottantanove falsi
> positivi, un terzo di tutti gli errori di precisione.
>
> **E l'ho riconosciuto dalla forma, non dalla dimensione**: il francese
> compariva centottantatré volte, e **nessuna era corretta**. Zero su
> centottantatré non è un modello impreciso — è un meccanismo che sbaglia
> sempre.

## 25 · Parser degli annunci — 18"

> L'annuncio è il caso difficile: prosa libera, nessuna struttura. Il punto di
> partenza era F1 0,39, con una precisione di 0,30 — il parser estraeva **quasi
> il doppio** delle competenze attese.

## 26 · Il difetto — 40"

> Invece di cercare di migliorare il modello, sono andato a vedere *quali*
> candidati sbagliati si ripetevano. E la risposta era netta: il frammento
> «responsible» compariva in settecentonovantadue annunci su ottocentodieci, e
> generava settecentonovantadue falsi positivi.
>
> Ora, il punto. L'etichetta ESCO che il modello gli associava —
> «comportarsi in modo responsabile» — **è il match corretto**. Il modello
> aveva fatto esattamente il suo lavoro.
>
> Il difetto non era nel modello e non era nell'ontologia: era **nella domanda
> posta al sistema**. Il segmentatore aveva isolato un aggettivo dal suo
> complemento, e si stava chiedendo quale competenza somigliasse di più a un
> frammento che non significava nulla.
>
> *(pausa di due secondi)*

## 27 · Quattro tentativi falliti — 22"

> Prima di capirlo ho progettato e misurato quattro contromisure. Nessuna ha
> funzionato, e le riporto in tesi tutte e quattro con la diagnosi del perché.
>
> La più istruttiva è il vincolo di reciprocità: presupponeva che il rumore si
> ripetesse *dentro* il documento, mentre il fenomeno era *fra* documenti.
> Rimedio corretto, problema con la forma sbagliata.

## 28 · La soluzione — 33"

> La contromisura efficace è stata accettare, dalla prosa, solo candidati di
> almeno due parole: elimina il 45% dei candidati, e il bilancio è
> trecentotrentaquattro veri positivi persi contro diecimila falsi positivi
> eliminati. Uno a trenta.
>
> Il grafico mostra il percorso completo, da 0,39 a 0,63.
>
> E la diagnosi ha una **conferma indipendente**: un riconoscitore addestrato,
> che non segmenta nello stesso modo, sugli stessi annunci produce **sette**
> frammenti privi di contenuto su diecimila. Contro i settecentonovantadue del
> solo «responsible».

## 29 · Matching — 13"

> Il punteggio di compatibilità combina tre componenti: quanto dei requisiti è
> coperto, quanto le occupazioni si somigliano, e quanto il livello di
> esperienza è allineato.

## 30 · Il difetto del matching — 22"

> Alla prima misura il sistema proponeva posizioni junior a chiunque:
> quarantasette volte su cento contro le trentatré attese, con un'accuratezza
> sul livello del 37%, appena sopra il caso.
>
> La causa non era nel candidato: **gli annunci junior elencano meno
> requisiti**, quindi la frazione coperta risultava più alta per pura
> aritmetica del denominatore.

## 31 · La correzione — 13"

> Due interventi — un termine sul numero assoluto di competenze coperte e
> l'allineamento esplicito del livello — portano l'accuratezza dal 37 al 97%.

## 32 · Raccomandatore di corsi — 30"

> E qui il terzo caso in cui la misura mi ha smentito.
>
> La copertura del divario risultava del 43%. Ma quel numero dice soltanto che
> **esiste** un corso associato alla competenza, non che sia quello giusto.
>
> Ho controllato a mano sessantacinque raccomandazioni: pertinenti il 18%. La
> copertura effettiva scende al 23%, con un intervallo di confidenza che non
> contiene il valore nominale.
>
> La causa è che l'indice collega i corsi ai **tag** della piattaforma, non
> alle competenze — e solo quel primo anello era stato misurato.
>
> *(pausa)*

## 33 · Sezione 5 — 3"

> I risultati.

## 34 · Cinque modelli — 27"

> Ho ripetuto l'intera pipeline con cinque modelli di embedding diversi,
> ricalibrando le soglie per ciascuno.
>
> Sulle competenze lo scarto fra il migliore e il peggiore è **0,026**.
> Sull'occupazione è **0,336**: tredici volte tanto.
>
> La lettura non è che il modello conti poco, ma che **quanto conta dipende da
> quanta pipeline lo circonda**. Dove il sistema è strutturato, gli stadi a
> valle assorbono le differenze; dove è nudo, la qualità del modello passa
> intera.

## 35 · Quindici curriculum reali — 25"

> Infine, la prova sui primi documenti che nessuno strumento mio ha generato:
> quindici curriculum veri.
>
> Ha trovato tre difetti che i dati sintetici nascondevano per costruzione. Il
> più netto: le certificazioni avevano una precisione di 0,25 — tre su quattro
> sbagliate — e nessuna metrica lo segnalava, perché quel percorso non era mai
> stato valutato separatamente.

## 36 · Quadro delle metriche — 14"

> Questo è il quadro complessivo, sempre con il confronto accanto: ogni numero
> va letto insieme al suo punto di partenza o alla sua baseline.

## 37 · Sezione 6 — 3"

> Chiudo con i limiti.

## 38 · Limiti — 18"

> Il principale lo conoscete già: i dati sono sintetici e condividono il
> lessico con l'ontologia. La valutazione richiede l'identificativo ESCO
> esatto, quindi un match concettualmente giusto ma con identificativo diverso
> conta come errore. E i pesi del punteggio sono stati scelti, non ottimizzati.

## 39 · Sviluppi futuri — 17"

> Da qui, la direzione è una sola: dati reali annotati. Lo strumento di
> annotazione è già costruito, il protocollo e il costo per documento sono
> noti. E con quelli diventa possibile il confronto completo con un
> riconoscitore addestrato, di cui ho verificato solo il primo stadio.

## 40 · Grazie — 6"

> Grazie per l'attenzione. Resto a disposizione per le domande.

---

## Le tre frasi che devono arrivare

Se la commissione ricorda tre cose, che siano queste:

1. **«Il difetto non era nel modello né nell'ontologia: era nella domanda
   posta al sistema.»** (slide 26)
2. **«Zero su centottantatré non è un modello impreciso, è un meccanismo che
   sbaglia sempre.»** (slide 24)
3. **«Il 43% dice che un corso esiste, non che sia quello giusto.»** (slide 32)

Tutte e tre hanno la stessa struttura: un numero che sembrava dire una cosa e
ne diceva un'altra. È il filo del discorso, e non serve dichiararlo — si sente.

## Prova a voce

La prima volta durerà dodici minuti. Non tagliare contenuto: **togli le pause
involontarie**, che sono quasi sempre la causa. Cronometra i blocchi 14-15,
24-28 e 32: se quelli stanno nei tempi, sta nei tempi tutto il resto.
