# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: 4 miglioramenti in sequenza, tutti usando dati già ingeriti (nessuna nuova fonte esterna): (1) collegare Dixon-Coles al Monte Carlo del voto, (2) usare FVM come prior secondario per giocatori a basso storico, (3) recuperare le quote scommesse da football-data.co.uk, (4) decadimento temporale nel bootstrap voto/partecipazione.
- Perché ora: audit ha trovato che Dixon-Coles (validato, ADR-2026-011) non è mai riusato dal voto/Monte Carlo, e FVM/quote scommesse sono dati già presenti mai sfruttati.
- In scope blocco 1: rating attacco/difesa per squadra da Dixon-Coles, confrontati contro il contesto-squadra storico medio del giocatore (pesato per partite), applicati come aggiustamento al campione Monte Carlo per ruoli offensivi (A/C, su rating attacco) e difensivi (D, su rating difesa — P escluso, già coperto da `team_goals_conceded`). Coefficiente di scala validato via walk-forward (stesso schema di `prior_games` in ADR-2026-012), non inventato.
- Fuori scope: aggiustamento per P (già gestito diversamente), rimodellazione completa del bootstrap (resta un aggiustamento additivo post-hoc, non una riscrittura del meccanismo di campionamento).
- Documenti canonici: ADR-2026-011 (Dixon-Coles), ADR-2026-012/018 (voto/Monte Carlo).
- File probabilmente coinvolti: `src/fantacalcio/scoring/team_strength_adjustment.py`, test, script di validazione.
- Criteri di accettazione: coefficiente scelto per validazione onesta (walk-forward), non arbitrario; nessun peggioramento della correlazione con `Fm` reale rispetto alla baseline senza aggiustamento, altrimenti scartato con la stessa onestà usata per il tentativo fallito su porta-inviolata-difensori (ADR-2026-017).
- Comandi test/quality: `pytest -q`.
- Seed: eredita 42.
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: blocco 1 (ADR-2026-023) e blocco 2 (ADR-2026-024) completati; blocco 3 (quote scommesse) prossimo.
- Blocco 1: `src/fantacalcio/scoring/team_strength_adjustment.py`, k=0,5 validato via walk-forward, correlazione Fm 0,3472→0,3522. Integrato in `scripts/run_monte_carlo_fantavoto.py` parte B.
- Blocco 2: `src/fantacalcio/scoring/fvm_prior.py`, pool per quartile FVM sostituisce il pool di ruolo piatto per giocatori con <10 partite storiche. Validato sul sotto-insieme mirato (`scripts/run_fvm_prior_validation.py`): correlazione Fm 0,3326→0,4048 (177 giocatori a basso storico). Integrato in parte B, 130/498 giocatori del roster 2026/27 interessati. 216 test totali passano.
- Prossima azione: blocco 3 — recuperare le colonne quote scommesse da football-data.co.uk (attualmente scartate da `_OPTIONAL_COLUMNS` in `src/fantacalcio/ingest/football_data_co_uk.py`) come verifica/input indipendente per la forza-squadra, validato onestamente prima di adottare.
