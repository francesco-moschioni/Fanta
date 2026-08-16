# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: import della lista admin ufficiale 2026/27, ricevuta dall'utente in un nuovo formato Markdown (`Liste Fantacalcio 26_27.md`), come oggetto `official` separato dal ranking modello, e app pronta per la prima fase d'asta (ADR-2026-044/045/046).
- Stato: **completo e verificato in browser**. Pipeline curata (parser → risoluzione identità → integrazione separata) + overlay `official` sulla tabella giocatori dell'app + cross-check lock + simulazione asta completa, tutto fatto.
  - `src/fantacalcio/ingest/admin_list_markdown.py`, `src/fantacalcio/identity/player_name_resolver.py`, `src/fantacalcio/identity/admin_official_list.py`: pipeline curata, output in `data/curated/admin_list_2026_27/`. 151 giocatori risolti, 9 nuovi confermati senza `player_code`, 20/20 blocchi portiere per squadra.
  - `src/fantacalcio/auction/apply_official_admin_list.py` + `scripts/apply_admin_official_list.py`: overlay `list_state=official` su `_m3_replacement_values.csv`/tabella DuckDB `players` — 210/498 giocatori ora ufficiali (151 movimento + 59 portieri via blocco club), senza toccare i numeri del modello. `app/Home.py` e `app/pages/1_Giocatori.py` aggiornati per riflettere lo stato reale (non più "tutto provvisorio" fisso).
  - Cross-check dei 4 lock reali (team_01) contro la lista ufficiale: **nessun conflitto**.
  - `scripts/run_auction_simulation.py` (4 turni, 20 squadre): tutti gli invarianti rispettati; carenze reali confermate (59/60 portieri, 88/100 attaccanti, Cagliari/Lecce senza blocco portieri monoclub possibile).
  - 27 nuovi test totali su questo filone, 358 test totali nel progetto, tutti passano.
- Prossima azione: nessuna bloccante. Eventuale rifinitura futura: superficie dedicata nell'app per i 9 nuovi giocatori senza `player_code` e per i 20 blocchi portiere ufficiali (oggi solo nei CSV curati).
- Nota separata, non correlata: rimane sospeso il filone "undici ideale"/storico estero (ADR-2026-040/041/042/043) — 7/84 giocatori con storico reale trovato, ~35 a quotazione più bassa non ancora testati, quota API-Football esaurita. Riprendere solo su richiesta esplicita.

---

## Task precedente (archiviata)

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
- Avvisi di mercato in Home (`market_supply.py`, ADR-2026-037): carenza per ruolo e club senza blocco portieri, visibili subito all'apertura dell'app.
- 320 test totali passano. Server locale riavviato con le ultime modifiche, ledger reale dell'utente verificato intatto.
- Prossima azione: resta da decidere con l'utente — "undici ideale" bloccato dai dati mancanti, confronto moduli, o import del formato admin quando arriva (venerdì sera).
