# Registro fonti

Stato verifiche riportato dal research design al 10 agosto 2026. Prima dell’uso reale, archiviare ToS/licenza applicabili, piano e data; verificare di nuovo ciò che può cambiare.

| Fonte | Uso previsto | Accesso/policy | Stato |
|---|---|---|---|
| File admin | regolamento, liste, offerte, assegnazioni, crediti, rose | import manuale; autorità per pool/asta | primario |
| Export Fantacalcio posseduti + archivi community | voto, bonus, ruoli, quotazioni | solo import manuale (download umano dal browser); niente scraper/private endpoint; tier e provenienza | **formato verificato 2026-08-10** su un file reale (`Voti_Fantacalcio_Stagione_2025_26_Giornata_38.xlsx`, singolo download manuale dell'utente). Struttura: 3 fogli (`Fantacalcio`/`Statistico`/`Italia`, tre redazioni), colonne `Cod.` (ID giocatore stabile), `Ruolo`, `Nome`, `Voto` (può avere suffisso `*` = provvisorio), `Gf/Gs/Rp/Rs/Rf/Au/Amm/Esp/Ass`. Parser in `src/fantacalcio/ingest/fantacalcio_voti.py`, **nessuna logica di download/HTTP** — richiede sempre un file già presente sul disco. Il file stesso dichiara "AD USO PERSONALE ESCLUSIVO, NON RIPRODUCIBILE NÉ PUBBLICABILE": mai commitare il contenuto grezzo (già coperto da `.gitignore` su `data/raw|staged|curated`), mai redistribuire. In attesa del set completo di giornate/stagioni (da admin lega o download manuali propri) per l'ingestion storica completa. |
| Sportmonks | lineup, minuti, eventi, infortuni, quote/xG add-on | API commerciale/trial | **verificato 2026-08-10**: piano gratuito ("Football Free Plan", 3000 req/h) attivo ma **non include la Serie A** (solo poche leghe minori, es. Superliga danese, Premiership scozzese) — la ricerca `leagues/search/Serie A` non restituisce risultati. Serve upgrade a pagamento per l'Italia; nessun audit sul campione possibile finché non approvato. |
| API-Football | stessi feed principali; candidato per probabili formazioni (stagione corrente) e storico estero per giocatori trasferiti/neopromossi (`no_history_transfer`/`no_history_new_team`, 84 giocatori in `_m3_replacement_values.csv`) | API free/commerciale | **verificato 2026-08-10**: piano gratuito attivo, 100 richieste/giorno + rate limit per-minuto più stretto (429 osservato a sole 10 chiamate senza spaziatura; throttling a ~1 chiamata/7s applicato in `src/fantacalcio/ingest/api_football.py`), stagioni disponibili limitate a 2022-2024 (stagione corrente richiede piano a pagamento, es. Pro $19/mese verificato 2026-08-12). Audit completo su campione 2023 (380 fixture, 100% match rate e 30 partite di profondità lineup/eventi) in `data/outputs/m1_provider_audit_report.md`. **Aggiornamento 2026-08-12**: l'endpoint `players` (ricerca per nome) rifiuta una ricerca globale senza `team`/`league` — non è possibile "cercare ovunque" un giocatore per nome, serve già sapere il club/lega precedente (confermato con chiamata reale, `data/staged/fantacalcio_voti_manual/_foreign_history_audit.md`). Il nostro listone non ha un campo "club di provenienza", quindi il recupero storico estero richiederebbe un hint per-giocatore fornito dall'utente, non un'integrazione automatica in blocco. |
| Big Balls Sports Data | lineup/eventi/statistiche/xG se disponibile | provider nuovo; audit storico, granularità e contratto | **auditato con chiamate reali 2026-08-10**: account creato dall'utente, API funzionante (200 OK), autenticazione bearer token corretta. Fixture/risultati Serie A disponibili e corretti (dati probabilmente derivati da TheSportsDB, loghi squadra puntano a `r2.thesportsdb.com`). **Ma: lineup non disponibili su 0/20 partite Serie A testate, e stesso esito su Premier League e La Liga (0/2)** — l'endpoint esiste e risponde con lo schema corretto (`meta.available: false`, "coverage is expanding"), ma i dati non sono ancora popolati per nessuna delle leghe controllate, non solo la Serie A. Statistiche di squadra aggregate (possesso, cross, ecc.) sono invece popolate. **Non utilizzabile oggi per il gap lineup/minuti**, nonostante la documentazione lo descriva come disponibile — da ricontrollare periodicamente se "coverage is expanding" si concretizza. |
| Understat | xG, npxG, xA, tiri, minuti | import manuale personale; parser puro, fetch standalone fuori pipeline | **override d'uso personale autorizzato 2026-09-01 (ADR-2026-070)** — vedi sezione dedicata sotto. `robots.txt` resta `Disallow: /`, riconosciuto; nessun fetch automatizzato in pipeline/CI. Prima di questa data: **Escluso** (`robots.txt`, stesso trattamento di Fantacalcio.it). |
| WhoScored | infortuni, squalifiche, probabili formazioni, eventi Opta | import manuale personale; parser puro, fetch standalone fuori pipeline | **override d'uso personale autorizzato 2026-09-01 (ADR-2026-070)** — vedi sezione dedicata sotto. Prima: non automatizzabile (ToS/scraping, sezione sotto). |
| football-data.co.uk | risultati, statistiche match, quote storiche | CSV scaricabili, automazione permessa (no ToS restrittivo su questo uso) | **verificato 2026-08-10**: ingerito campione stagione 2025/26 (380 righe), 0% missing su colonne chiave, snapshot raw con checksum in `data/raw/football_data_co_uk/`. Vedi `data/outputs/m1_data_quality_report.md`. |
| OpenFootball Italy | fixture/risultati e riconciliazione | CC0, automazione permessa | **verificato 2026-08-10**: ingerito campione stagione 2025-26 (380 righe) da `openfootball/football.json`, 0% missing sui campi chiave. Schema del campo `score` non uniforme (dict con `ft`, lista bare, o null per match non giocati) — gestito esplicitamente nel parser. Vedi `data/outputs/m1_data_quality_report.md`. |
| football-data.org | fixture, risultati, classifiche | API documentata/free | fallback |
| ClubElo | rating/benchmark | fonte di confronto; preferire Elo interno riproducibile | benchmark |
| StatsBomb Open Data | eventi/lineup/xG storici | open data con attribuzione, nessun account, nessun rate limit | **verificato 2026-08-10**: Serie A 2015/16 disponibile per intero (380 partite), 100% match rate e 100% score agreement contro football-data.co.uk stessa stagione; profondità evento (titolari, sostituzioni, cartellini, rigori) confermata su 15 partite campione. Nessuna copertura stagione corrente — resta R&D/benchmark, non provider live. Vedi `data/outputs/m1_provider_audit_report.md`. |
| Wyscout public dataset | eventi Serie A 2017/18 | dataset accademico | R&D |
| Wikidata | alias, nascita, nazionalità, ID | CC0; supporto crosswalk | identity support |
| Open-Meteo | meteo | opzionale, solo con beneficio OOS | opzionale |
| Dataset derivati Transfermarkt | trasferimenti/presenze/età/valori | feature isolata, sperimentale e rimovibile | solo sensitivity |

## Fonti non automatizzabili per semplice disponibilità tecnica

Fantacalcio, FBref, Sofascore, WhoScored, Transfermarkt, Understat e siti simili non diventano API autorizzate perché esiste una libreria community. Vietato promuovere endpoint interni/non documentati senza audit di ToS, licenza, robots, caching e derivazione. Evitare dataset Kaggle senza provenienza/licenza verificabile.

## Override d'uso personale — Understat, WhoScored (autorizzato 2026-09-01, ADR-2026-070)

Il project owner autorizza esplicitamente l'uso di dati Understat (xG/npxG/xA/tiri/minuti) e WhoScored (infortuni/squalifiche/probabili formazioni, ed eventualmente eventi Opta) **per il proprio fantacalcio privato locale**, in deroga circoscritta alla riga Understat "Escluso" sopra, alla presente sezione "Fonti non automatizzabili", e alla regola di `CLAUDE.md` "mai scraping di fonti che lo vietano". Understat dichiara `robots.txt: Disallow: /`, riconosciuto e non aggirato in modo automatizzato.

Confine tecnico (contiene il rischio, rende la fonte sostituibile):

- **Parser** (`src/fantacalcio/ingest/understat.py`, `src/fantacalcio/ingest/whoscored.py`): puri, nessun HTTP, richiedono un file già su disco. Stesso pattern di `ingest/fantacalcio_voti.py`.
- **Fetch** (`src/fantacalcio/ingest/understat_fetch.py`, `whoscored_fetch.py`): standalone (`if __name__ == "__main__"` only), rate-limit ≥5 s, cache su disco, snapshot via `ingest/snapshot.py`. **Mai importati** da un modulo di pipeline, da `scripts/run_*` o dalla CI (test statico che lo verifica). Se il project owner non vuole nemmeno il parser committato, si declassa a spec-formato in `docs/` + parser in scratchpad.
- **Grezzo mai committato** (`data/raw|staged` già in `.gitignore`); fixture di test sintetiche, mai contenuto reale.
- **Quality tier**: Understat = C (aggregato, modello xG proprietario, provenienza non-provider-diretta); WhoScored = B/C secondo il campo.
- **`available_time`**: data del match per le statistiche Understat; timestamp del report per infortuni/probabili WhoScored.

Template per fonte (da completare al primo import reale): URL, campi, ufficialità, metodo accesso (manuale), evidenza ToS/robots (archiviata), data verifica, refresh (manuale on-demand), raw snapshot (locale, non committato), mapping ID (via `identity/player_name_resolver.py`, ambigui in coda), fallback (assenza → degradazione al comportamento pre-override), coverage nota (Understat non copre l'intera rosa), errori osservati, stato.

### Understat — riga template (parser committato, primo import reale ancora da fare)

| Voce | Valore |
|---|---|
| URL | `https://understat.com/league/Serie_A/<anno>` (aggregati stagione), `https://understat.com/player/<id>` (tiri) |
| Campi | `games, time (minuti), goals, xG, assists, xA, shots, key_passes, npg, npxG, xGChain, xGBuildup`; tiri: `minute, X, Y, xG, result, situation, shotType, player, player_assisted` |
| Ufficialità | non ufficiale; modello xG proprietario Understat |
| Metodo accesso | **manuale**: pagina salvata a mano dal browser dell'owner; parsing offline con `ingest/understat.py` (puro, zero HTTP). Fetch opzionale via script standalone `ingest/understat_fetch.py` (rate-limit ≥5 s, cache, mai in pipeline/CI). |
| ToS/robots | `robots.txt: Disallow: /` — riconosciuto, non aggirato in automatico; deroga uso personale ADR-2026-070 |
| Data verifica robots | 2026-09-01 (ADR-2026-070) |
| Refresh | manuale on-demand |
| Raw snapshot | locale in `data/raw/understat/` (gitignored), immutabile+checksummed via `ingest/snapshot.write_snapshot` |
| Mapping ID | `identity/player_name_resolver.resolve_against_anchor` role-constrained; ambigui/omonimi stesso ruolo → coda review, mai `player_code` inventato |
| Fallback | assenza xG → `scoring/xg_propensity` peso 0 → Monte Carlo bit-identico allo Stage 2 |
| Coverage | Understat non copre l'intera rosa (portieri e riserve spesso assenti) |
| Errori osservati | nessuno (nessun export reale ancora processato; parser difensivo, assunzioni sul formato JSON incorporato documentate nel docstring di `ingest/understat.py`) |
| Stato | parser + feature + wiring MC spediti **absent-safe, default OFF** (ADR-2026-075); in attesa del primo export reale per il gate |
| Feature prodotte | `xg_per90_shrunk, npxg_per90_shrunk, xa_per90_shrunk, shots_per90_shrunk, minutes_understat, xg_overperformance_shrunk` (tier C, `features/xg_features.py`) |

## Gerarchia per campo

| Campo | Fonte prevalente |
|---|---|
| voto, assist/assist light fantasy | miglior export riconciliato compatibile con la redazione |
| ruolo, quotazione, lista d’asta | file admin; poi export riconciliato |
| offerte, assegnazioni, crediti | file/ledger admin |
| calendario, risultato, squalifiche | fonte ufficiale Lega Serie A |
| lineup, minuti, eventi | provider scelto dopo audit |
| xG/xA | Understat MVP; provider licenziato challenger |
| quote storiche | football-data.co.uk |
| identità | provider principale + Wikidata + review manuale |

## Audit obbligatorio per un provider

Campione identico di almeno 100 partite; copertura di match/giocatori/campi; confronto indipendente di almeno 50 partite; minuti/titolari/sostituzioni/cartellini/rigori/correzioni; latenza; storico/paginazione/limiti; ToS/piano/data; richieste con caching; mapping ID; missingness e drift; decisione primaria/fallback/conflitto documentata con ADR.

Per ogni fonte aggiunta compilare: URL/provider, campi, ufficialità, metodo accesso, permesso automazione, evidenza licenza/ToS, data verifica, refresh, raw snapshot, ID, fallback, coverage, errori osservati e stato.

## Stato dell'audit provider lineup/minuti/eventi (M1) — completato 2026-08-10

Audit eseguito su API-Football (campione reale, stagione 2023) e StatsBomb Open Data (campione reale, stagione 2015/16), entrambi validati contro football-data.co.uk sulla stessa stagione. Sportmonks escluso: il piano gratuito non copre la Serie A, nessun campione possibile senza upgrade a pagamento. Report completo e raccomandazione primario/fallback in `data/outputs/m1_provider_audit_report.md` e ADR-2026-010.

Wyscout public dataset non è stato ancora auditato (non richiede account, rimane candidato R&D per un giro successivo se serve un secondo benchmark storico).

## Quotazioni e statistiche stagionali Fantacalcio.it — verificato 2026-08-10

Due nuovi export manuali dall'admin: `Quotazioni_Fantacalcio_Stagione_2025_26.xlsx` (532 giocatori, ruolo/quotazione/FVM, sia classic che Mantra) e `Statistiche_Fantacalcio_Stagione_2025_26.xlsx` (663 giocatori, statistiche aggregate stagionali: `Pv`=partite a voto, `Mv`=voto medio, `Fm`=fantamedia, bonus/malus totali). Stesso `Id` giocatore dei file voti (verificato: Carnesecchi=4431 in entrambi, join pulito senza mai passare dal nome). Nessun banner di licenza esplicito in questi due file, ma trattati con la stessa cautela "uso personale" dei voti per coerenza di provenienza. Parser in `src/fantacalcio/ingest/fantacalcio_listone.py`.

**Correzione a una precedente affermazione**: il campo `Pv` copre l'universo squadra completo (532-663 giocatori, molto più ampio dei ~330 votati in una singola giornata) e dà quindi un vero segnale di partecipazione **aggregato stagionale** (quante giornate su quelle disputate il giocatore ha ricevuto un voto). Non è granulare giornata-per-giornata (serve comunque una fonte lineup per quello) ma il modello di partecipazione non è più "completamente bloccato" come dichiarato in ADR-2026-012 — è parzialmente sbloccato a livello di tasso stagionale.

**Aggiornamento 2026-08-11**: ricevute (import manuale) le coppie quotazioni/statistiche per **tutte** le stagioni 2021/22-2025/26 (colmando lo storico) più **2026/27** (il listone della prossima asta, 498 giocatori — non ancora giocata, nessun dato voti corrispondente). 12 file, 12/12 parsati senza errori (`scripts/ingest_listone_folder.py`). Cross-check di `Pv` contro il conteggio derivato dai voti ripetuto su tutte le 5 stagioni storiche: correlazione 0.977-0.984, MAE 1.8-2.0 giornate — validazione forte e consistente, non un caso isolato (vedi ADR-2026-014 e `data/staged/fantacalcio_voti_manual/_m2_participation_report.md`, locale).

## Lista admin ufficiale in formato Markdown — verificato 2026-08-15

Nuovo formato di lista admin ricevuto dall'utente (`Liste Fantacalcio 26_27.md`), diverso dagli export xlsx Quotazioni/Statistiche: 9 blocchi `**Lista N (range ruolo)**`, righe `rank. Nome punteggio`, nessun `Id` stabile. Parser in `src/fantacalcio/ingest/admin_list_markdown.py`, stage grezzo (hash SHA-256, nessuna interpretazione) in `data/staged/admin_list_markdown/`. **Lista 1 ("Portieri") è in realtà una quotazione per-squadra** (nomi di club, non giocatori) — confermato dall'utente, taggata `entity_type="team"` per evitare un join errato con `player_code`. Risoluzione identità per le liste 2-9 (giocatori) via `src/fantacalcio/identity/player_name_resolver.py`, stesso pattern di `teams.py` (match esatto/fuzzy con vincolo di ruolo, ambiguità in coda di revisione, mai forzate). Sul file reale: 151/160 giocatori (94%) risolti automaticamente. I 9 rimanenti confermati dall'utente come giocatori reali non ancora nel listone xlsx (`identity_status="new_player_pending_code"`, mai un `player_code` inventato). Integrazione curata (`src/fantacalcio/identity/admin_official_list.py`) in `data/curated/admin_list_2026_27/`: giocatori risolti, nuovi giocatori, blocchi portiere per squadra — sempre oggetti separati, mai fusi in un'unica tabella. Vedi ADR-2026-044, ADR-2026-045.

## Altri provider valutati (ricerca allargata 2026-08-10)

- **FantaMaster, Fantacalcio-Online**: aggregatori che dichiarano di combinare fino a 4 fonti voti — stesso profilo di rischio ToS di Fantacalcio.it, non fonti indipendenti pulite.
- **`www.legaseriea.it/api/`**: 404, nessuna documentazione pubblica per sviluppatori — indica endpoint interno, stessa categoria di rischio dell'endpoint privato Fantacalcio.it già escluso in questa sessione. Non consigliato senza verifica ToS separata.
- **football-data.org**: Serie A inclusa nel piano gratuito, ma **lineup/sostituzioni sono a pagamento** (piano da 29€/mese) — il piano gratuito copre solo classifiche/calendario con dati in ritardo. Non risolve il gap lineup.
- **Big Balls Sports Data**: vedi riga sopra — candidato migliore individuato.
- **Repository GitHub non ufficiali** (scraper FBref: `soccerdata`, `fbref_football_player_data_scraper`, `footballwebscraper`, ecc.): tutti fanno scraping di FBref/Sofascore/WhoScored, stesso problema ToS già discusso per Fantacalcio.it — **non integrati**, stesso standard applicato coerentemente.
- **Dataset Kaggle** (`serie-a-matches-dataset-2020-2025`, `serie-a-2324-team-and-player-insights`, ecc.): dati storici derivati, utili come eventuale ulteriore benchmark R&D ma non per lineup della stagione corrente; licenza da verificare caso per caso prima di un uso reale.
- **`ml-fantacalcio-2024-2025` (GitHub, Lollitor)**: repository con dataset player-level 2024/25 inclusi minuti giocati — verosimilmente costruito anch'esso scrapando Fantacalcio.it/fonti simili; stesso rischio di provenienza, da non riusare direttamente senza verificarne la fonte originale.

## StatsBomb Open Data — copertura multi-lega (scoperta 2026-08-11, non ancora integrata)

Oltre a Serie A 2015/16 (già usato in M1/M2), StatsBomb Open Data copre anche competizioni estere gratis, senza account: **Premier League** (2015/16, 2003/04 — vecchie), **1. Bundesliga** (2023/24 — la più recente e utile, 2015/16), **La Liga** (fino al 2020/21), **Ligue 1** (fino al 2022/23). Nessuna è aggiornata alla stagione corrente. Utile potenzialmente per profilare giocatori trasferiti in Serie A dall'estero senza storico nel nostro dataset (vedi ADR-2026-020, categoria `no_history_transfer`), ma:

- Costruire l'ingestion multi-lega richiede lo stesso lavoro di audit/parsing fatto per Serie A in M1, ripetuto per ciascuna lega.
- Serve risoluzione identità **cross-campionato** (stesso giocatore, nomi/grafie diverse tra fonti) — più complesso del cross-source single-league già fatto.
- Copertura temporale disallineata (Bundesliga 2023/24, Premier League 2015/16) limita l'utilità per profilare trasferimenti recenti.

Non integrato in questa sessione per dimensione del lavoro (paragonabile a un intero M1 aggiuntivo). Candidato per un blocco dedicato futuro se si vuole migliorare la stima per i ~50 giocatori `no_history_transfer` del roster 2026/27.
