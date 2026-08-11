# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — prima valutazione pre-asta 2026/27 completata (voto atteso + partecipazione), vedi Progresso.
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

- Stato: **prima valutazione pre-asta completata** (ADR-2026-015); ingestion listone 2021/22-2026/27 completata prima di questo (12 file).
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 129 passed.
- Sintesi: voto atteso (shrinkage fittato su tutto lo storico) + tasso di partecipazione (ultima stagione nota) applicati ai 498 giocatori del listone 2026/27 reale. Risultati plausibili (top players noti in cima, difensori minori in fondo, medie per ruolo sensate). 84/498 giocatori senza storico, fallback dichiarato. Esplicitamente NON un modello di valore d'asta — manca il layer forecast-to-bid (replacement level, scarsità, budget, domanda avversari).
- Prossima azione possibile: costruire il layer forecast-to-bid (valore sopra replacement, collegamento a `config/auction_rules.v1.yaml` e ai pool G1-G4), oppure il motore Monte Carlo di scoring che applica `SCORING_RULES.md` alle distribuzioni.
