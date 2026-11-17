# SkillPath AI — Risultati sperimentali

Raccolta dei numeri prodotti in questa fase di lavoro, con la metodologia e i
limiti di ciascuno. Pensato come materiale grezzo per la relazione: ogni
sezione indica lo script che genera il dato, così è riproducibile.

---

## 1. Quadro d'insieme

| componente | metrica principale | valore |
|---|---|---|
| Parser CV | F1 skill | 0.878 |
| Parser annunci (denylist) | F1 skill | 0.580 |
| Parser annunci (classificatore appreso) | F1 skill | **0.629** |
| Estrattore seniority | accuratezza | 92,3% |
| Matching engine — occupazione (CV → offerte) | Precision@1 | 96,7% |
| Matching engine — occupazione (offerta → candidati) | Precision@1 | 90,0% |
| Matching engine — livello | accuratezza | 97,0% |
| Raccomandatore corsi | copertura nominale del gap | 43,1% |
| Raccomandatore corsi | **copertura effettiva** (revisione a mano) | **23,3%** |
| Raccomandatore corsi | corsi non pertinenti | 61,5% |
| Confronto fra 5 encoder | scarto di F1 sulle competenze | 0,026 |
| Confronto fra 5 encoder | scarto sull'occupazione | 0,336 |

Nessuno di questi valori va letto isolatamente: quasi tutti hanno un vincolo
metodologico che ne cambia il significato, discusso nelle sezioni seguenti.

---

## 2. Parser dei CV

`tests/batch_parse_cvs.py` → `analysis/analisi_parser.py --section gt --from-batch`
Valutazione su tutti gli 810 CV sintetici.

| | Precision | Recall | F1 |
|---|---|---|---|
| baseline iniziale | 0.760 | 0.547 | 0.623 |
| prima di questa fase | 0.865 | 0.860 | 0.857 |
| **finale** | **0.907** | **0.860** | **0.878** |

Per template: `classic` 0.905 · `europass` 0.872 · `modern` 0.858.
Per seniority: junior 0.885 · mid 0.877 · senior 0.873.

**Modifica introdotta.** Filtro sui nomi di lingua. ESCO cataloga le lingue
come competenze, e quelle dichiarate nel CV venivano estratte due volte: una
dal rilevatore dedicato (che le restituisce col livello CEFR) e una come
skill. Erano circa un terzo di tutti i falsi positivi — 489 su 1480, con
"francese" a 183 occorrenze errate e nessuna corretta. Il filtro ne elimina
489 senza perdere alcun vero positivo.

**Le certificazioni: due rimedi equivalenti.** Il percorso dedicato aveva una
soglia tarata sul sintetico che sui CV reali produceva precisione 0,250. Sono
stati misurati due rimedi indipendenti, sullo stesso insieme di riporto di 567
CV:

| configurazione | Precisione | Richiamo | F1 |
|---|---|---|---|
| tutto il documento, soglia 0,75 | 0,250 | 0,779 | 0,364 |
| tutto il documento, soglia 0,86 *(in uso)* | 0,837 | 0,781 | 0,799 |
| **solo sezione dedicata**, soglia 0,75 | 0,841 | 0,780 | 0,801 |

Sono equivalenti, e non si sommano: sono sostituti. Nella terza configurazione
la soglia **smette di fare qualcosa** — da 0,75 a 0,88 i risultati sono
identici alla terza cifra, perché il punteggio minimo osservato è 0,891: cercare
solo dentro la sezione giusta impedisce ai candidati spuri di essere generati,
e non resta nulla da filtrare.

Sul sintetico pareggiano, ma hanno natura diversa — un numero calibrato contro
un vincolo strutturale — e il §6-bis.1 dà una ragione per preferire il secondo:
i valori calibrati non si trasferiscono. Il costo del vincolo strutturale è che
circa un quinto delle certificazioni vere sta fuori dalla sezione dedicata, e
che dipende dal riconoscimento delle sezioni, debole su 2 CV reali su 15.
Riproducibilità: `tests/batch_parse_cvs.py --cert-solo-sezione`.

---

## 3. Parser degli annunci

`tests/batch_parse_jobs_gt.py` → `analysis/analisi_job_parser.py`
Valutazione su 810 annunci sintetici con ground truth ESCO.

| configurazione | Precision | Recall | F1 |
|---|---|---|---|
| nessun rimedio (ablazione) | 0.297 | 0.615 | 0.391 |
| denylist 232 etichette | 0.529 | 0.607 | 0.551 |
| vincolo multi-parola | 0.540 | 0.581 | 0.546 |
| multi-parola + denylist 232 | 0.600 | 0.575 | 0.572 |
| multi-parola + denylist 64 | 0.614 | 0.577 | 0.580 |
| **multi-parola + classificatore appreso** | **0.807** | 0.539 | **0.629** |

Occupazione: 75,9% di ID esatto, 87,5% di macro-settore ISCO.

### 3.1 La correzione principale

Il falso positivo dominante nasceva da un frammento grammaticale. Il
segmentatore, applicato a una frase come *"The successful candidate will be
responsible for coordinating technological activities, using our ICT ticketing
system"*, produceva sette candidati: tre competenze reali e quattro detriti
(`successful`, `responsible`, `using`, `complying`).

La corrispondenza con gli errori è esatta:

| candidato | annunci in cui compare | etichetta agganciata | falsi positivi |
|---|---|---|---|
| `responsible` | 792 | comportarsi in modo responsabile | 792 |
| `seeking` | 773 | motori di ricerca | 772 |

Va sottolineato che per il candidato `responsible` l'etichetta *"comportarsi in
modo responsabile"* è il match **corretto**: il difetto non era nel modello né
nell'ontologia, ma nella domanda posta. Accettare dalla prosa solo candidati di
almeno due parole elimina il 45,5% dei candidati e quasi tutti i falsi
positivi sistematici, al costo di 3,5 punti di recall.

### 3.2 Contromisure valutate e scartate

| tentativo | esito | motivo |
|---|---|---|
| stadio di match lessicale | scartato | contributo incrementale con precision 0.27, sotto lo 0.53 dello stadio semantico |
| correzione hubness | nessun effetto | 0.298 contro 0.297: il problema era nelle query, non nelle etichette |
| vincolo di reciprocità | inefficace | presupponeva ripetizioni interne al documento; le etichette problematiche comparivano una sola volta per annuncio, in 792 annunci distinti |
| filtri sulle etichette del parser CV | nessun effetto | calibrati su un difetto diverso (nomi di lingua, verbi inglesi) |

### 3.3 Denylist

Ricostruita dopo la correzione al segmentatore: 232 → 64 etichette, di cui 137
delle originali non comparivano più perché nascevano da candidati ormai
inesistenti. Validata su holdout (lista da 405 annunci, effetto misurato sui
405 mai visti): Precision 0.543 → 0.585, F1 0.551 → 0.570, recall invariata.

**Limite dichiarato.** A differenza del vincolo multi-parola, la lista è
ricavata osservando quali predizioni erano sbagliate: è supervisionata e
specifica del dominio. Il sistema funziona anche senza (F1 0.546), quindi non
è un componente critico. Disattivabile con `JobParser(use_denylist=False)`.

### 3.4 Riconoscimento dell'occupazione

Secondo compito dello stesso parser, sugli stessi 810 annunci:

| livello di granularità | accuratezza |
|---|---|
| identificativo ESCO esatto | 75,9% |
| macro-settore ISCO (1 cifra) | 87,5% |

Alimenta il motore di matching (§5) e il confronto multimodello (§6-bis), dove
è il compito su cui lo scarto fra encoder è massimo (0,336 contro 0,026).

### 3.5 I falsi negativi residui

Conteggi grezzi sugli 810 annunci nella configurazione finale: **TP 5.589,
FP 1.280, FN 5.345**. Danno una micro-media di 0,511 di richiamo, leggermente
inferiore alla macro-media di 0,539 riportata sopra, perché gli annunci hanno
un numero diverso di competenze attese.

I 5.345 falsi negativi si separano in tre categorie disgiunte:

| causa | casi | quota | come è stata stabilita |
|---|---|---|---|
| scartati dal classificatore appreso | 378 | 7,1% | confronto esatto fra due file di output |
| presenti nel testo ma non catturati dal segmentatore | 4.158 | 77,8% | euristica lessicale — approssimazione |
| mai comparsi nel testo generato | 809 | 15,1% | complemento dei precedenti |

La terza categoria non è un difetto del parser ma del generatore: la ground
truth è l'elenco dato in input al modello linguistico, non una verifica di che
cosa abbia poi scritto (§7, punto 2). È la stessa *distant supervision* del
lato falsi positivi, vista dal lato del richiamo.

### 3.6 Conferma indipendente con un riconoscitore appreso

La diagnosi di §3.1 — il difetto sta nella generazione dei candidati, non nel
modello né nell'ontologia — è una spiegazione, non una verifica: resta
compatibile con l'ipotesi che il problema sia intrinseco al compito. Per
distinguerle serve un estrattore che non condivida il difetto per costruzione.

`jjzha/escoxlmr_skill_extraction` (ESCOXLM-R, ACL 2023, affinato su SkillSpan)
individua span di competenza senza segmentare sui confini delle parole
funzionali. Sugli stessi 810 annunci con ground truth:

| indicatore | valore |
|---|---|
| span prodotti | 10.045 (12,4 per annuncio) |
| di cui frammenti senza contenuto (`responsible`, `seeking`, …) | **7 — lo 0,07%** |
| span di una sola parola | 2,97% |
| tempo | 0,7 s per annuncio in CPU |

Confronto: il solo candidato `responsible` genera **792 falsi positivi** nella
pipeline locale, e il vincolo multi-parola deve eliminare il 45,5% dei
candidati per contenere lo stesso fenomeno.

Nessun problema di lingua entra in gioco — gli annunci con ground truth sono in
inglese, e SkillSpan pure — e il modello non ha mai visto questi annunci,
mentre soglie e denylist locali sono tarate proprio su di essi. La conferma
arriva quindi in condizioni sfavorevoli.

**Non è un confronto di F1** e non va presentato come tale: la ground truth
elenca competenze che il generatore doveva inserire e che nel testo a volte non
compaiono, e quel costo l'estrattore lo pagherebbe per intero mentre le soglie
locali vi sono state ottimizzate contro.

Riproducibilità: `analysis/prova_escoxlmr.py --sorgente gt --annunci 810`, in
un ambiente virtuale separato (`transformers`, `torch`).

---

## 4. Estrazione del livello di esperienza

`src/job_parser.py` → `_detect_seniority()`

Accuratezza 92,3% su 810 annunci, 4,3% di casi non rilevati, nessun errore da
due livelli.

| vero \ stimato | junior | mid | senior | non rilevato |
|---|---|---|---|---|
| junior | 259 | 0 | 5 | 6 |
| mid | 0 | 219 | 22 | 29 |
| senior | 0 | 0 | 270 | 0 |

---

## 5. Matching engine

### 5.1 Il difetto individuato

Il punteggio era la frazione di requisiti dell'annuncio coperti dal candidato.
Poiché gli annunci junior elencano meno requisiti, la frazione risultava più
alta a prescindere dal candidato:

| livello dell'annuncio | skill richieste (media) |
|---|---|
| junior | 10,77 |
| mid | 13,54 |
| senior | 16,19 |

Conseguenza misurata su 100 CV: il motore sceglieva un annuncio junior 47
volte su 100 (atteso 33), e l'accuratezza sul livello era 37,0% contro una
baseline casuale del 33,3%. In pratica il sistema proponeva posizioni
sotto-livello a chiunque avesse esperienza.

Inoltre `JobMatchingEngine` non conteneva alcun termine legato all'esperienza:
la logica sulla seniority presente nel file apparteneva all'altro motore,
quello dello Scenario 1.

### 5.2 Le due correzioni

**Termine sul conteggio assoluto** (`count_weight`, predefinito 0.15). Miscela
alla copertura un termine saturante sul numero assoluto di competenze coperte.
Taratura misurata su 100 CV, dove le colonne indicano quante volte il motore
sceglie un annuncio di ciascun livello (atteso 33/33/33):

| peso | accuratezza | junior/mid/senior scelti |
|---|---|---|
| 0.00 | 37,0% | 47 / 29 / 24 |
| **0.15** | **44,0%** | **33 / 33 / 34** |
| 0.25 | 44,0% | 25 / 36 / 39 |
| 0.40 | 43,0% | 19 / 36 / 45 |

A 0.15 e 0.25 l'accuratezza coincide, ma solo a 0.15 le scelte sono
equilibrate: a parità di errori è preferibile che siano rumore anziché una
tendenza sistematica.

**Termine di allineamento del livello** (`seniority_weight`, predefinito 0.1).
Confronta l'esperienza del candidato con il livello estratto dall'annuncio:
1.0 se coincidono, 0.5 se adiacenti, 0.0 se distano due passi.

Il valore iniziale era 0.3, tarato sul solo test della seniority — che però
confronta esclusivamente annunci della stessa occupazione, dove il contenuto è
costante. Il test di monotonia (§5.5) ha rivelato che con quel peso un
abbinamento perfetto per contenuto ma con livello disallineato veniva superato
da un annuncio di tutt'altro settore. A 0.10 la sovrapposizione fra livelli
scende dal 40% al 2,5% e l'accuratezza sul livello resta identica: il termine
deve fare da spareggio, non da criterio dominante.

### 5.3 Risultato

| | prima | dopo |
|---|---|---|
| Occupazione — Precision@1 | 96,7% | 96,7% |
| Occupazione — Precision@10 | 96,7% | 100,0% |
| Livello — accuratezza | 37,0% | 97,0% |
| Livello — accuratezza adiacente | 86,0% | 100,0% |
| Distorsione nelle scelte | 47/29/24 | 33/33/34 |

**Come leggere il 97%.** Non è una capacità emergente del motore: il livello
gli viene passato esplicitamente dal job parser. Il numero che descrive una
capacità è il **92,3%** dell'estrattore; il 97% dimostra che il collegamento
regge ed è robusto agli errori sul singolo annuncio, perché ogni occupazione
ha due annunci per livello e ne basta uno etichettato correttamente.

### 5.4 La direzione inversa: dato un annuncio, ordinare i candidati

`analysis/valida_recruiter.py` — 20 annunci × 361 candidati, con i pesi
predefiniti del motore (γ = 0,10, β = 0,15).

| Metrica | Valore |
|---|---|
| Precision@1 | 90,0% |
| Precision@3 | 100,0% |
| Precision@10 | 100,0% |
| MRR | 0,950 |
| Baseline casuale | 1,7% |

> **Attenzione alla versione.** Una prima misura, in `recruiter_attuale.json`,
> era stata presa con γ = 0,3 — il valore che la Sezione 5.3 dichiara tarato
> male — e dava 85,0% · 95,0% · MRR 0,912. I valori qui sopra vengono da
> `recruiter_sw010.json`, con la configurazione effettivamente consegnata.
> Correggere γ ha quindi migliorato anche questo compito, che non era quello
> per cui la correzione era stata fatta: **+5 punti di Precision@1**.

La Precision@1 è più bassa che nel verso opposto (90% contro 96,7%): scegliere
fra candidati della stessa occupazione è più difficile che fra annunci, perché
i CV variano per livello e per sottoinsieme di competenze possedute, mentre gli
annunci di uno stesso ruolo sono più omogenei fra loro. In tutti i casi il
candidato giusto resta comunque entro i primi dieci.

**Un'ipotesi verificata e smentita.** Il termine sul conteggio assoluto,
introdotto per correggere la preferenza verso le posizioni junior, in questa
direzione avrebbe potuto produrre l'effetto opposto: premiare i curriculum più
lunghi, che coprono più requisiti per pura ampiezza. Nel dataset la variabilità
c'è — un CV del 90° percentile ha 23 competenze estratte contro le 7 del 10°.

La misura non conferma il sospetto:

| indicatore | con count_weight 0.15 | senza (0.0) |
|---|---|---|
| Precision@1 | 90,0% | 90,0% |
| Precision@3 | 100,0% | 100,0% |
| MRR | 0,950 | 0,950 |
| skill medie nel pool | 13,1 | 13,1 |
| skill medie nei primi 10 | 14,2 | 14,1 |
| rapporto | **1,08×** | 1,08× |
| correlazione punteggio↔lunghezza fra i NON pertinenti | **+0,194** | +0,208 |

La correlazione fra punteggio e lunghezza del CV, sui soli candidati
dell'occupazione sbagliata, è **+0,194**: debole, ma non nulla. Il punto
decisivo però non è il suo valore, è che **rimuovendo il termine di conteggio
non diminuisce** — sale a 0,208. Quella correlazione non è dunque causata dal
termine sospetto: sarebbe rimasta comunque, e la spiegazione residua è che i CV
più lunghi elencano più competenze e hanno quindi più occasioni di sovrapporsi
a un annuncio qualsiasi. È una proprietà dei dati, non della formula.

È una smentita più solida di quella che si otteneva a γ = 0,3, dove la
correlazione era +0,012: lì l'ipotesi veniva respinta per **assenza** di
segnale — argomento fragile, perché un valore basso può sempre essere un caso —
mentre qui viene respinta per **ablazione**, rimuovendo la causa sospetta e
osservando che l'effetto resta.

Si noti inoltre che a γ = 0,10 le due colonne coincidono su tutte le metriche
di ordinamento, mentre a γ = 0,3 differivano (MRR 0,912 contro 0,925): il
denominatore della copertura è fisso, quindi il termine assoluto non altera
l'ordinamento relativo fra candidati.

### 5.5 Il punteggio è una misura o solo un ordinamento?

`analysis/valida_monotonia.py` — 40 CV, tre confronti ciascuno ad affinità
decrescente.

| livello di affinità | media | mediana | min | max |
|---|---|---|---|---|
| stessa occupazione | 0.861 | 0.862 | 0.736 | 0.945 |
| stesso settore ISCO | 0.763 | 0.782 | 0.611 | 0.864 |
| settore diverso | 0.733 | 0.742 | 0.532 | 0.829 |

Sovrapposizione fra livelli contigui 2,5% e 12,5%: le distribuzioni sono
separate, quindi il valore assoluto è informativo e non solo l'ordinamento.

**Il difetto che questo test ha rivelato.** Con `seniority_weight` a 0.3 le
sovrapposizioni erano 40% e 30%, e il minimo della stessa occupazione (0.573)
scendeva sotto il massimo di un settore diverso (0.867). I casi tracciati
hanno mostrato il meccanismo:

| confronto | occupazione dell'annuncio | copertura | similarità | punteggio |
|---|---|---|---|---|
| stessa occupazione | telecommunications manager | 0.967 | 1.000 | **0.646** |
| settore diverso | mask maker | 0.881 | 0.805 | **0.711** |

Il CV era senior, l'annuncio della stessa occupazione junior: allineamento
nullo, trenta punti azzerati, confronto ribaltato.

Il parametro era stato ottimizzato su un test che isolava una sola dimensione,
dove il valore alto era sempre preferibile. Solo misurando entrambe le
dimensioni insieme è emerso che comprometteva il compito principale.

**Casi tracciati.** `docs/casi_tracciati.md` riporta cinque confronti completi
con la scomposizione del punteggio, le competenze coperte e quelle mancanti:
servono a rendere i risultati verificabili a mano.

### 5.6 Limite del test sull'occupazione

Il 96,7% di Precision@1 sovrastima ampiamente la difficoltà del compito. CV e
annunci della stessa occupazione sono generati campionando dalla medesima
lista di skill ESCO:

| coppia CV ↔ annuncio | sovrapposizione media (Jaccard) |
|---|---|
| stessa occupazione | 0.640 |
| stesso settore ISCO, occupazione diversa | 0.0164 |
| settore diverso | 0.0034 |

Il 93% delle coppie di occupazioni diverse non condivide alcuna competenza. Al
motore basta rilevare "hanno qualcosa in comune" per vincere, e restringere il
pool non aiuta: anche dentro lo stesso settore la separazione resta di 39
volte. Il valore va riportato insieme a questa quantificazione, altrimenti
suggerisce una capacità discriminativa che il test non ha verificato.

Il test sulla seniority non ha questo problema: i sei annunci di una stessa
occupazione hanno competenze quasi identiche, quindi il segnale sul livello
non è replicato dalla costruzione del dataset.

---

## 6. Raccomandatore di corsi

`analysis/valida_course_recommender.py`

### 6.1 Scelta dello scenario

Confrontare un candidato con un annuncio del lavoro che già svolge non produce
nulla da colmare: **0,17 competenze mancanti per confronto**, su circa 12
richieste. Chi cerca formazione lo fa per un lavoro che ancora non può
ottenere, quindi sono stati provati tre scenari.

| scenario | confronto | skill mancanti distinte | copertura |
|---|---|---|---|
| stessa occupazione | CV ↔ annuncio dello stesso ruolo | 22 | 50,0% |
| avanzamento | CV junior/mid ↔ annuncio senior dello stesso ruolo | 8 | 37,5% |
| **transizione** | CV ↔ annuncio di altra occupazione, stesso settore ISCO | **72** | **43,1%** (pesata 40,8%) |

Solo la transizione produce un campione utilizzabile. Gli altri due sono
riportati perché il loro fallimento è informativo, non perché misurino il
raccomandatore.

### 6.1-bis Un limite del dataset emerso qui

Lo scenario di avanzamento avrebbe dovuto essere il più significativo — è la
progressione di carriera, il caso d'uso naturale della formazione. Ha invece
prodotto appena 10 occorrenze su 60 CV, praticamente nulla.

Il motivo è che nel dataset sintetico la seniority cambia **quanto** viene
richiesto, non **che cosa**: i sei annunci di un'occupazione attingono tutti
alla stessa lista ESCO, e passando da junior a senior il numero di competenze
sale da 10,8 a 16,2 ma la loro natura resta identica. Un candidato junior
possiede quindi già, qualitativamente, ciò che l'annuncio senior richiede.

Nella realtà la progressione comporta competenze di tipo diverso —
coordinamento, responsabilità di budget, specializzazione tecnica — che il
generatore non ha modellato. È un limite del dataset, non del raccomandatore,
e una direzione concreta per un lavoro successivo: differenziare le
competenze campionate in funzione del livello, non solo la loro quantità.

### 6.2 Il limite è il catalogo, non l'algoritmo

Copertura dell'indice Coursera sull'intera ontologia ESCO:

| settore ISCO | skill | con corso |
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

Il gradiente supera il doppio fra lavoro intellettuale e lavoro manuale.
Coursera è un catalogo accademico, tecnologico e gestionale: competenze come
"tipi di pelle", "codice della strada" o "manage crop rotation" non vi
compaiono.

Il 43,1% osservato è quindi quasi il doppio del 23,7% medio dell'ontologia: le
competenze che emergono come mancanti sono meglio coperte della media. Un
sistema di orientamento che copra tutti i mestieri richiederebbe cataloghi
diversi — formazione professionale, apprendistato, enti regionali. È un limite
di dominio, non algoritmico, e va dichiarato come tale.

### 6.3 La pertinenza dei corsi, misurata a mano

`analysis/rivedi_corsi.py` → `docs/revisione_corsi.md`

Il 43,1% della sezione precedente misura una cosa sola: che per quella quota di
competenze mancanti **esista** un corso attribuito nell'indice. Non misura che
il corso sia pertinente. Erano due domande diverse e ne era stata verificata
solo la prima.

Campione casuale di 30 competenze con seme fisso, 65 raccomandazioni giudicate
a mano una per una.

| indicatore | conteggio | valore | IC 95% |
|---|---|---|---|
| corsi pertinenti | 12/65 | 18,5% | 10,9% – 29,6% |
| corsi parzialmente attinenti | 13/65 | 20,0% | — |
| corsi non pertinenti | 40/65 | **61,5%** | 49,4% – 72,4% |
| copertura nominale | — | 43,1% | — |
| **copertura effettiva** | 7/30 | **23,3%** | 11,8% – 40,9% |

L'intervallo di confidenza della copertura effettiva arriva al 40,9% e **non
contiene il 43,1% nominale**: la differenza fra le due misure non è
attribuibile al caso. Un campione preliminare di 10 competenze non permetteva
questa conclusione — l'intervallo andava dal 5,7% al 51% — ed è la ragione per
cui è stato ampliato.

#### Il difetto è nella costruzione dell'indice

L'indice non abbina i corsi alle competenze: abbina i **tag** alle competenze,
e poi attribuisce alla competenza tutti i corsi che portano quel tag.

```
competenza ESCO ──(similarità)── tag ──(appartenenza)── corso
```

Solo il primo anello è misurato. Il campo `esco_match_score` salvato in
`config/course_index.json` — mediana 0,881, con l'aspetto di un punteggio di
pertinenza — quantifica quanto il *tag* somigli alla competenza e non dice
nulla su quanto il *corso* c'entri.

#### Quattro modi di sbagliare, tutti osservati

| modo | esempio |
|---|---|
| **Omonimia del tag** | «rispondere alle richieste di preventivi» → tag «quotation», che vale sia preventivo sia citazione: arrivano corsi di scrittura |
| **Tag giusto, corso sbagliato** | «eseguire il debug di un software» → tag «debugging» corretto, ma i corsi che lo portano sono per insegnanti di scuola primaria |
| **Tag errato sul corso** | «carne halal» → «I/O-efficient algorithms» tramite il tag «daging», che in indonesiano significa carne ma non appartiene a quel corso |
| **Concetto fuori contesto o troppo generico** | «tecnologia di laboratorio medico» → corsi di informatica; tag come «religion» che coprono aree intere |

Nei due casi riusciti il tag era specifico e tecnico — «cataract surgery»,
«test-driven development». **Il tag generico distrugge la pertinenza, quello
specifico la conserva.**

#### Che cosa ne segue

Il limite non è nell'algoritmo di raccomandazione, che fa correttamente ciò che
gli si chiede sull'indice che riceve. È nell'indice. La direzione di lavoro è
quindi precisa: calcolare la similarità fra la **descrizione del corso** e la
competenza, invece che fra il tag e la competenza, ed eventualmente richiedere
l'accordo di entrambi.

---

---

## 6-bis. Confronto fra encoder

`analysis/calibra_soglie.py` → `tests/batch_parse_jobs_gt.py` → `analysis/confronto_modelli.py --solo-riepilogo`

Cinque encoder, tre famiglie, stessa pipeline e stessi 810 annunci. Ciascun
modello ha le proprie soglie, ricavate dalla stessa procedura di calibrazione:
parsing unico a soglie 0,50, ricerca fuori linea su 202 annunci di taratura,
metriche riportate sui 608 restanti.

| modello | fam. | dim | Precision | Recall | F1 | occupazione |
|---|---|---|---|---|---|---|
| multilingual-e5-base | E5 | 768 | 0,764 | 0,533 | **0,612** | 0,759 |
| bge-m3 | BGE | 1024 | 0,741 | 0,543 | 0,610 | **0,861** |
| multilingual-e5-small | E5 | 384 | 0,691 | 0,570 | 0,609 | 0,622 |
| mpnet-base-v2 | S-T | 768 | 0,683 | 0,558 | 0,598 | 0,525 |
| MiniLM-L12-v2 | S-T | 384 | 0,708 | 0,526 | 0,586 | 0,570 |

**Scarto sulle competenze 0,026; sull'occupazione 0,336.** Tredici volte tanto.

### 6-bis.1 Le soglie non sono trasferibili fra encoder

| modello | famiglia | occupazione | 1 parola | >1 parola | acronimi |
|---|---|---|---|---|---|
| multilingual-e5-small | E5 | 0,84 | 0,82 | 0,88 | 0,90 |
| multilingual-e5-base | E5 | 0,82 | 0,82 | 0,88 | 0,90 |
| MiniLM-L12-v2 | S-T | 0,52 | 0,82 | 0,90 | 0,94 |
| mpnet-base-v2 | S-T | 0,56 | 0,82 | 0,82 | 0,98 |
| bge-m3 | BGE | 0,54 | 0,82 | 0,80 | 0,84 |

La soglia sull'occupazione si dispone su due livelli separati secondo la
famiglia: attorno a 0,83 per E5, attorno a 0,54 per le altre due. Il valore 0,72
scelto inizialmente osservando i punteggi di e5-base non è un parametro del
sistema, è un parametro di quel modello.

Il caso limite misurato: con MiniLM e soglie predefinite l'accuratezza
sull'occupazione risultava **0,047**, con il sistema che si pronunciava sul 5,9%
dei documenti — ma nei casi in cui si pronunciava indovinava l'84,4%, più di
e5-base. Con la soglia calibrata l'accuratezza sale a **0,570** sugli stessi
dati e con lo stesso modello.

Un confronto a soglie fisse non misura la qualità degli encoder: misura quanto
ciascuno somigli a E5 nella scala dei punteggi.

### 6-bis.2 Il caso bge-m3

bge-m3 è **il migliore sull'occupazione di dieci punti** (0,861 contro 0,759) e
**indistinguibile sulle competenze** (0,610 contro 0,612). Stesso encoder,
stessi documenti, stessa esecuzione: su un compito nettamente superiore,
sull'altro identico agli altri.

La differenza non sta nel modello ma in quanta pipeline lo circonda.
Sull'occupazione il titolo viene confrontato con le etichette ESCO e vince la
più simile: l'encoder decide da solo. Sulle competenze ci sono segmentazione,
vincolo multi-parola, soglie per tipo di candidato e classificatore appreso:
ogni stadio assorbe parte degli errori dell'encoder.

**La formulazione corretta non è «il modello conta poco», ma: quanto conta il
modello dipende da quanta pipeline lo circonda.**

Riferimento sul lato competenze: il lavoro di pipeline vale +0,238 di F1
(da 0,391 a 0,629); passare da e5-small a e5-base ne vale +0,003.

### 6-bis.3 Due encoder esclusi

`intfloat/multilingual-e5-large` — escluso per costo computazionale, non
misurato.

`Alibaba-NLP/gte-multilingual-base` — escluso per un difetto verificato nella
sua implementazione. Il codice remoto distribuito col modello indicizza le
rotary embeddings con un `position_ids` contenente memoria non inizializzata e
fallisce in codifica. L'errore **non è deterministico**: la stessa memoria può
contenere valori piccoli e lasciar proseguire l'esecuzione con posizioni
sbagliate, producendo embedding privi di senso ma dall'aspetto normale. Da qui
`analysis/prova_modello.py`, che verifica forma, normalizzazione e stabilità su
cinque esecuzioni prima di impegnare ore di calcolo.

---

## 6-ter. Validazione dell'ordinamento del divario

Ultimo componente della pipeline a ricevere una misura. Ordinava le competenze
mancanti con 40% frequenza, 40% trasversalità, 20% co-occorrenza: pesi scelti e
mai verificati, e una componente di co-occorrenza nata come surrogato perché il
dataset iniziale non conteneva le relazioni fra competenze.

**Verifica di versione.** Gli UUID dei CSV ufficiali corrispondono al dataset
locale nel 100% dei casi (5.818 su 5.818, zero orfani). Il dataset del progetto
è **ESCO v1.2.1**: verificato, non dedotto.

**Che cosa contengono i file.**

| file | contenuto | copertura |
|---|---|---|
| `skillSkillRelations.csv` | 5.818 dipendenze (189 `essential`, 5.629 `optional`) | 41% |
| `broaderRelationsSkillPillar.csv` | 20.183 righe di gerarchia | **100%** |

**A. Accordo fra ricostruzione e gerarchia ufficiale** (10.000 coppie per gruppo):

| | co-occorrenti | casuali |
|---|---|---|
| similarità tassonomica media | **0,103** | 0,040 |
| quota con antenato comune | 28,3% | 13,9% |
| quota vicine (≥ 0,5) | **7,9%** | 1,8% |

Correlazione di rango fra numero di co-occorrenze e similarità: **ρ = 0,033**.
La ricostruzione conteneva informazione binaria — «queste due competenze hanno a
che fare l'una con l'altra» — e veniva usata come misura graduata.

**B. Contributi effettivi contro pesi nominali** (787 divari reali):

| componente | peso nominale | contributo reale |
|---|---|---|
| trasversalità | 40% | **72,6%** |
| frequenza | 40% | 20,7% |
| co-occorrenza | 20% | **1,6%** |
| *tassonomia (sostituzione)* | *20%* | *6,7%* |

Causa: `co_occurrence_score` divide una media di co-occorrenze (0–3) per la
frequenza massima (340). Grandezze diverse, risultato schiacciato a zero.

**C. Effetto della sostituzione**, a pesi invariati: tau di Kendall **0,791**,
ordine invariato nel 20,5% dei casi, prima competenza raccomandata cambiata nel
**14,2%**.

**Errore di campionamento da dichiarare.** Il primo tentativo usava i divari di
`job_to_candidates_results.json` e dava τ = 1,000 con zero cambiamenti. Quel
file è il confronto di un solo annuncio contro 810 candidati: 755 divari su
**5 competenze distinte**. Il campione definitivo — competenze `essential`
dell'occupazione meno quelle estratte dal parser — ne ha 1.346, con divari
lunghi in media 9.

Dettaglio completo in `docs/validazione_skill_graph.md`.

---

## 7. Limiti generali da dichiarare

1. **Valutazione per ID ESCO esatto.** Un match concettualmente corretto ma con
   ID diverso conta come errore: le metriche sono un limite inferiore.
2. **Ground truth parziale.** Le competenze attese sono un campione di quelle
   ESCO dell'occupazione; quelle davvero citate nel testo ma non campionate
   risultano falsi positivi. È il problema dei falsi negativi da *distant
   supervision*, noto in letteratura.
3. **Dati sintetici.** CV e annunci sono generati dallo stesso modello di
   linguaggio a partire dalla stessa ontologia, con cui condividono il
   lessico. Su documenti reali le metriche sarebbero verosimilmente inferiori.
4. **Componenti tarati sui dati.** Denylist ed euristiche sono state costruite
   osservando questo dataset. Dove possibile validate su holdout, ma la
   generalizzazione a dati reali resta da verificare.
5. **Numerosità dei campioni.** Le validazioni del matching engine girano su
   30–100 CV per ragioni di tempo: differenze di pochi punti percentuali sono
   entro il rumore statistico.
6. **Ordinamento del divario fondato ma non validato.** La prossimità viene ora
   dalla gerarchia ufficiale ESCO e cambia l'ordine nel 79,5% dei casi (§6-ter).
   Non è stato verificato che l'ordine nuovo sia *migliore* per chi deve
   studiare: servirebbe un giudizio umano, non raccolto. I pesi 40/40/20
   restano scelti e non derivati.

---

## 8. Riproducibilità

```
# Parser
python tests/batch_parse_cvs.py
python analysis/analisi_parser.py --section gt --from-batch
python tests/batch_parse_jobs_gt.py
python analysis/analisi_job_parser.py

# Matching engine
python analysis/valida_matching_engine.py --max-cvs 30 --max-jobs 300
python analysis/valida_matching_engine.py --max-cvs 30 --max-jobs 300 --occ-source parser
python analysis/valida_seniority.py --max-cvs 100 --seniority-weight 0.3

# Raccomandatore corsi
python analysis/valida_course_recommender.py --scenario transizione --n-cv 60
python analysis/valida_course_recommender.py --scenario avanzamento --n-cv 60

# Ablazioni del job parser
python tests/batch_parse_jobs_gt.py --no-denylist --out outputs/ab_nodeny.json
python analysis/analisi_job_parser.py --in outputs/ab_nodeny.json

# Ordinamento del divario (richiede i due CSV ESCO in dataset/source/)
python src/build_skill_relations.py
python analysis/valida_skill_graph.py
```

I due CSV ufficiali — `broaderRelationsSkillPillar_en.csv` e
`skillSkillRelations_en.csv` — si scaricano da
<https://esco.ec.europa.eu/en/use-esco/download> con Version **v1.2.1**,
Content **classification**, File type **csv**, Language **en**. La versione
conta: `build_skill_relations.py` verifica la corrispondenza degli
identificativi con il dataset locale e segnala gli orfani.

Ogni configurazione va salvata su un file distinto con `--out`: durante il
lavoro è già capitato due volte di perdere risultati perché due esecuzioni
scrivevano sullo stesso file. Vedi `outputs/INDICE.md` per la provenienza dei
file esistenti.
