# Kit completo per Claude Code — Fantacalcio

Questo pacchetto contiene le istruzioni operative, le specifiche di prodotto, il research design integrale, il regolamento storico, la configurazione corrente dei quattro giri, gli agenti Claude e il wrapper isolato per Gemini CLI.

## 1. Installazione nel repository

Copia **il contenuto** del kit nella root del repository, non la cartella esterna:

```bash
cp -R fantacalcio-project-kit-completo/. /percorso/fantacalcio-asta/
cd /percorso/fantacalcio-asta
git status
```

Se il repository contiene già file con gli stessi nomi, confrontali prima di sovrascriverli.

## 2. Cosa legge Claude e quando

| Livello | File | Effetto |
|---|---|---|
| Sempre attivo | `CLAUDE.md` | Regole permanenti e gerarchia delle fonti |
| Task corrente | `docs/CURRENT_TASK.md` | Scope, criteri di accettazione e permessi |
| Canonico | `docs/*.md`, `config/*.yaml` | Comportamento approvato da implementare |
| On demand | `.claude/skills/*` | Workflow specialistico per asta, dati o Gemini |
| Contesto separato | `.claude/agents/*` | Esplorazione, test e review senza gonfiare il lead |
| Rationale | `docs/research/*` | Ricerca completa da leggere solo per task pertinenti |
| Storico | `docs/archive/*` | Fonte originale che non prevale sulle ADR correnti |

## 3. Prima sessione

Dalla root:

```bash
claude
```

Prompt iniziale consigliato:

```text
Leggi CLAUDE.md, docs/DECISIONS.md, docs/PROJECT_SPEC.md,
docs/AUCTION_RULES.md, docs/OPEN_QUESTIONS.md e config/auction_rules.v1.yaml.
Fai un audit in sola lettura: verifica coerenza, segnala solo i blocchi reali
e proponi le prime tre milestone eseguibili. Non modificare file.
```

## 4. Lavorare task per task

Compila `docs/CURRENT_TASK.md`, poi usa:

```text
Implementa esclusivamente docs/CURRENT_TASK.md. Carica solo le skill pertinenti.
Prima ispeziona il codice e dammi un piano breve; poi implementa, testa e aggiorna
i documenti canonici o DECISIONS.md solo se il comportamento è cambiato.
```

Non chiedere “costruisci tutta l’app”. Un buon task produce una modifica verificabile in una sessione coerente.

## 5. Questioni da decidere prima del motore partita

I quattro giri d’asta sono già configurati. Restano deliberatamente aperti alcuni dettagli del punteggio e dell’amministrazione storica, raccolti in `docs/OPEN_QUESTIONS.md`. Non bloccano data audit, identity layer, motore d’asta o UI pre-asta; bloccano soltanto le parti che richiedono quelle formule esatte.

## 5b. MCP `football-docs` (opzionale, riferimento provider dati)

L'MCP `football-docs` (progetto nutmeg, https://nutmeg.withqwerty.com) espone
documentazione ricercabile di 23 provider di dati calcio (endpoint, sistemi di
coordinate, qualifier ID). E' solo documentazione: non porta dati. Utile quando
si scrive codice di ingest per non indovinare gli schemi.

`.mcp.json` e `.mcp.local.json` sono **gitignored** (ADR-2026-070): contengono un
path assoluto della macchina, non portabile. Setup per macchina:

```bash
npm install -g football-docs
# poi crea .mcp.json nella root con:
# { "mcpServers": { "football-docs": {
#     "command": "node",
#     "args": ["<prefix-npm-globale>/node_modules/football-docs/bin/serve.js"] } } }
```

`npx -y football-docs` a freddo va in timeout (>30 s) alla prima connessione MCP:
usare l'install globale + path esplicito. `resolve_entity` non funziona senza una
credenziale "Reep" (non necessaria per il resto).

## 6. Gemini CLI

Installa e autentica Gemini CLI, poi delega solo tramite il wrapper:

```bash
python scripts/delegate_gemini.py \
  --task-file tasks/GEMINI_TASK_TEMPLATE.md \
  --file src/percorso.py \
  --file tests/test_percorso.py
```

Il wrapper copia in un ambiente temporaneo soltanto i file autorizzati, rimuove variabili sensibili, limita input/output e non applica automaticamente patch.

## 7. Primo ordine di implementazione

1. Bootstrap repository, config loader e validazione YAML.
2. Motore regole/asta deterministico con ledger e replay.
3. Schema dati, registry fonti e identity resolver.
4. Import manuale admin e stato liste `unknown/provisional/official`.
5. Baseline predittive e Monte Carlo del regolamento.
6. Costruttore rosa/formazione e cockpit live.
7. Apprendimento incrementale dei prezzi e domanda avversaria.

La roadmap completa e i quality gate sono in `docs/ROADMAP.md`.
