# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: raccomandazione di offerta massima ("quanto offrire ora"), collegando il ledger d'asta vivo (M0) al VAR (M3) — prima versione, dichiaratamente semplificata.
- Perché ora: è il pezzo che rende lo strumento realmente utilizzabile durante l'asta, non solo un elenco di valutazioni statiche.
- In scope:
  - Metodologia standard da aste fantasy ("dollar rule"): riserva 1 credito per ogni slot di rosa ancora da riempire (tranne quello che si sta per comprare), il budget discrezionale residuo si distribuisce proporzionalmente al VAR positivo tra i giocatori ancora disponibili nel pool/round.
  - Stato squadra (budget residuo, slot rimanenti, giocatori già assegnati) letto dal ledger vivo via replay (`src/fantacalcio/domain.py`), mai da uno snapshot statico.
  - Dichiarare esplicitamente cosa manca rispetto al layer forecast-to-bid completo di `docs/DATA_AND_MODELING.md`: nessuna modellazione della domanda avversari, nessuna inflazione osservata di mercato, nessun aggiustamento per fit di modulo/rischio.
- Fuori scope: apprendimento di mercato/domanda avversari (M5), fit rosa/moduli (richiede UX M4), inflazione osservata (serve storico aste reali che non abbiamo ancora).
- Documenti canonici: `docs/DATA_AND_MODELING.md` (forecast-to-bid layer), `src/fantacalcio/domain.py` (ledger/replay), ADR-2026-019/021.
- File probabilmente coinvolti: `src/fantacalcio/auction/bid_recommendation.py`, test, script dimostrativo con ledger sintetico.
- Criteri di accettazione: budget/slot letti dal ledger via replay, mai hardcoded; formula dichiarata come standard/semplificata, non presentata come definitiva; test su scenario sintetico + applicazione dimostrativa.
- Comandi test/quality: `pytest -q`.
- Seed: n/a (deterministico dato lo stato del ledger).
- Delegazione: vietata.
- Decisioni aperte/blocchi: nessuno per lo scope sopra (l'asta reale non è ancora iniziata, quindi il ledger di dimostrazione sarà sintetico).

## Progresso

- Stato: not started
- Ultimo commit/stato verificato: `c62b2d0`
- Prossima azione: implementare `src/fantacalcio/auction/bid_recommendation.py`.
