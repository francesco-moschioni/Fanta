# Task corrente

Compilare prima di ogni modifica significativa e mantenere lo scope a una singola unità verificabile.

- Obiettivo: motore deterministico di scoring (applica `SCORING_RULES.md` a eventi reali per calcolare il fantavoto), validato contro `Fm` (fantamedia) del file statistiche.
- Perché ora: prerequisito reale per un valore d'asta onesto (voto grezzo non basta); i dati voti contengono già eventi reali per giornata (gol, assist, cartellini, rigori), quindi il motore può essere validato su dati veri prima di aggiungere previsione/Monte Carlo per giornate future.
- In scope:
  - Funzione deterministica pura: (voto, eventi individuali) → punteggio fantacalcio individuale, per le componenti **confermate** in `SCORING_RULES.md`: gol (+3), assist (+1), assist light (+0.5, se disponibile nei dati — verificare), gol subito (-1), porta inviolata (+1, solo per portiere/difesa), rigore sbagliato (-3), rigore parato (portiere, verificare valore), autogol (-2), ammonizione (-0.5), espulsione (-1), gol pareggio/vittoria (+0.5/+1, richiede risultato partita — verificare disponibilità), bonus capitano (se identificabile).
  - Modificatori di squadra (modificatore difesa, bonus rendimento, fair play, bonus inferiorità) restano **bloccati** se la formula esatta non è confermata in `SCORING_RULES.md`/`OPEN_QUESTIONS.md` — stub esplicito con errore che rimanda alla domanda aperta, stesso pattern di `resolve_sealed_bid_round`.
  - Applicare il motore ai dati voti reali (5 stagioni) e confrontare la fantamedia media calcolata con `Fm` del file statistiche, come validazione indipendente.
- Fuori scope: previsione di eventi futuri, simulazione Monte Carlo (blocco successivo), bonus "uomo partita" (esplicitamente vietato dal regolamento).
- Documenti canonici da leggere: `docs/SCORING_RULES.md`, `docs/OPEN_QUESTIONS.md` (sezione motore partita), `docs/DATA_AND_MODELING.md`.
- File probabilmente coinvolti: nuovo `src/fantacalcio/scoring/engine.py`, test correlati, script di validazione.
- Criteri di accettazione:
  1. Ogni componente implementata è tracciabile a una riga confermata di `SCORING_RULES.md`; ogni componente non confermata è uno stub bloccato esplicito, non un'invenzione.
  2. Confronto fantamedia calcolata vs `Fm` reale: differenza riportata onestamente (non nascosta se grande).
  3. Test per ogni componente individuale.
- Comandi test/quality: `pytest -q`.
- Data cutoff/snapshot/`as_of`: voti 2021/22-2025/26.
- Seed: n/a (deterministico).
- Delegazione: vietata (logica di dominio/regolamento).
- Decisioni aperte/blocchi: verificare quali colonne dei voti bastano per le componenti "gol pareggio/vittoria" (serve il risultato finale partita, non solo eventi individuali) e "assist light" (non è chiaro se distinta da "Ass" nei dati) — potrebbero restare bloccate per mancanza di dato, non di regola.

## Progresso

- Stato: not started
- Ultimo commit/stato verificato: `01e7f5c`
- Prossima azione: leggere `docs/SCORING_RULES.md` per confermare esattamente quali componenti sono implementabili con i dati che abbiamo, poi scrivere `src/fantacalcio/scoring/engine.py`.
