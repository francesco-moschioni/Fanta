# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — primo blocco M2 (Elo/Dixon-Coles) completato, vedi Progresso. Prossimo blocco da scoping: modello voto/minuti giocatore, ora possibile con le 5 stagioni di voti reali ingerite in M1.
- Perché ora: `TODO`
- In scope: `TODO`
- Fuori scope: `TODO`
- Documenti canonici da leggere: `TODO`
- File/simboli probabilmente coinvolti: `TODO`
- Criteri di accettazione: `TODO`
- Comandi test/quality: `TODO`
- Data cutoff/snapshot/`as_of`: `TODO o N/A`
- Seed, se applicabile: `TODO`
- Delegazione: vietata | Gemini per `TODO` | subagente `TODO` per `TODO`
- Decisioni aperte/blocchi: `TODO`

## Progresso

- Stato: **blocco Elo/Dixon-Coles completato**.
- Ultimo commit/stato verificato: sessione 2026-08-10, `pytest -q` → 98 passed.
- Sintesi:
  - Rolling-origin validation (`src/fantacalcio/modeling/validation.py`), leakage check esplicito, baseline naive obbligatorie.
  - Elo sequenziale + modello probabilità esito fittato (`elo.py`); Dixon-Coles Poisson attacco/difesa con time-decay (`dixon_coles.py`, correzione tau dichiaratamente omessa per ora).
  - Backtest su 5 stagioni reali (2021/22-2025/26): entrambi i modelli battono le baseline su ogni fold. Report in `data/outputs/m2_team_strength_backtest.md`. ADR-2026-011.
  - Gestito esplicitamente il caso squadre neopromosse senza storico (fallback a forza media, tracciato non nascosto).
- Prossima azione: aprire un nuovo `CURRENT_TASK.md` per il modello voto/minuti giocatore (prossimo blocco M2), usando le 5 stagioni di voti in `data/staged/fantacalcio_voti_manual/` come target.
