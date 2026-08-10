# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: secondo blocco M2 — modello voto giocatore (stima gerarchica/shrinkage), validato walk-forward su 5 stagioni di voti reali.
- Perché ora: Elo/Dixon-Coles (primo blocco M2) completato; abbiamo 5 stagioni di voti reali auditati da M1 (189k righe, 0% missingness sui campi chiave).
- In scope:
  - Panel giocatore-giornata dal pannello "Fantacalcio" (primario), escluse righe `ALL` (allenatore) e `voto_no_vote`.
  - Stimatore a shrinkage (Empirical Bayes / James-Stein: media giocatore pesata verso media di ruolo in base al numero di osservazioni storiche) calcolato walk-forward, mai con dati futuri.
  - Baseline obbligatorie: ultimo voto noto, media di ruolo, media stagionale non pesata.
  - Metriche: MAE/RMSE, breakdown per ruolo.
- Fuori scope (dichiarato esplicitamente, non un buco nascosto): **modello di partecipazione/minutaggio**. I file voti elencano solo i giocatori che hanno ricevuto un voto quella giornata, non l'intera rosa — non c'è modo di derivare "probabilità di essere schierato" da questi dati soli senza un riferimento rosa completo per giornata, che non abbiamo ancora. Da riprendere quando/se disponibile una fonte lineup completa (vedi M1: API-Football a pagamento, o listone rose).
- Documenti canonici da leggere: `docs/ROADMAP.md` (gate M2), `docs/DATA_AND_MODELING.md`, `docs/SOURCE_REGISTER.md` (gerarchia campi voto).
- File probabilmente coinvolti: `src/fantacalcio/modeling/player_voto.py`, `tests/test_modeling_player_voto.py`, `scripts/run_m2_player_voto_backtest.py`.
- Criteri di accettazione:
  1. Predizione walk-forward (mai dati futuri per un giocatore/ruolo).
  2. Batte le baseline (ultimo voto, media ruolo, media stagionale) su MAE.
  3. Breakdown per ruolo riportato, non un solo numero aggregato.
  4. Riproducibile (nessuna componente stocastica, o seed fissato se introdotta).
- Comandi test/quality: `pytest -q`; `python scripts/run_m2_player_voto_backtest.py`.
- Data cutoff/snapshot/`as_of`: voti 2021/22-2025/26 già in `data/staged/fantacalcio_voti_manual/` (locale, non committato).
- Seed: n/a per questo blocco (stimatore deterministico).
- Delegazione: vietata (scelte statistiche del lead).
- Decisioni aperte/blocchi: nessuno per lo scope sopra; il modello di partecipazione resta esplicitamente bloccato in attesa di dati lineup completi.

## Progresso

- Stato: not started
- Ultimo commit/stato verificato: `cc97269`
- Prossima azione: implementare `src/fantacalcio/modeling/player_voto.py`.
