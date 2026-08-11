# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — assegnazione pool G1-G4 completata (ADR-2026-021), vedi Progresso.
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

- Stato: **assegnazione pool G1-G4 completata** (ADR-2026-021).
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 191 passed.
- Sintesi: `src/fantacalcio/auction/round_pools.py`, soglie lette da config (mai hardcoded), pareggi al cutoff mai spezzati arbitrariamente (nessuna regola di tie-break confermata). Marcato `provisional`, mai `official`. Applicato al roster 2026/27 reale: 59P/61D in G1, 60C/40A in G2, 278 in G3/G4.
- **Stato complessivo del progetto**: M0 ✅, M1 ✅, M2 ✅ (forza squadra, voto, partecipazione, scoring engine, Monte Carlo), M3 in corso (VAR ✅, pool G1-G4 ✅). Restano: collegamento al ledger d'asta vivo per raccomandazioni round-per-round, fit con rosa utente/moduli, budget shadow price, domanda avversari, apprendimento di mercato (M5), UX (M4).
- Prossima azione naturale: collegare VAR+pool al ledger d'asta (M0) per produrre una vera raccomandazione "quanto offrire ora, dato quello che è già stato assegnato" — il pezzo che rende lo strumento realmente utilizzabile in asta.
