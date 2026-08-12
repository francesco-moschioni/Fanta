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

### ADR-2026-022 — Raccomandazione di offerta massima, collegata al ledger vivo

- Data: 2026-08-11
- Stato: approved
- Scope: auction
- Decisione: `src/fantacalcio/auction/bid_recommendation.py` calcola un'offerta massima raccomandata usando la formula standard delle aste fantasy ("dollar rule": riserva 1 credito per ogni slot di rosa ancora da riempire tranne quello corrente; il budget discrezionale residuo si distribuisce proporzionalmente al VAR positivo tra i giocatori ancora disponibili nel pool). Budget e slot rimanenti sono letti dal replay del ledger (`src/fantacalcio/domain.py`), mai da uno snapshot statico — la raccomandazione cambia in tempo reale con ciò che viene assegnato, sia dagli avversari sia dalla propria squadra.
- Rationale: dichiarata esplicitamente come prima versione semplificata, non il layer forecast-to-bid completo di `docs/DATA_AND_MODELING.md` (mancano domanda avversari modellata, inflazione di mercato osservata, fit di modulo/rischio — tutti richiedono dati che non abbiamo ancora, es. uno storico di aste reali). Bug reale trovato durante i test: gli ID giocatore nel ledger sono stringhe (`AssignmentItem.player_ids: tuple[str,...]`) mentre nel pool VAR sono interi — il confronto silenziosamente non escludeva mai i giocatori già assegnati. Corretto normalizzando a stringa prima del confronto.
- Conseguenze: `scripts/run_m3_bid_recommendation_demo.py` dimostra su dati VAR reali (pool difensori G1 2026/27) che la raccomandazione sale quando i rivali comprano le alternative migliori e scende quando la propria squadra consuma budget/slot — comportamento corretto per uno strumento da usare live in asta. 201 test passano.
- Approvato da: project owner

### ADR-2026-023 — Dixon-Coles collegato al Monte Carlo del voto: aggiustamento piccolo ma reale, adottato con k validato

- Data: 2026-08-11
- Stato: approved
- Scope: modeling
- Decisione: `src/fantacalcio/scoring/team_strength_adjustment.py` collega il modello di forza-squadra Dixon-Coles (validato, ADR-2026-011) — mai riusato dal voto/Monte Carlo prima di questo blocco — alle distribuzioni Monte Carlo (ADR-2026-018). Per ogni giocatore in ruolo offensivo (A/C, sul rating d'attacco) o difensivo (D, sul rating di difesa — P escluso, già coperto da `team_goals_conceded` via ADR-2026-017), calcola lo scarto tra il rating Dixon-Coles della squadra attuale e la media storica pesata per partite delle squadre in cui il giocatore ha giocato, e applica un aggiustamento additivo `k * scarto` ai campioni Monte Carlo. Convenzione di segno verificata esplicitamente in test (rating difesa più basso = difesa più forte, l'opposto dell'attacco).
- Rationale: coefficiente `k` scelto per validazione onesta via walk-forward (`scripts/run_team_strength_adjustment_validation.py`, stesso schema di `prior_games` in ADR-2026-012), non arbitrario: addestrato su 2021/22-2024/25, testato su 2025/26 mai visto, sweep di `k` ∈ {0, 0.1, 0.25, 0.5, 1.0}. Risultato: correlazione con `Fm` reale sale da 0,3472 (k=0, baseline) a 0,3522 (k=0,5) con un pattern monotono (0→0,25→0,5 in salita, poi discesa a k=1,0) coerente con un segnale reale e non rumore campionario — miglioramento piccolo (+0,005, ~1,4% relativo) ma non nullo, adottato con `k=0,5`. A differenza del tentativo sui difensori (ADR-2026-017), qui il test conferma l'ipotesi invece di falsificarla, ma la dimensione dell'effetto è riportata senza gonfiarla: non è un miglioramento drammatico.
- Conseguenze: `scripts/run_monte_carlo_fantavoto.py` (parte B, applicazione al roster reale 2026/27) ora fitta Dixon-Coles su tutte le 5 stagioni e applica l'aggiustamento `k=0,5` ai 498 giocatori; colonna `team_strength_adjustment` aggiunta al CSV di output. La parte A (validazione walk-forward contro `Fm` reale) resta senza aggiustamento per isolare il baseline storico. 209 test passano (8 nuovi per `team_strength_adjustment.py`). Report di validazione dedicato in `data/staged/fantacalcio_voti_manual/_team_strength_adjustment_validation.md` (locale).
- Approvato da: project owner

### ADR-2026-024 — FVM come prior secondario per giocatori a basso/zero storico: miglioramento più forte del blocco 1, adottato

- Data: 2026-08-11
- Stato: approved
- Scope: modeling
- Decisione: `src/fantacalcio/scoring/fvm_prior.py` sostituisce, solo per giocatori con meno di 10 partite di storico proprio, il fallback "pool di ruolo piatto" (media di tutti i centrocampisti mai visti, indifferentemente) di `monte_carlo.py` con un pool segmentato per quartile di FVM (`fvm_classic`, già ingerito dalle quotazioni, mai usato prima d'ora) — un giocatore a basso storico pesca da giocatori storicamente valutati in modo simile dal mercato Fantacalcio stesso, non dalla media indifferenziata di ruolo. I bordi dei quartili sono fittati sui soli dati di training (stesso schema walk-forward degli altri blocchi), non sui dati del giocatore target.
- Rationale: validato onestamente su un sotto-insieme mirato (`scripts/run_fvm_prior_validation.py`), non sull'intero roster — confrontare su tutti i giocatori avrebbe diluito l'effetto, dato che riguarda solo chi ha poco/nessuno storico. Addestrato su 2021/22-2024/25, testato sui 177 giocatori 2025/26 con meno di 10 partite pre-stagione e FVM noto: correlazione con `Fm` reale sale da 0,3326 (pool piatto) a 0,4048 (pool per FVM) — un salto di +0,072, molto più marcato del +0,005 del blocco 1 (ADR-2026-023) e non un artefatto di soglia arbitraria (lo scarto medio assoluto scende in parallelo, da 0,6395 a 0,5645).
- Conseguenze: `scripts/run_monte_carlo_fantavoto.py` (parte B) applica il prior FVM a 130 dei 498 giocatori del roster 2026/27 (quelli con <10 partite di storico e FVM noto); colonna `used_fvm_prior` aggiunta al CSV. Verifica di plausibilità: due trasferimenti a zero storico Serie A ma FVM alto (Ramos G., Adams A.) ora entrano nella top-15 per fantavoto simulato, invece di essere sepolti nella media di ruolo come accadeva prima — comportamento atteso, non più un artefatto della carenza dati. 216 test passano (7 nuovi per `fvm_prior.py`). Report di validazione dedicato in `data/staged/fantacalcio_voti_manual/_fvm_prior_validation.md` (locale).
- Approvato da: project owner

### ADR-2026-025 — Quote scommesse recuperate come cross-check di Dixon-Coles, non come input di previsione; bug di provenance nello snapshot corretto

- Data: 2026-08-11
- Stato: approved
- Scope: data | modeling
- Decisione: `src/fantacalcio/ingest/football_data_co_uk.py` recupera le colonne quote medie pre-partita (`AvgH`/`AvgD`/`AvgA`, media di mercato tra bookmaker, non un singolo bookmaker) precedentemente scartate da `_OPTIONAL_COLUMNS`. `src/fantacalcio/modeling/market_odds.py` le converte in probabilità implicite (de-vigged, overround rimosso) e in un rating di forza-squadra basato sui punti attesi dal mercato. **Non collegato alla pipeline di previsione 2026/27**: le quote per una stagione non ancora iniziata non esistono, quindi non c'è nulla da recuperare per la stagione target reale — usato solo come cross-check a parità di stagione (`scripts/run_market_odds_crosscheck.py`) contro le forze Dixon-Coles (ADR-2026-011, fittato solo su gol).
- Rationale: il mercato scommesse prezza informazione che Dixon-Coles (solo gol) non vede mai (infortuni, squalifiche, forma, voci) — un forte accordo tra i due è una validazione indipendente rassicurante, non un motivo per sostituire il modello a gol con uno a quote. Risultato: correlazione media 0,9278 su 5 stagioni (range 0,8974-0,9604) tra forza combinata Dixon-Coles (attacco - difesa) e rating di mercato — accordo forte, nessuna bandiera rossa sul modello esistente. Durante il recupero, trovato e corretto un bug reale di provenance in `src/fantacalcio/ingest/snapshot.py`: due snapshot dello stesso source scritti nella stessa cartella con timestamp al secondo (es. un audit M1 che scarica più stagioni in rapida sequenza) condividevano un unico `manifest.json` — la seconda scrittura sovrascriveva silenziosamente il manifest della prima, lasciando il contenuto checksummato corretto ma la provenance del primo file corrotta (verificato: il manifest di `serie_a_2122.csv` in una cartella condivisa puntava in realtà a `serie_a_2223.csv`). Corretto rendendo il nome del manifest specifico per file (`{filename}.manifest.json`).
- Conseguenze: `scripts/reingest_football_data_odds.py` ri-scarica le 5 stagioni con snapshot puliti (non ricostruiti da manifest corrotti) per avere provenance corretta oltre alle nuove colonne quote. 222 test passano (6 nuovi per `market_odds.py`). Report cross-check in `data/staged/fantacalcio_voti_manual/_market_odds_crosscheck.md` (locale). Nessuna modifica alla pipeline di applicazione roster 2026/27 — dichiarato esplicitamente fuori scope per mancanza di dati futuri, non per pigrizia.
- Approvato da: project owner

### ADR-2026-026 — Decadimento temporale nel bootstrap voto/partecipazione: testato onestamente, non adottato

- Data: 2026-08-11
- Stato: approved (tested-and-not-adopted)
- Scope: modeling
- Decisione: `src/fantacalcio/modeling/time_decay.py` (decadimento esponenziale per "giornata globale", coerente con `xi` di Dixon-Coles) collegato in due punti come funzionalità **opt-in**, non attivata di default: (1) `src/fantacalcio/scoring/monte_carlo.py`'s `simulate_fantavoto(..., use_recency_weights=True)` — ricampionamento pesato per recency invece che uniforme, con `HistoricalRow.recency_weight` (default 1.0, comportamento pre-blocco-4 invariato quando non richiesto esplicitamente); (2) `src/fantacalcio/modeling/participation.py`'s `decayed_participation_estimate()` — media multi-stagione pesata per recency, alternativa a `latest_known_participation` (singola stagione più recente).
- Rationale: validato via walk-forward su entrambi i fronti, **nessuno dei due supera onestamente il baseline esistente**. (1) Bootstrap: sweep di `half_life_matchdays` ∈ {19, 38, 76, 150, 300, 1000} mostrava inizialmente un apparente miglioramento (fino a +0,012 di correlazione con `Fm` reale), ma un controllo a parità di algoritmo di campionamento (`rng.choice` con pesi uniformi, cioè decadimento nullo ma stesso percorso di codice del campionamento pesato) ha isolato l'effetto reale: **+0,0168 di correlazione veniva dal solo cambio di algoritmo RNG** (`rng.choice` vs `rng.integers`, che consumano lo stream casuale in modo diverso anche a parità di distribuzione), e il decadimento vero e proprio, controllato per questo artefatto, dava **-0,0035** (leggermente peggio, non meglio). Errore metodologico evitato grazie al controllo esplicito, non assunto. (2) Partecipazione: sweep di `half_life_seasons` ∈ {0.5, 1.0, 2.0, nessuno} contro il baseline "ultima stagione nota" — il miglior caso (`half_life=0,5`, quasi equivalente a "usa quasi solo l'ultima stagione") dava +0,0017 di correlazione, sotto la soglia di rilevanza (0,005) usata in tutti i blocchi precedenti; la correlazione peggiorava monotonicamente allontanandosi da "solo ultima stagione" verso una media multi-stagione piatta (0,4369→0,4386→0,4323→0,4242→0,4116), segno che la partecipazione è abbastanza volatile stagione su stagione da rendere lo storico più vecchio prevalentemente rumore, non segnale aggiuntivo.
- Conseguenze: `scripts/run_time_decay_validation.py` e `scripts/run_participation_decay_validation.py` documentano entrambi gli esiti onestamente (inclusi i numeri "prima del controllo" per trasparenza sul quasi-errore). L'infrastruttura resta nel codice (funzionante, testata, opt-in) per un possibile riuso futuro se arriveranno più stagioni di dati, ma **non è collegata** a `scripts/run_monte_carlo_fantavoto.py` — nessuna modifica al roster 2026/27 applicato. 234 test passano (18 nuovi: 6 `time_decay.py`, 2 `monte_carlo.py`, 4 `participation.py`, più i test di `market_odds.py`/`fvm_prior.py` dei blocchi precedenti già conteggiati). Chiude la sequenza dei 4 blocchi di miglioramento aperta da `docs/CURRENT_TASK.md`.
- Approvato da: project owner

### ADR-2026-027 — M4 slice 1: prima schermata UI, ricerca/scheda giocatore su Streamlit + DuckDB

- Data: 2026-08-11
- Stato: approved
- Scope: architecture | ux
- Decisione: prima riga di codice UI del progetto. `src/fantacalcio/persistence/player_table.py` costruisce una tabella DuckDB locale (`data/local/fantacalcio.duckdb`, gitignored) da `_m3_replacement_values.csv` (già Monte Carlo + VAR + round pool + data quality tier), con tabella `meta` separata per provenance (path sorgente, sha256, timestamp di build) — mai mostrata senza dire quando/da cosa è stata costruita, per la regola `as_of`/provenienza di `CLAUDE.md`. `app/Home.py` (stato dati) e `app/pages/1_Giocatori.py` (ricerca/filtri/scheda) sono sola lettura: nessuna formula viene ricalcolata nella UI, solo lettura di ciò che il motore ha già prodotto. Stack conforme alla decisione già presa in ADR-2026-008 (DuckDB per letture columnar su snapshot immutabili; SQLite per il ledger vivo, riservato a una slice M4 successiva non ancora costruita).
- Rationale: `docs/ROADMAP.md`'s regola di priorità blocca solo il modeling avanzato (M5) prima dei gate; M0-M3 hanno gate soddisfatti (dominio, dati, baseline, motore VAR/max-bid), quindi M4 può iniziare. Scelta la prima fetta di `docs/UX_PRODUCT.md`'s priorità P0 ("ricerca/filtri, scheda compatta") perché è la più piccola unità che rende effettivamente usabile ciò che il motore già calcola, prima dell'asta reale. Campi della "scheda giocatore" non ancora disponibili in questa slice (offerta consigliata, massimo dinamico, valore marginale per la rosa, confronto a tre alternative — tutti richiedono il ledger vivo o il costruttore rosa, non ancora costruiti) sono mostrati esplicitamente come "non ancora disponibile" in un pannello dedicato, mai inventati o impliciti. Il badge `list_state=provisional` (ADR-2026-021) è sempre visibile: la UI non lascia mai intendere che il ranking del modello sia la lista ufficiale dell'admin.
- Conseguenze: verificato end-to-end in browser (non solo test unitari, per la regola di sessione sulle modifiche UI): ricerca per nome, filtro per ruolo/squadra/round pool/qualità dati, scheda dettaglio con driver oggettivi (aggiustamento Dixon-Coles, prior FVM, avviso esplicito per `no_history_transfer`) tutti confermati funzionanti su dati reali (es. "Ramos" → 1 risultato, zero storico, prior FVM applicato, avviso cautela mostrato correttamente). 245 test passano (11 nuovi per il data layer `player_table.py`; la UI Streamlit stessa non è unit-testata, non praticamente possibile — verificata in browser). Aggiunte dipendenze `duckdb`/`streamlit` a `pyproject.toml`, nuova cartella `data/local/` gitignored, `.claude/launch.json` per l'avvio locale (`streamlit run app/Home.py`).
- Approvato da: project owner

### ADR-2026-028 — M4 slice 2: ledger vivo (SQLite) + tabellone squadre + registrazione risultati; bug critico di budget cross-team corretto

- Data: 2026-08-11
- Stato: approved
- Scope: architecture | domain | ux
- Decisione: `src/fantacalcio/persistence/ledger_store.py` collega il ledger deterministico già esistente (`src/fantacalcio/domain.py`, M0) a una tabella SQLite append-only (ADR-2026-008), riusando `src/fantacalcio/ledger_io.py`'s serializzazione (nessuno schema duplicato). Nuova funzione `domain.effective_events()`: `replay()` non annulla retroattivamente gli effetti di un evento voidato/corretto (documentato e testato fin dal M0) — `effective_events()` è la query "stato attuale" che un'interfaccia deve mostrare, distinta dall'audit trail completo. `app/pages/2_Squadre.py` (tabellone 20 squadre, registrazione manuale risultati, undo via `VoidEvent`) e l'estensione di `app/pages/1_Giocatori.py` con un "tetto di riferimento" (massimo consigliato, ADR-2026-022) per la squadra selezionata. **Vincolo di dominio esplicito**: i round G1-G4 sono sealed bid risolti dall'admin, non un'asta live — questa slice registra risultati già decisi, non offerte in tempo reale; il tetto di riferimento è esplicitamente etichettato come tale, non come previsione di vittoria. Identificativi squadra generici (`team_01`..`team_NN`), nessun nome reale non ancora in repo.
- **Bug critico trovato e corretto durante il testing in browser**: `replay()` teneva un unico dizionario `remaining_by_round` condiviso fra TUTTE le squadre invece che per-squadra. Un'espressione di budget come `remaining_G1 + 100` (G2) usava quindi il residuo dell'ULTIMA squadra processata per quel round, non quello della squadra a cui il budget apparteneva — riproduco con test: squadra A spende 190/200 in G1 (residuo 10), squadra B spende 50/200 (residuo 150); il budget G2 di A veniva calcolato come 250 (10+100 sostituito da 150+100) invece di 110. Bug mai emerso prima perché `generate_demo_events()` (fixture M0) processa un round per intero prima del successivo, e nessun test esistente verificava il VALORE numerico del budget G2 (solo `spent <= available`, che un budget erroneamente più alto non viola). Avrebbe corrotto silenziosamente i budget reali di ogni squadra tranne l'ultima processata per round, nell'asta vera. Corretto: `remaining_by_round_per_team: dict[str, dict[str, int]]`, keyed per team_id prima che per round_id. Trovato anche un bug di threading minore (SQLite + `st.cache_resource` di Streamlit su thread diversi): corretto con `check_same_thread=False`, sicuro per un'app locale single-user senza scrittori concorrenti.
- Rationale: entrambi i bug sono stati scoperti testando onestamente il flusso reale in browser (non solo unit test), esattamente la disciplina richiesta da CLAUDE.md per le modifiche UI. Il bug di budget cross-team è correttezza critica per l'asta reale (M0's gate "budget conservato" era rispettato solo nel senso ristretto spent<=available, non nel senso che il numero fosse quello giusto) — corretto immediatamente invece di rimandato, coerente con "make the smallest coherent change" applicato alla causa radice, non a un workaround nella UI.
- Conseguenze: verificato end-to-end in browser reale (non solo unit test): registrazione G1 (Dimarco, team_01, 190 crediti) → G2 (Leao, team_01, 35 crediti, budget calcolato correttamente 110 = 10+100) → undo del G2 (Leao liberato, budget G2 tornato a "nessuno") → tetto di riferimento nella scheda Leao coerente con la formula (budget 110, slot 23, quota VAR 5,3%, massimo 5). 258 test passano (13 nuovi: 9 `ledger_store.py`, 3 `effective_events`/carryover in `test_domain_replay.py`, 1 threading implicito nei test esistenti). Dati di test locali rimossi da `data/local/ledger.sqlite3` prima di chiudere (non dati reali d'asta).
- Approvato da: project owner

### ADR-2026-029 — M4 slice 3: spiegabilità permanente dei numeri derivati (VAR, fantavoto, massimo consigliato)

- Data: 2026-08-11
- Stato: approved
- Scope: ux
- Decisione: su richiesta esplicita dell'utente ("vorrei che sia tutto ben spiegato... da dove viene il VAR di Lautaro Martinez?"), `docs/UX_PRODUCT.md` registra un principio **permanente**, non solo di questa slice: ogni numero derivato mostrato in UI deve avere un tooltip breve al passaggio del mouse e, dove sensato, un pannello espandibile con la traccia di calcolo reale — i valori veri del record selezionato, non testo statico generico. Implementato in `app/pages/1_Giocatori.py` (tooltip `help=` su tutte le metriche VAR/fantavoto/massimo consigliato/quotazione; due pannelli "Come si calcola questo numero?" con aritmetica reale per VAR+fantavoto atteso e per il massimo consigliato) e `app/pages/2_Squadre.py` (tooltip sulle colonne del tabellone via `column_config`). Nessun nuovo calcolo nella UI: solo scomposizione di numeri già prodotti dal motore (`replacement_level`, `player_games_in_pool`, i campi di `MaxBidRecommendation`), mai un LLM che genera la spiegazione.
- Rationale: verificato con l'esempio esatto dell'utente — la scheda di Martinez L. (Lautaro) mostra: fantavoto atteso 7,64 (167 partite proprie nello storico, peso storia propria 167/(167+60)=73,6%), VAR = 7,64 − 6,09 (livello di replacement, 100° attaccante in lega su 100 slot totali) = 1,55. Verificata anche la traccia del massimo consigliato con dati reali dal ledger (budget 110, riserva 22 slot, discrezionale 88, quota VAR 5,3%, massimo 5).
- **Due bug reali trovati e corretti durante la verifica in browser**: (1) `app/pages/1_Giocatori.py` catturava solo `BidRecommendationError` attorno a `recommend_max_bid`, non `ConfigError` — con un ledger senza eventi nel round precedente necessario (es. G2 prima di G1), la pagina andava in crash non gestito invece di mostrare un messaggio chiaro; corretto aggiungendo `except ConfigError`. (2) Stesso gap in `app/pages/2_Squadre.py`'s form di registrazione (`except DomainError` non copriva `ConfigError`); corretto con `except (DomainError, ConfigError)`.
- Conseguenze: nessun nuovo test automatico (slice puramente di visualizzazione, nessuna nuova logica di dominio) — 258 test esistenti continuano a passare; verificato in browser con dati reali per entrambi i bug fix e per entrambe le tracce di calcolo. Principio di spiegabilità documentato in `docs/UX_PRODUCT.md`, vincolante per le slice M4 future.
- Approvato da: project owner

### ADR-2026-030 — M4 slice 4: rettifica di budget generica nel ledger; regola bonus logo personalizzato (+3 crediti)

- Data: 2026-08-11
- Stato: approved
- Scope: domain | architecture | ux
- Decisione: nuovo campo versionato `league.custom_logo_bonus_credits: 3` in `config/auction_rules.v1.yaml` (mai un letterale nel codice), con provenienza esplicita in commento ("Postilla admin, 2026-08-11: come lo scorso anno..."). `src/fantacalcio/domain.py` aggiunge `BudgetAdjustmentEvent` (event_id, ts, round_id, team_id, amount, reason, author) — meccanismo **generico** per qualsiasi rettifica di budget con causale (non solo il bonus logo; `amount` può essere negativo per un'eventuale penalità futura, nessuna nota ora), gestito in `replay()` sommando `amount` al budget disponibile della squadra per quel round (creandolo se non esiste ancora, stessa logica di `AssignmentEvent`). Applicato di norma a G1: si propaga automaticamente a G2/G3/G4 tramite la catena `remaining_G1` già esistente, senza logica speciale altrove. `effective_events()` esteso per includerlo (voidabile come gli altri tipi). Serializzazione in `src/fantacalcio/ledger_io.py` (tipo `"budget_adjustment"`), persistenza in `src/fantacalcio/persistence/ledger_store.py` (nessuna modifica necessaria, già generica). UI in `app/pages/2_Squadre.py`: form "Assegna bonus" (solo squadre non ancora premiate), colonna "Bonus logo" nel tabellone con tooltip, undo esteso a questo tipo di evento.
- Rationale: la regola è reale e comunicata dall'utente direttamente (non dedotta), analoga a un anno precedente — non richiede un ADR di "non ancora confermato" come altre regole in `docs/OPEN_QUESTIONS.md`. Il meccanismo scelto (evento di ledger generico, non un flag ad-hoc) rispetta CLAUDE.md ("preserve an append-only, replayable ledger for auction events"): il bonus è un fatto amministrativo con la stessa natura di un'assegnazione, quindi vive nello stesso ledger append-only, con lo stesso undo, senza introdurre un secondo canale di stato.
- Conseguenze: verificato end-to-end in browser con dati reali: bonus assegnato a `team_01` (G1 disponibile 200→203), poi un acquisto reale da 203 crediti registrato senza overspend (conferma che il tetto usato è quello corretto, non quello base). 269 test passano (11 nuovi: 1 config, 7 `domain.py`/`effective_events`, 3 `ledger_io.py`). Dati di test locali rimossi da `data/local/ledger.sqlite3` prima di chiudere.
- Approvato da: project owner

### ADR-2026-031 — M4 slice 5: prima fetta del costruttore rosa — vista "La mia rosa" + lock con verifica di fattibilità

- Data: 2026-08-11
- Stato: approved
- Scope: domain | ux
- Decisione: `src/fantacalcio/persistence/locks_store.py` (tabella SQLite `locks`, stesso DB del ledger ma tabella separata — i lock sono intenzione pre-asta, mai eventi di dominio, non entrano mai in `domain.replay()`). `src/fantacalcio/auction/lock_feasibility.py`: verifica pura (nessun I/O) prima di persistere un lock — rifiuta un giocatore già nella rosa reale della squadra (superfluo), già assegnato a un'altra squadra nel ledger reale (impossibile, spiegato con l'`team_id` reale), già bloccato, o che farebbe superare la capacità di ruolo (rosa reale + lock esistenti), spiegando sempre quale vincolo e cosa rimuovere per fare spazio — CLAUDE.md: "Locked players remain locked. If infeasible, explain the conflicting constraint and minimum relaxation." Nuova pagina `app/pages/3_Rosa.py`: rosa reale (da replay del ledger) per ruolo con slot pieni/vuoti e budget per round, sezione lock separata e sempre etichettata come ipotetica con costo stimato (somma quotazioni, non un'offerta), lock/unlock. Pulsante blocca/sblocca aggiunto anche alla scheda giocatore in `app/pages/1_Giocatori.py`.
- Rationale: il formato file admin resta sconosciuto (arriva venerdì sera, `docs/OPEN_QUESTIONS.md`), quindi l'import automatico resta bloccato; il costruttore rosa completo (drag-and-drop, ottimizzatore "rosa ideale"/"undici ideale", confronto moduli) richiede un motore di ottimizzazione non ancora costruito ed è troppo grande per una singola unità — questa slice ne costruisce il primo strato verificabile senza inventare un ottimizzatore: solo vista + lock con verifica di fattibilità onesta, mai un lock infeasible applicato silenziosamente.
- Conseguenze: verificato end-to-end in browser: Lautaro Martinez bloccato come obiettivo di `team_01` dalla scheda giocatore, comparso correttamente nella pagina Rosa (costo stimato 35 crediti, dalla quotazione reale), sbloccato con successo. 284 test passano (23 nuovi: 7 `locks_store.py`, 8 `lock_feasibility.py`, più le integrazioni). Nessun dato di test residuo nel ledger/locks locali.
- Approvato da: project owner

### ADR-2026-032 — Colma il gap: registrazione blocco portieri in Squadre (bug bloccante trovato in autonomia)

- Data: 2026-08-11
- Stato: approved
- Scope: ux
- Decisione: `app/pages/2_Squadre.py` aggiunge un modulo dedicato "Registra blocco portieri" (3 campi nome, una squadra, un prezzo unico per il blocco) che costruisce un `AssignmentEvent` con `role=GK`, `pool_id="goalkeeper_blocks"`, `item.player_ids` con i 3 codici giocatore risolti per nome (filtrati per ruolo `P`). Se i tre portieri non sono dello stesso club (`ruleset.roster.goalkeeper_same_club`), un avviso esplicito lo segnala — non bloccante, perché il vincolo "stesso club" non è ancora imposto a livello di dominio (`domain.py`'s `gk_block_identity` resta un placeholder, M1), quindi la UI non può far finta di applicarlo con certezza, solo avvisare onestamente.
- Rationale: trovato durante un'esplorazione autonoma di cosa restava da fare senza dati admin ("fai tutto quello che puoi fare senza input admin"). Il modulo di registrazione esistente (ADR-2026-028) rifiutava esplicitamente ogni tentativo di registrare un portiere ("non ancora gestito da questo form") — ma ogni squadra DEVE comprare un blocco portieri in G1 (regola di rosa obbligatoria), quindi senza questo il ledger non poteva rappresentare un'asta G1 reale e completa per nessuna squadra. Bug bloccante per l'uso reale dello strumento, non solo una funzionalità mancante minore — corretto immediatamente.
- Conseguenze: verificato end-to-end in browser con portieri reali (Svilar/Meret/Di Gregorio, club diversi): evento registrato correttamente (3 player_ids, un prezzo, budget G1 aggiornato), confermato via query diretta del ledger. 284 test esistenti continuano a passare (nessuna nuova logica di dominio, solo UI — replay() già gestiva correttamente i blocchi portieri dal M0). Dati di test locali rimossi prima di chiudere.
- Approvato da: project owner

### ADR-2026-033 — M4 slice 6: "rosa ideale" — ottimizzatore esatto di completamento rosa entro budget

- Data: 2026-08-11
- Stato: approved
- Scope: domain | ux
- Decisione: `src/fantacalcio/auction/roster_optimizer.py` risolve un knapsack 0/1 multi-vincolo (budget totale + capacità per ruolo) tramite programmazione dinamica esatta, non un'euristica greedy — massimizza il VAR totale della combinazione scelta tra i candidati non ancora presi (esclusi rosa reale e lock). Per trattabilità computazionale, il pool di candidati è limitato ai migliori `TOP_N_PER_ROLE=25` per VAR per ruolo prima di risolvere — approssimazione esplicita e dichiarata (mai un candidato scartato silenziosamente: il risultato riporta se il pool è stato limitato). L'obiettivo è "massimizza il VAR totale", non "riempi sempre ogni slot a ogni costo": uno slot resta volutamente vuoto se nessun candidato affidabile entro budget ha VAR sufficiente a giustificarlo — comportamento dichiarato esplicitamente nel modulo e testato. Integrato in `app/pages/3_Rosa.py`: nuova sezione "Rosa ideale" per round selezionato, budget = residuo reale dal ledger meno il costo stimato dei lock già bloccati per i ruoli di quel round, slot = target di ruolo meno rosa reale meno lock.
- Rationale: il formato file admin resta sconosciuto (venerdì sera), quindi resta la priorità più alta e fattibile del costruttore rosa (`docs/UX_PRODUCT.md`) costruibile senza quei dati. Scelta la programmazione dinamica esatta invece di un'euristica perché "rosa ideale" è esplicitamente uno strumento di pianificazione su cui l'utente farà affidamento per decisioni di credito reali — un'euristica greedy non garantita ottima sarebbe stata più semplice ma meno onesta rispetto al nome della funzionalità. Verificata la trattabilità computazionale con dati realistici (fino a 3 ruoli, ~180 candidati, budget~200): sotto 1,5 secondi.
- Conseguenze: verificato end-to-end in browser: calcolo rosa ideale per G1 (8 difensori, budget 200) ha prodotto una combinazione reale entro budget (costo 107, VAR totale 4.18) usando dati veri della tabella giocatori. 295 test passano (11 nuovi per `roster_optimizer.py`). Fuori scope dichiarato: "undici ideale" (richiede probabilità di voto/rischio SV, non ancora esposta nella tabella giocatori — dato mancante, non deciso ora), confronto tra moduli, profili prudente/bilanciato/aggressivo.
- Approvato da: project owner

### ADR-2026-034 — Probabilità di voto (rischio SV) collegata alla scheda giocatore

- Data: 2026-08-11
- Stato: approved
- Scope: data | ux
- Decisione: `scripts/run_m3_replacement_values.py` collega `src/fantacalcio/modeling/participation.py`'s `latest_known_participation()` (già costruito e validato, mai prima collegato all'output finale) alla tabella `_m3_replacement_values.csv`: nuove colonne `participation_rate`, `participation_season`, `participation_seasons_of_history`. Aggiunte a `REQUIRED_COLUMNS` in `src/fantacalcio/persistence/player_table.py`. `app/pages/1_Giocatori.py` mostra il tasso come "probabilità di voto (rischio SV), stima" con provenienza esplicita (stagione di riferimento, numero di stagioni di storico), o un messaggio onesto di non disponibilità per i giocatori a zero storico — mai un numero inventato. Rimossa dalla lista "non ancora disponibile in questa vista".
- Rationale: identificato come dato mancante ma già calcolabile durante l'esplorazione autonoma di cosa restava da fare senza input admin — il modello di partecipazione esisteva dal M2 ma non era mai stato collegato all'output finale usato dalla UI, un gap di collegamento (come Dixon-Coles→Monte Carlo nel blocco 1 della sequenza precedente), non un dato mancante per davvero.
- Conseguenze: 498 giocatori nella tabella, 84 senza tasso (zero storico, coerente con `data_quality_tier`). Verificato in browser con dati reali (Lautaro Martinez: 79%, stagione 2025/26, 5 stagioni di storico). 295 test esistenti continuano a passare (nessuna nuova logica di dominio, solo collegamento dati già validati). "Undici ideale" resta comunque bloccato: la probabilità di voto da sola non basta a un ottimizzatore di formazione titolare (servirebbe anche un modello di minutaggio/rischio per giornata specifica, non ancora costruito).
- Approvato da: project owner

### ADR-2026-035 — M4 slice 7: passata di chiarezza UI + rischi di rosa (concentrazione + da evitare)

- Data: 2026-08-11
- Stato: approved
- Scope: ux | domain
- Decisione: due parti, richieste insieme dall'utente dopo aver provato l'app in prima persona ("così non si capisce niente"). **(1) Chiarezza**: `src/fantacalcio/persistence/team_labels_store.py` (tabella SQLite `team_labels`, solo cosmetica — il ledger continua a usare `team_id` come unica chiave di dominio, mai un'etichetta come chiave, CLAUDE.md's entity-resolution rule) permette all'utente di dare un nome scelto da sé alla propria squadra, mostrato ovunque al posto dell'identificativo grezzo (`"I Bocconiani (team_01)"` invece di solo `team_01`). Ogni pagina (`app/Home.py`, `app/pages/*.py`) ora apre con una spiegazione in italiano semplice di cosa fa e come si usa — prima l'unico testo visibile in cima era il titolo. Valori tecnici (turno G1-G4, tier di qualità dati, ruolo) tradotti con le stesse mappe ovunque compaiono, non solo nella scheda giocatore. Home riscritta come guida reale (le tre aree, un flusso d'uso consigliato) invece che solo stato dei dati. **(2) Rischi di rosa**: `src/fantacalcio/persistence/avoid_list_store.py` (simmetrico a `locks_store.py`, tabella separata `avoid_list` — un giocatore da evitare non è mai anche un obiettivo, ambiguità strutturalmente impossibile) e `src/fantacalcio/auction/roster_risk.py` (conteggio puro, nessuna nuova statistica: quanti giocatori della rosa reale + lock vengono dallo stesso club reale, soglia di avviso dichiarata `DEFAULT_WARNING_THRESHOLD=3`). Integrati in `app/pages/1_Giocatori.py` (avviso + pulsante evita/rimuovi) e `app/pages/3_Rosa.py` (sezioni dedicate).
- Rationale: la chiarezza ha priorità sulle nuove funzionalità costruite sopra una UI che l'utente stesso ha definito incomprensibile — corretto prima di procedere oltre, anche se la richiesta di "rischi di rosa" era già stata concordata in precedenza. Verificando in browser con la sessione reale dell'utente (non un ledger di test, il loro), trovato un vero bug: colonne di tabella con tipo misto intero/stringa (`budget.remaining if budget else "—"`) causavano un errore di conversione Arrow silenziosamente recuperato da Streamlit ma con traceback nei log — corretto forzando `str()` su ogni colonna di questo tipo in `app/pages/2_Squadre.py` e `app/pages/3_Rosa.py`. Rimosso anche il rumore nei log da `use_container_width` (deprecato, sostituito con `width="stretch"`).
- Conseguenze: verificato in browser, incluso sulla sessione reale dell'utente (nome squadra "I Bocconiani" impostato e propagato correttamente su tutte le pagine; azione di test rimossa subito dopo la verifica per non alterare la loro pianificazione reale). 314 test totali passano (19 nuovi: 7 `team_labels_store.py`, 7 `avoid_list_store.py`, 5 `roster_risk.py`). Nessun bug residuo nei log dopo il fix.
- Approvato da: project owner

### ADR-2026-036 — Simulazione asta completa (4 turni, 20 squadre): tutti gli invarianti reggono; scoperta carenza reale di portieri

- Data: 2026-08-11
- Stato: approved
- Scope: domain | data
- Decisione: `scripts/run_auction_simulation.py` gioca un'asta completa e realistica (4 turni, 20 squadre, dati reali 2026/27) usando il codice reale del prodotto — non una simulazione separata: `domain.replay()`, `ledger_store`, `recommend_max_bid()`, `check_lock_feasibility()`, `optimize_roster_completion()` — su un database SQLite isolato e temporaneo (`data/local/_simulation_ledger.sqlite3`, cancellato a ogni esecuzione), **mai** il ledger reale dell'utente. Prezzo di ogni acquisto simulato calcolato dalla stessa funzione `recommend_max_bid()` usata dalla UI, non da una formula separata — la simulazione fa così anche da stress-test della formula su molti più scenari di quanti ne coprisse la demo precedente (`scripts/run_m3_bid_recommendation_demo.py`).
- **Scoperta reale**: solo **59 portieri** disponibili nel listone 2026/27 contro **60 slot richiesti** (3 per squadra × 20 squadre) — carenza di lega, anche minima, mai notata prima. Due club (Cagliari, Lecce) hanno solo 2 portieri reali nel listone: per una squadra che punta al loro blocco portieri, un blocco dello stesso club è **strutturalmente impossibile**, non solo sfortuna d'asta. La simulazione mostra l'effetto concreto: 19/20 squadre completano un blocco (una con club misti, nessun club con 3 liberi rimasti), l'ultima squadra non riesce a completarlo affatto (solo 2 portieri rimasti nel pool). Carenza analoga a quella già nota per gli attaccanti (ADR-2026-019: 88 disponibili contro 100 richiesti), confermata di nuovo esattamente dalla simulazione (40 in G2 + 48 in G3/G4 = 88).
- Rationale: su richiesta esplicita dell'utente di "arrivare a un prodotto finale da provare" e "simulare le fasi dell'asta" — verificare l'intero sistema con un'esecuzione realistica end-to-end, non solo con unit test isolati, è esattamente come sono stati trovati i bug precedenti più seri (ADR-2026-028 sul budget cross-team, ADR-2026-032 sul blocco portieri). Due bug trovati durante la costruzione dello script di simulazione stesso (non nel prodotto): un file SQLite temporaneo non veniva chiuso prima di essere cancellato (Windows blocca la cancellazione di file aperti) e un test di rifiuto-lock cercava per errore il primo giocatore già assegnato senza escludere la squadra che stava testando, finendo per testare il ramo sbagliato ("già nella tua rosa" invece di "assegnato a un'altra squadra") — entrambi corretti, nessuno dei due era un bug del prodotto.
- Conseguenze: **tutti gli invarianti verificati rispettati** su un'esecuzione realistica completa: budget mai negativo né sforato per nessuna delle 20 squadre in nessun turno, nessun ruolo mai oltre il tetto, nessun giocatore assegnato due volte, replay deterministico (due repliche dello stesso ledger danno risultati identici), rifiuto di lock su giocatori già assegnati con la squadra corretta nel motivo, ottimizzatore mai oltre budget. Report completo in `data/staged/fantacalcio_voti_manual/_auction_simulation_report.md` (locale). Script riutilizzabile prima dell'asta reale per una verifica finale; non incluso in `pytest -q` (33 secondi, quasi triplicherebbe il tempo della suite) — resta un diagnostico a esecuzione manuale, come gli altri script `scripts/run_*`.
- Approvato da: project owner

### ADR-2026-037 — Avvisi di mercato in Home: carenza per ruolo e club senza blocco portieri

- Data: 2026-08-11
- Stato: approved
- Scope: domain | ux
- Decisione: `src/fantacalcio/auction/market_supply.py` (conteggio puro, nessuna nuova statistica) confronta quanti giocatori esistono davvero nel listone 2026/27 per ruolo con quanti slot servirebbero in tutta la lega (letti da config, mai un letterale) — e quali club reali hanno meno portieri del necessario per un blocco dello stesso club. Nuova sezione "Avvisi di mercato" in `app/Home.py`, visibile subito, con le carenze reali trovate dalla simulazione (ADR-2026-036): portieri (-1), attaccanti (-12), e i due club (Cagliari, Lecce) senza abbastanza portieri per un blocco proprio.
- Rationale: dato reale e azionabile per la pianificazione pre-asta, scoperto durante l'esplorazione autonoma richiesta dall'utente ("integra anche nuovi dati") — non serviva un nuovo file esterno, solo collegare un conteggio già implicito nei dati già presenti (config + listone), esattamente come i blocchi precedenti (Dixon-Coles→Monte Carlo, partecipazione→scheda giocatore) erano gap di collegamento, non dati mancanti.
- **Bug reale trovato e corretto durante la verifica in browser**: la colonna "Carenza" della nuova tabella mischiava interi e il segnaposto `"—"` (stesso schema di tipo misto già corretto altrove in ADR-2026-035) — stesso errore di conversione Arrow nei log, stesso fix (`str()` esplicito). Verificato con un controllo su tutte le pagine (`grep 'else "—"'`) che non restassero altre istanze non corrette.
- Conseguenze: verificato in browser, dati reali confermano esattamente i numeri della simulazione. 320 test totali passano (6 nuovi per `market_supply.py`). Ledger reale dell'utente verificato intatto (1 evento, invariato) durante tutta questa sessione autonoma.
- Approvato da: project owner

### ADR-2026-038 — Audit adversariale (data-quality + statistico): tre gap reali corretti, nessun bug bloccante

- Data: 2026-08-12
- Stato: approved
- Scope: domain | ux
- Decisione: due subagent di audit dedicati (`data-quality-reviewer`, `statistical-reviewer` — CLAUDE.md's delegation policy, uso bounded/read-only) hanno esaminato l'intera pipeline (ingestion → entity resolution → modeling → persistenza → UI) e il nucleo statistico (target, leakage, calibrazione, Monte Carlo, inferenza previsione→offerta) in modo indipendente e avversariale, senza vedere il lavoro dell'altro. Data-quality: nessun blocco, un solo gap cosmetico (freschezza dati parziale in Home, vedi sotto). Statistico: nessun bug di leakage o join (walk-forward confermato corretto ovunque), due gap reali corretti in questa ADR, tre miglioramenti minori non bloccanti loggati ma non implementati (fallback discrezionale piatto per VAR molto negativo in `bid_recommendation.py:126`, clamp mancante sull'aggiustamento forza-squadra, FVM-prior e Dixon-Coles mai validati congiuntamente sul sottogruppo che li usa entrambi).
  1. **Freschezza dati incompleta (data-quality)**: `app/Home.py` mostrava solo `built_at` (quando la tabella DuckDB è stata (ri)costruita), non quando il calcolo sottostante (Monte Carlo + replacement values) è stato effettivamente generato — i due possono divergere se si ricostruisce la tabella da un CSV invariato. `src/fantacalcio/persistence/player_table.py`: nuovo campo `source_generated_at` (mtime del CSV sorgente) accanto a `built_at`, entrambi mostrati distintamente in Home.
  2. **P10-P90 dichiarato come certezza mai verificata (statistico, finding B1)**: il tooltip diceva "80% dei possibili esiti cade in questo range" come un fatto, ma nessun backtest di copertura empirica esisteva in tutto il repository (grep su "coverage"/"calibrat": zero risultati) — un rischio diretto di falsa precisione (CLAUDE.md: "show uncertainty... not false precision"). `scripts/run_monte_carlo_fantavoto.py`'s `part_a_validation` ora calcola la copertura empirica reale riusando lo stesso split walk-forward già validato per la media (ADR-2026-018): quale frazione della fantamedia reale 2025/26 cade nell'intervallo [P10,P90] simulato. Risultato reale misurato: **95.2%** su 562 giocatori (obiettivo nominale 80%) — la banda è più larga del necessario quando confrontata con un aggregato di stagione, non più stretta: nessuna falsa precisione trovata, ma prima d'ora non era mai stato verificato, solo assunto. Scritto in `data/staged/fantacalcio_voti_manual/_monte_carlo_validation_meta.json` (nuovo, letto da `scoring/monte_carlo.py`'s `load_calibration_meta()`); `app/pages/1_Giocatori.py` mostra ora il numero reale misurato invece dell'80% nominale, con fallback esplicito se il file non esiste ancora.
  3. **Livello di replacement degenere non segnalato per riga (statistico, finding B2)**: `replacement.py` già gestiva correttamente la carenza di offerta per ruolo (portieri, attaccanti — ADR-2026-036/037) a livello aggregato, ma quando succede il livello di replacement diventa silenziosamente "il peggiore disponibile" invece di "il miglior escluso", il che spinge meccanicamente il VAR di ogni giocatore di quel ruolo verso l'alto — un cambio reale nel significato del numero, non solo rumore in più, e la traccia "come si calcola" per-giocatore non lo segnalava mai. Nuovo campo booleano `degenerate_replacement` in `add_value_above_replacement()` (`replacement.py`), propagato in `REQUIRED_COLUMNS` (`player_table.py`) e mostrato come avviso esplicito nella traccia VAR di `app/pages/1_Giocatori.py` per ogni giocatore di un ruolo in carenza.
  - Corretto anche un difetto minore di formulazione (non bloccante, dal report statistico): la didascalia del limite del pool candidati nell'ottimizzatore (`app/pages/3_Rosa.py`) riportava il totale complessivo come se fosse il limite per-ruolo — ora usa `TOP_N_PER_ROLE` esplicitamente e mostra entrambi i numeri.
- Rationale: gli audit erano stati richiesti dalla direttiva "fai tutto quello che puoi fare, tutto tutto. usa agenti e subagenti come nella struttura del progetto" — la prima esecuzione con `isolation: "worktree"` è fallita in modo ambientale (non recuperabile via `SendMessage`, verosimilmente Windows + percorso OneDrive con spazi che interagisce male con i worktree git), rieseguita senza isolamento con successo. Ogni finding è stato verificato con citazione di file/riga prima di essere accettato, non applicato ciecamente; i tre miglioramenti non bloccanti sono stati deliberatamente non implementati (rischio/beneficio non abbastanza chiaro senza una decisione esplicita sulla robustezza ai casi limite, fuori scope per una correzione guidata da audit).
- Conseguenze: pipeline completa rieseguita (`run_monte_carlo_fantavoto.py` → `run_m3_replacement_values.py` → `build_player_table.py`) per generare i nuovi campi/metadati sui dati reali 2026/27; verificato in browser che entrambi i fix compaiano correttamente (avviso di carenza su un attaccante reale, tooltip P10-P90 con il numero misurato reale), nessun errore in console o nei log del server. 321 test totali passano (1 nuovo netto: test di `degenerate_replacement`, assert aggiuntivo su `source_generated_at`). Ledger reale dell'utente verificato intatto durante il riavvio del server necessario per sbloccare il file DuckDB.
- Approvato da: project owner

### ADR-2026-039 — Confronto moduli: forza rosa per modulo, non un nuovo target d'asta

- Data: 2026-08-12
- Stato: approved
- Scope: domain | ux
- Decisione: prima di implementare, verificato nei numeri reali (`config/auction_rules.v1.yaml`) che la rosa fissa (3 portieri, 8 difensori, 8 centrocampisti, 5 attaccanti) copre già contemporaneamente il fabbisogno di titolari di **tutti** gli 8 moduli configurati (il più esoso per ruolo, 5D/5C/3A a seconda del modulo, è sempre sotto il conteggio fisso posseduto) — quindi estendere `roster_optimizer.py` con un target di slot diverso per modulo non avrebbe cambiato alcun risultato: i target sarebbero sempre stati dominati dai conteggi fissi già esistenti. Segnalato esplicitamente all'utente prima di procedere (CLAUDE.md: "never silently resolve a conflict"), che ha scelto lo scope corretto una volta chiarito.
  Implementato invece `src/fantacalcio/auction/formation_strength.py` (conteggio puro, nessuna nuova formula sui numeri del motore): per ciascuno degli 8 moduli, sceglie i migliori giocatori posseduti (rosa reale + obiettivi bloccati) per ruolo fino al fabbisogno di quel modulo e ne somma il VAR — mostra con quale modulo la rosa **reale** dell'utente rende di più, in **media di stagione**. Sezione "Confronto moduli" in `app/pages/3_Rosa.py`, tra "Concentrazione di squadra" e "Rosa ideale".
- Rationale: dichiarato esplicitamente e ripetutamente nella UI che questa è un'approssimazione onesta di "undici ideale" (docs/UX_PRODUCT.md), non un sostituto: usa solo il VAR medio di stagione, non dati di rischio per giornata (probabile formazione, infortuni, avversario) che non esistono ancora nella pipeline (docs/OPEN_QUESTIONS.md) — "undici ideale" vero resta bloccato in attesa di una fonte dati esplicita per quello. Un modulo non completamente copribile con la rosa attuale non viene mai nascosto: `fully_coverable=False` e `missing_by_role` sempre esposti, mai un numero silenziosamente ottimistico.
- Conseguenze: 328 test totali passano (7 nuovi per `formation_strength.py`). Verificato in browser: la sezione mostra correttamente lo stato "non ancora copribile" con la rosa reale attuale dell'utente (solo obiettivi bloccati, nessun acquisto reale ancora), nessun errore in console/log. Nessuna colonna a tipo misto (pattern di bug già visto tre volte in questa sessione, controllato esplicitamente questa volta prima di considerare fatto).
- Approvato da: project owner

### ADR-2026-040 — Rifiutata l'idea di un LLM che cerca dati in rete; niente scraping via intermediario

- Data: 2026-08-12
- Stato: approved
- Scope: process | domain
- Decisione: l'utente ha chiesto se un LLM economico non-Anthropic potesse "cercare informazioni su internet" (probabili formazioni, infortuni) per aggirare il divieto di scraping. Rifiutato esplicitamente: un LLM che recupera contenuto da un sito che vieta l'accesso automatizzato nei suoi ToS sta facendo esattamente lo scraping vietato da CLAUDE.md, indipendentemente dal modello usato come intermediario — non è una scappatoia, è la stessa violazione con un passaggio in più. In aggiunta, un LLM con web search può "allucinare" con più facilità proprio su notizie locali molto recenti (probabili formazioni cambiano ora per ora), e un output senza provenienza/`as_of` verificabile non passerebbe comunque il requisito di CLAUDE.md su incertezza/provenienza — un dato di input sbagliato spacciato per pulito è più pericoloso di un calcolo LLM esplicitamente segnalato come tale.
- Rationale: mantenere la distinzione netta già presente in CLAUDE.md ("un LLM può spiegare risultati ma non calcolarli") anche per l'ingestion dei dati grezzi, non solo per il calcolo — una fonte di input scelta autonomamente da un LLM è altrettanto pericolosa di un calcolo LLM, solo mascherata meglio.
- Conseguenze: nessuna modifica al codice. Proposta alternativa legittima e verificata al suo posto: API-Football (già parzialmente adottato, ADR-2026-010) a pagamento ($19/mese piano Pro, verificato 2026-08-12 via ricerca web sui prezzi ufficiali) per le probabili formazioni Serie A stagione corrente; per notizie/infortuni, import manuale di testo che l'utente stesso incolla da una fonte a cui è già abbonato, con l'LLM che fa solo parsing in struttura, mai ricerca autonoma.
- Approvato da: project owner

### ADR-2026-041 — Audit storico estero (API-Football): scoperta un vincolo reale, nessuna integrazione fatta

- Data: 2026-08-12
- Stato: approved
- Scope: data
- Decisione: quantificato il problema reale — 84 giocatori (`no_history_transfer`/`no_history_new_team` in `_m3_replacement_values.csv`) hanno zero storico perché arrivano da campionati non coperti dalla pipeline (solo Serie A oggi). Prima di proporre un'integrazione, verificato Understat (bloccato: `robots.txt` vieta ogni crawler, corretto il suo stato in `docs/SOURCE_REGISTER.md` da "ammesso con cautela" a "escluso") e testato API-Football con una chiamata reale (`scripts/run_foreign_history_audit.py`, nuova funzione `search_player()` in `src/fantacalcio/ingest/api_football.py`). **Scoperta reale**: l'endpoint `players` rifiuta una ricerca globale per nome — richiede già un `team`/`league` noto, e il nostro listone non ha un campo "club di provenienza" per risolverlo automaticamente. "Cercare ovunque" non è quindi possibile come integrazione in blocco; richiederebbe un hint per-giocatore fornito dall'utente (club precedente, da una fonte che l'utente già conosce/si fida), poi una chiamata mirata — `search_player()` supporta già questo caso via il parametro `team_id`, aggiunto proprio per questo. Nessuna chiamata sprecata: fermato il campione dopo la prima chiamata reale, dato che l'errore è un vincolo API deterministico, non specifico del giocatore cercato.
- Rationale: CLAUDE.md vieta join per solo nome — anche solo "cercare un giocatore per nome" su una fonte esterna senza uno scope già noto (club/lega) rischia di restituire l'omonimo sbagliato; il vincolo API stesso, per una ragione diversa (limite del piano), impone comunque la stessa disciplina che avremmo dovuto imporci noi.
- Conseguenze: 330 test totali passano (2 nuovi per `search_player`). Nessun dato scritto nella pipeline di dominio — puro discovery, come richiesto esplicitamente dall'utente ("audit gratuito prima"). Report completo in `data/staged/fantacalcio_voti_manual/_foreign_history_audit.md` (locale, gitignored). Prossimo passo dipende dall'utente: se vuole procedere, serve fornire i club di provenienza reali per i giocatori a quotazione più alta (Ramos G. 27, Mastantuono 12) — non inventabili da qui.
- Approvato da: project owner

### ADR-2026-042 — Hint di provenienza via subagent Haiku + web search: 2/5 giocatori con storico reale trovato

- Data: 2026-08-12
- Stato: approved
- Scope: data | process
- Decisione: su richiesta esplicita dell'utente ("lancia degli agenti Haiku per cercare"), lanciati 5 subagent Haiku indipendenti (uno per giocatore, `general-purpose`, `model: haiku`) con istruzione esplicita di usare solo ricerca web pubblica (notizie di mercato, comunicati ufficiali) e **non tentare di scrapare siti che bloccano l'accesso automatizzato** — stesso principio già applicato a mano per Understat (ADR-2026-041). Ogni agente ha restituito nome completo, club/lega di provenienza, livello di confidenza e fonti citate (comunicati ufficiali club, ESPN, beIN Sports, ecc.) — tutti con confidenza "alta" e fonti multiple concordanti. Con questi hint, risolto il vincolo scoperto in ADR-2026-041 (l'endpoint `players` di API-Football richiede un `team`/`league` noto): aggiunta `search_team()` (simmetrica a `search_player()`) per risolvere il `team_id` dal nome del club, poi interrogato `search_player(..., team_id=...)` per ciascuno dei 5 giocatori sulla stagione 2023 (unica disponibile sul piano gratuito).
  **Risultato reale**: 2 giocatori su 5 trovati con statistiche vere — Gonçalo Ramos (PSG, 2022/23: 11 gol, 1 assist, 29 presenze) e John Stones (Manchester City, 2022/23: 1 gol, 27 presenze) — invece del placeholder piatto "role-average" che hanno oggi in `data_quality_tier=no_history_transfer`. Gli altri 3 (Mastantuono, Kevin Carlos, Alajbegovic) non trovati nella stagione 2023 al club indicato dall'agente: i loro trasferimenti/prestiti più rilevanti sono più recenti (2024-2026) della finestra gratuita disponibile (2022-2024) o coinvolgono un club diverso da quello formalmente "di provenienza" (es. Alajbegovic: venduto e riacquistato dal Leverkusen, minutaggio vero al prestito Salisburgo 2025/26).
  **Bug reale trovato e corretto**: `_call()` in `src/fantacalcio/ingest/api_football.py` costruiva la query string concatenando i parametri senza URL-encoding — un nome con spazio ("Paris Saint Germain") produceva un URL non valido (`InvalidURL: control characters`). Sarebbe scattato anche su `search_player` con qualunque nome multi-parola (es. "Kevin Carlos"), bug preesistente mai emerso perché finora l'unico caller reale (`fetch_fixtures`) passava solo ID numerici. Corretto con `urllib.parse.urlencode`, test di regressione aggiunto.
- Rationale: la ricerca web generica per notizie di mercato pubbliche (riportate da decine di fonti indipendenti) è categoricamente diversa dallo scraping di un sito specifico che lo vieta nei suoi ToS/robots.txt (Fantacalcio.it, Understat) — è esattamente cosa farebbe l'utente stesso cercando su un motore di ricerca, solo delegato ad agenti economici per bounded lookup, coerente con la policy di delegazione di CLAUDE.md. L'output resta comunque puro discovery, mai scritto automaticamente nella pipeline di dominio: ogni hint andrebbe riverificato da un umano prima di un uso reale, dichiarato esplicitamente nel codice e nel report.
- Conseguenze: 332 test totali passano (2 nuovi: `search_team`, regression sull'URL-encoding). Nessuna scrittura nella pipeline di dominio. Budget API-Football usato: 10/100 richieste giornaliere. Report aggiornato in `data/staged/fantacalcio_voti_manual/_foreign_history_audit.md`. Prossimo passo dipende dall'utente: se vuole procedere a una vera integrazione (join per `player_code` con verifica manuale, mai per solo nome), serve decidere caso per caso quale stagione/club usare per i 3 giocatori non ancora trovati, e se vale la pena del piano a pagamento per coprire le stagioni più recenti dove probabilmente si trovano.
- Approvato da: project owner
