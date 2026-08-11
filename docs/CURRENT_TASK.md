# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: distribuzione Monte Carlo del fantavoto per giocatore (non solo stima puntuale), via bootstrap dai dati storici reali + motore di scoring deterministico già validato.
- Perché ora: `CLAUDE.md` vieta output puntuali per le previsioni ("distributions, not single magic numbers"); finora M2 produce solo medie. Il motore di scoring (ADR-2026-016/017) e i dati storici (5 stagioni, join squadra-giornata) sono pronti per essere ricampionati invece di modellati parametricamente — evita di inventare una forma di distribuzione non confermata dai dati.
- In scope:
  - Pool di righe storiche reali (voto + eventi individuali, incluso `team_goals_conceded` dove disponibile) per giocatore e per ruolo.
  - Simulazione a mistura: per ogni sorteggio, con probabilità `n/(n+prior_games)` (stesso schema di shrinkage già validato in ADR-2026-012) pesca dalla storia del giocatore, altrimenti dal pool di ruolo — preserva le correlazioni reali tra voto ed eventi (niente Poisson indipendenti che romperebbero quella correlazione).
  - Seed esplicito, riproducibile.
  - Output: media, mediana, P10-P90 per giocatore.
  - Validazione: la media simulata deve essere coerente con la fantamedia storica reale (stesso controllo di onestà usato finora).
  - Applicazione al roster 2026/27 per sostituire/arricchire le valutazioni puntuali di ADR-2026-015.
- Fuori scope: modificatore difesa e altri componenti di squadra ancora bloccati (restano bloccati anche nella simulazione).
- Documenti canonici: `docs/DATA_AND_MODELING.md` (Monte Carlo, distribuzioni), ADR-2026-012/016/017.
- File probabilmente coinvolti: `src/fantacalcio/scoring/monte_carlo.py`, test, script.
- Criteri di accettazione: seed fissato e riproducibile; media simulata validata contro dati reali; applicato al roster 2026/27 reale.
- Comandi test/quality: `pytest -q`.
- Seed: esplicito (42, coerente col resto del progetto).
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno per lo scope sopra.

## Progresso

- Stato: not started
- Ultimo commit/stato verificato: `7953bbe`
- Prossima azione: implementare `src/fantacalcio/scoring/monte_carlo.py`.
