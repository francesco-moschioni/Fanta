# Regole di punteggio

Stato: sintesi fedele del regolamento storico allegato. Le formule confermate in futuro devono essere promosse con ADR e configurazione versionata.

## Componenti individuali storiche

| Evento | Punti |
|---|---:|
| Gol | +3 |
| Assist | +1 |
| Assist light/contributo al gol | +0,5 |
| Gol subito | −1 |
| Porta inviolata | +1 |
| Rigore sbagliato | −3 |
| Autogol | −2 |
| Ammonizione | −0,5 |
| Espulsione | −1 |
| Gol del pareggio finale | +0,5 |
| Gol della vittoria finale | +1 |
| Fair play: zero ammoniti | +0,5 |

Nessun bonus uomo partita.

## Capitano storico

- voto base almeno 6: +1;
- voto base almeno 7: +2;
- voto base almeno 8: +3;
- voto base sotto 5,5: −1.

## Componenti di formazione storiche

- Fasce gol ogni 5 punti a partire da 66: 66, 71, 76, 81, …
- Bonus rendimento: almeno 9 giocatori con voto base ≥6 → +0,5; 10 → +1; 11 → +1,5.
- Modificatore difesa disponibile con almeno 4 difensori: da media 6,25 vale +1 e cresce di +1 per ogni 0,25; il testo cita 6 → +0, 6,25 → +1, 6,5 → +2.
- Massimo 5 sostituzioni; no switch.
- Bonus storico per ogni giocatore mancante a 11: +3,5. Il testo contiene anche una proposta non approvata di +4,5 progressivo fino a +5,5 dopo il terzo mancante.

## Implicazione per il modello

Non prevedere direttamente una singola fantamedia. Simulare stato di partecipazione/minuti, voto base, eventi, risultato/scoreline e dipendenze fra compagni; poi applicare il motore deterministico. Servono distribuzioni congiunte per modificatore, rendimento, fair play, sostituzioni e inferiorità numerica.

I dettagli non deterministici sono elencati in `OPEN_QUESTIONS.md` e bloccano soltanto i relativi rami del motore partita.
