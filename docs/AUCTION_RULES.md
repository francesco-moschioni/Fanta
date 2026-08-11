# Specifica canonica dell'asta

La configurazione eseguibile è `config/auction_rules.v1.yaml`. Questo documento ne spiega semantica e invarianti. Fonte primaria: recap regole admin, 2026-08-11 (`docs/archive/Recap_regole_asta_admin_20260811.txt`, ADR-2026-013).

Nota di coerenza: il meccanismo confermato ora (liste con preferenze, prezzo minimo, fallback, completamento admin) coincide nella sostanza con quello del regolamento storico a tre fasi (`docs/archive/Regolamento_originale.txt`) — non è stato sostituito, è stato confermato con i numeri esatti. I "quattro giri" sono la fase 1 (due giornate: portieri+difensori, poi centrocampisti+attaccanti) e la fase 2 (due giri di asta libera), più una fase 3 finale che non è un'asta.

## Quattro giri + completamento finale

| Giro | Modalità | Pool | Budget disponibile | Risoluzione |
|---|---|---|---|---|
| G1 | Busta chiusa a liste | Blocco portieri + top 60 difensori | 200 | Preferenza (6/lista) prima, offerta poi |
| G2 | Busta chiusa a liste | Top 60 centrocampisti + top 40 attaccanti | residuo G1 + 100 | Preferenza (6/lista) prima, offerta poi |
| G3 | Busta chiusa libera | giocatori rimanenti, nessun vincolo ruolo | residuo G2 + 40 | Offerta più alta, max 6 giocatori |
| G4 | Busta chiusa libera | giocatori rimanenti, nessun vincolo ruolo | residuo G3 | Offerta più alta, max 6 giocatori |
| Fase 3 | Nessuna asta | tutti i rimanenti | n/a | Admin assegna manualmente, squadre con più crediti residui prima |

**G3/G4 non sono un'asta aperta/live** — è un errore precedente ora corretto (erano marcati `open_auction` in una versione precedente della config). Restano a busta chiusa come G1/G2, semplicemente senza liste/preferenze: vince chi offre di più.

Round, modalità, incrementi, pool e vincoli devono essere letti dalla configurazione versionata, mai hardcoded.

## Liste top

La lista dell'admin e il ranking del modello sono entità diverse.

| Stato | Significato | Uso |
|---|---|---|
| `unknown` | lista non comunicata | scenari, nessun vincolo reale di eleggibilità |
| `provisional` | stima/ranking | preparazione e sensitivity analysis |
| `official` | file importato dall'admin | unica autorità per offerte e assegnazioni reali |

Finché la lista non è `official`, la UI mostra `LISTA NON UFFICIALE`. Le liste reali arrivano venerdì sera (soglie esatte non ancora note, vedi `docs/OPEN_QUESTIONS.md`); le soglie attuali in config (top 60/40) restano una stima ereditata dal regolamento storico. Gli scenari possono usare soglie top 20/40/60 o personalizzate, probabilità di inclusione e attenzione ai giocatori vicini al cutoff. L'import ufficiale ricalcola strategia e costo-opportunità, conservando lo snapshot precedente.

## Ledger e stato

Ogni evento contiene almeno: timestamp, round, squadra, giocatore/pool, tipo evento, importo, fonte, autore, stato validità e riferimento all'evento corretto. Acquisto, correzione e undo devono ricostruire:

- budget iniziale, incrementi, spesa e residuo esatti;
- minimo necessario a completare gli slot;
- budget realmente spendibile e massimo dinamico;
- slot, ruoli, tier e domanda residua di ogni squadra;
- disponibilità del giocatore e pool corrente;
- snapshot del mercato e profilo avversario.

## Invarianti minime

- Nessun giocatore assegnato due volte.
- Nessuna assegnazione fuori pool ufficiale quando il pool è vincolante.
- Nessuna spesa oltre il budget spendibile preservando il minimo per completare la rosa.
- Gli incrementi di round sono applicati una sola volta e sono riproducibili.
- Le assegnazioni rispettano rosa, ruoli e blocco portieri.
- Il replay dello stesso ledger produce lo stesso stato.
- Correzione/undo non lascia prezzi o profili avversari "fantasma".
- I tie-breaker e fallback non vengono inventati: finché non approvati, il ramo resta bloccato (resta bloccato solo il tie-breaker per pari preferenza+pari offerta, vedi `docs/OPEN_QUESTIONS.md`; il fallback generico G1/G2 è ora confermato).

## Valore e offerta

Il massimo dinamico non coincide con la previsione fantasy. Deve dipendere da valore sopra replacement, fit con la rosa, copertura dei moduli, rischio, budget ombra, offerta futura, stato del round, inflazione osservata e probabilità di concorrenza. Mostrare sempre prezzo atteso come distribuzione e spiegare costo-opportunità e vincoli attivi.
