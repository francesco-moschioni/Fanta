# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: **Asta di riparazione inizio settembre 2026 — dati + strumento.** Due parti:
  1. **[FATTA] Refresh listone fine mercato** (ADR-2026-072): ingerito `Quotazioni_Fantacalcio_Stagione_2026_27.xlsx` (531 giocatori, +81/−48 vs pre-mercato), rigenerata la catena MC → m3 → player table. DuckDB rigenerato e committato. 473 test verdi.
  2. **[IN CORSO] Riconciliazione rose reali + G3/G4 nel ledger, poi vista riparazione.** L'utente ha fornito `20lega-rosters-*.xlsx` (stato rose pre-riparazione dalla piattaforma lega): 20 squadre, 23 giocatori ciascuna, 460 righe (giocatore + costo). Il ledger contiene solo G1+G2 (218 assegnazioni) — **G3/G4 non sono mai stati importati**, quindi il roster file è l'unica fonte per ~242 assegnazioni G3/G4/post-asta. Marker `*` nel file = giocatore ceduto all'estero/fuori Serie A (confermato dall'utente; ~24 in lega, coincidono col foglio `Ceduti` del listone). Mappa nome-squadra → `team_id`: 19/20 esatte contro `ledger.sqlite3::team_labels`, la 20ª (`team_05` label "Werder Bremer" vs roster "I Have a N'Drim") per eliminazione — **da confermare**. La squadra dell'utente è `team_01` = "Garlascow Rangers" (confermato).
- Approccio deciso con l'utente:
  - Integrare G3/G4 come **eventi `AssignmentEvent` nel ledger** (batch marcato `source="lega_roster_export_import"`), replayable, sul modello di `scripts/import_g2_results.py`. NON uno snapshot separato.
  - Risoluzione identità dei ~460 nomi via `identity/player_name_resolver.py` (vincolo di ruolo, auto ≥0.90, ambigui in coda review, mai `player_code` inventati). Nessun omonimo cross-squadra nel file (verificato: 0 nomi posseduti da >1 squadra).
  - Riparazione = stesse regole di G3/G4 (`sealed_bid_free`, minimo = quotazione giocatore) **più un meccanismo di svincolo**: le squadre possono liberare un numero di giocatori dalle fasi precedenti e recuperarne i crediti.
- Gap di regolamento aperti (NON indovinati, `CLAUDE.md`) — da confermare con l'admin lega:
  1. **Budget totale di lega / come si calcola il residuo per la riparazione.** I `totale` per squadra nel roster file (spesa) sono ~345–369; il residuo dipende dal budget totale (200+100+40+G4? oppure 500 fisso?).
  2. **Numero massimo di giocatori svincolabili in riparazione** e se i crediti recuperati sono la quotazione pagata o la quotazione corrente.
  Entrambi vanno in `config/auction_rules.v1.yaml` (`uncertain_historical_fields` o nuova sezione `repair_auction`) e nessun ramo di codice che li richiede deve indovinare.
- File probabilmente coinvolti: `scripts/import_lega_rosters.py` (nuovo, dry-run default + `--yes`), `src/fantacalcio/ingest/lega_rosters.py` (parser griglia), riuso `identity/player_name_resolver.py`, `persistence/team_labels_store.py`, `persistence/ledger_store.py`, `domain.py` (`replay` per validazione), `config/auction_rules.v1.yaml` (sezione riparazione), eventualmente nuova pagina `app/pages/8_*_Riparazione.py`.
- Criteri di accettazione: dry-run risolve tutti i 460 nomi (ambigui elencati esplicitamente, mai forzati); il delta ledger↔roster per squadra torna (ledger G1+G2 ⊂ roster file); `replay()` valida ogni evento nuovo senza `DomainError`; budget conservato; con `--yes` il ledger passa da 200 a ~200+242 eventi, riproducibile; i 473 test passano + nuovi test su parser e riconciliazione; verificato in browser che rose e residui compaiano corretti.
- Comandi test/quality: `pytest -q`.
- Seed: non applicabile (nessun campionamento).
- Delegazione: consentita per parser + test; vietata ogni scelta di regolamento o identità ambigua.
- Decisioni aperte/blocchi: i 2 gap di regolamento sopra bloccano il calcolo dei residui e la config riparazione, NON la riconciliazione delle rose nel ledger (quella si può fare subito).

## Progresso

- Parte 1 (refresh listone): **fatta**, ADR-2026-072, DuckDB committato.
- Parte 2: parser roster + dry-run in costruzione. Mappa team_id pronta (19 esatte + 1 da confermare). Nessun evento scritto sul ledger finché il dry-run non è validato e l'utente non conferma la mappa team_05.

---

## Task precedente (archiviata)

- Obiettivo (due filoni in parallelo, richiesti insieme dall'utente):
  1. **Ingest risultati reali G2 + liste di preferenza complete (incluse le offerte fallite)**: l'utente ha caricato `Riepilogo secondo giro asta.xlsx` (recap admin cumulativo G1+G2, 9 coppie giocatore/costo per squadra: col.1 blocco portieri G1 già a ledger, col.2-4 i 3 difensori G1 già a ledger, col.5-7 le 3 fasce centrocampisti G2 nuove, col.8-9 le 2 fasce attaccanti G2 nuove — colore giallo/viola = assegnazione automatica admin, confermato dall'utente, trattata come vinta al pari di verde/ciano) e le 9 "Lista N - ... (Risposte).xlsx" (una riga per squadra con le 6 preferenze reali per fascia, colorate verde=vinta/rosso=tentata e persa/arancione=mai valutata). Obiettivo: (a) scrivere sul ledger reale i soli eventi G2 nuovi (le colonne già coperte da G1 vanno saltate, sono già eventi nel ledger da ADR-2026-055); (b) usare le liste complete (comprese le offerte perse) per modellare meglio il comportamento delle squadre avversarie in `market_model.py` — quanto sopra la propria quotazione/minimo una squadra è disposta a spingersi prima di perdere, quante preferenze "brucia" — per inferire strategia/aggressività reale, non i soli esiti finali.
  2. **Interfaccia per G3 (fase finale a busta chiusa, senza liste)**: G3 è già in `config/auction_rules.v1.yaml` (`sealed_bid_free`, pool `remaining_players`, `max_players_this_phase: 6`, `minimum_bid_source: player_quotazione`, `resolution_priority: highest_bid`) ma non ha ancora una pagina app. A differenza di G2 (buste a fasce, preferenza-poi-offerta, si vince al più 1 per fascia), in G3 non ci sono liste/fasce: si scelgono fino a 6 giocatori liberi qualsiasi con un'offerta secca ciascuno, e si può potenzialmente vincerli tutti e 6 (nessun cap "1 per gruppo" come in G2) — il caso peggiore di spesa è quindi la SOMMA delle 6 offerte, non il massimo. Dopo G3/G4 l'admin assegna manualmente il resto (`post_auction_completion`, non un'asta).
- Stato: **completo e verificato in browser** (ADR-2026-063 → ADR-2026-069). 99 eventi G2 reali + 1 evento Schmid + 19 bonus-logo mancanti scritti sul ledger; profilo comportamentale per squadra (`market_model.team_preference_profiles`) da 616 righe di preferenza curate, ora collegato alla simulazione Monte Carlo G3 (`g3_simulation.py`, cascata con `team_aggressiveness_index`); pagina Buste G3 con store/feasibility dedicati (spesa peggiore = somma, non massimo) + simulazione della competizione avversaria in tempo reale. Audit dell'ingestione della lista admin: corretto un bug reale (`admin_rank` azzerato per 4 giocatori nuovi, bloccava le buste G2) + 2 giocatori con ruolo forzato in asta (Rodriguez Je./Isaksen, C per punteggio ma pescati da Attaccanti). 473 test totali passano.
- Fuori scope per ora (confermato in chat): usare le offerte fallite anche per segnalare la domanda futura su un giocatore specifico, non solo per il profilo comportamentale della squadra — richiesto solo "modellazione comportamento".
- Gap noti, non bloccanti: Lista 1 (portieri, formato a nomi di club non ancora gestito dal resolver) non ingerita nello storico preferenze; ~20% delle righe delle altre 6 liste escluse per nomi ambigui/non risolti; i 2 eventi ledger reali di Rodriguez Je./Isaksen portano ancora il vecchio `pool_id` di provenienza (non un problema funzionale, solo di tracciabilità storica).
- Prossima azione: nessuna bloccante. Possibili estensioni future su richiesta: collegare il profilo comportamentale anche a `bid_recommendation.py` (oggi solo in `g3_simulation.py`); ingest di Lista 1 (portieri).

---

## Task precedente (archiviata)

- Obiettivo: G2 (centrocampisti/attaccanti) non è un pool unico per ruolo come G1 — l'admin lo divide in fasce da 20 (3 per centrocampisti, 2 per attaccanti), ciascuna una busta indipendente da 6 preferenze. L'utente vuole comporre e verificare la fattibilità di budget delle 5 buste direttamente nell'app.
- Stato: **completo e verificato in browser** (ADR-2026-060, ADR-2026-061, ADR-2026-062). Config/dominio corretti per le 5 fasce G2; pagina `app/pages/6_📝_Buste_G2.py` con multiselect per fascia (filtrato per `admin_rank`, mai VAR come fallback silenzioso), bozza persistente in `g2_envelope_picks` (SQLite), fattibilità G2 (caso peggiore + tutte-prime-scelte) e proiezione a valle su G3/G4 (budget residuo vs minimo reale = somma quotazioni dei più economici ancora liberi, non 1 credito a slot). 24 nuovi test totali sul filone, 444 totali passano. Dati reali rigenerati (CSV + DuckDB) per riflettere le nuove fasce.
- Prossima azione: nessuna bloccante. Possibili estensioni future su richiesta: incrociare le buste G2 con i lock/rosa-ideale già esistenti in Rosa; includere anche G1 (già chiuso) e una riserva unificata su tutto l'arco G1→completamento in un'unica vista.

---

## Task precedente (archiviata)

- Obiettivo: l'app pubblicata su Streamlit Community Cloud parte con un ledger vuoto (storage effimero, ADR-2026-048); l'utente vuole i dati reali di G1 lì senza dover fare upload manuale a ogni riavvio.
- Stato: **completo e verificato** (ADR-2026-059). Sezione "Importa/esporta ledger" in Squadre (upload/download JSON, merge senza duplicati) + seeding automatico idempotente da Streamlit Secrets (`ledger_store.seed_missing_events_from_streamlit_secrets`, chiave `ledger_seed_json`, mai su Git) richiamato a ogni pagina che usa il ledger. 9 nuovi test, 417 totali passano. Ledger reale (81 eventi) esportato e consegnato all'utente come file.
- Prossima azione (utente, non bloccante per il codice): (1) push di questo commit; (2) caricare `ledger_export_for_cloud.json` una volta nella pagina Squadre dell'app cloud (import manuale, immediato), OPPURE incollare il contenuto del file nei Secrets del progetto su Streamlit Cloud dashboard con chiave `ledger_seed_json` (si riseeda da solo a ogni riavvio, azione che solo l'utente può fare — l'assistente non ha accesso all'account Cloud).

---

## Task precedente (archiviata)

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
