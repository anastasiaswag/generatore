# Validazione dell'ordinamento del divario formativo

Fino a questo punto lo `skill_graph` era l'unico componente della pipeline
senza una misura. Ordinava le competenze mancanti con un punteggio composito
— 40% frequenza, 40% trasversalità, 20% co-occorrenza — i cui pesi erano stati
scelti e mai verificati, e la componente di co-occorrenza esisteva solo perché
il dataset scaricato non conteneva le relazioni fra competenze.

Scaricati i file ufficiali, la domanda è diventata rispondibile.

---

## 1. Che cosa contengono davvero i file ESCO

Vale la pena dirlo perché contraddice l'aspettativa che i nomi suggeriscono.

| file | contenuto | copertura |
|---|---|---|
| `skillSkillRelations.csv` | 5.818 coppie: 5.629 `optional`, 189 `essential`. Sono **dipendenze** orientate, non somiglianze | 5.650 competenze su 13.939 — **41%** |
| `broaderRelationsSkillPillar.csv` | 20.183 righe di gerarchia | 13.939 su 13.939 — **100%** |

Il file utile è il secondo, non quello dal nome più promettente. Da
`skillSkillRelations` non si può ordinare un divario: su una competenza presa a
caso, sei volte su dieci non dice nulla.

**Verifica di versione.** Gli UUID dei CSV corrispondono al dataset locale nel
100% dei casi (5.818 su 5.818, zero identificativi orfani). Il dataset del
progetto è quindi **ESCO v1.2.1**, e la questione della riproducibilità è
chiusa con una verifica invece che con una deduzione.

---

## 2. La misura adottata

Similarità di Wu e Palmer sulla gerarchia:

```
sim(a, b) = 2 · prof(antenato comune più profondo) / (prof(a) + prof(b))
```

Due dettagli della struttura ESCO che hanno richiesto attenzione.

**Quattro radici, non una.** `skills`, `knowledge`, `language skills and
knowledge`, `transversal skills and competences` non hanno un nodo comune
sopra di loro. Due competenze possono quindi non avere alcun antenato in
comune: la similarità è 0, e non è un errore.

**Profondità come cammino più lungo, non più corto.** In ESCO un concetto può
essere più generale di un altro senza stargli sopra di un livello:
«programmazione informatica» e «Python» pendono entrambi dal gruppo «sviluppo
e analisi di software e applicazioni», e al tempo stesso la prima è dichiarata
più generale del secondo. Contando i passi minimi risultavano alla stessa
profondità, e la formula restituiva **1,000 — identità — per Python e Java**.
Con il cammino più lungo, calcolato in ordine topologico, un concetto è sempre
più profondo dei suoi antenati e i valori diventano corretti:

| coppia | similarità | antenato comune |
|---|---|---|
| Python ~ Java | 0,800 | computer programming |
| Python ~ JavaScript | 0,727 | computer programming |
| Python ~ tecniche di potatura | 0,000 | knowledge (radice) |

---

## 3. La ricostruzione era arbitraria?

No, ma funzionava per una ragione diversa da quella per cui veniva usata.

| | coppie co-occorrenti | coppie casuali |
|---|---|---|
| similarità tassonomica media | **0,103** | 0,040 |
| quota con antenato comune | 28,3% | 13,9% |
| quota concettualmente vicine (≥ 0,5) | **7,9%** | 1,8% |

Le coppie che la co-occorrenza giudica vicine sono **2,5 volte più vicine del
caso**: come indicatore binario — «queste due competenze hanno a che fare l'una
con l'altra» — la ricostruzione conteneva segnale.

Ma la correlazione di rango fra **numero** di co-occorrenze e similarità
tassonomica è **ρ = 0,033**, cioè nulla. Sapere che due competenze compaiono
insieme in quaranta occupazioni invece che in tre non dice niente su quanto
siano concettualmente vicine.

**È il modo in cui veniva usata a essere sbagliato.** `co_occurrence_score`
restituisce un valore graduato e lo tratta come misura di intensità, mentre
l'informazione contenuta era binaria.

---

## 4. Il difetto di normalizzazione

Misurando i contributi effettivi delle tre componenti su 787 divari reali è
emerso un secondo problema, indipendente dal primo.

| componente | peso nominale | contributo effettivo |
|---|---|---|
| trasversalità (`reuse_level`) | 40% | **72,6%** |
| frequenza | 40% | 20,7% |
| co-occorrenza | 20% | **1,6%** |
| *tassonomia (sostituzione)* | *20%* | *6,7%* |

La causa è in `co_occurrence_score`: normalizza dividendo una **media di
co-occorrenze** (tipicamente fra 0 e 3) per la **frequenza massima** (340).
Sono due grandezze diverse, e il risultato viene schiacciato verso lo zero. La
componente pesava un ventesimo di quanto dichiarato.

Il metodo non è stato corretto: è stato documentato e sostituito. Lasciarlo
invariato permette di riprodurre i risultati precedenti con
`build(usa_tassonomia=False)`.

Va detto anche che `reuse_level` domina pur avendo solo **tre valori distinti**
nel campione: ordina per fasce larghe, e dentro ogni fascia decide la
frequenza.

---

## 5. Quanto cambia l'ordine finale

Sostituendo la co-occorrenza con la prossimità tassonomica, a pesi invariati:

| indicatore | valore |
|---|---|
| casi esaminati | 787 |
| tau di Kendall medio | **0,791** |
| ordinamento identico | 20,5% |
| prima competenza raccomandata cambiata | **14,2%** |

L'effetto è reale ma contenuto, ed era prevedibile: la componente sostituita
pesa un quinto del punteggio ed è quella meno influente. In quattro casi su
cinque l'ordine cambia; in un caso su sette cambia la competenza che il sistema
mette al primo posto.

### Una nota sul campione, che è essa stessa un risultato

Il primo tentativo usava i divari di `job_to_candidates_results.json`. Dava
τ = 1,000 e 0,0% di cambiamenti — apparentemente la prova che la sostituzione
non serviva a niente. **Era invece un artefatto del campione:** quel file
contiene il confronto di *un solo* annuncio contro 810 candidati, quindi i 755
divari pescavano tutti dalle stesse sei competenze richieste, per un totale di
**5 competenze distinte**. Su un insieme così ogni ordinamento coincide per
costruzione.

Il campione definitivo è costruito diversamente: per ogni curriculum, le
competenze `essential` della sua occupazione meno quelle estratte dal parser.
Dà 787 casi su **1.346 competenze distinte**, divari lunghi in media 9
competenze, e tutti e tre i livelli di trasversalità rappresentati.

---

## 6. Che cosa resta non misurato

La prossimità tassonomica è **fondata**, non **validata**. Sappiamo che viene
da ESCO invece che da una ricostruzione, e che cambia l'ordinamento nel 79,5%
dei casi. Non sappiamo se l'ordine nuovo sia *migliore* per chi deve studiare:
per dirlo servirebbe un giudizio umano su quale competenza convenga imparare
prima, che non è stato raccolto.

I pesi 40/40/20 restano scelti e non derivati. Ora però il loro effetto è
misurato, e la distanza fra peso nominale e contributo effettivo è documentata.

---

## Comandi

```bash
python src/build_skill_relations.py          # converte i CSV ESCO
python analysis/valida_skill_graph.py        # riproduce tutte le misure
```

File prodotti: `dataset/source/skill_relations.json`,
`outputs/valida_skill_graph.json`.
