# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — join risultati partita per porta-inviolata completato (ADR-2026-017), vedi Progresso.
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

- Stato: **join risultati partita completato** (ADR-2026-017).
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 162 passed.
- Sintesi: `src/fantacalcio/modeling/team_matchday.py` deriva gol per squadra-giornata da football-data.co.uk (giornata dedotta dal rank cronologico, verificato contro OpenFootball). Provato a estendere porta-inviolata/gol-subito ai difensori con questo dato — **peggiorava** l'accordo con `Fm` reale, scartato con evidenza empirica (non un'assunzione). Il portiere invece beneficia del join (copertura 96,6% vs dato individuale parziale): correlazione con `Fm` reale migliorata a 0,51-0,60.
- Prossima azione possibile: modificatore difesa (formula ancora bloccata in `OPEN_QUESTIONS.md`, ma ora abbiamo il join squadra-giornata pronto per quando sarà confermata); oppure motore Monte Carlo per giornate future.
