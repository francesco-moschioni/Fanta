# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: primo blocco M3 — valore sopra il replacement (VAR) per giocatore, usando le distribuzioni Monte Carlo (ADR-2026-018) e le quote di rosa reali da `config/auction_rules.v1.yaml`.
- Perché ora: M2 è sostanzialmente completo; VAR è il concetto fondamentale che collega "quanto vale un giocatore in assoluto" a "quanto vale per la mia rosa", primo passo del layer forecast-to-bid richiesto da `docs/DATA_AND_MODELING.md`.
- In scope:
  - Livello di replacement per ruolo = fantavoto medio simulato del giocatore all'N-esimo posto per ruolo, dove N = slot totali di lega per quel ruolo (letto da config, non hardcoded: `8 difensori × 20 squadre = 160`, ecc.), applicato al roster 2026/27 reale.
  - Valore sopra replacement = media simulata del giocatore − livello di replacement del suo ruolo.
  - Propagare l'incertezza: VAR calcolato anche su P10/P90, non solo sulla media (mostrare un range, non un numero secco).
- Fuori scope: scarsità dinamica durante l'asta (dipende da chi è già stato assegnato, serve il ledger vivo — blocco successivo), fit con la rosa dell'utente, budget shadow price, domanda avversari.
- Documenti canonici: `docs/DATA_AND_MODELING.md` (forecast-to-bid layer), `config/auction_rules.v1.yaml` (quote rosa).
- File probabilmente coinvolti: `src/fantacalcio/auction/replacement.py` (nuovo package), test, script.
- Criteri di accettazione: quote di rosa lette dalla config, mai hardcoded; VAR con range di incertezza, non solo media; applicato al roster 2026/27 reale con risultati plausibili (i migliori per ruolo hanno VAR più alto, i giocatori mediocri vicino a zero).
- Comandi test/quality: `pytest -q`.
- Seed: eredita quello della simulazione Monte Carlo (42).
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno per lo scope sopra.

## Progresso

- Stato: not started
- Ultimo commit/stato verificato: `8a98a2d`
- Prossima azione: implementare `src/fantacalcio/auction/replacement.py`.
