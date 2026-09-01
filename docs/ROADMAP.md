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

## M7 — Engine v2 (ADR-2026-070)

Programma a fasi che completa i livelli 4-5 della tassonomia dati e condiziona il
forecast con segnali già ingeriti ma non collegati. Tutto su branch
`feature/engine-v2`; nessun merge su `fanta` prima dell'ultimo giro extra.
Assorbe gli item parziali di M2 (modello minuti dentro la simulazione) e M5
(boosting/calibrazione/ablation, domanda avversaria nel prezzo).

- **Stage 0** — branch, ADR ombrello, registri aggiornati, `.mcp.json` portabile, `numpy` esplicito.
  Gate: 473 test verdi, nessun cambio di comportamento.
- **Stage 1** — livello `features/` (`src/fantacalcio/features/`): feature store con lineage per riga
  (`event_time/available_time/ingested_time/source_version/quality_tier`), slicing `as_of`, test di
  leakage automatico; migrazione delle feature oggi implicite; `modeling/metrics.py` condiviso (CRPS,
  PIT/coverage, Brier, log-loss, NDCG, MAE/RMSE).
  Gate: feature migrate identiche numericamente ai moduli sorgente; leakage test fallisce su riga
  avvelenata; path a valle invariati.
- **Stage 2** — priori da quote football-data.co.uk nel Monte Carlo (`modeling/odds_priors.py`,
  `scoring/odds_conditioning.py`): distribuzioni esito/gol-squadra/clean-sheet che sostituiscono lo
  shift scalare di `team_strength_adjustment`. Fonte già production, policy-clean.
  Gate: batte o pareggia l'attuale su CRPS/coverage P/D nel walk-forward, senza regredire A/C;
  altrimenti off by default con risultato a verbale. Fallback verificato quando le quote mancano.
- **Stage 3** — ingest manuale Understat (`ingest/understat.py` parser puro + fetch standalone fuori
  pipeline) → feature xG/xA per-90 (`features/xg_features.py`) → propensione gol/assist nel MC
  (`scoring/xg_propensity.py`). Degradazione: assente xG → identico a Stage 2.
  Gate: lineage completo; test statico "nessun `run_*` importa il fetch"; identità ambigue in coda,
  mai `player_code` inventati.
- **Stage 4** — Monte Carlo generativo modulare (`scoring/generative/`): partecipazione/minuti
  campionati prima degli eventi, gol/assist/xA, scoreline/clean-sheet, disciplina, voto base,
  dipendenze compagni/avversari (v1: solo scoreline di squadra condivisa). Stagione ≠ giornata × 38.
  Gate: riproduce `bootstrap` entro rumore quando privato dei nuovi input; lo batte su CRPS/coverage
  seasonal nel walk-forward. Default resta `bootstrap` finché il gate non passa.
- **Stage 5** — registro `models/` (`src/fantacalcio/models/registry.py`: `manifest.json` +
  `artifact.pkl` per config-hash, niente MLflow/DVC) + boosting LightGBM per il voto base con CV
  rolling-origin, calibrazione isotonica in-fold, ablation per fonte/tier.
  Gate: GBM promosso solo se batte il miglior baseline obbligatorio su MAE OOS **e** rank-corr **e**
  calibrazione, con ablation che non mostra dipendenza da singola fonte. "Non spedito" è esito valido.
- **Stage 6** — forecast-to-bid: prezzo ombra del budget (Lagrangiano sul DP di `roster_optimizer`,
  `PuLP` solo cross-check nei test), covarianza/complementarità tra pick, domanda avversaria nel
  prezzo (regola limitata/monotona/calibrata, sub-ADR dedicato), profilo di rischio (CVaR/P10).
  Gate: prezzo ombra validato contro il duale LP; nuovo path batte l'attuale sul regret di replay
  G1/G2 o si spedisce opt-in; `recommend_max_bid` senza nuovi argomenti byte-identico a oggi.
- **Stage 7** — disponibilità WhoScored (import manuale) → `features/availability.py` che sostituisce
  il fallback "stato manuale"; prototipo VAEP/xT come spike offline su StatsBomb open 2015/16
  (risultati in un ADR, nessun codice/dipendenza committati).
  Gate: la disponibilità cambia la partecipazione solo con un report reale; nessuna dipendenza live.
- **Stage C** (continuo) — UI: i numeri nuovi entrano solo via `scripts/build_player_table.py`; le
  pagine ottengono badge/provenienza, mai calcolo (test che lo verifica). `config/seeds.yaml`
  centralizza i seed. Test di riproducibilità byte-stable sulla mini-pipeline.

Core onesto ad alto valore: Stage 0-1-2 + il prezzo ombra dello Stage 6. Il resto è opzionale;
Stage 5 e 7 sono i più sacrificabili (gated / solo benchmark).

## Regola di priorità

Non iniziare modeling avanzato o UI ornamentale prima dei gate di dominio, dati e baseline. Le questioni di punteggio aperte bloccano i rami partita correlati, non il motore d’asta e i moduli indipendenti.
