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
| football-data.co.uk | risultati, statistiche match, quote storiche | CSV scaricabili | produzione |
| OpenFootball Italy | fixture/risultati e riconciliazione | CC0 | produzione |
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
