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
