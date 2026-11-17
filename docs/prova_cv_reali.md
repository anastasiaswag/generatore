# La prova su curriculum reali

Quindici curriculum autentici, in PDF, forniti da Riccardo. Sono i primi
documenti del progetto che nessuno ha generato.

La prova nasceva come verifica di generalizzazione: constatare quanto il parser
perdesse passando dal sintetico al reale. Ha prodotto invece qualcosa di
diverso e più utile — ha **trovato tre difetti che il dataset sintetico
nascondeva**, uno dei quali attivo dall'inizio del progetto.

---

## 1. Che cosa si può misurare senza ground truth

Nessuno ha annotato quali competenze ESCO siano presenti in questi documenti,
quindi precision, recall e F1 non sono calcolabili. Non è un limite da
aggirare: è la natura della prova. Ciò che si misura è se il parser **regge**.

| indicatore | reale | sintetico |
|---|---|---|
| documenti parsati senza errori | 15/15 | 810/810 |
| competenze estratte per documento | 14,1 | 13,95 |
| mediana dei punteggi di similarità | 0,889 | 0,926 |
| sezione competenze riconosciuta | 12/15 | 15/15 |
| sezione esperienza riconosciuta | 13/15 | 15/15 |
| sezione certificazioni riconosciuta | **1/15** | 15/15 |

Il numero di competenze estratte è quasi identico, il che è già un risultato:
il parser non collassa né sovra-produce su documenti mai visti.

**La mediana dei punteggi è più bassa sul reale**, 0,889 contro 0,926. È la
conferma quantitativa di un'ipotesi che finora era una supposizione: i
curriculum veri sono lessicalmente più distanti da ESCO di quelli generati a
partire da ESCO.

---

## 2. Primo difetto: le certificazioni

### Il sintomo

| certificazione | assegnata a |
|---|---|
| Abilitazione PES/PAV (lavori elettrici) | 14 persone su 15 |
| RSPP | 12 su 15 |
| Abilitazione Muletto / Carrello Elevatore | 10 su 15 |
| Abilitazione Gru su autocarro | 9 su 15 |
| Databricks Certified Associate Developer | 7 su 15 |

Nove documenti su quindici avevano saturato il tetto di dieci certificazioni.
Quindici persone diverse non hanno tutte il patentino del muletto.

### Le due cause

**La soglia.** 0,75, contro lo 0,85 e 0,88 usati per le competenze. Non c'è
ragione perché le certificazioni siano più permissive: semmai il contrario,
dato che sono un vocabolario chiuso e ben definito.

**Dove si cerca.** I candidati sono `cert_lines + skl_lines + edu_lines`, cioè
anche le righe di competenze e istruzione. Recupera qualcosa quando la sezione
dedicata non viene riconosciuta, ma espone ogni riga di competenze al rischio
di essere scambiata per una certificazione. Qui la sezione dedicata è stata
riconosciuta in **un** documento su quindici: quasi tutti i candidati
arrivavano da righe che certificazioni non erano.

### Perché era invisibile sul sintetico

Il generatore pescava le certificazioni dalla stessa lista usata per il
riconoscimento: i match risultavano corretti per costruzione. Ma la ground
truth esisteva ed era verificabile — bastava usarla. I CV sintetici hanno in
media **1,34** certificazioni; il parser ne estraeva **4,77**.

Il percorso non era mai stato valutato. Le competenze sì, le lingue sì,
l'occupazione sì; le certificazioni no.

### La misura, e la correzione

Valutazione su 567 CV sintetici di riporto, mai usati per scegliere la soglia:

| soglia | Precision | Recall | F1 | estratte per CV |
|---|---|---|---|---|
| **0,75** (in uso) | 0,250 | 0,779 | 0,364 | 4,83 |
| **0,86** (calibrata) | **0,837** | 0,781 | **0,799** | 1,08 |

La precisione passa da 0,250 a 0,837 **e il richiamo non cambia** — da 0,779 a
0,781. Non è un compromesso: alzare la soglia elimina solo spazzatura. Guadagno
di F1 **+0,434**.

Sui quindici curriculum reali le assegnazioni passano da **125 a 11**, e le
superstiti sono plausibili: quattro «Patente B» — esattamente ciò che ci si
aspetta in curriculum italiani — più PMP, PRINCE2 Practitioner, CISSP, CQC.

Restano due casi da verificare a mano: un docente universitario a cui vengono
attribuite l'abilitazione ai lavori elettrici e la gru su autocarro, e un
atleta professionista con il certificato di qualificazione conducenti. Undici
casi sono ispezionabili in cinque minuti; centoventicinque non lo erano.

**Il secondo difetto — dove si cercano i candidati — non è ancora stato
misurato.** L'opzione `--cert-solo-sezione` esiste per provarlo, ma va fatto
separatamente: una modifica per volta, altrimenti non si sa quale delle due ha
prodotto l'effetto.

---

## 3. Secondo difetto: gli anni di esperienza

### Il sintomo

Sette curriculum su quindici restituivano **zero** anni e ricadevano
automaticamente su *junior*. Uno ne restituiva **48**.

Sui CV sintetici la stessa funzione otteneva l'87,2% di stime esatte, il 99,1%
entro due anni, errore medio 0,2 anni, e non falliva mai.

### La causa a monte

`render_cvs.py`, riga 135:

```python
period = f"{start_year} – 2024" if years else "2024"
```

**Tutti e 810 i CV sintetici usano un solo formato di data**, generato dallo
stesso script che fornisce la ground truth. L'87,2% non misurava la capacità di
leggere le date di un curriculum: misurava la capacità di sottrarre due numeri
in un formato noto.

### I quattro difetti corretti

1. **I mesi venivano scartati.** Erano catturati da un gruppo non catturante e
   il calcolo era `(anno_fine − anno_inizio) × 12`: «Gennaio 2020 – Novembre
   2020» valeva **zero mesi**. Ogni esperienza interna a un anno solare
   spariva. Invisibile sul sintetico, dove i periodi erano sempre su anni
   interi.
2. **Il trattino lungo non era un separatore.** La classe era `[-–to/]`:
   conteneva trattino breve e medio, non l'em-dash `—`, che è quello inserito
   automaticamente dai word processor.
3. **Le formule di attualità erano quattro.** Mancavano *presente*, *ad oggi*,
   *tuttora*, *currently*, *now*, *today*.
4. **Gli intervalli si sommavano senza unirli.** Due ruoli paralleli venivano
   contati due volte: origine dei 48 anni.

Aggiunti inoltre due formati osservati sui documenti veri: `Sep '22` con
apostrofo e anno a due cifre, e — più importante — gli **intervalli spezzati su
due righe**, tipici dei curriculum a due colonne, dove l'estrazione del PDF
restituisce la colonna laterale come righe isolate.

### Un secondo caso di circolarità, scoperto verificando

Il generatore rende due ruoli come `2022 – 2024` e `2021 – 2024` — periodi che
nel documento **si sovrappongono** — ma la ground truth li somma: 2 + 3 = 5
anni. Un lettore umano direbbe 3, che è l'arco temporale coperto. Riguarda
**540 CV su 810**.

Ne segue che la vecchia funzione otteneva l'87,2% *perché sommava senza unire*,
replicando l'aritmetica del generatore invece di leggere il documento. Con
l'unione — che è la lettura corretta e ciò che elimina il caso dei 48 anni —
l'accordo con quella ground truth scende al **22,1%**.

I due numeri vanno riportati insieme: **il divario misura un'incoerenza fra ciò
che il generatore scrive e ciò che dichiara**, non un peggioramento del parser.

### Il risultato

| esito | CV | quanti |
|---|---|---|
| stima fondata su periodi dichiarati | 04, 06, 07, 08, 09, 10, 13, 14 | **8/15** |
| numero prodotto dal ripiego, non fondato | 03 (16,0) · 05 (20,0) | 2 |
| formato di data non ancora coperto | 01, 11, 15 | 3 |
| sezione esperienza non riconosciuta | 02, 12 | 2 |

Da sette fallimenti su quindici a otto stime fondate, con **una causa
identificata per ciascun caso residuo**.

### Il campo di provenienza

I casi 03 e 05 producono 16 e 20 anni senza aver riconosciuto un solo
intervallo: il numero viene dal ripiego, che sottrae l'anno più piccolo dal più
grande trovati nel blocco. Potrebbero essere approssimativamente giusti, ma il
sistema non lo sa e li presentava con la stessa faccia dei valori ricavati
dalle date vere.

L'output porta ora un campo `years_source` accanto a `years_of_experience`:

| valore | significato |
|---|---|
| `intervalli` | letto da periodi dichiarati nel testo |
| `ripiego` | congettura da anno minimo e massimo |
| `assente` | nessuna data riconosciuta, valore 0 |

Serve a due cose. Il matching engine può decidere se fidarsi — e ha già la
logica giusta, perché quando il livello è ignoto omette il termine invece di
penalizzare. E in tesi l'accuratezza si può riportare separata per provenienza,
che è più informativo di una percentuale unica.

---

## 4. Terzo difetto: la segmentazione

In 2 documenti su 15 la sezione esperienza non viene riconosciuta affatto, e in
3 non viene riconosciuta quella delle competenze. Il blocco arriva vuoto e
nessuna correzione a valle può rimediare.

È la fragilità nota del parser dei CV, ed è il rovescio del suo vantaggio: la
segmentazione per sezioni è ciò che lo rende trenta punti di F1 migliore del
parser degli annunci, ed è anche ciò che lo fa cadere quando le intestazioni
non somigliano a quelle previste. Sui CV sintetici le intestazioni venivano da
tre template noti; qui da quindici persone che hanno scelto ciascuna la
propria.

Non è stato affrontato: è una correzione di natura diversa dalle prime due.

---

## 5. Che cosa questa prova insegna

Tutti e tre i difetti hanno la stessa forma. **Un componente tarato su
documenti generati, messo davanti a documenti veri.** E in due casi su tre il
dataset sintetico non solo nascondeva il problema: lo rendeva invisibile per
costruzione, perché generazione e valutazione condividevano la stessa
convenzione.

Ne discende una raccomandazione operativa che vale oltre questo progetto: **un
componente valutato solo su dati sintetici va considerato non valutato**, a
meno che non si possa dimostrare che la generazione e la misura non condividono
alcuna assunzione. Qui condividevano la lista delle certificazioni, il formato
delle date e la convenzione sulla somma dei periodi.

Il costo della verifica è stato di quindici documenti e mezza giornata. Il
difetto delle certificazioni era attivo da mesi con precisione 0,250.

---

## 6. Riproducibilità

```
# Parsing dei curriculum reali, anonimizzato, con la soglia corretta
python tests/parse_cv_reali.py --cartella "<cartella>" --anonimo \
       --soglia-cert 0.86 --out outputs/cv_reali_finale.json

# Analisi complessiva
python analysis/analisi_cv_reali.py --in outputs/cv_reali_finale.json

# Perché un singolo curriculum fallisce
python analysis/diagnostica_date.py --cartella "<cartella>" --solo cv_reale_04

# Valutazione del percorso certificazioni sui CV sintetici
python analysis/valuta_certificazioni.py --in outputs/cv_batch_results.json

# Collaudo del calcolo degli anni su formati reali
python tests/test_anni_esperienza.py
```

**Dati personali.** L'opzione `--anonimo` sostituisce i nomi dei file con
identificativi progressivi e scrive la corrispondenza in un file separato,
`*_nomi.json`, che **non va allegato alla tesi**.

---

## 7. Cosa resta aperto

| voce | costo stimato | valore |
|---|---|---|
| Annotare a mano le competenze dei 15 CV, per avere precision e recall su dati reali | 2 ore | **alto** — è l'unica risposta solida all'obiezione sul dataset sintetico |
| Misurare `--cert-solo-sezione`, il secondo difetto delle certificazioni | 30 min | medio |
| Aggiungere i 3 formati di data ancora scoperti | 1 ora | medio |
| Riparsare gli 810 CV sintetici con `--soglia-cert 0.86` | una notte | basso, non blocca nulla |
| Migliorare il riconoscimento delle intestazioni di sezione | mezza giornata | medio |
