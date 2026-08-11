# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: integrare `Pv` (partite a voto, statistiche stagionali Fantacalcio.it) come segnale di partecipazione nel modello voto giocatore (M2).
- Perché ora: recap regole asta ricevuto e già integrato (ADR-2026-013, config corretta); `Pv` è un segnale di partecipazione stagionale reale scoperto integrando quotazioni/statistiche, non ancora usato nel modello.
- In scope:
  - Calcolare tasso di partecipazione stagionale (`Pv` / giornate disputate fino a quel punto) per giocatore, walk-forward (mai usando `Pv` finale di fine stagione per predire l'inizio stagione).
  - Usarlo come feature/filtro nel modello voto (es. pesare o segnalare bassa affidabilità per giocatori con tasso di partecipazione basso) o come output separato (probabilità di essere schierato, approssimata dal tasso storico).
  - Restare onesti sul limite: `Pv` è un aggregato *a fine stagione* nel file statistiche attuale — per un vero walk-forward servirebbe `Pv` calcolato giornata per giornata, che non abbiamo. Documentare esplicitamente questa approssimazione.
- Fuori scope: sostituire il bisogno di una fonte lineup granulare (resta comunque preferibile quando disponibile).
- Documenti canonici da leggere: `docs/DATA_AND_MODELING.md`, `docs/CURRENT_TASK.md` (storico), ADR-2026-012.
- File probabilmente coinvolti: `src/fantacalcio/modeling/player_voto.py` o nuovo modulo `participation.py`, test correlati.
- Criteri di accettazione: approssimazione dichiarata esplicitamente nel codice/report; nessun uso di `Pv` di fine stagione per predire giornate precedenti senza flag esplicito.
- Comandi test/quality: `pytest -q`.
- Data cutoff/snapshot/`as_of`: statistiche stagione 2025/26 (parziale, aggiornate alla data di estrazione dell'admin).
- Seed: n/a.
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: not started (blocco precedente — correzione regole d'asta — completato, vedi sotto).
- Ultimo commit/stato verificato: sessione 2026-08-11.
- Sintesi blocco appena chiuso: recap regole admin integrato. Corretto un errore reale: G3/G4 erano configurati come "asta aperta/live" ma il regolamento vero le descrive come busta chiusa libera (vince l'offerta più alta, no asta dal vivo). `config/auction_rules.v1.yaml`, `docs/AUCTION_RULES.md`, `docs/OPEN_QUESTIONS.md` aggiornati; ADR-2026-013. Risolti: numero preferenze (6), priorità risoluzione (preferenza poi offerta), fallback G1/G2, minimo offerta G3/G4. Ancora aperti: tie-breaker per pari preferenza+pari offerta, soglie esatte liste (arrivano venerdì), formato file admin.
- Prossima azione: implementare l'integrazione di `Pv` nel modello voto/partecipazione.
