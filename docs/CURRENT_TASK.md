# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: `TODO` — distribuzione Monte Carlo del fantavoto completata (ADR-2026-018), vedi Progresso.
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

- Stato: **distribuzione Monte Carlo completata** (ADR-2026-018). M2 ora produce distribuzioni, non solo stime puntuali — soddisfa la regola non negoziabile del progetto.
- Ultimo commit/stato verificato: sessione 2026-08-11, `pytest -q` → 171 passed.
- Sintesi: `src/fantacalcio/scoring/monte_carlo.py`, bootstrap a mistura su righe storiche reali (voto+eventi+dato squadra), seed fissato. Validazione walk-forward onesta: correlazione 0,35 (più bassa dell'in-sample 0,51-0,60, riportato senza minimizzare, con le cause plausibili dichiarate). Applicato al roster 2026/27 reale con distribuzioni complete (media/mediana/P10/P90) per tutti i 498 giocatori.
- Con questo blocco, **M2 è sostanzialmente completo** rispetto a `docs/ROADMAP.md` (forza squadra, voto giocatore, partecipazione, motore di scoring, Monte Carlo con distribuzioni — tutti presenti e validati su dati reali). Restano bloccati solo componenti che richiedono decisioni/dati non disponibili (modificatore difesa, fair play, bonus capitano, rigore parato/procurato).
- Prossima azione naturale: **M3** — motore d'asta vero e proprio (layer forecast-to-bid: replacement level, scarsità, collegamento a `config/auction_rules.v1.yaml` e ai pool G1-G4, simulazione dei 4 giri). È il primo pezzo che produce un vero "quanto offrire", non solo "cosa aspettarsi dal giocatore".
