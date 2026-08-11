# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — raccomandazione offerta massima collegata al ledger vivo completata (ADR-2026-022), vedi Progresso.
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

- Stato: **raccomandazione offerta massima completata** (ADR-2026-022). Con questo, lo strumento produce un vero "quanto offrire ora" collegato allo stato reale dell'asta, non solo un elenco statico.
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 201 passed.
- Sintesi: `src/fantacalcio/auction/bid_recommendation.py`, formula standard "dollar rule" (riserva 1 credito/slot + distribuzione proporzionale al VAR), budget/slot letti dal replay del ledger. Trovato e corretto un bug reale (confronto ID giocatore stringa-vs-intero che non escludeva mai i già assegnati). Dimostrato su dati reali: la raccomandazione sale quando i rivali comprano alternative, scende quando la propria squadra consuma budget/slot.
- **Stato complessivo**: M0 ✅, M1 ✅, M2 ✅, M3 con pezzo centrale funzionante (VAR → pool → raccomandazione live). Dichiaratamente semplificato: manca domanda avversari modellata, inflazione di mercato osservata, fit di modulo/rischio (richiedono uno storico di aste reali che non abbiamo).
- Prossima azione possibile: interfaccia utente minima per usare questo durante l'asta reale (M4), oppure raffinare la formula di offerta con apprendimento di mercato quando ci saranno dati d'asta reali da osservare (M5).
