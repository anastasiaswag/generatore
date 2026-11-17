# Casi tracciati — matching engine

Cinque confronti CV↔annuncio mostrati per intero, con la
scomposizione del punteggio. Servono a rendere i risultati
verificabili a mano: le metriche aggregate dicono quanto spesso il
sistema ha ragione, questi esempi mostrano *come* arriva alla
risposta.

Per ogni CV sono riportati tre confronti con affinità decrescente,
così si vede il punteggio degradare al diminuire della pertinenza.

---

## Caso 1 — telecommunications manager

CV: `parsed_cv_3ce4691e-ecea-4278-939e-b89ab01087b8_senior_1.pdf`

| confronto | occupazione dell'annuncio | punteggio | copertura skill | similarità ruolo |
|---|---|---|---|---|
| stessa occupazione | telecommunications manager | **0.831** | 0.967 | 1.000 |
| stesso settore ISCO | import export manager in textile industry machinery | **0.791** | 0.876 | 0.821 |
| settore diverso | mask maker | **0.771** | 0.881 | 0.805 |

Dettaglio del confronto con la stessa occupazione:

- punteggio finale **0.831** (giudizio: ottimo)
- copertura delle competenze richieste: 0.967
- similarità fra i ruoli: 1.000
- pesi in uso: conteggio assoluto 0.15, seniority 0.1

Competenze coperte dal candidato:

- eseguire audit TIC
- telecom regulations
- coordinare la formazione del personale dei trasporti
- protocolli di comunicazione TIC
- gestire i bilanci
- coordinare attività tecnologiche
- gestione di un’azione legale
- assumere dipendenti
- attuare la gestione del rischio TIC
- usare sistemi di ticketing TIC

---

## Caso 2 — ticket sales agent

CV: `parsed_cv_bdf2dd9d-6c92-46f4-a8e7-76c12302d3e7_senior_0.pdf`

| confronto | occupazione dell'annuncio | punteggio | copertura skill | similarità ruolo |
|---|---|---|---|---|
| stessa occupazione | ticket sales agent | **0.802** | 0.960 | 0.917 |
| stesso settore ISCO | baggage flow supervisor | **0.728** | 0.863 | 0.834 |
| settore diverso | lawyer | **0.802** | 0.793 | 0.871 |

Dettaglio del confronto con la stessa occupazione:

- punteggio finale **0.802** (giudizio: ottimo)
- copertura delle competenze richieste: 0.960
- similarità fra i ruoli: 0.917
- pesi in uso: conteggio assoluto 0.15, seniority 0.1

Competenze coperte dal candidato:

- vendere biglietti
- fornire informazioni turistiche
- avere conoscenze informatiche
- parlare lingue diverse
- convincere i clienti ad acquistare prodotti e servizi aggiuntivi più costosi
- elaborare i pagamenti
- aiutare i clienti con le biglietterie self-service
- conservare i dati dei clienti

---

## Caso 3 — pulp control operator

CV: `parsed_cv_d0d7d777-073f-4c33-8f27-1d4a0e8e626f_senior_1.pdf`

| confronto | occupazione dell'annuncio | punteggio | copertura skill | similarità ruolo |
|---|---|---|---|---|
| stessa occupazione | pulp control operator | **0.850** | 0.923 | 1.000 |
| stesso settore ISCO | wholesale merchant in machine tools | **0.766** | 0.810 | 0.853 |
| settore diverso | fish production operator | **0.656** | 0.741 | 0.855 |

Dettaglio del confronto con la stessa occupazione:

- punteggio finale **0.850** (giudizio: ottimo)
- copertura delle competenze richieste: 0.923
- similarità fra i ruoli: 1.000
- pesi in uso: conteggio assoluto 0.15, seniority 0.1

Competenze coperte dal candidato:

- alimentare la macchina
- utilizzare un digestore
- eseguire un giro di prova
- lavorare con la rete sociale degli assistiti
- monitorare le macchine automatiche
- tipi di fibre modellate
- individuare soluzioni per la risoluzione dei problemi
- utilizzare una macchina per il controllo della cellulosa

---

## Caso 4 — aquaculture harvesting manager

CV: `parsed_cv_4fe4b1f1-e84d-4056-b062-83d5a64fc571_junior_0.pdf`

| confronto | occupazione dell'annuncio | punteggio | copertura skill | similarità ruolo |
|---|---|---|---|---|
| stessa occupazione | aquaculture harvesting manager | **0.862** | 0.961 | 0.922 |
| stesso settore ISCO | telecommunications manager | **0.642** | 0.698 | 0.872 |
| settore diverso | product assembly inspector | **0.739** | 0.867 | 0.836 |

Dettaglio del confronto con la stessa occupazione:

- punteggio finale **0.862** (giudizio: ottimo)
- copertura delle competenze richieste: 0.961
- similarità fra i ruoli: 0.922
- pesi in uso: conteggio assoluto 0.15, seniority 0.1

Competenze coperte dal candidato:

- eseguire le operazioni di classificazione dei pesci
- garantire la salute e la sicurezza del personale dell’acquacoltura
- prevenire gli infortuni sul lavoro
- regolamenti sul benessere dei pesci
- effettuare la manutenzione delle attrezzature per la cattura dei pesci
- standard di qualità applicabili ai prodotti di acquacoltura
- anatomia dei pesci
- metodi di raccolta delle piante
- biologia della pesca
- fornire assistenza per le procedure veterinarie di diagnostica

---

## Caso 5 — fish production operator

CV: `parsed_cv_83de6811-975d-4f7c-b81e-604c0c17e800_senior_0.pdf`

| confronto | occupazione dell'annuncio | punteggio | copertura skill | similarità ruolo |
|---|---|---|---|---|
| stessa occupazione | fish production operator | **0.889** | 0.953 | 0.842 |
| stesso settore ISCO | footwear finishing and packing operator | **0.747** | 0.744 | 0.828 |
| settore diverso | manicurist | **0.708** | 0.777 | 0.743 |

Dettaglio del confronto con la stessa occupazione:

- punteggio finale **0.889** (giudizio: ottimo)
- copertura delle competenze richieste: 0.953
- similarità fra i ruoli: 0.842
- pesi in uso: conteggio assoluto 0.15, seniority 0.1

Competenze coperte dal candidato:

- utilizzare strumenti di taglio per alimenti
- sollevare pesi pesanti
- rimuovere parti di pesce
- Azionare attrezzature per la lavorazione del pesce
- confezionare pesce
- eseguire i processi di raffreddamento dei prodotti alimentari
- azionare la motosega
- gestione della catena di approvvigionamento
- materiali ad uso alimentare
- sfilettare il pesce

---
