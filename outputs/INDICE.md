# Indice dei file in `outputs/`

Serve a sapere quale file è attuale e quale descrive uno stato del progetto
ormai superato. Diversi risultati qui dentro sono stati prodotti su dataset o
versioni del codice che non esistono più: citarli in tesi credendoli aggiornati
è l'errore da evitare.

Aggiornato al 20/08/2026.

---

## ATTUALI — usare questi

| file | contenuto | prodotto da |
|---|---|---|
| `cv_batch_results.json` | 810 CV parsati (con filtro nomi di lingua) | `tests/batch_parse_cvs.py` |
| `analisi_risultati.json` | metriche parser CV: P 0.907 · R 0.860 · F1 0.878 | `analysis/analisi_parser.py --from-batch` |
| `job_gt_batch_results.json` | 810 annunci parsati (multi-parola + denylist 64) | `tests/batch_parse_jobs_gt.py` |
| `job_parser_eval.json` | metriche job parser: P 0.614 · R 0.577 · F1 0.580 | `analysis/analisi_job_parser.py` |
| `matching_engine_eval_parser.json` | matching con occupazione stimata dal parser: P@1 96.7% | `analysis/valida_matching_engine.py --occ-source parser` |

**Mancante:** `matching_engine_eval_ground_truth.json`. Il primo run (P@1 96.7%,
MRR 0.969, baseline 2.0%) è stato sovrascritto dal secondo prima che gli script
salvassero su file distinti. Va rifatto:

```
python analysis/valida_matching_engine.py --max-cvs 30 --max-jobs 300
```

---

## REGISTRO DEGLI ESPERIMENTI — conservare, non sono attuali

Output intermedi dei confronti A/B sul job parser. Servono a documentare come
si è arrivati alla configurazione finale; nessuno rappresenta lo stato corrente
del codice.

| file | configurazione | risultato |
|---|---|---|
| `ab_nodeny.json` / `eval_nodeny.json` | nessun rimedio | P 0.299 · R 0.613 · F1 0.393 |
| `ab_full.json` / `eval_full.json` | denylist 232 etichette | P 0.531 · R 0.605 · F1 0.551 |
| `ab_bg.json` | correzione hubness attiva | P 0.298 — nessun effetto |
| `pilot_nodeny.json` | pilota multi-parola su 150 annunci | P 0.552 · F1 0.554 |
| `ab_multiword_nodeny.json` | multi-parola senza denylist | P 0.540 · R 0.581 · F1 0.546 |
| `ab_multiword_deny.json` | multi-parola + denylist 232 | P 0.600 · R 0.575 · F1 0.572 |

`ab_multiword_nodeny.json` è anche l'input di
`analysis/ricostruisci_denylist.py`: serve per rifare la denylist, non va
cancellato.

---

## OBSOLETI — non citare senza rigenerarli

| file | perché | cosa fare |
|---|---|---|
| `batch_job_results.json`, `batch_job_summary.csv`, `batch_job_stats.json` | vecchio dataset di 1000 annunci limitato a 3 aree professionali, sostituito da `job_gt_batch_results.json` | rigenerare o ignorare |
| `course_recommender_eval.json` | calcolato sul vecchio dataset: 15 skill mancanti distinte in tutto, cifra priva di significato statistico | **da rifare** con `analysis/valida_course_recommender.py` |
| `end_to_end_results.json`, `job_to_candidates_results.json` | maggio 2026, precedono tutte le correzioni ai parser | **da rifare** |
| `fn_analysis.json` | analisi dei falsi negativi di maggio, su codice molto diverso | rigenerare se serve |
| `cv_parsed_result.json`, `job_parsed_result.json`, `match_result.json` | esempi singoli di dimostrazione | innocui |
| `analisi_risultati_baseline.json` | baseline storica del parser CV (P 0.760 · R 0.547 · F1 0.623) | **conservare**: è il termine di paragone di partenza |

---

## Convenzione da seguire

Gli script che accettano `--out` vanno usati con un nome diverso per ogni
configurazione. È già successo due volte di perdere risultati perché due
esecuzioni scrivevano sullo stesso file:

```
python tests/batch_parse_jobs_gt.py --no-denylist --out outputs/prova_x.json
python analysis/analisi_job_parser.py --in outputs/prova_x.json --out outputs/eval_x.json
python analysis/valida_matching_engine.py --occ-source parser   # nome automatico
```
