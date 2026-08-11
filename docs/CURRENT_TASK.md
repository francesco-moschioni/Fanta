# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — flag di affidabilità dati completato (ADR-2026-020), vedi Progresso.
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

- Stato: **flag di affidabilità dati completato** (ADR-2026-020).
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 184 passed.
- Sintesi: `src/fantacalcio/modeling/data_quality.py` distingue 4 livelli invece di un unico bucket "sconosciuto". Bug reale trovato e corretto durante l'implementazione (confronto contro 5 stagioni invece che solo l'ultima, dato che la Serie A ruota per promozione/retrocessione). Risultato finale sensato: 50 giocatori "vero trasferimento sconosciuto" (es. Stones, Mastantuono) vs 34 "squadra neopromossa" (Frosinone/Venezia). Ricerca su statistiche estere: StatsBomb copre anche Premier League/Bundesliga/La Liga/Ligue 1 gratis, ma integrarlo è un blocco a sé (dimensione paragonabile a un intero M1) — documentato in `docs/SOURCE_REGISTER.md`, non implementato.
- Prossima azione possibile: blocco StatsBomb multi-lega (se prioritario); oppure continuare M3 (collegare VAR ai 4 giri d'asta / ledger vivo, fit con rosa utente).
