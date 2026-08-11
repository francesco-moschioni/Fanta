# Registro decisioni

La decisione approvata più recente e applicabile prevale. Appendere; non riscrivere la storia. Una proposta non è approvata finché l’utente/admin non la accetta esplicitamente.

## Template

### ADR-YYYY-NNN — Titolo

- Data: YYYY-MM-DD
- Stato: proposed | approved | superseded | rejected
- Supersedes: ADR/fonte, se applicabile
- Scope: auction | scoring | data | modeling | architecture | UX | operations
- Decisione: frase non ambigua
- Rationale: motivo
- Conseguenze: comportamento, migration, test, docs
- Approvato da: nome/ruolo

## Decisioni registrate

### ADR-2026-001 — Quattro giri sostituiscono le tre fasi storiche

- Data: 2026-08-10
- Stato: approved
- Supersedes: descrizione d’asta a tre fasi in `docs/archive/Regolamento_originale.txt`
- Scope: auction
- Decisione: G1 busta chiusa per blocchi portieri e top 60 difensori con 200; G2 busta chiusa per top 60 centrocampisti e top 40 attaccanti con residuo G1 +100; G3 asta aperta sui rimanenti con residuo G2 +40; G4 asta aperta sui rimanenti con residuo G3.
- Rationale: è la specifica di lavoro più recente.
- Conseguenze: configurazione versionata; nessuna logica corrente deriva automaticamente dalle tre fasi storiche.
- Approvato da: project owner

### ADR-2026-002 — Liste ufficiali separate dal ranking

- Data: 2026-08-10
- Stato: approved
- Scope: auction | UX
- Decisione: gestire `unknown`, `provisional`, `official`; solo l’import admin `official` vincola l’asta reale.
- Rationale: la composizione top non è ancora nota e può divergere dalla valutazione tecnica.
- Conseguenze: badge non ufficiale, scenari/probabilità di inclusione, snapshot e ricalcolo all’import.
- Approvato da: project owner

### ADR-2026-003 — Modello generativo probabilistico

- Data: 2026-08-10
- Stato: approved
- Scope: modeling
- Decisione: prevedere minuti/stato, voto, eventi, scoreline e dipendenze; applicare il regolamento con Monte Carlo, non prevedere direttamente una fantamedia unica.
- Rationale: bonus individuali, collettivi e non lineari richiedono distribuzioni congiunte.
- Conseguenze: output con quantili/calibrazione e motore deterministico separato.
- Approvato da: project owner

### ADR-2026-004 — UX attorno alle scelte dell’utente

- Data: 2026-08-10
- Stato: approved
- Scope: UX | auction
- Decisione: visualizzare campo/rosa durante la composizione; supportare giocatori bloccati, modulo fisso/libero e ottimizzazione di undici o rosa senza rimuovere lock incompatibili silenziosamente.
- Rationale: l’app deve costruire una soluzione attorno alle preferenze reali dell’utente.
- Conseguenze: infeasibility explanation, distinzione acquistati/ipotetici e profili di rischio.
- Approvato da: project owner

### ADR-2026-005 — Ledger mercato e apprendimento incrementale

- Data: 2026-08-10
- Stato: approved
- Scope: auction | modeling | UX
- Decisione: ogni prezzo/assegnazione osservato aggiorna crediti esatti, slot, inflazione, distribuzioni prezzo e domanda avversaria; undo/correzione ricostruisce tutto dal ledger.
- Rationale: il mercato osservato contiene informazione sul valore residuo e sul comportamento degli avversari.
- Conseguenze: forte shrinkage iniziale, confidenza visibile e separazione tra stato certo e profilo predittivo.
- Approvato da: project owner

### ADR-2026-006 — Workflow LLM selettivo

- Data: 2026-08-10
- Stato: approved
- Scope: architecture | operations
- Decisione: Claude Sonnet lead; Opus solo eccezionale; Haiku per subtask isolati; Gemini CLI per draft low-risk tramite wrapper; niente team permanenti; calcoli di dominio in codice.
- Rationale: minimizzare token Claude a pagamento preservando qualità e responsabilità finale.
- Conseguenze: allowlist, review e test obbligatori per output esterni.
- Approvato da: project owner

### ADR-2026-007 — Policy dati privata e tracciabile

- Data: 2026-08-10
- Stato: approved
- Scope: data | operations
- Decisione: progetto locale/non commerciale; import manuali posseduti ammessi con provenance/tier; niente scraping Fantacalcio, endpoint privati, bypass o redistribuzione.
- Rationale: pragmaticità dell’MVP senza confondere accessibilità e licenza.
- Conseguenze: registry fonti, raw immutabile, moduli rimovibili e degradazione controllata.
- Approvato da: project owner

### ADR-2026-008 — Stack tecnico

- Data: 2026-08-10
- Stato: approved
- Scope: architecture
- Decisione: Python come linguaggio unico per engine deterministico, pipeline dati e modeling. Persistenza locale su DuckDB (analitica/features) + SQLite (stato transazionale: ledger, rose, sessioni) invece di un DB server. UI come app locale monoprocesso in Streamlit per l'MVP (P0/P1 di `UX_PRODUCT.md`); rivalutare un frontend dedicato (es. FastAPI + SPA) solo se il cockpit live richiede interattività che Streamlit non regge, con ADR successiva. Test con `pytest`. Ambiente gestito con `venv` + `pip-tools` o `uv`, senza servizi esterni per la modalità offline-capable.
- Rationale: locale-first e riproducibilità richiedono la minima superficie di infrastruttura; un solo linguaggio evita adapter tra motore e modello statistico; DuckDB è adatto ad analisi colonnari su snapshot immutabili, SQLite è adatto a scritture transazionali frequenti del ledger d'asta live.
- Conseguenze: `docs/PROJECT_SPEC.md` e `docs/OPEN_QUESTIONS.md` aggiornati; M0 di `docs/ROADMAP.md` può iniziare; import/export restano JSON/CSV come già specificato in `UX_PRODUCT.md`.
- Approvato da: project owner

### ADR-2026-009 — Fonti calendario/risultati confermate per M1 (parziale)

- Data: 2026-08-10
- Stato: approved
- Scope: data
- Decisione: football-data.co.uk e OpenFootball (`openfootball/football.json`) sono confermate come fonti di produzione per calendario/risultati/quote storiche, con automazione permessa. Nessuna decisione ancora su lineup/minuti/eventi player-level (Sportmonks vs API-Football): quell'audit resta bloccato in attesa di account/trial, che l'agente non può creare autonomamente (vedi vincoli su creazione account).
- Rationale: entrambe le fonti sono gratuite, senza autenticazione, con licenza/ToS compatibili con l'uso previsto; l'audit del campione 2025/26 (380 partite ciascuna) mostra 0% missing sui campi chiave e 100% di match rate incrociato sulle partite con identità squadra risolta.
- Conseguenze: `docs/SOURCE_REGISTER.md` aggiornato con stato verificato; pipeline di ingestion (`src/fantacalcio/ingest/`) e report riproducibile (`scripts/run_m1_audit.py` → `data/outputs/m1_data_quality_report.md`) disponibili. M1 resta aperto per la parte lineup/minuti/eventi e per l'entity resolution completa (6/20 squadre in coda di revisione manuale, vedi `data/identity/team_review_queue.json`).
- Approvato da: project owner

### ADR-2026-010 — Provider lineup/minuti/eventi: API-Football primario (futuro, a pagamento), StatsBomb come benchmark

- Data: 2026-08-10
- Stato: approved
- Supersedes: parte "lineup/minuti/eventi" di ADR-2026-009 (che la lasciava bloccata)
- Scope: data
- Decisione: **API-Football** è il candidato primario per lineup/minuti/eventi player-level, da attivare su piano a pagamento quando si vorrà coprire la stagione corrente (piano gratuito verificato: 100 richieste/giorno + rate limit per-minuto più stretto, stagioni disponibili solo 2022-2024). **StatsBomb Open Data** resta un benchmark di validazione permanente e gratuito (nessun account, nessun rate limit, ma copertura Serie A ferma al 2015/16) — non un provider di produzione. **Sportmonks è escluso**: il piano gratuito non include la Serie A, nessuna base per preferirlo ad API-Football finché non si valuta un piano a pagamento head-to-head.
- Rationale: audit comparativo eseguito con campioni reali (API-Football stagione 2023, 380 fixture + 30 partite di profondità; StatsBomb stagione 2015/16, 380 partite + 15 di profondità), entrambi validati contro football-data.co.uk sulla stessa stagione con 100% match rate. Nessuna criticità di qualità dati emersa su nessuno dei due; il fattore decisivo è la copertura di lega/stagione, non la qualità dei dati in sé.
- Conseguenze: `docs/SOURCE_REGISTER.md` aggiornato; report completo in `data/outputs/m1_provider_audit_report.md`; `src/fantacalcio/ingest/{api_football,statsbomb}.py` disponibili e testati. Attivazione in produzione di API-Football rimandata a quando si approva il piano a pagamento — nessun'azione ulteriore richiesta per sbloccare M2 (baseline predittive), che può usare StatsBomb come dataset di validazione nel frattempo.
- Approvato da: project owner

### ADR-2026-011 — Modelli forza-squadra Elo e Dixon-Coles confermati come baseline M2

- Data: 2026-08-10
- Stato: approved
- Scope: modeling
- Decisione: adottare Elo sequenziale (rating diff + modello di probabilità esito fittato via log loss) e Dixon-Coles (Poisson attacco/difesa con time-decay, senza la correzione tau per i punteggi bassi — omissione dichiarata, non silenziosa) come modelli di forza-squadra per M2, entrambi validati rolling-origin su 5 stagioni (2021/22-2025/26) di football-data.co.uk.
- Rationale: backtest su 4 fold espandenti mostra che entrambi i modelli battono le baseline naive (tasso esito costante, media gol) su ogni fold: log loss medio 1.087 (baseline) → 1.008 (Elo) / 1.010 (Dixon-Coles); MAE gol medio 0.935 (baseline) → 0.870 (Dixon-Coles).
- Conseguenze: `src/fantacalcio/modeling/{validation,baselines,elo,dixon_coles}.py` disponibili e testati (98 test totali); report riproducibile in `data/outputs/m2_team_strength_backtest.md`. Squadre neopromosse senza storico ricevono forza media di default (flag `is_known_team`/colonna "unknown-team matches" nel report) — comportamento dichiarato, non un bug. Correzione tau di Dixon-Coles e time-decay tuning restano miglioramenti futuri, non bloccanti per procedere al blocco successivo di M2 (modello voto/minuti giocatore).
- Approvato da: project owner

### ADR-2026-012 — Stimatore voto giocatore a shrinkage, con limite di metodo dichiarato

- Data: 2026-08-10
- Stato: approved
- Scope: modeling
- Decisione: adottare uno stimatore Empirical-Bayes (media giocatore pesata verso media di ruolo, `weight = n/(n+prior_games)`, `prior_games=60`) come baseline per il voto base giocatore, validato walk-forward su 5 stagioni reali (59.306 righe votate, pannello "Fantacalcio"). Il modello di partecipazione/minutaggio resta esplicitamente fuori scope: i file voti elencano solo i giocatori votati, non l'intera rosa, quindi non è derivabile "probabilità di essere schierato" da questi dati soli.
- Rationale: lo stimatore batte tutte le baseline obbligatorie sull'MAE complessivo (0.4137 vs 0.4154 media-ruolo, 0.4494 media-stagione, 0.5670 ultimo voto noto). **Limite dichiarato**: `prior_games=60` è stato scelto scansionando un set di valori sullo stesso backtest poi usato per il report finale (nessun validation split separato per la selezione dell'iperparametro) — è una forma mite di tuning-on-test. Il margine di miglioramento sulla baseline è inoltre piccolo (~0.4%) e non uniforme: sul ruolo C lo stimatore è leggermente peggiore della media-ruolo (0.3805 vs 0.3760); sugli altri ruoli (P, D, A) è marginalmente migliore. Non è un risultato clamoroso, è un miglioramento modesto e onestamente riportato.
- Conseguenze: `src/fantacalcio/modeling/player_voto.py` disponibile e testato (111 test totali nel progetto); report in `data/staged/fantacalcio_voti_manual/_m2_player_voto_backtest.md` (locale, non committato, deriva da dati a licenza personale). Raffinamento futuro suggerito: nested cross-validation per la scelta di `prior_games` invece dello sweep singolo attuale, prima di usare questo stimatore per decisioni economiche reali (offerte d'asta).
- Approvato da: project owner

### ADR-2026-013 — Meccaniche d'asta confermate dal recap admin; corretto errore G3/G4

- Data: 2026-08-11
- Stato: approved
- Supersedes: parte "meccaniche" di ADR-2026-003/ADR-2026-009 (il premesso quattro-giri e i budget restano confermati, invariati)
- Scope: auction
- Decisione: G1/G2 sono a busta chiusa con liste (6 preferenze/lista, priorità preferenza poi offerta, fallback ad assegnazione al prezzo minimo se nessuna preferenza vince, minimo d'offerta dalla lista pubblicata). G3/G4 sono a busta chiusa libera (nessuna lista/preferenza/vincolo di ruolo, vince l'offerta più alta, max 6 giocatori a fase, minimo d'offerta = quotazione giocatore) — **non asta aperta/live come erroneamente configurato in precedenza**. Una fase 3 finale, non un'asta, assegna manualmente i rimanenti partendo dalle squadre con più crediti residui.
- Rationale: recap completo fornito direttamente dall'admin (`docs/archive/Recap_regole_asta_admin_20260811.txt`), fonte primaria autorevole. La correzione G3/G4 emerge da lettura diretta del testo: non descrive mai un'asta dal vivo, solo "offerta più alta" in busta chiusa.
- Conseguenze: `config/auction_rules.v1.yaml` aggiornato (mode `sealed_bid_list`/`sealed_bid_free` invece di `sealed_bid`/`open_auction`; nuova sezione `post_auction_completion`); `src/fantacalcio/config.py` aggiornato di conseguenza; `docs/AUCTION_RULES.md` e `docs/OPEN_QUESTIONS.md` aggiornati. Restano aperti: tie-breaker per pari preferenza+pari offerta, soglie esatte delle liste (arrivano venerdì sera), formato file admin da importare. `resolve_sealed_bid_round()` in `src/fantacalcio/domain.py` resta bloccata (`NotImplementedError`) — le meccaniche sono ora note ma l'implementazione è lavoro futuro (M3), non fatto in questa ADR. 117 test passano.
- Approvato da: project owner

### ADR-2026-014 — Tasso di partecipazione stagionale come feature, derivato dai voti

- Data: 2026-08-11
- Stato: approved
- Scope: modeling
- Decisione: calcolare il tasso di partecipazione (giornate votate / 38) per giocatore-stagione direttamente dal pannello voti (tutte e 5 le stagioni), invece di dipendere solo dal campo `Pv` del file statistiche (che copre una sola stagione). Il file statistiche resta utile come **cross-check indipendente**, non come unica fonte.
- Rationale: la stagione 2025/26 nei voti è già completa (38/38, noto da M1), quindi non è un problema di walk-forward infra-stagionale ma di persistenza stagione-su-stagione — utile proprio per preparare l'asta 2026/27 che non è ancora iniziata. Risultati su dati reali (2955 coppie giocatore-stagione, 1432 transizioni stagione-su-stagione consecutive): il tasso dell'anno precedente predice quello dell'anno successivo meglio della media globale (MAE 0.2173 vs 0.2560, correlazione 0.428) — segnale più solido del guadagno marginale trovato per il voto base (ADR-2026-012). Cross-check contro `Pv`: correlazione 0.979, MAE 2 giornate su 38 — le due fonti indipendenti (voti, statistiche) sono coerenti tra loro.
- Conseguenze: `src/fantacalcio/modeling/participation.py` disponibile e testato (124 test totali nel progetto); report in `data/staged/fantacalcio_voti_manual/_m2_participation_report.md` (locale, non committato). Non ancora integrato come feature diretta nello stimatore voto di `player_voto.py` — prossimo passo naturale se si vuole un output combinato voto-atteso × probabilità-di-schierarsi.
- Approvato da: project owner

### ADR-2026-015 — Prima valutazione pre-asta sul roster 2026/27 (voto atteso + partecipazione)

- Data: 2026-08-11
- Stato: approved
- Scope: modeling
- Decisione: combinare lo stimatore voto (ADR-2026-012, fittato su tutto lo storico 2021/22-2025/26, non walk-forward perché la 2026/27 non è ancora giocata) e il tasso di partecipazione (ADR-2026-014, ultima stagione nota) applicati al listone reale 2026/27 (498 giocatori). Output esplicitamente dichiarato **non un modello di valore d'asta**: manca replacement level, scarsità, budget, domanda avversari (layer forecast-to-bid di M3/`docs/DATA_AND_MODELING.md`).
- Rationale: prima verifica end-to-end su dati reali dell'intera pipeline costruita finora (ingestion → identity → modeling). Risultati plausibili: i primi 15 per voto atteso sono nomi noti di alto livello (Berardi, Lautaro Martinez, Dybala, Calhanoglu, Thuram, migliori portieri); media per ruolo coerente (portieri 6.175, attaccanti/centrocampisti ~6.0-6.06, difensori 5.930 — sensato, il voto base non include ancora il modificatore difesa che si applica nel motore di scoring). 84/498 giocatori (16.9%) sono nuovi al dataset a 5 stagioni (neopromossi/nuovi acquisti) e ricevono fallback a media di ruolo, segnalato esplicitamente riga per riga, non nascosto.
- Conseguenze: `src/fantacalcio/modeling/player_voto.py` esteso con `fit_final_stats` (stato finale su tutto lo storico, distinto da `walk_forward` che è per backtest); `participation.py` esteso con `latest_known_participation`. Script `scripts/run_m2_pre_auction_valuations.py`, output in `data/staged/fantacalcio_voti_manual/_m2_pre_auction_valuations.{md,csv}` (locale). 129 test passano.
- Approvato da: project owner

### ADR-2026-016 — Motore deterministico di scoring: componenti individuali confermate, resto bloccato

- Data: 2026-08-11
- Stato: approved
- Scope: modeling | auction
- Decisione: `src/fantacalcio/scoring/engine.py` implementa solo le componenti individuali confermate in `docs/SCORING_RULES.md` e calcolabili con i dati disponibili: gol (+3), assist (+1, **approssimazione dichiarata**: i dati non distinguono assist da assist-light, tutti scored a tariffa piena), gol subito (-1, solo portiere — vedi correzione sotto), porta inviolata (+1, **solo portiere**), rigore sbagliato (-3), autogol (-2), cartellini (-0,5/-1), assente = 0. Bloccati esplicitamente (`ScoringComponentBlocked`, mai un valore inventato): rigore parato/procurato (regola non confermata, pur avendo il dato), gol pareggio/vittoria e bonus capitano (dato mancante), fair play/modificatore difesa/bonus rendimento/bonus inferiorità (formula non confermata in `OPEN_QUESTIONS.md`).
- Rationale: verifica su dati reali (59.306 righe) ha trovato un bug reale prima del rilascio: il campo `goals_conceded` dei voti è popolato quasi solo per i portieri (71% non-zero) ed è sostanzialmente sempre 0 per i difensori (0,005% non-zero) — non perché tengano la porta inviolata, ma perché il dato individuale non è tracciato per quel ruolo in questa fonte. Applicare "porta inviolata" anche ai difensori con quel campo li premiava quasi ogni giornata, gonfiando il punteggio (correlazione con `Fm` reale 0,33-0,44, scarto medio -0,51/-0,59). Corretto limitando la porta inviolata al solo portiere: correlazione sale a 0,47-0,57, scarto scende a -0,15/-0,23. Un vero bonus porta-inviolata per i difensori richiederebbe un join con i risultati partita (football-data.co.uk, non ancora collegato).
- Conseguenze: `scripts/run_scoring_engine_validation.py` confronta la fantavoto calcolata con `Fm` reale su tutte le 5 stagioni, riportando onestamente il divario residuo (dovuto alle componenti ancora escluse) invece di nasconderlo. 153 test passano. Prossimo passo naturale: join coi risultati partita per porta-inviolata-difensori e modificatore difesa; poi Monte Carlo per giornate future.
- Approvato da: project owner

### ADR-2026-017 — Join risultati partita per porta-inviolata: aiuta il portiere, NON i difensori

- Data: 2026-08-11
- Stato: approved
- Scope: modeling
- Decisione: `src/fantacalcio/modeling/team_matchday.py` deriva gol fatti/subiti per squadra-giornata da football-data.co.uk (giornata dedotta dal rank cronologico delle partite per squadra, verificato contro il campo "round" esplicito di OpenFootball per la stagione 2025/26 — coincide esattamente). Il motore di scoring usa questo dato per portiere/porta-inviolata quando disponibile (96,6% di copertura, più completo del campo individuale), **ma il tentativo di estenderlo ai difensori è stato testato e scartato**: peggiorava nettamente l'accordo con `Fm` reale (correlazione da ~0,5 a 0,16-0,41, scarto da negativo piccolo a +0,75/+0,99). Conferma empirica che questa lega non applica un malus individuale "gol subito" al singolo difensore — il contributo difensivo passa dal modificatore squadra (ancora bloccato), non da un malus per-giocatore.
- Rationale: la scoperta non era assumibile a priori (il testo di `SCORING_RULES.md` non specifica il ruolo per "gol subito"/"porta inviolata"); il test contro dati reali ha falsificato l'ipotesi iniziale ed è stato onestamente ribaltato invece di forzare il risultato atteso. Risultato finale: correlazione con `Fm` reale migliorata a 0,51-0,60 (da 0,47-0,57 della versione solo-portiere-dato-individuale), grazie alla maggiore copertura del join rispetto al campo individuale.
- Conseguenze: `src/fantacalcio/scoring/engine.py` aggiornato con nota esplicita "Tested-and-reverted" nel docstring, per evitare che un futuro tentativo ripeta lo stesso errore senza sapere che è già stato provato. 162 test passano. Join squadra-giornata riutilizzabile in futuro per il modificatore difesa (quando la formula sarà confermata).
- Approvato da: project owner

### ADR-2026-018 — Distribuzione Monte Carlo del fantavoto via bootstrap, non stima puntuale

- Data: 2026-08-11
- Stato: approved
- Scope: modeling
- Decisione: `src/fantacalcio/scoring/monte_carlo.py` sostituisce/arricchisce la stima puntuale del voto (ADR-2026-012/2026-015) con una distribuzione (media, mediana, P10-P90) ottenuta ricampionando **righe storiche reali complete** (voto + eventi individuali + `team_goals_conceded`), non assumendo una forma parametrica (normale/Poisson) mai confermata dai dati. Mistura a shrinkage: pesca dalla storia del giocatore con probabilità `n/(n+60)`, altrimenti dal pool di ruolo — stesso schema già validato per lo stimatore voto puntuale. Seed fissato (42), riproducibile.
- Rationale: `CLAUDE.md` vieta output puntuali per le previsioni ("distributions, not single magic numbers"); questo chiude quel gap. Validazione walk-forward onesta (addestrato su 2021/22-2024/25, testato su 2025/26 mai visto): correlazione con `Fm` reale **0,3532** — sensibilmente più bassa della validazione in-sample dell'ADR-2026-017 (0,51-0,60), riportato senza minimizzare. Due possibili cause non discriminabili con i dati attuali: (1) prevedere una stagione futura è oggettivamente più difficile che spiegarla con i suoi stessi dati; (2) il 31,4% dei giocatori target non ha storico pre-2025/26 (trasferimenti/promozioni) e viene scored solo dalla media di ruolo, che non cattura abilità individuale.
- Conseguenze: applicato al roster reale 2026/27 (498 giocatori, 1000 simulazioni ciascuno) in `data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27.{csv,md}` (locale). Report per ruolo mostra ampiezza di incertezza (P90-P10) molto diversa: attaccanti/portieri ~4,5 punti di spread, centrocampisti/difensori ~1,6-2,3 — segnale plausibile (ruoli offensivi/portiere più volatili). 171 test passano. Correlazione 0,35 va trattata come l'aspettativa onesta per previsioni out-of-sample con questo metodo, non il numero 0,5-0,6 in-sample.
- Approvato da: project owner

### ADR-2026-019 — Primo blocco M3: valore sopra il replacement (VAR)

- Data: 2026-08-11
- Stato: approved
- Scope: auction | modeling
- Decisione: `src/fantacalcio/auction/replacement.py` calcola il livello di replacement per ruolo (fantavoto medio simulato del giocatore all'N-esimo posto, N = slot totali di lega letti da `config/auction_rules.v1.yaml`, mai hardcoded) e il VAR (valore sopra replacement) per ogni giocatore, con range di incertezza propagato (P10/P90), non un solo numero.
- Rationale: applicato al roster reale 2026/27 ha rivelato una carenza di offerta reale non ipotizzata a priori: **88 attaccanti disponibili su 100 slot di lega richiesti** (-12) e 59 portieri su 60 (-1). Per gli attaccanti questo è esattamente lo scenario per cui esiste `forwards_fallback_if_supply_insufficient: 4` nella config — non un errore del codice, un fatto del mercato che il codice ora segnala esplicitamente invece di assorbirlo silenziosamente nel fallback "usa l'ultimo disponibile". I risultati sono plausibili: i migliori attaccanti (Lautaro Martinez, Thuram) hanno il VAR più alto, coerente con l'intuito calcistico.
- Conseguenze: `scripts/run_m3_replacement_values.py` applicato ai dati reali, report in `data/staged/fantacalcio_voti_manual/_m3_replacement_values.{csv,md}` (locale). 178 test passano. Resta fuori scope: scarsità dinamica durante l'asta live (serve il ledger), fit con la rosa dell'utente, budget shadow price, domanda avversari — prossimi blocchi M3.
- Approvato da: project owner

### ADR-2026-020 — Flag esplicito di affidabilità dati; ricerca campionati esteri scoperta ma non integrata

- Data: 2026-08-11
- Stato: approved
- Scope: modeling | data
- Decisione: `src/fantacalcio/modeling/data_quality.py` classifica ogni giocatore in 4 livelli (`full_history`, `partial_history`, `no_history_transfer`, `no_history_new_team`) invece di trattare "zero storico" come un unico bucket indifferenziato. Nessuna distribuzione viene allargata artificialmente per compensare — il flag serve a segnalare all'utente dove il prior a media di ruolo è debole (trasferimento vero) invece di ragionevole (giocatore di una neopromossa), non a inventare un'incertezza numerica senza base.
- Rationale: su richiesta esplicita di arricchire i profili con statistiche da campionati esteri per giocatori a zero/pochi dati. Ricerca: **StatsBomb Open Data copre anche Premier League, Bundesliga, La Liga, Ligue 1** (gratis, nessun account, già verificato in M1) — ma la copertura recente è limitata (Bundesliga 2023/24 è la più recente; Premier League ferma al 2015/16) e costruire l'ingestion multi-lega con risoluzione identità cross-campionato è un blocco di dimensioni paragonabili a un intero M1, non improvvisabile in questa sessione. **Non implementato ora, documentato come pista futura scoperta e pronta**. Nel frattempo, bug reale trovato e corretto durante l'implementazione del flag: la classificazione confrontava lo zero-storico contro l'unione di 5 stagioni di squadre invece che contro la sola stagione più recente (2025/26) — poiché la Serie A ruota per promozione/retrocessione, una squadra neopromossa può comunque essere apparsa in una stagione passata, e il confronto sbagliato classificava **tutti** gli 84 giocatori come "vero trasferimento" invece di distinguerli (corretto: 50 trasferimenti reali, es. Stones/Mastantuono, contro 34 giocatori di neopromosse Frosinone/Venezia).
- Conseguenze: `scripts/run_m3_replacement_values.py` mostra il breakdown per livello e una lista dedicata dei 50 "trasferimento reale" con nota di cautela esplicita. 184 test passano. `docs/SOURCE_REGISTER.md` da aggiornare con la pista StatsBomb multi-lega per un blocco futuro dedicato.
- Approvato da: project owner

### ADR-2026-021 — Assegnazione ai pool G1-G4 reali, ranking provvisorio non ufficiale

- Data: 2026-08-11
- Stato: approved
- Scope: auction
- Decisione: `src/fantacalcio/auction/round_pools.py` assegna ogni giocatore al pool reale (G1: blocco portieri + top 60 difensori; G2: top 60 centrocampisti + top 40 attaccanti; G3/G4: tutti i rimanenti) usando il VAR come criterio di ranking. Le soglie numeriche (60/60/40) sono lette dai nomi dei pool già presenti in `config/auction_rules.v1.yaml`, non ridichiarate come letterali nel codice. Il risultato è marcato esplicitamente `list_state=provisional` (mai `official`) — distinto dalla lista vera dell'admin, che arriva via Google Form venerdì sera (`docs/archive/Recap_regole_asta_admin_20260811.txt`).
- Rationale: le soglie esatte di pareggio non hanno una regola di tie-break confermata (`docs/OPEN_QUESTIONS.md`); invece di inventarne una, tutti i giocatori a pari valore al cutoff vengono inclusi nel pool superiore (verificato: 61 difensori in G1 invece di esattamente 60, per un pareggio al 60° posto). Applicato al roster 2026/27 reale: 59 portieri, 61 difensori, 60 centrocampisti, 40 attaccanti nei pool G1/G2, 278 giocatori in G3/G4.
- Conseguenze: `scripts/run_m3_replacement_values.py` mostra la ripartizione per pool e il round di ogni giocatore nella classifica VAR. 191 test passano. Prossimo passo naturale: collegare questi pool al ledger d'asta vivo (M0) per un vero motore di raccomandazione round-per-round.
- Approvato da: project owner
