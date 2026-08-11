# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: sessione autonoma "fai tutto quello che puoi fare senza input admin" — completata con due unità: (1) fix del gap bloccante sulla registrazione blocco portieri (ADR-2026-032), (2) ottimizzatore "rosa ideale" (ADR-2026-033).
- Stato: entrambe le unità completate e verificate in browser. 295 test totali passano.

## Progresso

- ADR-2026-032: `app/pages/2_Squadre.py` ora gestisce la registrazione del blocco portieri (3 nomi, un prezzo, avviso se club diversi) — prima il form rifiutava esplicitamente ogni portiere, bloccando la rappresentazione di un'asta G1 reale e completa.
- ADR-2026-033: `src/fantacalcio/auction/roster_optimizer.py` (knapsack esatto 0/1 multi-vincolo, non euristica) + sezione "Rosa ideale" in `app/pages/3_Rosa.py`. Verificato con dati reali: G1, 8 difensori, budget 200 → combinazione entro budget (costo 107, VAR 4.18).
- Prossima azione (non ancora scoped): "undici ideale" resta bloccato dalla mancanza di probabilità di voto/rischio SV nella tabella giocatori (dato non ancora esposto, non una decisione admin); il resto del costruttore rosa completo (drag-and-drop, confronto moduli, profili) richiede lavoro UI aggiuntivo quando si riprende M4. L'import del formato file admin resta bloccato fino a venerdì sera.
