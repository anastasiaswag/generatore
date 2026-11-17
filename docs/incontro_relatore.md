# Incontro con il relatore — scaletta

Venti minuti di racconto, con i numeri al posto giusto. La struttura non è
«cosa ho costruito» ma **«cosa ho misurato e cosa ho scoperto misurando»**: è
ciò che distingue questo lavoro da una tesi che riporta soltanto i risultati
riusciti.

---

## Apri con una frase, non con l'architettura

> «Ho costruito un sistema che confronta curriculum e annunci di lavoro
> attraverso l'ontologia ESCO. Funziona. Ma la parte del lavoro che mi sembra
> più solida non sono i numeri: è che ho scoperto che alcuni di quei numeri non
> misuravano quello che sembravano misurare, e li ho rifatti.»

Se dici questo per primo, tutto quello che segue si legge come rigore invece
che come autocritica. Se lo dici alla fine, sembra una confessione.

---

## 1. Il problema e la scelta di fondo — 2 minuti

Curriculum e annuncio descrivono la stessa realtà con parole scelte
indipendentemente. «Progettazione di applicazioni iOS» contro «esperienza di
sviluppo mobile»: un lettore umano vede la corrispondenza, un confronto per
parole no. Serve un vocabolario condiviso, ed è ESCO — 3.039 occupazioni,
13.939 competenze, 98.847 etichette per le competenze contando le denominazioni
alternative.

**Il punto da piantare subito**, perché regge tutto il resto: nei sistemi
industriali il confronto semantico **propone, non decide**. Nell'architettura
di LinkedIn i riconoscitori generano candidati con criterio inclusivo, e uno
stadio addestrato a valle decide quali tenere. Chi non ha dati etichettati usa
la soglia di similarità *come* decisione, per mancanza di alternative. È la
scelta fatta qui, ed è la causa diretta del problema principale del progetto.

---

## 2. I quattro componenti, con un numero ciascuno — 3 minuti

| componente | risultato |
|---|---|
| Parser dei curriculum | P 0,907 · R 0,860 · **F1 0,878** |
| Parser degli annunci | P 0,807 · R 0,539 · **F1 0,629** |
| Estrattore del livello di esperienza | **92,3%** (baseline casuale 33,3%) |
| Matching CV → offerte | **P@1 96,7%** · P@10 100% |
| Matching offerta → candidati | **P@1 90,0%** · MRR 0,950 (baseline 1,7%) |
| Discriminazione del livello | **97,0%** (baseline 33,3%) |
| Raccomandatore corsi | copertura nominale 43,1% |

Non recitarli tutti. Dì i due parser e passa oltre: i numeri singoli sono la
parte meno interessante, e soffermarcisi sposta la conversazione dove il lavoro
è più debole.

---

## 3. Il risultato concettuale — 4 minuti, il cuore del colloquio

Il parser degli annunci partiva da **F1 0,391**, con precisione 0,297: estraeva
**1,99 volte** le competenze attese.

Indagando, il falso positivo dominante veniva da un frammento grammaticale. Da
una frase come *«The successful candidate will be responsible for coordinating
technological activities»* il segmentatore produceva sette candidati: tre
competenze reali e quattro detriti.

| candidato | annunci in cui compare | falsi positivi |
|---|---|---|
| `responsible` | 792 su 810 | **792** |
| `seeking` | 773 su 810 | 772 |

**Qui sta il punto, e va detto lentamente:** per il candidato `responsible`
l'etichetta ESCO *«comportarsi in modo responsabile»* è il match **corretto**.
Il difetto non era nel modello né nell'ontologia: era nella domanda posta. Si
chiedeva al sistema la competenza più simile a un frammento privo di contenuto,
e il sistema rispondeva bene a una domanda malposta.

La soluzione — accettare dalla prosa solo candidati di almeno due parole —
elimina il 45,5% dei candidati. Bilancio misurato: **334 veri positivi persi
contro 10.076 falsi positivi eliminati**, rapporto 1 a 30.

E spiega perché quattro contromisure precedenti erano fallite: agivano tutte
sul lato ontologia, e nessuna penalizzazione delle etichette può rimediare a un
candidato senza contenuto.

---

## 4. Le contromisure fallite — 2 minuti

Raccontale. Sono la parte che un relatore riconosce come lavoro serio.

| tentativo | esito | perché |
|---|---|---|
| stadio lessicale | scartato | precisione incrementale 0,27 contro 0,53 del semantico |
| correzione hubness | nessun effetto | 0,298 contro 0,297: il problema era nelle query |
| vincolo di reciprocità | inefficace | presupponeva ripetizioni *dentro* il documento; il fenomeno era *fra* documenti |
| filtri del parser CV riusati | nessun effetto | calibrati su un difetto diverso |

Il caso della reciprocità è il più istruttivo: contromisura corretta in sé,
applicata a un fenomeno con la forma sbagliata.

---

## 5. Il confronto multimodello — 3 minuti

Cinque encoder, tre famiglie, stessa pipeline e stessi dati, soglie calibrate
per ciascuno con la stessa procedura.

| modello | dim | F1 competenze | occupazione |
|---|---|---|---|
| e5-base | 768 | **0,612** | 0,759 |
| bge-m3 | 1024 | 0,610 | **0,861** |
| e5-small | 384 | 0,609 | 0,622 |
| mpnet | 768 | 0,598 | 0,525 |
| MiniLM | 384 | 0,586 | 0,570 |

**Scarto sulle competenze 0,026. Scarto sull'occupazione 0,336 — tredici volte
tanto.**

Il caso che dimostra tutto è **bge-m3**: migliore sull'occupazione di dieci
punti, indistinguibile sulle competenze. Stesso modello, stessi documenti,
stessa esecuzione.

> **La formulazione da usare:** non «il modello conta poco», ma **quanto conta
> il modello dipende da quanta pipeline lo circonda**. Sull'occupazione
> l'encoder decide da solo e la sua qualità passa intera; sulle competenze ci
> sono segmentazione, vincoli, soglie e un classificatore, e ogni stadio
> assorbe parte dei suoi errori.

Riferimento: il lavoro di pipeline vale **+0,238** di F1, cambiare encoder ne
vale **+0,003**.

**Scoperta metodologica collegata:** le soglie non sono trasferibili fra
encoder. Con MiniLM e le soglie tarate su E5, l'accuratezza sull'occupazione
risultava **0,047** — ma nei 45 casi in cui il sistema si pronunciava indovinava
l'**84,4%**, più di e5-base. Calibrando la soglia sale a **0,570** sugli stessi
dati e con lo stesso modello. Un confronto a soglie fisse non misura la qualità
degli encoder: misura quanto ciascuno somigli a E5 nella scala dei punteggi.

---

## 6. La prova su dati reali — 4 minuti, la parte più forte

Quindici curriculum autentici. La prova doveva verificare la generalizzazione;
ha trovato tre difetti che il dataset sintetico **nascondeva per costruzione**.

**Due aggiunte misurate dopo il primo incontro.** Le certificazioni hanno un
secondo rimedio, strutturale: cercarle **solo nella sezione dedicata** dà
0,841 / 0,780 / 0,801, equivalente ad alzare la soglia — e lì la soglia smette
di contare del tutto. E la diagnosi del parser degli annunci ha ora una
**conferma indipendente**: un riconoscitore addestrato (ESCOXLM-R) produce
7 frammenti senza contenuto su 10.045 span, contro i 792 falsi positivi del
solo `responsible`.

**Le certificazioni.** Soglia a 0,75, catalogo di 45 voci, tetto di 10: ogni
curriculum ne pescava oltre un quinto. «Abilitazione Muletto» assegnata a 10
persone su 15, il tetto saturato in 9 documenti su 15. Misurato sul sintetico
con la ground truth che c'era da sempre: **precisione 0,250**. Alzata la soglia
a 0,86: **precisione 0,837, richiamo invariato**, F1 da 0,364 a 0,799. Il
componente aveva lavorato per mesi con tre certificazioni su quattro sbagliate,
e nessuna metrica lo segnalava perché **quel percorso non era mai stato
valutato**.

**Gli anni di esperienza.** Sette CV reali su quindici davano zero, uno dava 48.
Indagando: `render_cvs.py` genera i periodi con **una sola formattazione**,
`f"{anno_inizio} – 2024"`. L'87,2% di accuratezza misurato sul sintetico non
misurava la capacità di leggere date: misurava la capacità di fare un'operazione
aritmetica su un formato noto.

**Il raccomandatore di corsi.** La copertura del 43,1% verifica che *esista* un
corso, non che sia pertinente. Revisione manuale su 30 competenze e 65
raccomandazioni: **18,5% pertinenti, 61,5% del tutto fuori bersaglio, copertura
effettiva 23,3%** con un intervallo di confidenza che **non contiene** il 43,1%
nominale. La causa: l'indice abbina i **tag** alle competenze, non i corsi, e
solo quel primo anello era misurato.

> **La conclusione da consegnare al relatore:** un componente valutato solo su
> dati sintetici va considerato non valutato, a meno di poter dimostrare che
> generazione e misura non condividono alcuna assunzione. Qui condividevano la
> lista delle certificazioni, il formato delle date e la convenzione sulla somma
> dei periodi.

---

## 7. Cosa manca — 1 minuto, dillo tu per primo

- **Venti annunci reali**, in raccolta: due per ciascuno dei nove grandi gruppi
  ISCO, con la regola di campionamento fissata in anticipo.
- **Annotazione manuale dei quindici curriculum**, per avere precision e recall
  su dati reali e non solo la verifica che il sistema regga.
- Segmentazione delle sezioni: 2 CV su 15 senza sezione esperienza riconosciuta.
- **L'ordinamento del divario è fondato ma non validato**: la prossimità viene
  ora dalla gerarchia ufficiale ESCO v1.2.1 invece che da una ricostruzione, e
  cambia l'ordine nel 79,5% dei casi — ma nessuno ha verificato che l'ordine
  nuovo sia *migliore* per chi deve studiare.
- Il sistema non è pronto per la produzione, e non è mai stato l'obiettivo.

**Se chiede dell'ontologia completa**, questa è la risposta breve: le
occupazioni e le competenze erano già complete (3.039 e 13.939); mancavano le
relazioni *fra* competenze, ora scaricate. Misurandone l'effetto è emerso che la
ricostruzione precedente conteneva informazione binaria ma non graduata
(ρ = 0,033) e che una normalizzazione sbagliata riduceva quella componente dal
20% nominale all'1,6% effettivo.

---

## Le tre domande difficili, e cosa rispondere

**«Tutti i tuoi numeri sono su dati che hai generato tu.»**
Vero, ed è il limite principale del lavoro. Per questo la prova su quindici
curriculum reali non è un'appendice ma una sezione della tesi, e ha trovato tre
difetti che il sintetico nascondeva. I venti annunci reali sono in raccolta.

**«Che cosa c'è di nuovo?»**
Algoritmicamente niente: nessuna delle tecniche è mia. Il contributo è empirico
e metodologico — ho misurato cosa succede applicando strumenti standard a un
problema senza dati annotati, e ho documentato tre casi in cui il metodo di
valutazione ingannava. Dirlo per primo è meglio che farselo dire.

**«F1 0,629 sugli annunci non è alto.»**
No. È un problema più difficile di quello dei curriculum — prosa continua contro
documento strutturato — e la distanza fra i due parser (0,878 contro 0,629) è
la conseguenza dell'input, non della qualità dei componenti. Il numero va letto
con la sua ablazione: da 0,391 a 0,629 è quello che ha aggiunto il lavoro di
pipeline.

---

## Il frontend

Funziona. `app/streamlit_app.py` compila e istanzia i parser senza argomenti,
quindi le modifiche recenti non lo hanno rotto.

```
streamlit run app/streamlit_app.py
```

**Provalo stasera prima di andare a dormire**, non domani mattina davanti al
professore. Verifica le tre modalità: un CV contro un annuncio, un annuncio
contro più candidati, un CV contro più annunci.

**Una modifica fatta apposta per la demo:** la soglia delle certificazioni è
stata portata da 0,75 a **0,86** come valore predefinito. Con la vecchia soglia
l'interfaccia avrebbe mostrato dieci certificazioni per curriculum, quasi tutte
sbagliate — la prima cosa che un professore avrebbe notato aprendo un profilo.
Ora ne mostra una o due, plausibili.

Se apri l'interfaccia, usa **la modalità 1 CV ↔ 1 annuncio**: mostra il
punteggio, le competenze coperte, quelle mancanti e i corsi suggeriti in un
colpo solo. Ed è anche l'occasione per dire, guardando i corsi, che quella parte
l'hai verificata a mano e sai che è il punto debole — molto meglio dirlo tu
mentre lo si guarda.
