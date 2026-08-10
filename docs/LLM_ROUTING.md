# Policy di routing LLM

Obiettivo: ridurre token Claude a pagamento e contaminazione del contesto, non massimizzare il numero di agenti. Più agenti possono aumentare i token totali.

| Task | Default | Quality owner |
|---|---|---|
| Architettura/confini dominio | Claude Sonnet; Opus solo motivato | lead + utente |
| Schema canonico/entity policy | Claude Sonnet | lead |
| Statistica, scoring, validazione | Sonnet + statistical reviewer | lead + utente |
| Assegnazione/ottimizzazione | Sonnet + test deterministici | lead |
| Mappa repository | `repo-explorer` Haiku | lead |
| Log/test lunghi | `test-runner` Haiku | lead |
| Audit dati | `data-quality-reviewer` Haiku | lead |
| Boilerplate, fixture, draft test/UI/docs | Gemini CLI isolato | lead |
| Calcoli, score, replay, simulazioni | codice deterministico | test/reproducibilità |

## Vincolo noto: quota Gemini free-tier

La API key configurata è sul tier gratuito di Google AI Studio, con un limite di circa 20 richieste/giorno sul modello di default (verificato 2026-08-10, esaurita durante il solo test di setup). Non pianificare grandi volumi di delega a Gemini in una singola sessione: trattarla come risorsa opportunistica, non come dipendenza. Se `delegate_gemini.py` fallisce per quota/429, il lead esegue il task direttamente invece di insistere o attendere il reset quota.

## Gate di delega

Delegare solo se il task è circoscritto e indipendente, gli input sono allowlistabili, l’accettazione è verificabile, la review costa meno dell’esecuzione diretta e non coinvolge segreti, dati privati o autorità di dominio/statistica.

Output worker: sintesi, assunzioni, file/simboli, proposta/diff, test da eseguire, rischi irrisolti. Niente tutorial, ristampa input, dump file o test inventati.

Opus richiede una nota esplicita su perché Sonnet non basta e quale decisione deve restituire. Tornare a Sonnet per implementazione; evitare cambi frequenti di modello nella stessa sessione.
