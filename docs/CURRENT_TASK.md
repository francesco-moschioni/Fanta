# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — modello di partecipazione (tasso stagionale) completato, vedi Progresso.
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

- Stato: **blocco partecipazione completato**; blocco regole d'asta completato prima di quello.
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 124 passed.
- Sintesi:
  - Regole d'asta: recap admin integrato, corretto un errore reale (G3/G4 non sono asta aperta), ADR-2026-013.
  - Partecipazione: `src/fantacalcio/modeling/participation.py`, tasso di partecipazione stagione-su-stagione batte la baseline media globale (MAE 0.217 vs 0.256, correlazione 0.428); cross-check tra voti e statistiche molto forte (corr 0.979). ADR-2026-014.
- Prossima azione possibile: integrare il tasso di partecipazione come feature nello stimatore voto (`player_voto.py`) per un output combinato voto-atteso × probabilità-schierato; oppure procedere al motore Monte Carlo/scoring engine di M2/M3.
