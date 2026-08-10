# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: primo blocco di M2 (`docs/ROADMAP.md`) — modello Elo e Dixon-Coles per forza squadra/gol attesi, validato rolling-origin contro baseline naive.
- Perché ora: M1 è completo (fonti calendario/risultati verificate, 5 stagioni di voti reali ingerite e auditate); Elo/Dixon-Coles è il primo elemento M2 da cui dipendono sia il modello voto sia il motore Monte Carlo.
- In scope:
  - Rating Elo classico (esito partita, home advantage, K-factor) su football-data.co.uk, 5 stagioni disponibili (2021/22-2025/26).
  - Modello Dixon-Coles (Poisson bivariato, parametri attacco/difesa per squadra, time-decay, fit via MLE) per gol attesi casa/trasferta.
  - Baseline naive obbligatorie: media stagione precedente, tasso vittoria/pareggio/sconfitta costante.
  - Split rolling-origin (mai fold casuali nel tempo); test di leakage espliciti (`available_at` mai successivo al match).
  - Metriche: log loss/Brier per esito partita, MAE/RMSE per gol attesi; confronto con le baseline.
- Fuori scope: modello voto/minuti giocatore (prossimo blocco M2), motore Monte Carlo/scoring (dipende da questo blocco), qualunque uso dei dati voti Fantacalcio (qui servono solo risultati/gol da football-data.co.uk).
- Documenti canonici da leggere: `docs/ROADMAP.md` (gate M2), `docs/DATA_AND_MODELING.md` (validazione, baseline, leakage), `.claude/skills/data-modeling/SKILL.md`.
- File probabilmente coinvolti: nuovo `src/fantacalcio/modeling/{elo,dixon_coles,baselines,validation}.py`, `tests/test_modeling_*.py`, `scripts/run_m2_team_strength_backtest.py`.
- Criteri di accettazione:
  1. Split temporale rolling-origin implementato e testato (nessun fold casuale attraverso le stagioni).
  2. Test di leakage: nessuna feature usa dati con `available_at`/data partita successiva al timestamp di decisione.
  3. Elo e Dixon-Coles battono le baseline naive su almeno una metrica primaria, riportato con intervallo/incertezza, non un solo numero di leaderboard.
  4. Riproducibilità: stesso seed/config → stesso risultato.
  5. Report backtest su tutte le 5 stagioni disponibili.
- Comandi test/quality: `pytest -q`; `python scripts/run_m2_team_strength_backtest.py` per il report completo.
- Data cutoff/snapshot/`as_of`: stagioni football-data.co.uk 2021/22-2025/26 già in `data/staged/football_data_co_uk/` (da ri-fetchare se mancanti per stagioni diverse dal 25/26 e 15/16 già scaricate in M1).
- Seed: fissare esplicitamente per qualunque inizializzazione stocastica del fit.
- Delegazione: Gemini ammesso solo per boilerplate di scaffold/test iniziali, non per le scelte del modello statistico (restano del lead, per policy).
- Decisioni aperte/blocchi: nessuno per questo blocco.

## Progresso

- Stato: not started
- Ultimo commit/stato verificato: `72f676c`
- Prossima azione: implementare `src/fantacalcio/modeling/elo.py` e il fetch delle stagioni football-data.co.uk mancanti.
