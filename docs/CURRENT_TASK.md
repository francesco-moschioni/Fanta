# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M1 di `docs/ROADMAP.md` — registry fonti verificato, ingestion delle fonti gratuite senza autenticazione (football-data.co.uk, OpenFootball), entity resolver per l'identità squadra con coda di revisione, report di data quality. La parte di audit comparativo Sportmonks/API-Football è **bloccata** in attesa di credenziali (vedi sotto).
- Perché ora: M0 è completo; M1 è la milestone successiva in `docs/ROADMAP.md` e non ha blocchi per le fonti gratuite.
- In scope (completato):
  - Snapshot raw immutabili con checksum (`src/fantacalcio/ingest/snapshot.py`).
  - Ingestion tipizzata football-data.co.uk e OpenFootball, con gestione esplicita degli schemi non uniformi trovati nei dati reali (es. campo `score` di OpenFootball).
  - Entity resolver squadra (`src/fantacalcio/identity/teams.py`): match esatto normalizzato, match fuzzy solo sopra soglia di confidenza alta, coda di revisione per tutto il resto — nessun join forzato silenzioso.
  - Report coverage/missingness/cross-source match-rate riproducibile (`scripts/run_m1_audit.py` → `data/outputs/m1_data_quality_report.md`).
  - ADR-2026-009 e `docs/SOURCE_REGISTER.md` aggiornati per le due fonti verificate.
- Fuori scope / bloccato:
  - Audit comparativo Sportmonks vs API-Football (richiede creazione account/trial, non eseguibile da un agente autonomo).
  - Import football-data.co.uk storico multi-stagione, StatsBomb/Wyscout, Understat (rimandati, non prioritari per sbloccare M2).
  - Risoluzione manuale delle 6 squadre in `data/identity/team_review_queue.json`.
- Documenti canonici da leggere: `docs/ROADMAP.md` (gate M1), `docs/SOURCE_REGISTER.md`, `docs/DATA_AND_MODELING.md`, `.claude/skills/data-modeling/SKILL.md`, `docs/DECISIONS.md` (ADR-2026-009).
- File coinvolti: `src/fantacalcio/ingest/*`, `src/fantacalcio/identity/*`, `scripts/run_m1_audit.py`, `tests/test_ingest_*.py`, `tests/test_identity_teams.py`, `data/identity/*.json`, `data/outputs/m1_data_quality_report.md`.
- Criteri di accettazione (gate M1, parziali — vedi bloccati sopra):
  1. ✅ Report coverage/missingness prodotto e riproducibile.
  2. ✅ Mapping confidence esplicita per ogni entità risolta; nessun join sotto soglia eseguito silenziosamente.
  3. ✅ ADR della fonte primaria/fallback per calendario/risultati (ADR-2026-009).
  4. ⏳ Audit comparativo ≥100 partite Sportmonks/API-Football — bloccato su credenziali.
  5. ⏳ Confronto indipendente ≥50 partite tra provider — bloccato sullo stesso vincolo.
- Comandi test/quality: `pytest -q` (58 test, tutti verdi); `python scripts/run_m1_audit.py` per rigenerare il report (richiede rete).
- Data cutoff/snapshot/`as_of`: stagione Serie A 2025/26, snapshot del 2026-08-10 (vedi hash/timestamp nel report).
- Seed, se applicabile: n/a (nessuna componente randomica in questo giro; il resolver è deterministico).
- Delegazione: nessuna usata in questa unità (lavoro di dominio/schema, non boilerplate delegabile).
- Decisioni aperte/blocchi:
  - Serve una tua azione per sbloccare l'audit Sportmonks/API-Football: crea i due account/trial e fornisci `SPORTMONKS_API_KEY` / `API_FOOTBALL_KEY` come variabili d'ambiente (mai committate).
  - `data/identity/team_review_queue.json` contiene 6 squadre non risolte automaticamente (es. "AS Roma", "FC Internazionale Milano") — da confermare manualmente o lasciare al resolver di M1 successivo con alias curati.

## Progresso

- Stato: **M1 parzialmente completato** — bloccato in attesa di credenziali provider per la parte restante.
- Ultimo commit/stato verificato: implementato in sessione 2026-08-10, `pytest -q` → 58 passed.
- Prossima azione: attendere `SPORTMONKS_API_KEY`/`API_FOOTBALL_KEY` dall'utente, oppure passare nel frattempo a un'altra unità di M1/M2 non bloccata (es. curare gli alias per la coda di revisione squadre).
