# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: M4 slice 5 — prima fetta del costruttore rosa (`docs/UX_PRODUCT.md`, area "Costruttore rosa", P0): vista "La mia rosa" (reale, da ledger) + lock di giocatori target (pre-asta, ipotetici) con controllo di fattibilità, distinti sempre da ciò che è già acquistato.
- Perché ora: il formato file admin non è ancora noto (arriva venerdì sera, `docs/OPEN_QUESTIONS.md`), quindi l'import automatico resta bloccato; il costruttore rosa visuale completo (drag-and-drop, ottimizzatore "rosa ideale"/"undici ideale", confronto moduli) è troppo grande per una singola unità — questa slice ne costruisce il primo strato verificabile: vista rosa + lock, senza ancora ottimizzazione automatica.
- In scope:
  - `src/fantacalcio/persistence/locks_store.py`: tabella SQLite `locks` (stesso DB del ledger, tabella separata — i lock NON sono eventi d'asta, sono intenzione pre-asta, non entrano nel replay deterministico) — team_id, player_code, role, note, locked_at.
  - `src/fantacalcio/auction/lock_feasibility.py`: verifica di fattibilità pura (nessun I/O) prima di bloccare un giocatore — CLAUDE.md: "Locked players remain locked. If infeasible, explain the conflicting constraint and minimum relaxation." Controlla: giocatore già nella rosa reale della squadra (lock superfluo), giocatore già assegnato a un'ALTRA squadra (target impossibile, spiegato esplicitamente), capacità di ruolo superata combinando rosa reale + lock esistenti (spiega quale vincolo e cosa rimuovere per fare spazio).
  - Nuova pagina `app/pages/3_Rosa.py`: rosa reale (da replay del ledger) per ruolo con slot pieni/vuoti, budget speso/residuo per round; sezione lock separata e chiaramente etichettata come ipotetica ("obiettivi bloccati, non ancora acquistati"), con stima di budget/slot residui SE tutti i lock andassero a buon fine; lock/unlock con causale di infeasibility se applicabile.
  - Piccola aggiunta a `app/pages/1_Giocatori.py`: pulsante blocca/sblocca per "la mia squadra" sulla scheda giocatore selezionata.
- Fuori scope: campo grafico drag-and-drop, ottimizzatore automatico "rosa ideale"/"undici ideale", confronto tra gli otto moduli, profili prudente/bilanciato/aggressivo — slice future, richiedono un vero motore di ottimizzazione non ancora costruito.
- Documenti canonici: `docs/UX_PRODUCT.md` (costruttore rosa, giocatori bloccati), `CLAUDE.md` (regola lock/infeasibility, "Distingui sempre acquistato da ipotetico").
- File probabilmente coinvolti: `src/fantacalcio/persistence/locks_store.py` (nuovo), `src/fantacalcio/auction/lock_feasibility.py` (nuovo), `app/pages/3_Rosa.py` (nuovo), `app/pages/1_Giocatori.py`, test corrispondenti.
- Criteri di accettazione: mai un lock infeasible applicato silenziosamente (sempre spiegato); reale e ipotetico sempre visivamente distinti; nessun ricalcolo di formule già esistenti (solo combinazione di dati già prodotti da domain/replay + tabella lock); verificato in browser prima di dichiarare fatto.
- Comandi test/quality: `pytest -q`.
- Seed: non applicabile.
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno.

## Progresso

- Stato: **completato** (ADR-2026-031). Verificato in browser: lock/unlock di Lautaro Martinez da Giocatori, riflesso su Rosa con costo stimato corretto.
- `src/fantacalcio/persistence/locks_store.py`, `src/fantacalcio/auction/lock_feasibility.py`, `app/pages/3_Rosa.py`, pulsante blocca/sblocca in `app/pages/1_Giocatori.py`.
- 284 test totali passano (23 nuovi).
- Prossima azione (M4 slice 6, non ancora scoped): ottimizzatore "rosa ideale"/"undici ideale" con confronto moduli, oppure import del formato admin quando disponibile (venerdì sera, formato ancora sconosciuto).
