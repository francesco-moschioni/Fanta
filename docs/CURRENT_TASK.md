# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: Bootstrap del progetto (M0 di `docs/ROADMAP.md`) — inizializzare il progetto Python, il loader/validatore della configurazione d'asta, i tipi canonici di dominio con i relativi invarianti, il ledger d'asta append-only con replay ed edit/undo, e l'import/export locale JSON/CSV con fixture demo.
- Perché ora: è la prima milestone della roadmap e non ha blocchi aperti in `docs/OPEN_QUESTIONS.md`; sblocca tutte le milestone successive.
- In scope:
  - Scaffold progetto Python (struttura pacchetto, `pyproject.toml`, ambiente `venv`/`uv`, `pytest` configurato) secondo ADR-2026-008.
  - Loader e validatore di `config/auction_rules.v1.yaml` (schema check, valori mancanti/malformati falliscono esplicitamente, nessun default inventato per i campi `uncertain_historical_fields`).
  - Tipi canonici di dominio: squadra, rosa/slot per ruolo, round, pool, evento di offerta/assegnazione, stato budget.
  - Test degli invarianti: conservazione budget, blocco portieri 3 stesso club, quote rosa 8D/8C/5A (fallback 4A), nessuna doppia assegnazione, nessuna assegnazione fuori pool ammesso per il round corrente.
  - Ledger append-only: schema evento, replay deterministico dello stato da sequenza di eventi, edit/undo che produce un nuovo evento correttivo (mai mutazione silenziosa della storia).
  - Import/export locale in JSON/CSV e almeno una fixture demo (dati sintetici, 20 squadre, 4 round) per i test end-to-end.
- Fuori scope: qualunque modello statistico/predittivo (M2+), ingestion di fonti dati reali (M1), UI (M4), meccaniche di risoluzione busta chiusa/asta aperta ancora bloccate da `docs/OPEN_QUESTIONS.md` (implementare solo lo scheletro dati/evento, non gli algoritmi di risoluzione delle preferenze).
- Documenti canonici da leggere: `docs/ROADMAP.md` (gate M0), `config/auction_rules.v1.yaml`, `docs/AUCTION_RULES.md`, `docs/OPEN_QUESTIONS.md`, `docs/DECISIONS.md` (ADR-2026-008 per lo stack), `.claude/skills/auction-domain/SKILL.md`.
- File/simboli probabilmente coinvolti: nuova struttura `src/`, `tests/`, `pyproject.toml`; nessun file esistente da modificare oltre alla documentazione se emergono chiarimenti.
- Criteri di accettazione (= gate M0 di `docs/ROADMAP.md`):
  1. Il replay del ledger da una sequenza di eventi identica produce sempre lo stesso stato finale (test di determinismo).
  2. Budget conservato in ogni round: nessun saldo negativo, nessuna spesa oltre il residuo disponibile.
  3. Test che dimostrano il blocco di: doppia assegnazione dello stesso giocatore/blocco, assegnazione fuori pool ammesso, violazione quote rosa.
  4. I rami che dipendono da un campo `uncertain_historical_fields` (preference count, tie-breaker, minimo offerta, fallback automatico) falliscono esplicitamente con un errore che rimanda a `docs/OPEN_QUESTIONS.md`, invece di usare un default silenzioso.
  5. La fixture demo importa/esporta correttamente e produce un replay valido.
- Comandi test/quality: `pytest -q` (da definire in dettaglio nello scaffold: linting/type-check se introdotti, es. `ruff`, `mypy`).
- Data cutoff/snapshot/`as_of`: n/a per M0 (nessun dato reale coinvolto, solo fixture sintetiche).
- Seed, se applicabile: fissare un seed esplicito per la generazione della fixture demo, se contiene componenti randomiche.
- Delegazione: Gemini ammesso per boilerplate di scaffold (struttura cartelle, `pyproject.toml`, fixture dati sintetiche, bozze di test) tramite `scripts/delegate_gemini.py` con allowlist esplicita; vietata per tipi di dominio, invarianti, schema ledger e logica di replay/validazione, che restano decisioni del lead.
- Decisioni aperte/blocchi: nessuno per lo scope sopra definito. Se durante l'implementazione emerge la necessità di decidere una meccanica di risoluzione asta (buste/tie-breaker), fermarsi e riportare in `docs/OPEN_QUESTIONS.md`/`docs/DECISIONS.md` invece di implementarla.

## Progresso

- Stato: **completato** — tutti i criteri di accettazione soddisfatti (vedi verifica sotto).
- Ultimo commit/stato verificato: implementato in sessione 2026-08-10, `pytest -q` → 39 passed.
- Verifica dei 5 criteri di accettazione:
  1. Replay deterministico: `tests/test_domain_replay.py::test_replay_is_deterministic` + verifica manuale (stesso stato da doppio replay).
  2. Budget conservato: `tests/test_domain_replay.py::test_budget_never_overspent`, `test_overspend_raises`; nessun saldo negativo per costruzione (`TeamRoundBudget.remaining`).
  3. Blocchi invarianti: test dedicati per doppia assegnazione, pool non ammesso, ruolo incoerente col pool, quota ruolo superata, blocco portieri di dimensione errata/duplicato.
  4. Rami bloccati fino ad ADR: `resolve_sealed_bid_round()` solleva `NotImplementedError` con riferimento esplicito a `docs/OPEN_QUESTIONS.md`; i campi `uncertain_historical_fields` restano non confermati (test `test_uncertain_fields_are_unconfirmed`).
  5. Fixture demo: `fantacalcio.fixtures.generate_demo_events` genera un ledger valido per 20 squadre/4 round; import/export JSON verificato round-trip (`tests/test_ledger_io.py`) ed export CSV derivato.
- File creati: `pyproject.toml`, `src/fantacalcio/{config,domain,ledger_io,fixtures}.py`, `tests/{conftest,test_config,test_domain_replay,test_ledger_io}.py`, ambiente `.venv` locale (non tracciato).
- Note per M1: identità club reale non ancora modellata (placeholder `gk_block_identity`); ruolo per pool `remaining_players` (G3/G4) è dichiarato esplicitamente nell'evento, non derivato da un'anagrafica giocatore reale (arriverà con l'identity layer di M1). Il vincolo `require_future_slot_reserve` della config non è applicato dal replay (è descrittivo/storico, non un motore di raccomandazione) — resta da implementare nell'auction engine di M3.
- Prossima azione: aprire un nuovo `CURRENT_TASK.md` per M1 (registry fonti, audit provider, entity resolver).
