# Questioni aperte

Questi punti non vanno ricostruiti per analogia. Quando l’utente/admin decide, aggiungere un’ADR approvata e aggiornare config/test.

## Motore partita

- Fonte/redazione esatta per voto, assist e assist light.
- Definizione operativa di “contributo al gol”.
- Formula esatta del modificatore: quali voti entrano, gestione portiere, migliori tre difensori o tutti, difensori SV e sostituzioni.
- Perimetro fair play: quali giocatori devono avere zero ammonizioni.
- Bonus inferiorità definitivo: +3,5 storico oppure proposta progressiva 4,5–5,5.
- Trattamento completo degli SV e della formazione ereditata.

## Buste e amministrazione

Risolto 2026-08-11 dal recap regole dell'admin (`docs/archive/Recap_regole_asta_admin_20260811.txt`, ADR-2026-013):

- Preferenze per lista G1/G2: **6**, confermato.
- Priorità di risoluzione G1/G2: **preferenza espressa prima, offerta poi** (non un singolo punteggio combinato).
- Minimo d'offerta G1/G2: quello indicato per ciascun giocatore nella lista pubblicata (valori esatti non ancora nel repo, arriveranno con le liste venerdì sera).
- Minimo d'offerta G3/G4: **quotazione del giocatore**.
- Fallback G1/G2 se nessuna preferenza vince: **assegnazione di un giocatore ancora disponibile nella lista al prezzo minimo**.
- G3/G4 **non sono asta aperta/live**: sono comunque a busta chiusa, vince l'offerta più alta, nessun vincolo di ruolo/lista, max 6 giocatori a fase.
- Fase 3 (completamento): **non è un'asta**, l'admin assegna manualmente i rimanenti, a partire dalle squadre con più crediti residui. Algoritmo esatto di equità non specificato oltre l'ordine.

Ancora aperto:

- Tie-breaker se due squadre danno allo stesso giocatore la stessa preferenza di rango con la stessa offerta (caso raro ma non escluso).
- Formato effettivo dei file admin da importare (liste, risultati asta).
- Soglie esatte delle liste (top 20/40/60 ecc.) — il recap dice solo "liste divise per classifica di riferimento", pubblicate venerdì sera; le soglie attuali in `config/auction_rules.v1.yaml` (`defenders_top_1_60`, ecc.) restano una stima ereditata dal regolamento storico, da confermare quando arrivano le liste reali.

## Tecnico

- Stack risolto: Python + DuckDB/SQLite + Streamlit (ADR-2026-008). Resta aperto solo se rivalutare un frontend dedicato dopo il gate M4.
- Provider principale giocatore-partita dopo audit comparativo (blocca solo la parte M1 dell'audit provider, non M0).

Ogni domanda ha scope locale: non bloccare task che non dipendono dalla risposta.
