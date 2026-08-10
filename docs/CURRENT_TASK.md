# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — M1 di `docs/ROADMAP.md` è completo (vedi Progresso sotto). Prossima unità da scoping: M2 (baseline predittive) o curare la coda di revisione entità.
- Perché ora: `TODO`
- In scope: `TODO`
- Fuori scope: `TODO`
- Documenti canonici da leggere: `TODO`
- File/simboli probabilmente coinvolti: `TODO`
- Criteri di accettazione: `TODO`
- Comandi test/quality: `TODO`
- Data cutoff/snapshot/`as_of`: `TODO o N/A`
- Seed, se applicabile: `TODO`
- Delegazione: vietata | Gemini per `TODO` | subagente `TODO` per `TODO`
- Decisioni aperte/blocchi: `TODO`

## Progresso

- Stato: **M1 completato**.
- Ultimo commit/stato verificato: sessione 2026-08-10, `pytest -q` → 67 passed.
- Sintesi M1:
  - Fonti calendario/risultati (football-data.co.uk, OpenFootball): verificate, ADR-2026-009.
  - Provider lineup/minuti/eventi: audit comparativo completato su campioni reali (API-Football stagione 2023, StatsBomb Open Data stagione 2015/16), entrambi validati al 100% contro football-data.co.uk sulla stessa stagione. Sportmonks escluso (piano gratuito non copre la Serie A). Raccomandazione primario/fallback in ADR-2026-010 e `data/outputs/m1_provider_audit_report.md`.
  - Entity resolver squadra con coda di revisione: funzionante, usato su tre coppie di fonti diverse senza mai forzare un match sotto soglia.
  - Residuo non bloccante: `data/identity/team_review_queue.json` contiene alcune squadre non risolte automaticamente (es. "AS Roma", "FC Internazionale Milano") — da confermare manualmente o arricchire il resolver con alias curati quando conviene, non blocca M2.
- Prossima azione: aprire un nuovo `CURRENT_TASK.md` per M2 (baseline predittive: Elo/Dixon-Coles, modello minuti/partecipazione, scoring engine Monte Carlo) oppure per la curatela della coda di revisione, a scelta del project owner.
