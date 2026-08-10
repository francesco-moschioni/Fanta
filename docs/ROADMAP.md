# Roadmap e quality gate

## M0 — Bootstrap e dominio

- loader/validatore del ruleset YAML;
- tipi canonici e test degli invarianti di rosa/round/budget;
- ledger append-only, replay, edit/undo;
- import/export locale JSON/CSV e demo fixture.

Gate: replay deterministico, budget conservato, duplicati/pool/slot bloccati, branch irrisolti falliscono esplicitamente.

## M1 — Audit dati e identità

- registry fonti, snapshot raw e checksum;
- trial Sportmonks/API-Football sullo stesso campione ≥100 partite;
- confronto indipendente ≥50 partite;
- import football-data.co.uk, OpenFootball, Understat campione, StatsBomb/Wyscout;
- entity resolver e coda review.

Gate: report coverage/missingness/drift, mapping confidence, nessun join silenzioso, ADR della fonte primaria/fallback.

## M2 — Baseline predittive

- Elo/Dixon–Coles;
- modello minuti/partecipazione;
- per-90 shrinkato per eventi;
- voto gerarchico se target omogeneo disponibile;
- scoring engine e Monte Carlo seeded;
- forecast stagionale con intervalli.

Gate: split temporale, leakage test, baseline report, calibrazione/coverage, riproducibilità con `as_of`.

## M3 — Motore d’asta e liste

- stati `unknown/provisional/official` e versioni pool;
- replacement/scarsità/fit/costo-opportunità;
- simulazione quattro round e max bid dinamico;
- storico aste e prior prezzo quando disponibili.

Gate: replay storici/sintetici, vincoli futuri rispettati, incertezza visibile, ranking modello mai promosso a lista ufficiale.

## M4 — UX P0

- player search/card;
- costruttore campo/rosa, lock e modulo fisso/libero;
- cockpit live, tabellone 20 squadre, ledger, undo e recovery;
- badge lista non ufficiale e stato `as_of`.

Gate: flusso demo end-to-end su laptop/tastiera, recovery dopo refresh, nessuna formula duplicata nel frontend.

## M5 — Mercato adattivo e modeling avanzato

- boosting/calibrazione/ablation;
- dipendenze di squadra e scenari congiunti;
- inflazione per ruolo/tier, prezzo P25/P50/P75 e domanda avversaria;
- shrinkage e confidence dinamici, ricostruibili dopo undo.

Gate: miglioramento OOS e nel replay decisionale; nessuna personalizzazione forte da campioni minimi.

## M6 — Post-asta

- formazione settimanale, capitano e panchina;
- sostituzioni/no-switch e bonus congiunti;
- regret analysis e storico decisioni;
- NLP news solo da fonti autorizzate se aggiunge valore.

## Regola di priorità

Non iniziare modeling avanzato o UI ornamentale prima dei gate di dominio, dati e baseline. Le questioni di punteggio aperte bloccano i rami partita correlati, non il motore d’asta e i moduli indipendenti.
