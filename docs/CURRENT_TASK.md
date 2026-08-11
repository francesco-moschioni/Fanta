# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — motore deterministico di scoring (componenti individuali) completato, vedi Progresso.
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

- Stato: **motore di scoring individuale completato e validato** (ADR-2026-016).
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 153 passed.
- Sintesi: `src/fantacalcio/scoring/engine.py` implementa le componenti individuali confermate (gol, assist approssimato, gol subito/porta inviolata solo portiere, cartellini, autogol, rigore sbagliato). Trovato e corretto un bug reale durante la validazione: porta inviolata veniva erroneamente assegnata anche ai difensori per un campo dati non affidabile per quel ruolo — corretto, correlazione con `Fm` reale migliorata da ~0.35-0.44 a ~0.47-0.57. Componenti non confermate (rigore parato/procurato, gol pareggio/vittoria, capitano, fair play, modificatore difesa, bonus rendimento, bonus inferiorità) esplicitamente bloccate con `ScoringComponentBlocked`, mai inventate.
- Prossima azione possibile: join con risultati partita (football-data.co.uk) per abilitare porta-inviolata-difensori e modificatore difesa; poi motore Monte Carlo per prevedere giornate future (non solo replay di eventi storici).
