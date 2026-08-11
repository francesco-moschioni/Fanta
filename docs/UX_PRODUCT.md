# Specifica UX e prodotto

## Contesti principali

Separare `preparazione`, `asta live` e `post-asta/giornata`. Tutte le viste chiamano lo stesso motore; il frontend non replica formule.

| Area | Decisione | Funzioni essenziali |
|---|---|---|
| Home | cosa richiede attenzione | stato dati/modello, countdown, alert e azioni rapide |
| Giocatori | chi considerare | ricerca, filtri, ranking, confronto e scheda |
| Costruttore rosa | quale combinazione | campo, slot, budget, moduli, replacement e scenari |
| Asta live | quanto offrire | max bid, costo-opportunità, ledger rapido e undo |
| Giornata | chi schierare | formazione, capitano, panchina, sostituzioni e rischio SV |
| Dati/modello | quanto fidarsi | freschezza, copertura, anomalie, fonti, versione e tier |

## Scheda giocatore

Mostrare prima: valore atteso, mediana/P10–P90, probabilità di voto, valore sopra replacement, valore marginale per la rosa, prezzo atteso, offerta consigliata e massimo dinamico, compatibilità slot/moduli, driver positivi, rischi, confidenza, `as_of` e provenienza. Consentire confronto con massimo tre alternative. Dettagli e distribuzioni in pannelli espandibili.

## Spiegabilità (principio permanente, vale per ogni slice UI presente e futura)

Ogni numero derivato mostrato nella UI (VAR, fantavoto atteso, massimo consigliato, budget, ecc.) deve avere:

- una definizione breve accessibile al passaggio del mouse (tooltip/`help`), non solo il numero nudo;
- dove sensato, una traccia di calcolo espandibile con i **valori reali** del record selezionato (formula + numeri di quel giocatore/quella squadra specifici), non una descrizione statica generica che sarebbe identica per chiunque.

La UI non calcola nulla di nuovo per produrre queste spiegazioni: mostra solo la scomposizione di un numero già prodotto dal motore deterministico (es. VAR = fantavoto atteso − livello di replacement, entrambi già colonne calcolate). Nessuna spiegazione generata da un LLM: è visualizzazione di aritmetica già fatta da codice deterministico, mai testo prodotto da un modello linguistico spacciato per calcolo (`CLAUDE.md`: un LLM può spiegare risultati ma non calcolarli).

## Costruttore visuale

- Campo grafico durante la composizione, con titolari, panchina e obiettivi non acquistati distinti.
- Vista `rosa completa` e `formazione titolare`.
- Drag-and-drop e tastiera; controllo immediato 3P–8D–8C–5A, blocco portieri e fallback configurabile 4A.
- Copertura degli otto moduli consentiti, budget totale/impegnato/residuo/minimo di completamento.
- Profondità, rischio combinato di no voto, concentrazione di squadra e confronto acquisto/non acquisto.
- Shortlist, note, tag, giocatori da evitare e snapshot nominati.

### Giocatori bloccati e formazione ideale

L’utente può bloccare liberamente uno o più giocatori. Due ottimizzazioni separate:

1. `undici ideale`: completa una formazione per giornata/scenario;
2. `rosa ideale`: completa 24 slot con ruoli, blocco portieri, budget, pool e costo d’asta.

Modalità `modulo fisso`: riempie il modulo scelto. Modalità `modulo libero`: confronta tutti i moduli validi. Profili `prudente`, `bilanciato`, `aggressivo` cambiano il peso di media, floor, ceiling, probabilità di voto, modificatore, rendimento, concentrazione e flessibilità futura.

Se i lock sono incompatibili, non rimuoverli: mostra vincolo, prova di infeasibilità e minima modifica possibile. Distingui sempre acquistato da ipotetico.

## Cockpit live

Priorità: velocità, numeri grandi, focus e prevenzione errori. Includere command palette, inserimento rapido squadra/giocatore/prezzo, ledger cronologico con edit/undo, import admin, aggiornamento automatico di budget/slot/pool/max bid, tabellone di 20 squadre, alert non bloccanti, prossimi target/alternative, autosalvataggio e recovery.

Output decisionale tipo: offerta consigliata, massimo dinamico, range di mercato, budget dopo acquisto, utilità marginale e costo-opportunità principale. Nessun grafico ornamentale nella modalità focus.

## Apprendimento del mercato

Ogni evento valido aggiorna contabilità e distribuzioni di prezzo. Per ogni avversario mantenere budget, incrementi, spesa, residuo, minimo completamento, budget spendibile, acquisti/tier, fabbisogno e profilo di aggressività con confidenza.

Prior iniziali: quotazioni, FVM, ranking, ruolo, tier e aste storiche disponibili. Aggiornare inflazione globale/per ruolo/tier, distribuzione del prezzo, probabilità di concorrenza, P25/P50/P75 e massimo dinamico. Applicare shrinkage forte nelle prime osservazioni; due o tre acquisti non bastano per dichiarare un profilo appreso.

Undo/correzione deve ricostruire anche mercato e profili. Separare lettura `operativa` (crediti/slot certi) da `predittiva` (domanda/aggressività incerta).

## Priorità

- P0: ricerca/filtri, scheda compatta, liste unknown/provisional/official, costruttore visuale, lock, modulo fisso/libero, budget/slot, ledger 20 squadre, undo, max bid spiegato, autosave e `as_of`.
- P1: confronti, shortlist/note, scenari, ottimizzazione completa, apprendimento prezzi/avversari, alternative, costo-opportunità, import admin e data-quality dashboard.
- P2: giornata/formazione, notifiche, regret, NLP autorizzato e layout avanzato.
