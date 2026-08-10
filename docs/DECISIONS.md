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
