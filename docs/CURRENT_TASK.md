# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — secondo blocco M2 (stimatore voto giocatore) completato, vedi Progresso.
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

- Stato: **blocco stimatore voto giocatore completato**.
- Ultimo commit/stato verificato: sessione 2026-08-10, `pytest -q` → 111 passed.
- Sintesi:
  - Stimatore Empirical-Bayes (`src/fantacalcio/modeling/player_voto.py`), walk-forward su 59.306 righe reali (5 stagioni, pannello "Fantacalcio").
  - Batte tutte le baseline su MAE complessivo (0.4137 vs 0.4154/0.4494/0.5670), ma con margine piccolo e non uniforme per ruolo (leggermente peggio della media-ruolo sul ruolo C). ADR-2026-012, dichiarato onestamente incluso il limite di tuning-on-test sul parametro `prior_games`.
  - Modello di partecipazione/minutaggio dichiaratamente fuori scope: dati voti non includono l'intera rosa, solo i giocatori votati.
- Prossima azione possibile: nested cross-validation per `prior_games` prima di un uso reale in decisioni d'asta; oppure procedere al blocco successivo di M2 (scoring engine Monte Carlo che applica il regolamento alle distribuzioni) o valutare se sbloccare il modello di partecipazione (richiede fonte lineup completa, vedi M1).
