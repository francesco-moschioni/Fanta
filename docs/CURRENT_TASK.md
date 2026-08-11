# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M4 slice 2 — ledger vivo persistente (SQLite, ADR-2026-008) + tabellone squadre + registrazione manuale dei risultati pubblicati dall'admin + tetto di riferimento (massimo consigliato) nella scheda giocatore.
- Perché ora: la slice 1 (ricerca/scheda, ADR-2026-027) è sola lettura su dati statici; questa slice collega il ledger vivo (già costruito in M0/M3: `src/fantacalcio/domain.py`, `src/fantacalcio/ledger_io.py`, `src/fantacalcio/auction/bid_recommendation.py`) così budget/rosa/massimo consigliato riflettano lo stato reale dell'asta, non uno snapshot statico.
- **Vincolo di dominio importante** (`config/auction_rules.v1.yaml`): tutti i round G1-G4 sono **sealed bid**, risolti dall'admin dopo la chiusura di ciascun turno — non è un'asta live interattiva multi-squadra dentro l'app. Questa slice quindi:
  - NON implementa un'"asta live" dove le squadre offrono in tempo reale l'una contro l'altra.
  - Registra manualmente i **risultati già pubblicati dall'admin** (chi ha vinto cosa, a che prezzo, in che round) — un form di registrazione, non un meccanismo di offerta.
  - Il "massimo consigliato" (formula dollar-rule già validata, ADR-2026-022) è un **tetto di riferimento** da scrivere sulla propria lista sealed-bid per il prossimo round, non una previsione di chi vincerà (la vittoria dipende da preferenza-poi-offerta risolte dall'admin, non dal miglior offerente in tempo reale). Etichettato esplicitamente così nella UI.
- Fuori scope, esplicitamente bloccato:
  - Import automatico del formato file admin (formato non ancora noto, arriva via Google Form — `docs/OPEN_QUESTIONS.md` "Formato effettivo dei file admin da importare").
  - Risoluzione automatica delle preferenze sealed-bid (`resolve_sealed_bid_round` resta `NotImplementedError`, bloccato dal tie-breaker non confermato).
  - Nomi reali squadre/partecipanti (non ancora in repo, `private_participants/` vuoto): uso identificativi generici (`team_01`..`team_20`, quanti quanto `ruleset.teams`), sostituibili in futuro senza toccare lo schema.
  - Command palette, alert non bloccanti, apprendimento mercato, cockpit "velocità estrema" — slice successive.
- File probabilmente coinvolti: `src/fantacalcio/persistence/ledger_store.py` (nuovo, riusa la serializzazione già in `src/fantacalcio/ledger_io.py`, nessuna duplicazione schema), `app/pages/2_Squadre.py` (nuovo), `app/pages/1_Giocatori.py` (aggiunta: selezione "la mia squadra" + tetto di riferimento), test del data layer.
- Criteri di accettazione: append-only reale (mai UPDATE/DELETE su eventi esistenti, undo = nuovo `VoidEvent`); replay deterministico dal ledger persistito identico a quello in-memory già testato in M0; nessuna invenzione di nomi squadra/algoritmi di risoluzione non confermati; round G3/G4 gestiti esplicitamente come round distinti (non "G3_G4", che è solo un'etichetta di visualizzazione di `round_pools.py`) quando si registra un evento reale; verificato in browser prima di dichiarare fatto.
- Comandi test/quality: `pytest -q`.
- Seed: non applicabile (nessuna componente stocastica in questa slice).
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno per questa slice (i blocchi reali — formato import admin, tie-breaker — restano esplicitamente fuori scope, non aggirati).

## Progresso

- Stato: **completato** (ADR-2026-028). Verificato in browser end-to-end: registrazione G1→G2, undo, tetto di riferimento.
- `src/fantacalcio/persistence/ledger_store.py`, `domain.effective_events()`, `app/pages/2_Squadre.py`, estensione `app/pages/1_Giocatori.py`. 258 test totali passano.
- **Bug critico trovato e corretto durante il testing**: `domain.replay()` calcolava il budget di round successivi (es. G2 = remaining_G1 + 100) usando un dizionario di residui condiviso fra tutte le squadre invece che per-squadra — avrebbe corrotto i budget reali nell'asta vera. Corretto (`remaining_by_round_per_team`), test di regressione aggiunto. Vedi ADR-2026-028.
- Prossima azione (M4 slice 3, non ancora scoped in dettaglio): costruttore rosa visuale con lock, oppure import del formato file admin quando disponibile (venerdì sera, ancora sconosciuto).
