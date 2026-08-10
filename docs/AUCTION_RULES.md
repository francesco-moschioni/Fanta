# Specifica canonica dell’asta

La configurazione eseguibile è `config/auction_rules.v1.yaml`. Questo documento ne spiega semantica e invarianti. Il regolamento storico a tre fasi è archiviato e non prevale.

## Quattro giri correnti

| Giro | Modalità | Pool | Budget disponibile |
|---|---|---|---|
| G1 | Busta chiusa | Blocco portieri + top 60 difensori | 200 |
| G2 | Busta chiusa | Top 60 centrocampisti + top 40 attaccanti | residuo G1 + 100 |
| G3 | Asta aperta | giocatori rimanenti | residuo G2 + 40 |
| G4 | Asta aperta | giocatori rimanenti | residuo G3 |

Round, modalità, incrementi, pool e vincoli devono essere letti dalla configurazione versionata, mai hardcoded.

## Liste top

La lista dell’admin e il ranking del modello sono entità diverse.

| Stato | Significato | Uso |
|---|---|---|
| `unknown` | lista non comunicata | scenari, nessun vincolo reale di eleggibilità |
| `provisional` | stima/ranking | preparazione e sensitivity analysis |
| `official` | file importato dall’admin | unica autorità per offerte e assegnazioni reali |

Finché la lista non è `official`, la UI mostra `LISTA NON UFFICIALE`. Gli scenari possono usare soglie top 20/40/60 o personalizzate, probabilità di inclusione e attenzione ai giocatori vicini al cutoff. L’import ufficiale ricalcola strategia e costo-opportunità, conservando lo snapshot precedente.

## Ledger e stato

Ogni evento contiene almeno: timestamp, round, squadra, giocatore/pool, tipo evento, importo, fonte, autore, stato validità e riferimento all’evento corretto. Acquisto, correzione e undo devono ricostruire:

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
- Correzione/undo non lascia prezzi o profili avversari “fantasma”.
- I tie-breaker e fallback non vengono inventati: finché non approvati, il ramo resta bloccato.

## Valore e offerta

Il massimo dinamico non coincide con la previsione fantasy. Deve dipendere da valore sopra replacement, fit con la rosa, copertura dei moduli, rischio, budget ombra, offerta futura, stato del round, inflazione osservata e probabilità di concorrenza. Mostrare sempre prezzo atteso come distribuzione e spiegare costo-opportunità e vincoli attivi.
