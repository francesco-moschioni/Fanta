# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M4 slice 7 — due parti, richieste insieme dall'utente dopo aver provato l'app in prima persona ("così non si capisce niente"):
  1. **Chiarezza UI** (priorità, blocca la percezione di tutto il resto): nomi squadra personalizzabili (non più solo `team_01`), spiegazione in linguaggio semplice in cima a ogni pagina (cosa fa, quando usarla), Home riscritta come guida reale, valori tecnici tradotti ovunque compaiono (non solo nella scheda giocatore).
  2. **"Rischi di rosa"**: concentrazione di squadra (troppi giocatori dello stesso club reale, `docs/UX_PRODUCT.md`) + lista giocatori da evitare (simmetrica ai lock, stesso meccanismo di persistenza).
- Perché ora: feedback diretto dell'utente dopo test reale dell'app — priorità assoluta rispetto a nuove funzionalità costruite sopra una UI che "non si capisce".
- In scope:
  - `src/fantacalcio/persistence/team_labels_store.py` (nuovo): tabella SQLite `team_labels` (stesso DB, team_id -> etichetta personale). Mai usato per la logica di dominio (il ledger continua a usare `team_id` come chiave), solo per la visualizzazione.
  - Ogni pagina (`app/pages/*.py`, `app/Home.py`): blocco di spiegazione in italiano semplice in cima; sostituire `team_id` grezzo con l'etichetta personalizzata ovunque compaia in tabelle/testo; tradurre valori tecnici (round_pool, data_quality_tier, list_pool_name) con le stesse mappe già usate nella scheda giocatore, riusate coerentemente.
  - `src/fantacalcio/persistence/avoid_list_store.py` (nuovo): stesso schema di `locks_store.py` ma per giocatori da evitare (team_id, player_code, role, note, motivo).
  - Concentrazione di squadra: conteggio giocatori per club reale nella rosa combinata (reale + lock), soglia di avviso configurabile ma con default ragionevole dichiarato (non un numero magico nascosto).
  - Integrazione in `app/pages/1_Giocatori.py` (avviso se il giocatore selezionato è da evitare, pulsante evita/rimuovi) e `app/pages/3_Rosa.py` (sezione concentrazione + lista da evitare).
- Fuori scope: nomi reali squadre/partecipanti (restano etichette scelte dall'utente, non dati admin), drag-and-drop, confronto moduli.
- File probabilmente coinvolti: `src/fantacalcio/persistence/team_labels_store.py`, `src/fantacalcio/persistence/avoid_list_store.py`, `src/fantacalcio/auction/roster_risk.py` (concentrazione), `app/Home.py`, `app/pages/1_Giocatori.py`, `app/pages/2_Squadre.py`, `app/pages/3_Rosa.py`, test corrispondenti.
- Criteri di accettazione: ogni pagina ha una spiegazione comprensibile senza gergo tecnico non spiegato in cima; nessun `team_id` grezzo mostrato quando esiste un'etichetta; verificato in browser (non solo unit test) prima di dichiarare fatto, includendo una lettura della UI "a mente sgombra" per giudicare la chiarezza reale, non solo la correttezza funzionale.
- Comandi test/quality: `pytest -q`.
- Seed: non applicabile.
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: **completato** (ADR-2026-035, ADR-2026-036). Verificato in browser sulla sessione reale dell'utente e con una simulazione completa dell'asta.
- Chiarezza: `team_labels_store.py`, intro in linguaggio semplice su ogni pagina, Home riscritta come guida, valori tecnici tradotti ovunque.
- Rischi di rosa: `avoid_list_store.py` + `roster_risk.py`, integrati in Giocatori e Rosa.
- Bug reale trovato e corretto durante la verifica: colonne tabella a tipo misto (int/"—") causavano un errore di conversione Arrow nei log — corretto forzando stringa. Ripulito anche il rumore da `use_container_width` deprecato.
- Simulazione completa asta (`scripts/run_auction_simulation.py`, ADR-2026-036): 4 turni, 20 squadre, dati reali, tutti gli invarianti rispettati. Scoperta reale: solo 59 portieri disponibili per 60 slot richiesti, 2 club con meno di 3 portieri (blocco stesso-club impossibile per chi li punta).
- 314 test totali passano.
- Prossima azione: avvisi di mercato (supply/domanda per ruolo) da mostrare in UI, poi resta da decidere con l'utente — "undici ideale" bloccato dai dati mancanti, confronto moduli, o import del formato admin quando arriva (venerdì sera).
