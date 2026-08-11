# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M4 slice 4 — rettifica di budget generica nel ledger (`BudgetAdjustmentEvent`), applicata alla regola admin appena comunicata: +3 crediti per squadra con logo/immagine personalizzata invece dello stemma di stock ("come lo scorso anno").
- Perché ora: regola reale comunicata dall'utente, richiede una modifica di budget per-squadra che il ledger attuale non sa esprimere (i round hanno solo un'espressione di budget globale, non per-squadra). Serve prima di poter registrare risultati reali con bonus applicato.
- In scope:
  - `config/auction_rules.v1.yaml` + `src/fantacalcio/config.py`: nuovo campo versionato `league.custom_logo_bonus_credits: 3` (mai un letterale `3` nel codice).
  - `src/fantacalcio/domain.py`: nuovo tipo di evento `BudgetAdjustmentEvent` (event_id, ts, round_id, team_id, amount, reason, author) — generico (qualsiasi rettifica di budget con causale, non solo il bonus logo), gestito in `replay()` sommando `amount` al budget disponibile della squadra per quel round (creandolo se non esiste ancora, stessa logica di `AssignmentEvent`). `effective_events()` esteso per includere anche questo tipo (voidabile come gli altri).
  - `src/fantacalcio/ledger_io.py`: serializzazione JSON del nuovo tipo.
  - `app/pages/2_Squadre.py`: controllo per assegnare il bonus a una squadra (appende un `BudgetAdjustmentEvent` con l'importo da config, causale "custom_logo_bonus"); il tabellone/massimo consigliato lo riflettono automaticamente (nessuna modifica necessaria altrove: il bonus scorre attraverso `remaining_G1` come ogni altro credito).
- Fuori scope: interfaccia per rettifiche negative/penalità (il meccanismo le supporta già genericamente, ma nessuna causale di penalità è nota/richiesta ora — niente UI dedicata finché non serve), costruttore rosa.
- Documenti canonici: nessun ADR precedente copre questa regola — nuovo ADR necessario (rettifica di budget generica + regola specifica del bonus logo, con provenienza "comunicazione admin 2026-08-11").
- File probabilmente coinvolti: `config/auction_rules.v1.yaml`, `src/fantacalcio/config.py`, `src/fantacalcio/domain.py`, `src/fantacalcio/ledger_io.py`, `app/pages/2_Squadre.py`, test corrispondenti.
- Criteri di accettazione: nessun valore hardcoded (l'importo del bonus letto da config); il bonus si propaga correttamente attraverso G2/G3/G4 (già garantito dalla catena `remaining_G1` se applicato a G1, verificato con test); undo funziona anche per questo tipo di evento; verificato in browser prima di dichiarare fatto.
- Comandi test/quality: `pytest -q`.
- Seed: non applicabile.
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: **completato** (ADR-2026-030). Verificato in browser: bonus assegnato a team_01 (G1 200→203), acquisto reale da 203 crediti registrato senza overspend.
- `BudgetAdjustmentEvent` in `domain.py` (generico, riusabile per future rettifiche), campo config `custom_logo_bonus_credits`, UI in `app/pages/2_Squadre.py` (assegnazione, colonna tabellone, undo).
- 269 test totali passano (11 nuovi).
- Prossima azione (M4 slice 5, non ancora scoped): costruttore rosa visuale con lock, oppure import del formato file admin quando disponibile (venerdì sera, formato ancora sconosciuto).
