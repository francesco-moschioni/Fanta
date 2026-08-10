# Registro fonti

Stato verifiche riportato dal research design al 10 agosto 2026. Prima dell’uso reale, archiviare ToS/licenza applicabili, piano e data; verificare di nuovo ciò che può cambiare.

| Fonte | Uso previsto | Accesso/policy | Stato |
|---|---|---|---|
| File admin | regolamento, liste, offerte, assegnazioni, crediti, rose | import manuale; autorità per pool/asta | primario |
| Export Fantacalcio posseduti + archivi community | voto, bonus, ruoli, quotazioni | solo import manuale (download umano dal browser); niente scraper/private endpoint; tier e provenienza | **formato verificato 2026-08-10** su un file reale (`Voti_Fantacalcio_Stagione_2025_26_Giornata_38.xlsx`, singolo download manuale dell'utente). Struttura: 3 fogli (`Fantacalcio`/`Statistico`/`Italia`, tre redazioni), colonne `Cod.` (ID giocatore stabile), `Ruolo`, `Nome`, `Voto` (può avere suffisso `*` = provvisorio), `Gf/Gs/Rp/Rs/Rf/Au/Amm/Esp/Ass`. Parser in `src/fantacalcio/ingest/fantacalcio_voti.py`, **nessuna logica di download/HTTP** — richiede sempre un file già presente sul disco. Il file stesso dichiara "AD USO PERSONALE ESCLUSIVO, NON RIPRODUCIBILE NÉ PUBBLICABILE": mai commitare il contenuto grezzo (già coperto da `.gitignore` su `data/raw|staged|curated`), mai redistribuire. In attesa del set completo di giornate/stagioni (da admin lega o download manuali propri) per l'ingestion storica completa. |
| Sportmonks | lineup, minuti, eventi, infortuni, quote/xG add-on | API commerciale/trial | **verificato 2026-08-10**: piano gratuito ("Football Free Plan", 3000 req/h) attivo ma **non include la Serie A** (solo poche leghe minori, es. Superliga danese, Premiership scozzese) — la ricerca `leagues/search/Serie A` non restituisce risultati. Serve upgrade a pagamento per l'Italia; nessun audit sul campione possibile finché non approvato. |
| API-Football | stessi feed principali | API free/commerciale | **verificato 2026-08-10**: piano gratuito attivo, 100 richieste/giorno + rate limit per-minuto più stretto (429 osservato a sole 10 chiamate senza spaziatura; throttling a ~1 chiamata/7s applicato in `src/fantacalcio/ingest/api_football.py`), stagioni disponibili limitate a 2022-2024 (stagione corrente richiede piano a pagamento). Audit completo su campione 2023 (380 fixture, 100% match rate e 30 partite di profondità lineup/eventi) in `data/outputs/m1_provider_audit_report.md`. |
| Big Balls Sports Data | lineup/eventi/statistiche/xG se disponibile | provider nuovo; audit storico, granularità e contratto | candidato sperimentale |
| Understat | xG, npxG, xA, tiri, minuti | MVP privato con cache/rate limit; non dipendenza irremovibile | ammesso con cautela |
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
