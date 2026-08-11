# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — primo blocco M3 (valore sopra replacement) completato, vedi Progresso.
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

- Stato: **primo blocco M3 completato** (ADR-2026-019).
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 178 passed.
- Sintesi: `src/fantacalcio/auction/replacement.py`, replacement level per ruolo da config (mai hardcoded), VAR con range di incertezza. Applicato al roster 2026/27 reale: trovata una carenza reale di attaccanti disponibili (88/100 slot, -12) e portieri (59/60, -1), segnalata esplicitamente invece di assorbita silenziosamente nel fallback. Risultati plausibili (Lautaro Martinez, Thuram in testa per VAR).
- Prossima azione naturale: collegare il VAR ai 4 giri d'asta reali (pool G1-G4 da `config/auction_rules.v1.yaml`) per un vero "quanto offrire" per round; oppure fit con la rosa dell'utente (giocatori bloccati, moduli). Entrambi richiedono il ledger d'asta vivo (M0) collegato al valore (M2/M3) — il pezzo di integrazione finale.
