# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M4 slice 1 — prima schermata UI, sola lettura: ricerca/filtri giocatori + scheda compatta (`docs/UX_PRODUCT.md`, priorità P0), su Streamlit + DuckDB (stack deciso in ADR-2026-008). Trasforma i CSV già prodotti (Monte Carlo, VAR, round pool, data quality tier) in una schermata effettivamente usabile prima dell'asta.
- Perché ora: M0-M3 hanno gate soddisfatti (dominio, dati, baseline, motore VAR/max-bid); la regola di priorità di `docs/ROADMAP.md` blocca solo il modeling avanzato (M5) prima dei gate, non M4. Nessuna riga di UI esiste ancora nel repo.
- In scope:
  - Script di build che consolida `_m3_replacement_values.csv` (già include Monte Carlo + VAR + round pool + data quality tier) in una tabella DuckDB locale con colonna `as_of`/provenance esplicita (build timestamp, non finto "real-time").
  - Pagina Streamlit "Giocatori": ricerca per nome, filtri per ruolo/squadra/round pool/data quality tier, tabella ordinata per VAR, scheda dettaglio per giocatore selezionato con i campi già disponibili da `docs/UX_PRODUCT.md`'s "Scheda giocatore": valore atteso (sim_mean), mediana/P10-P90, VAR, quotazione, tier di qualità dati, `player_games_in_pool`, flag `used_fvm_prior`/`team_strength_adjustment` come "driver" oggettivi, round pool e `list_state=provisional` badge esplicito (mai spacciato per lista ufficiale, ADR-2026-021).
  - Campi esplicitamente NON disponibili in questa slice (offerta consigliata/massimo dinamico richiedono il ledger vivo, non ancora collegato all'UI; confronto a tre; costruttore rosa/lock) vanno mostrati come "non ancora disponibile", mai inventati o lasciati impliciti.
- Fuori scope: costruttore rosa/campo grafico, cockpit live/ledger, lock, moduli, undo/autosave, apprendimento mercato — slice M4 successive. Nessuna scrittura all'utente (sola lettura).
- Documenti canonici: `docs/UX_PRODUCT.md` (scheda giocatore, priorità P0), ADR-2026-008 (stack), ADR-2026-021 (list_state provisional).
- File probabilmente coinvolti: `pyproject.toml` (dipendenze streamlit/duckdb), `src/fantacalcio/persistence/` (nuovo, layer dati DuckDB), `scripts/build_player_table.py` (nuovo), `app/Home.py` o `app/pages/*.py` (nuovo), test del data layer (non della UI Streamlit stessa, non praticamente unit-testabile).
- Criteri di accettazione: build deterministico e riproducibile dai CSV già in `data/staged/`; nessun dato inventato per i campi non ancora disponibili; badge `list_state` sempre visibile; app avviata e verificata in browser (ricerca, filtri, scheda) prima di dichiarare fatto, per la regola di sessione sulle modifiche UI.
- Comandi test/quality: `pytest -q`.
- Seed: eredita 42 dove applicabile (non rilevante per UI sola lettura).
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: **completato** (ADR-2026-027). Verificato in browser end-to-end (ricerca, filtri, scheda).
- `src/fantacalcio/persistence/player_table.py` (data layer DuckDB + provenance), `scripts/build_player_table.py`, `app/Home.py`, `app/pages/1_Giocatori.py`. 245 test totali passano (11 nuovi).
- Prossima azione (M4 slice 2, non ancora scoped in dettaglio): costruttore rosa visuale + lock, oppure collegamento del ledger vivo (SQLite) per abilitare offerta consigliata/massimo dinamico nella scheda giocatore — da scegliere e scopare come nuova unità quando si riprende M4.
