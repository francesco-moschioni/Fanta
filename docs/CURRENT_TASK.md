# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: **M7 Engine v2 — Stage 1: livello `features/` (tassonomia livello 4)**. Costruire il feature store con lineage per riga e slicing `as_of`, migrare in esso le feature oggi implicite, aggiungere il test di leakage automatico e il modulo metriche condiviso. Nessun cambio di comportamento a valle. Contesto e piano completo: ADR-2026-070, `docs/ROADMAP.md` §M7, `C:\Users\franc\.claude\plans\usa-tutto-tutto-il-zesty-cherny.md`.
- Perché ora: l'utente ha chiesto di massimizzare previsione e valutazione d'asta ("usare tutto il disponibile"). Stage 0 (branch `feature/engine-v2`, ADR ombrello, registri, `.mcp.json` portabile, `numpy` esplicito) è fatto. Stage 1 è la spina dorsale che sblocca tutti gli stage successivi.
- In scope:
  - `src/fantacalcio/features/schema.py` — `FeatureRow` + `FEATURE_REGISTRY` (nome → dtype, descrizione, fonte, regola `available_time`).
  - `src/fantacalcio/features/store.py` — `write_features(df, dataset)` → `data/features/<dataset>/` (DuckDB `COPY ... TO ... (FORMAT parquet)`, niente `pyarrow`); `read_features(dataset, as_of, names=None)` filtra `available_time <= as_of`.
  - `src/fantacalcio/features/build.py` — builder deterministici che materializzano le feature **già consumate oggi** (running mean voto + peso shrinkage da `modeling/player_voto`, `decayed_participation_estimate` + delta `Pv` da `modeling/participation`, `recency_weight` da `modeling/time_decay`, attacco/difesa/Elo per squadra ai confini stagione da `dixon_coles`/`elo`, bucket FVM da `scoring/fvm_prior`, ruolo/quotazione/FVM/`admin_rank` dal listone). Chiamano i moduli esistenti, non li riscrivono.
  - `src/fantacalcio/features/leakage.py` — `assert_available_before_decision(...)` + versione batch sui fold (generalizza `modeling/validation.assert_no_leakage`).
  - `src/fantacalcio/modeling/metrics.py` — CRPS empirico, PIT/coverage, Brier, log-loss multinomiale (sposta quella in `validation.py` e re-export), rank-corr/NDCG@k, MAE/RMSE. Solo `numpy`/`pandas`/`scipy`.
  - `scripts/build_features.py` — batch (un passaggio per confine stagione + uno "final" per 2026/27), convenzione `run_*`.
  - `.gitignore` — `data/features/` (fatto in Stage 0).
- Fuori scope: qualsiasi condizionamento del Monte Carlo (Stage 2+), nuove fonti dati (Stage 3+), qualsiasi modifica al path d'asta live. Nessun merge su `fanta`.
- File probabilmente coinvolti: i 6 nuovi sopra + `tests/test_features_store.py`, `tests/test_features_leakage.py`, `tests/test_features_build.py`, `tests/test_metrics.py`.
- Criteri di accettazione: `python scripts/build_features.py` popola `data/features/`; `read_features(..., as_of=T)` esclude ogni riga con `available_time > T`; ogni output di builder ha tutte le colonne di lineage non-null e `quality_tier ∈ {A,B,C}`; il test di leakage **fallisce** su una riga avvelenata (`available_time` dopo il decision time) e **passa** sulle feature reali migrate; la feature di shrinkage migrata riproduce `player_voto.walk_forward` bit-a-bit (regression lock); CRPS di una point-mass sul valore vero = 0; i path a valle (`run_monte_carlo_fantavoto.py`, `build_player_table.py`, pagine) restano invariati e i 473 test esistenti + i nuovi passano.
- Comandi test/quality: `pytest -q` (e mirato: `pytest -q tests/test_features_*.py tests/test_metrics.py`).
- Seed: builder deterministici, nessun campionamento in Stage 1. Dove serve un `rng`, esplicito.
- Delegazione: consentita per lo scaffold dei moduli e dei test (worker Claude), inspection e test obbligatori prima del merge. Vietata ogni scelta di dominio/statistica.
- Decisioni aperte/blocchi: formato di persistenza — `COPY ... TO ... (FORMAT parquet)` di DuckDB evita `pyarrow`; se dà problemi su Windows, fallback a CSV gzip. Nessun altro blocco.

## Progresso

- Stage 0: **fatto** (commit `e78cc80`). Branch `feature/engine-v2`; ADR-2026-070 (ombrello); `docs/ROADMAP.md` §M7; `docs/SOURCE_REGISTER.md` sezione "Override d'uso personale"; `.mcp.json`/`.mcp.local.json` gitignored + nota setup in `README_SETUP.md` §5b; `numpy>=1.26` esplicito + extra `ml`/`solver`; `data/features/` e `data/models/` in `.gitignore`; `tests/test_mcp_config.py`, `tests/test_project_metadata.py`. 480 test.
- Stage 1: **fatto**. ADR-2026-071. `src/fantacalcio/features/` (`schema.py` con `FEATURE_REGISTRY` di 18 feature + `validate_feature_frame`; `store.py` write/read parquet via DuckDB con `as_of`; `leakage.py`; `build.py` con 6 builder che chiamano i moduli esistenti); `modeling/metrics.py` (CRPS/PIT/coverage/Brier/log-loss/NDCG/MAE/RMSE/Spearman) + shim `log_loss` in `validation.py`; `scripts/build_features.py`. 45 nuovi test, **518 totali passano**. `scripts/build_features.py` verificato end-to-end: 6 dataset parquet in `data/features/` (player_voto 177.918 righe, participation 4.221, recency_weight 59.306, team_strength 81, fvm_prior 1.494, listone 1.806). Nessun path a valle toccato.
- Stage 2: **fatto (default OFF, ship gate non superato)**. ADR-2026-074. `src/fantacalcio/modeling/odds_priors.py` (`devig` Shin/multiplicativo/power, `shin_z`, `team_goals_distribution` supremacy+total su grid Dixon–Coles `rho=-0.08` con fallback Poisson indipendente, `clean_sheet_prob`/`goals_conceded_pmf`/`expected_goals_conceded`/`match_outcome_probs` dal grid congiunto, `season_team_priors`); `src/fantacalcio/scoring/odds_conditioning.py` (`condition_samples` reweighting/SIR con clip+temper+ESS floor, `scale_scoring_propensity` per A/C); `metrics.py` +`crps_fair`/`rank_histogram`; `monte_carlo.simulate_fantavoto` +param `collect_rows` (default invariato); `features/schema.py` +3 feature `team_odds_*` + builder `build_odds_prior_features`; `scripts/run_monte_carlo_fantavoto.py --odds-priors` (default off, byte-identico); `scripts/run_stage2_odds_backtest.py`. 29 nuovi test, **547 totali passano**. Backtest rolling-origin: quote battono lo shift scalare su CRPS_fair per D/C/A ma **regrediscono su P** → ship gate FAIL → default resta OFF. Caveat: nessun effetto sul numero pre-asta 2026/27 (nessuna fixture prezzata). Nessun path a valle/asta live toccato.
- Stage 3: **fatto (default OFF, gate deferito — servono export Understat reali)**. ADR-2026-075. `src/fantacalcio/ingest/understat.py` (parser puro, zero HTTP, JSON+HTML `JSON.parse` con escape `\xHH`; `parse_player_season`/`parse_shot_events`; `StagedUnderstat` frozen, tier C, `available_time`=fine stagione; `UnderstatParseError`); `src/fantacalcio/ingest/understat_fetch.py` (standalone, `__main__` only, rate-limit ≥5 s, cache, snapshot; mai importato — test statico); `scripts/ingest_understat_folder.py`; `src/fantacalcio/features/xg_features.py` (6 feature per-90 shrinkate tier C, join a `player_code` solo via resolver role-constrained, ambigui in review-queue); `src/fantacalcio/scoring/xg_propensity.py::adjust_event_propensity` (blend `n/(n+prior)` + SIR resample; assente xG → byte-identico); `features/schema.py` +6 feature; `features/build.py` +dispatch; `scripts/run_monte_carlo_fantavoto.py --xg` (default off) + colonna `xg_data_present`. 20 nuovi test, **567 totali passano**. Nessun path a valle/asta live toccato. Assunzioni sul formato JSON Understat (nessun sample reale) documentate nel docstring del parser.
- Prossimo: Stage 4 (Monte Carlo generativo modulare). In alternativa, rivedere il target conceded-pmf per i portieri (causa del fallimento del gate Stage 2).

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
