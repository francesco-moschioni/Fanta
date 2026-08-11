# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M4 slice 3 — spiegabilità/provenienza di ogni numero derivato mostrato nella UI (VAR, fantavoto atteso, massimo consigliato), su richiesta esplicita dell'utente: tooltip al passaggio del mouse + pannello con la traccia di calcolo reale (formula + numeri veri del giocatore selezionato, non testo generico).
- Perché ora: richiesta esplicita dell'utente, con l'indicazione che vale anche per le slice future ("anche in futuro... tutto ben spiegato"). Diventa un principio permanente, non solo di questa slice — registrato in `docs/UX_PRODUCT.md` così le prossime slice lo ereditano senza doverlo richiedere ogni volta.
- In scope:
  - `docs/UX_PRODUCT.md`: nuovo principio esplicito ("Spiegabilità") — ogni numero derivato mostrato in UI deve avere una definizione breve (tooltip) e, dove sensato, una traccia di calcolo con i valori reali del record selezionato (non una descrizione statica).
  - `app/pages/1_Giocatori.py`: tooltip `help=` sulle metriche (VAR, fantavoto atteso, mediana/P10-P90); pannello espandibile "Come si calcola questo numero?" con traccia reale per VAR (fantavoto atteso − livello di replacement, con N di riferimento del ruolo letto da config), per il fantavoto atteso (bootstrap Monte Carlo: partite proprie nel pool, peso n/(n+60), eventuali aggiustamenti Dixon-Coles/FVM già mostrati come driver, ora collegati numericamente), e per il massimo consigliato (passaggi della formula dollar-rule con i numeri reali di `MaxBidRecommendation`).
  - `app/pages/2_Squadre.py`: tooltip sulle colonne del tabellone (budget, slot per ruolo) via `column_config`.
- Fuori scope: spiegabilità generativa via LLM (CLAUDE.md vieta che un LLM calcoli risultati autoritativi; qui si tratta solo di visualizzare numeri già calcolati dal motore deterministico, mai di farli spiegare da un modello linguistico), costruttore rosa, import admin.
- File probabilmente coinvolti: `docs/UX_PRODUCT.md`, `app/pages/1_Giocatori.py`, `app/pages/2_Squadre.py`.
- Criteri di accettazione: ogni numero spiegato usa i valori reali del giocatore/squadra selezionato (mai testo statico spacciato per specifico); nessun nuovo calcolo nella UI (solo visualizzazione di numeri già prodotti dal motore/dati già in tabella); verificato in browser prima di dichiarare fatto.
- Comandi test/quality: `pytest -q`.
- Seed: non applicabile.
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: **completato** (ADR-2026-029). Verificato in browser con l'esempio esatto dell'utente (VAR di Lautaro Martinez: 7,64 − 6,09 = 1,55, con traccia completa).
- Principio permanente registrato in `docs/UX_PRODUCT.md` ("Spiegabilità"), vincolante per le prossime slice M4. Tooltip + pannelli di traccia in `app/pages/1_Giocatori.py` e `app/pages/2_Squadre.py`.
- Due bug reali trovati e corretti durante la verifica in browser: `ConfigError` non catturato in entrambe le pagine quando il ledger non ha ancora i dati del round precedente necessario per una formula di budget — causava un crash invece di un messaggio chiaro.
- 258 test totali passano (nessun nuovo test: slice puramente di visualizzazione).
- Prossima azione (M4 slice 4, non ancora scoped): costruttore rosa visuale con lock, oppure import del formato file admin quando disponibile.
