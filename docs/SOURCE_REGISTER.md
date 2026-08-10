# Registro fonti

Stato verifiche riportato dal research design al 10 agosto 2026. Prima dell’uso reale, archiviare ToS/licenza applicabili, piano e data; verificare di nuovo ciò che può cambiare.

| Fonte | Uso previsto | Accesso/policy | Stato |
|---|---|---|---|
| File admin | regolamento, liste, offerte, assegnazioni, crediti, rose | import manuale; autorità per pool/asta | primario |
| Export Fantacalcio posseduti + archivi community | voto, bonus, ruoli, quotazioni | solo import manuale; niente scraper/private endpoint; tier e provenienza | target privato condizionato |
| Sportmonks | lineup, minuti, eventi, infortuni, quote/xG add-on | API commerciale/trial; audit ≥100 partite | candidato primario |
| API-Football | stessi feed principali | API free/commerciale; challenger sullo stesso campione | candidato challenger |
| Big Balls Sports Data | lineup/eventi/statistiche/xG se disponibile | provider nuovo; audit storico, granularità e contratto | candidato sperimentale |
| Understat | xG, npxG, xA, tiri, minuti | MVP privato con cache/rate limit; non dipendenza irremovibile | ammesso con cautela |
| football-data.co.uk | risultati, statistiche match, quote storiche | CSV scaricabili, automazione permessa (no ToS restrittivo su questo uso) | **verificato 2026-08-10**: ingerito campione stagione 2025/26 (380 righe), 0% missing su colonne chiave, snapshot raw con checksum in `data/raw/football_data_co_uk/`. Vedi `data/outputs/m1_data_quality_report.md`. |
| OpenFootball Italy | fixture/risultati e riconciliazione | CC0, automazione permessa | **verificato 2026-08-10**: ingerito campione stagione 2025-26 (380 righe) da `openfootball/football.json`, 0% missing sui campi chiave. Schema del campo `score` non uniforme (dict con `ft`, lista bare, o null per match non giocati) — gestito esplicitamente nel parser. Vedi `data/outputs/m1_data_quality_report.md`. |
| football-data.org | fixture, risultati, classifiche | API documentata/free | fallback |
| ClubElo | rating/benchmark | fonte di confronto; preferire Elo interno riproducibile | benchmark |
| StatsBomb Open Data | eventi/lineup/xG storici | open data con attribuzione | R&D |
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

## Stato dell'audit provider lineup/minuti/eventi (M1)

Sportmonks e API-Football restano `candidato primario`/`candidato challenger`, non ancora auditati: entrambi richiedono la creazione di un account/trial, azione che un agente automatico non può eseguire (vedi `docs/DECISIONS.md`, categoria azioni vietate). Per sbloccare l'audit comparativo su ≥100 partite richiesto da `docs/ROADMAP.md` M1:

1. Creare un account trial Sportmonks e un account API-Football (il tier gratuito è sufficiente per l'audit).
2. Fornire le due chiavi come variabili d'ambiente, mai committate: `SPORTMONKS_API_KEY`, `API_FOOTBALL_KEY`.
3. Riaprire `docs/CURRENT_TASK.md` per la parte restante di M1.

StatsBomb Open Data e Wyscout public dataset non richiedono account ma restano fuori da questo giro di audit (tier R&D, non prioritari per il campione player-match iniziale); da valutare in un secondo momento con licenza verificata.
