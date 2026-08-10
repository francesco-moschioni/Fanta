# Prevedere il rendimento nel Fantacalcio: dati, metodi e architettura consigliata

**Stato della ricerca:** 10 agosto 2026  
**Ambito:** Serie A, rendimento stagionale e per giornata, con applicazione al regolamento allegato  
**Destinazione d'uso:** progetto strettamente personale, locale, non commerciale e senza redistribuzione dei dati grezzi.  
**Obiettivo:** costruire previsioni probabilistiche utilizzabili dal futuro motore d'asta, mantenendo tracciate provenienza, qualità e data di disponibilità di ogni dato.

## 1. Conclusione esecutiva

Non conviene prevedere direttamente una sola fantamedia. Il regolamento richiede un modello generativo a componenti, perché attribuisce valore anche al voto base e a bonus collettivi e non lineari. Per ogni calciatore e partita bisogna stimare almeno:

1. probabilità di essere titolare, subentrare o non prendere voto e distribuzione dei minuti;
2. distribuzione del voto base;
3. probabilità o conteggi di gol, assist, assist light, rigori, cartellini e autogol;
4. probabilità di clean sheet e gol subiti;
5. esito e punteggio della partita, necessari per gol vittoria/pareggio;
6. dipendenze tra compagni, necessarie per modificatore difesa, bonus rendimento e fair play.

Queste distribuzioni vengono poi combinate mediante simulazione Monte Carlo con le regole della lega. Il risultato non è solo “7,1 punti attesi”, ma per esempio:

- 7,1 punti medi per giornata a voto;
- 5,8 punti medi per giornata di calendario;
- 76% di probabilità di voto;
- intervallo 10°–90° percentile: 3,5–11,0;
- 181 punti stagionali mediani;
- 22% di rischio di restare sotto 140;
- contributo atteso a modificatore, rendimento e affidabilità della rosa.

La raccomandazione pratica è una pipeline ibrida e pragmatica:

- **target fantasy:** export manuali dell'utente e archivi community dei voti, separati per affidabilità e riconciliati prima del training;
- **feed giocatore-partita:** trial comparativo tra Sportmonks e API-Football, scegliendo in base a copertura effettiva e non alla sola documentazione commerciale;
- **xG e produzione offensiva:** Understat per il prototipo privato, con cache, attribuzione e richieste moderate; eventuale add-on del provider come challenger;
- **risultati, quote e forza squadre:** football-data.co.uk, OpenFootball, football-data.org, ClubElo e un Elo/Dixon–Coles interno;
- **training event-level:** StatsBomb Open Data e dataset pubblico Wyscout;
- **identità e contesto:** Wikidata e Open-Meteo; dataset derivati da Transfermarkt soltanto come feature sperimentali eliminabili;
- **override umani tracciati:** rigoristi, gerarchie, cambi di ruolo, ballottaggi e notizie dell'ultima ora.

Non esiste oggi una fonte gratuita, stabile e unica che fornisca insieme Serie A corrente, eventi granulari, xG/xA, infortuni, probabili formazioni e gli stessi voti di Fantacalcio. Il sistema dovrà quindi integrare fonti diverse e conservare la provenienza di ogni dato. L'assenza di autorizzazione Fantacalcio non blocca l'MVP privato, ma limita la certezza contrattuale e impedisce di trattare un archivio community come fonte ufficiale.

## 2. Cosa significa “rendimento” con questo regolamento

### 2.1 Componenti individuali

Il punteggio individuale contiene:

- voto base;
- gol +3;
- assist +1;
- assist light +0,5;
- gol subito −1 e porta inviolata +1;
- rigore sbagliato −3;
- autogol −2;
- ammonizione −0,5 ed espulsione −1;
- gol del pareggio finale +0,5;
- gol della vittoria finale +1;
- bonus capitano a soglie del voto base.

La previsione di gol e assist non basta. Un difensore da 6,35 con pochi bonus può avere un valore marginale elevato per modificatore, rendimento e capitano. Al contrario, una media calcolata solo sulle partite giocate sovrastima i calciatori con scarsa disponibilità.

### 2.2 Componenti di formazione

Sono necessari output congiunti, non solo previsioni indipendenti:

- modificatore difesa a soglie di 0,25;
- numero di giocatori con voto almeno 6;
- fair play con zero ammoniti;
- probabilità di giocare in inferiorità e bonus compensativo;
- massimo cinque sostituzioni e assenza di switch.

Esempio: usare soltanto i voti medi di quattro difensori per stimare il modificatore è sbagliato. Serve la distribuzione congiunta dei loro voti e della loro presenza, perché una media attesa di 6,25 non implica una probabilità del 100% di superare la soglia 6,25.

### 2.3 Orizzonti distinti

Vanno prodotti tre forecast diversi:

- **pre-asta/stagionale:** 38 giornate, molta incertezza su titolarità, trasferimenti e infortuni;
- **rolling 3–6 giornate:** utile per valutare calendario e forma strutturale;
- **settimanale:** incorpora probabili formazioni, convocazioni, squalifiche e quote aggiornate.

Il modello stagionale non deve semplicemente moltiplicare la previsione della prima giornata per 38.

## 3. Strategia delle fonti per il progetto privato

### 3.1 Matrice operativa

| Fonte | Serie A | Contenuto utile | Accesso | Uso nel progetto |
|---|---|---|---|---|
| [Sportmonks](https://www.sportmonks.com/football-api/serie-a-api/) | Sì | Lineup, minuti, eventi, statistiche, infortuni, quote e xG con add-on | API commerciale con trial | **Candidato principale**, subordinato ad audit su più stagioni |
| [API-Football](https://www.api-football.com/pricing/) | Sì | Fixtures, eventi, lineup, trasferimenti, infortuni, statistiche e quote | Free tier e piani commerciali | **Challenger di Sportmonks** sullo stesso campione di partite |
| [Understat](https://understat.com/league/Serie_A) | Dal 2014/15 | xG, npxG, xA, tiri, minuti, titolarità e dati di squadra | Sito non ufficiale; librerie community | **Ammesso per MVP privato**, con cache e rate limiting; non dipendenza irremovibile |
| [football-data.co.uk](https://www.football-data.co.uk/italym.php) | Sì, storico lungo | Risultati, statistiche match-level e quote storiche | CSV scaricabili | **Produzione** per team strength, quote e backtest |
| [OpenFootball Italy](https://github.com/openfootball/italy) | Sì | Fixtures, giornate e risultati | CC0 | **Produzione** per test e riconciliazione |
| [football-data.org](https://www.football-data.org/coverage) | Sì | Calendario, risultati e classifiche | API documentata con piano gratuito | **Fallback** per fixture e risultati |
| [ClubElo](http://clubelo.com/) | Sì | Rating storici e probabilità partita | Endpoint pubblici | **Feature e benchmark**, non target |
| [StatsBomb Open Data](https://github.com/hudl/open-data) | 2015/16 e 1986/87 | Eventi, lineup, xG e metadati | Open data con attribuzione | **R&D e training event-level**, non feed corrente |
| [Wyscout public event dataset](https://www.nature.com/articles/s41597-019-0247-7) | 2017/18 | Eventi spaziotemporali, giocatori e minuti | Dataset accademico | **R&D su xG/xA e ruoli**, ma non corrente |
| Fantacalcio: export e archivi community | Storico frammentario | Ruoli, voto base, bonus/malus, quotazioni | File manuali e repository | **Target fantasy privato**, dopo audit e assegnazione del quality tier |
| Dataset derivati da Transfermarkt | Ampia | Trasferimenti, presenze, lineup, valori ed età | Dataset community derivati da scraping | **Solo feature sperimentali**, isolate e rimovibili |
| [Wikidata](https://www.wikidata.org/wiki/Wikidata:Licensing) | Variabile | Alias, nascita, nazionalità e ID esterni | CC0 | **Identity matching**, non fonte canonica per ruolo o squadra |
| [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api) | Tutti gli stadi | Meteo storico e forecast storico | API | **Opzionale**, solo se migliora l'out-of-sample |

### 3.2 Fantacalcio e archivi community: policy privata

Fantacalcio pubblica statistiche stagionali dal 2015/16 e pagine di voti per giornata. Sono esattamente le etichette che servono per imparare il voto editoriale. Tuttavia i [Termini di utilizzo, versione giugno 2026](https://www.fantacalcio.it/termini-e-condizioni), sezione Navigazione 3, vietano l'uso di software o altri meccanismi per copiare/accedere ai contenuti, incluso lo scraping, senza autorizzazione scritta; vietano inoltre copia, elaborazione e divulgazione dei contenuti senza autorizzazione.

Il progetto è esclusivamente personale, locale, non commerciale e non redistribuito. Questo consente una policy tecnica più pragmatica, ma non trasforma automaticamente i contenuti in open data e non annulla i termini della fonte.

Conseguenze operative:

- una pagina pubblicamente visibile non equivale a open data;
- non va costruito uno scraper Fantacalcio come componente del prodotto;
- il pulsante “Scarica” non va interpretato automaticamente come licenza a costruire e ridistribuire un database derivato;
- non verranno creati scraper Fantacalcio, chiamati endpoint privati o aggirate autenticazioni e protezioni;
- l'utente può importare manualmente export già posseduti e archivi community nel database locale;
- gli archivi community possono alimentare training e backtest privati, ma la loro qualità e provenienza devono restare visibili;
- nessun dato grezzo o database derivato verrà pubblicato o redistribuito;
- un'eventuale autorizzazione scritta resta un miglioramento desiderabile, non un blocco per lo sviluppo.

Senza un archivio omogeneo del voto esatto della redazione usata dalla lega, si può prevedere una proxy di performance, ma non si può onestamente sostenere di prevedere quel voto con precisione misurata.

### 3.3 API-Football

Il [piano ufficiale](https://www.api-football.com/pricing/) gratuito offre 100 richieste al giorno e include tutte le competizioni e tutti gli endpoint, ma limita le stagioni disponibili. Sono elencati: fixtures, eventi, lineups, giocatori, trasferimenti, sidelined, injuries, statistiche, predictions e quote. La [coverage](https://www.api-football.com/coverage/) include la Serie A.

Punti forti:

- un solo schema per dati correnti e molte leghe, utile per nuovi acquisti provenienti dall'estero;
- infortuni, trasferimenti e lineup nello stesso sistema di ID;
- abbastanza per aggiornamenti giornalieri se si scaricano endpoint bulk, si usa paginazione con criterio e si memorizzano risposte immutabili.

Limiti:

- 100 richieste/giorno non sono sufficienti per un backfill ingenuo di molte stagioni;
- la disponibilità delle stagioni free può cambiare;
- il provider dichiara dati “as is”, senza garanzia di disponibilità/accuratezza;
- non fornisce automaticamente diritti di pubblicazione sui dati delle competizioni;
- le sue statistiche/ratings non coincidono necessariamente con i voti Fantacalcio.

Strategia: usare il free tier per il prototipo; se l'audit è positivo, un solo mese Pro da 19 dollari può essere più economico del tempo necessario ad aggirare i limiti di backfill, fermo restando il tema licenze.

### 3.4 Big Balls Sports Data

La pagina [Serie A API](https://bigballsdata.com/serie-a-api) dichiara 1.000 richieste/giorno gratuite, tutte le 20 squadre, punteggi, quote, lineup, standings, eventi e statistiche, incluso xG quando il feed upstream lo fornisce. Le lineup confermate arriverebbero tipicamente circa 60 minuti prima del calcio d'inizio.

È molto interessante per un progetto hobby, ma non va ancora usata come unica fonte perché:

- è un provider relativamente nuovo;
- “xG quando disponibile” può generare missingness non casuale;
- bisogna verificare quanto storico Serie A sia realmente interrogabile;
- bisogna testare se le statistiche sono solo team-level o sufficientemente player-level;
- va letto e archiviato il contratto applicabile al momento della registrazione;
- occorre confrontare almeno 50 partite con una seconda fonte e monitorare correzioni retroattive.

### 3.5 StatsBomb Open Data

Il repository [StatsBomb Open Data](https://github.com/hudl/open-data) contiene JSON per competizioni, partite, lineup ed eventi e richiede attribuzione quando si pubblicano analisi. Il file competizioni, verificato il 10 agosto 2026, include Serie A 2015/16 e 1986/87. È un dataset event-level di alta qualità, ottimo per:

- costruire o studiare xG;
- tiri, passaggi, pressioni, duelli e azioni difensive;
- feature di ruolo e stile;
- simulazione di eventi e modelli di rating tipo PlayeRank.

Non risolve:

- giocatori correnti;
- voto Fantacalcio;
- infortuni e probabili formazioni correnti;
- storico multi-stagione recente della Serie A.

### 3.6 Dataset Wyscout pubblico

Il [dataset Scientific Data](https://www.nature.com/articles/s41597-019-0247-7) contiene circa 1.682 eventi medi per partita e copre competizioni europee, inclusa la Serie A 2017/18. Gli eventi includono posizione, tempo, esito, calciatore e caratteristiche. È utile per imparare modelli generali e confrontare feature, non per assegnare direttamente un valore a un giocatore 2026/27.

### 3.7 Risultati, quote ed Elo

[football-data.co.uk](https://www.football-data.co.uk/data.php) offre gratuitamente CSV storici con risultati, statistiche di partita e quote. Per questo progetto le quote sono molto preziose: aggregano informazioni su forza delle squadre, casa/trasferta, indisponibilità e aspettative di mercato. Vanno trasformate in probabilità senza margine bookmaker.

Conviene comunque costruire internamente:

- Elo dinamico con vantaggio casa e decay temporale;
- modello Dixon–Coles sui gol;
- forza attacco/difesa separata;
- rating della squadra con e senza alcuni titolari, solo quando i dati lo consentono.

ClubElo può essere una fonte di confronto, ma un Elo interno è più riproducibile e riduce la dipendenza da condizioni d'uso non chiare.

### 3.8 Fonti da non automatizzare senza permesso

Understat, FBref, Sofascore, WhoScored, Transfermarkt e siti simili sono spesso chiamati impropriamente “API gratuite”. Molti pacchetti Python non fanno altro che interrogarne endpoint interni o effettuare scraping. L'esistenza del codice non garantisce licenza, stabilità o autorizzazione.

Regola di progetto:

- nessun endpoint interno/non documentato entra in produzione solo perché risponde;
- controllare termini, robots, licenza e possibilità di caching/derivazione;
- documentare la provenienza a livello di campo;
- evitare dataset Kaggle senza provenienza e licenza verificabili;
- preferire esportazioni autorizzate, API documentate e open data con licenza esplicita.

### 3.9 Livelli di qualità e provenienza

La provenienza deve essere registrata anche quando il dato è usato soltanto in locale:

```text
quality_tier = A  # export diretto o provider documentato, completo e riconciliato
quality_tier = B  # archivio community completo, coerente e riconciliato
quality_tier = C  # aggregato, incompleto o di origine incerta
```

- i dati `A` e `B` possono entrare nel training partita-per-partita;
- i dati `C` servono a sviluppo dei parser, controlli aggregati e analisi di sensibilità;
- il modello deve poter essere riaddestrato escludendo intere fonti o tier;
- ogni record conserva `source_name`, `source_record_id`, `event_time`, `available_time`, `ingested_time`, `source_version`, `source_file_hash` e `quality_status`;
- il raw importato resta immutabile; deduplicazione, correzioni e crosswalk avvengono nel livello normalizzato.

Gerarchia in caso di conflitto:

| Campo | Fonte prevalente |
|---|---|
| Voto base, assist e assist light fantasy | Miglior export Fantacalcio disponibile e riconciliato |
| Ruolo, quotazione e liste d'asta | File ufficiale dell'admin; in subordine export Fantacalcio |
| Liste, offerte, assegnazioni e crediti | File dell'admin della lega |
| Calendario, risultato e squalifiche | Fonte ufficiale Lega Serie A |
| Formazione, minuti ed eventi | Provider principale scelto dopo audit |
| xG/xA | Understat per MVP; provider licenziato come challenger |
| Quote storiche | football-data.co.uk |
| Identità | Provider principale + crosswalk Wikidata e manuale |

## 4. Modello predittivo consigliato

### 4.1 Struttura generale

Per il calciatore `i` nella partita `m`:

\[
P(FP_{im}) = \sum_{s,\,t,\,e,\,v} P(s,t,e,v\mid X_{im})\;g(s,t,e,v,\text{regole})
\]

dove:

- `s` = stato di partecipazione (titolare, subentro, nessun voto);
- `t` = minuti;
- `e` = eventi;
- `v` = voto base;
- `g` = motore deterministico del regolamento.

In pratica non si calcola la somma analiticamente: si generano migliaia di scenari coerenti e si applicano le regole a ogni scenario.

### 4.2 Modulo A — disponibilità, titolarità e minuti

È spesso il modulo più importante. Gli eventi per 90 non valgono nulla se un calciatore non gioca.

Target a due stadi:

1. classificazione: titolare / subentra / non gioca;
2. distribuzione dei minuti condizionata allo stato.

Feature pre-match:

- ultime 5–10 presenze, partenze e minuti, con decay;
- posizione nella gerarchia e concorrenza nello stesso ruolo;
- allenatore, modulo e cambi recenti;
- giorni di riposo e congestione, trasferte europee e coppe;
- infortunio/squalifica/convocazione;
- età, rientro da stop e carico recente osservabile;
- importanza e difficoltà dell'incontro;
- partenza del concorrente diretto o nuovo acquisto;
- probabilità delle probabili formazioni, se disponibile legalmente.

Metodi:

- baseline: regressione logistica multinomiale + curve empiriche dei minuti;
- MVP forte: CatBoost/LightGBM/XGBoost per stato, regressione quantile o survival/hazard per minuti;
- gerarchico: effetti casuali di giocatore, squadra, allenatore e ruolo;
- override manuale con scadenza e autore per notizie non strutturate.

Per gli infortuni non bisogna fingere una precisione medica che i dati pubblici non consentono. La letteratura sull'injury prediction usa carichi di allenamento e dati fisici spesso privati. Con dati pubblici è più difendibile modellare “availability status + tempo tipico di rientro + scenari” che un rischio clinico individuale preciso.

### 4.3 Modulo B — gol, assist e rigori

Non stimare i gol futuri con la sola media dei gol passati. Gli xG sono più stabili perché misurano quantità e qualità delle occasioni. Uno [studio PLOS One](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0282295) mostra che xG può prevedere la performance futura meglio di statistiche tradizionali; modelli gerarchici come [Bayes-xG](https://arxiv.org/abs/2311.13707) permettono di separare qualità del tiro ed effetto del giocatore con shrinkage.

Struttura suggerita:

- occasioni/tiri per 90: Poisson o negative binomial con offset dei minuti;
- xG per tiro: modello fornito o logistic/gradient boosting su posizione, angolo, body part, assist type e contesto;
- conversione: effetto giocatore gerarchico, fortemente shrinkato verso ruolo/lega;
- assist: modello di chance creation e xA, non solo assist realizzati;
- rigori: probabilità che la squadra ne ottenga uno × probabilità che il giocatore sia in campo × quota nella gerarchia × conversione;
- avversario: forza difensiva, casa/trasferta e lineup prevista;
- nuovi campionati: partial pooling per ruolo, età e forza della lega, con intervalli più larghi.

Conteggi rari e overdispersion rendono la negative binomial spesso più adatta della regressione lineare. Zero-inflated/hurdle models possono aiutare, ma vanno confrontati fuori campione: la complessità non è un valore in sé.

### 4.4 Modulo C — risultato, clean sheet e gol subiti

Il modello [Dixon–Coles](https://academic.oup.com/jrsssc/article-abstract/46/2/265/6990546) parte da intensità di gol Poisson dinamiche per attacco, difesa e vantaggio casa, correggendo i punteggi bassi correlati.

Input:

- risultati pesati temporalmente;
- xG/xGA, se disponibili;
- Elo e casa/trasferta;
- giorni di riposo e congestione;
- forza della lineup prevista;
- probabilità bookmaker depurata dal margine.

Output:

- distribuzione del punteggio;
- probabilità di clean sheet;
- gol subiti attesi dal portiere;
- probabilità vittoria/pareggio;
- probabilità che un eventuale gol del calciatore sia quello che determina pareggio o vittoria.

Per il bonus gol decisivo, la soluzione più coerente è simulare numero, ordine e marcatori dei gol. Un'approssimazione più semplice può essere validata, ma deve essere dichiarata.

### 4.5 Modulo D — cartellini, autogol e fair play

- ammonizioni: Bernoulli o Poisson per minuto con ruolo, arbitro, avversario, intensità attesa, falli e storico shrinkato;
- espulsioni/autogol: eventi rarissimi, prior gerarchici molto forti; evitare stime individuali rumorose;
- fair play: simulare cartellini dei giocatori schierati con un fattore comune di partita/arbitro, non moltiplicare probabilità indipendenti senza correzione.

### 4.6 Modulo E — voto base

È il problema più specifico e difficile. Il voto è editoriale, discretizzato e dipende da ruolo, risultato, eventi visibili e narrazione della partita. Inoltre lo stesso match può ricevere voti diversi da testate diverse.

Target consigliato:

- distribuzione ordinale su 4,0; 4,5; …; 8,0+, oppure
- regressione eteroschedastica/quantile con arrotondamento coerente.

Feature **disponibili prima della partita** per il forecast:

- livello latente del calciatore stimato da voti passati con shrinkage;
- ruolo effettivo e posizione prevista;
- forza propria e avversaria;
- probabilità di risultato e clean sheet;
- minuti attesi;
- forma laggata, xG/xA/xT e azioni difensive laggate;
- casa/trasferta, riposo, allenatore e modulo;
- distribuzioni attese degli eventi della partita.

Una seconda rete/modello può tradurre gli eventi **simulati** in voto. Non vanno usate statistiche realizzate nella partita che si sta predicendo: sarebbe leakage.

La letteratura offre due famiglie utili:

- [PlayeRank](https://dl.acm.org/doi/fullHtml/10.1145/3343172): valutazione role-aware basata su eventi, confrontata con scout;
- plus-minus regolarizzato, incluso [xG plus-minus](https://livrepository.liverpool.ac.uk/3063562/), per isolare contributi al netto dei compagni.

Queste metriche sono feature o priors, non sostituti automatici del voto Fantacalcio. Il mapping finale va imparato sui voti esatti della fonte della lega.

Modello MVP raccomandato: ordinal logistic/mixed model interpretabile per ruolo; benchmark con CatBoost quantile. Se il boosting non migliora realmente la validazione temporale e la calibrazione, tenere il modello semplice.

### 4.7 Bonus rendimento, capitano e modificatore

Per ogni scenario simulato:

1. selezionare formazione e sostituzioni secondo il regolamento;
2. generare presenze, eventi e voti correlati;
3. calcolare il capitano a soglie;
4. calcolare numero di voti ≥6;
5. calcolare media difesa secondo la formula definitiva;
6. calcolare fair play e compensazioni;
7. sommare i punti e trasformarli in gol di lega.

Il valore di un calciatore include quindi anche:

\[
V_i = E[FP_i] + E[\Delta bonus\ di\ rosa\mid i] + E[\Delta copertura\mid i]
\]

Il termine marginale deve essere misurato confrontando simulazioni della rosa con e senza il giocatore, a parità di resto.

## 5. Feature engineering completo

### Giocatore

- età e curva età per ruolo;
- ruolo Classic e ruolo effettivo;
- minuti, partenze, presenze e sostituzioni;
- tiri, tiri in area, xG, xA, key passes, tocchi in area;
- rigori e piazzati;
- passaggi progressivi, xT/VAEP se ricostruibili;
- duelli, intercetti, tackle, errori, falli;
- cartellini;
- voti laggati e volatilità;
- infortuni/assenze osservate;
- trasferimento, nuova lega, nuovo allenatore;
- concorrenza nel ruolo.

### Squadra e partita

- Elo e forza attacco/difesa;
- xG/xGA rolling con regressione verso la media;
- ritmo, possesso e stile;
- casa/trasferta;
- difficoltà avversario;
- quote 1X2, over/under e clean sheet implicite;
- riposo, coppe, viaggi e congestione;
- arbitro e tassi cartellini/rigori;
- meteo estremo;
- lineup prevista e assenze.

### Tempo e recency

- rolling windows 3/5/10 gare;
- exponential decay;
- separazione tra stagione corrente e precedenti;
- cambio di regime per allenatore, squadra, ruolo o grave infortunio;
- snapshot “as known at prediction time”.

### Variabili manuali necessarie

Alcune informazioni ad alto valore non sono affidabilmente disponibili come open data:

- gerarchie rigoristi e piazzati;
- ballottaggi e probabilità soggettive;
- cambio tattico annunciato;
- minutaggio pianificato dopo rientro;
- eventuale trasferimento imminente;
- definizione Fantacalcio di assist light e ruoli del listone.

Devono entrare tramite una tabella override versionata, con fonte, autore, timestamp, scadenza e grado di confidenza.

## 6. Metodi da confrontare, non da scegliere per moda

### Baseline obbligatorie

1. media ultima stagione;
2. media pesata di 2–3 stagioni;
3. per-90 × minuti attesi;
4. media di ruolo/squadra per giocatori con pochi dati;
5. quotazione/FVM fornita dall'utente come benchmark, non come feature se si vuole misurare valore informativo indipendente;
6. probabilità bookmaker per esiti di squadra.

### Modelli statistici

- regressione lineare/regularizzata per target continui;
- ordinal logistic per voto;
- logistic/multinomial per presenza;
- Poisson, negative binomial, hurdle e zero-inflated per eventi;
- modelli gerarchici Bayesiani per partial pooling;
- survival/hazard per disponibilità e minuti;
- Dixon–Coles per scoreline;
- stato-spazio/Elo dinamico per forza squadra e forma latente.

### Machine learning tabellare

- CatBoost, LightGBM, XGBoost;
- Random Forest/Extra Trees come benchmark;
- ensemble per ruolo e target.

Il recente progetto accademico [OpenFPL](https://arxiv.org/html/2508.09992v1) usa ensemble separati per posizione di XGBoost e Random Forest su dati pubblici FPL e Understat e li valuta prospetticamente. È una prova utile che modelli tabellari ben costruiti possono competere con servizi commerciali; non prova che la stessa architettura sia ottimale per Serie A o per il voto editoriale.

### Deep learning

LSTM, TCN e Transformer possono modellare sequenze, ma hanno senso solo dopo:

- abbastanza stagioni omogenee;
- identità e feature stabili;
- baseline tabellari forti;
- validazione temporale rigorosa.

Per circa 20 squadre × 38 giornate e target rari, un modello profondo può imparare rumore e cambi di regime. Non è la scelta MVP.

### NLP su news

Possibile modulo futuro:

- classificazione di infortunio, convocazione, ballottaggio e gerarchia;
- estrazione entità giocatore/squadra;
- aggiornamento di probabilità, non decisione deterministica.

Problemi: copyright delle news, errori di entità, indiscrezioni contraddittorie e timestamp. Meglio iniziare con inserimento umano strutturato.

## 7. Validazione corretta

### 7.1 Split temporale

Mai random split tra righe di più stagioni. La documentazione [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) ricorda che i metodi casuali possono addestrare sul futuro e testare sul passato.

Schema:

- train expanding window;
- validation sulle giornate successive;
- test finale su un'intera stagione mai toccata;
- valutazione separata del pre-asta con snapshot congelato alla data dell'asta;
- nested temporal CV per tuning;
- gap quando una feature viene pubblicata con ritardo.

### 7.2 Prevenzione leakage

Per ogni feature conservare `event_time`, `available_time` e `ingested_time`. Una statistica della giornata è utilizzabile solo se `available_time` precede il momento della previsione.

Leakage tipici:

- usare minuti o lineup reali della partita da prevedere;
- usare una media stagionale ricalcolata includendo la partita target;
- usare quotazioni aggiornate dopo il match;
- imputare in base a statistiche future;
- risolvere trasferimenti con la squadra finale della stagione;
- ottimizzare sugli stessi dati usati per calibrare le probabilità.

### 7.3 Metriche per componente

| Target | Metriche principali |
|---|---|
| presenza/titolarità | log loss, Brier, curve di calibrazione, PR-AUC per classi rare |
| minuti | MAE, pinball loss, copertura degli intervalli |
| gol/assist/cartellini | Poisson deviance o log likelihood, Brier per almeno un evento, calibrazione |
| voto base | MAE, ranked probability score, accuracy entro 0,5, calibrazione delle code |
| punti fantasy | MAE/RMSE, CRPS o log score della distribuzione, calibrazione dei quantili |
| ranking asta | Spearman, NDCG/top-k recall, regret rispetto al miglior portafoglio ex post |
| stagione/rosa | punti simulati vs reali, bonus catturati, partite in inferiorità, decision regret |

Per probabilità d'acquisto e scenari d'asta, la calibrazione conta più dell'accuracy secca. [Gneiting e Raftery](https://academic.oup.com/jrsssb/article/69/2/243/7109375) distinguono calibrazione e sharpness e raccomandano proper scoring rules; la documentazione [scikit-learn](https://scikit-learn.org/stable/modules/calibration.html) richiama Brier e log loss.

### 7.4 Backtest realistico

Ogni backtest deve ricreare ciò che era noto alla data dell'asta:

- listone e ruoli di allora;
- rose e allenatori di allora;
- infortuni e mercato noti allora;
- quote disponibili allora;
- regolamento di quella stagione;
- nessun dato futuro.

Il confronto decisivo non è solo errore medio per giocatore, ma:

> se avessimo usato il modello all'asta, la rosa scelta avrebbe ottenuto più valore della strategia baseline, a budget e vincoli uguali?

## 8. Incertezza e simulazione

### Fonti di incertezza

- **aleatoria:** gol, assist, cartellini e voto nella singola gara;
- **epistemica:** pochi dati su giovani/nuovi acquisti;
- **di regime:** trasferimento, cambio allenatore o ruolo;
- **di disponibilità:** infortunio e turnover;
- **di fonte:** dato mancante o corretto in ritardo;
- **di mercato:** ruolo/listone o rosa non definitiva.

Output obbligatori:

- media, mediana e quantili;
- probabilità di voto e di almeno N presenze;
- intervallo stagionale;
- confidence grade basato su quantità/qualità dei dati;
- scenari basso/base/alto separati da una distribuzione statistica.

La conformal prediction può aggiungere intervalli empirici, ma per serie temporali non va applicata ingenuamente: la dipendenza temporale viola l'exchangeability classica. Usarla solo con calibrazione rolling/adattiva e controllare la copertura nel tempo.

## 9. Architettura dati

### Tabelle minime

- `players`, `teams`, `competitions`, `seasons`;
- `player_identity_map` per gli ID delle fonti;
- `fixtures` e `fixture_snapshots`;
- `lineups`, `availability`, `injuries`, `transfers`;
- `player_match_stats`, `team_match_stats`, `events`;
- `fantasy_votes`, `fantasy_events`, `fantasy_roles`;
- `odds_snapshots`, `weather`;
- `manual_overrides`;
- `model_features_asof`, `predictions`, `prediction_intervals`;
- `auction_rounds`, `auction_pools` e `auction_pool_versions`;
- `auction_events`, `auction_team_state`, `market_price_snapshots` e `opponent_market_profiles`;
- `roster_scenarios`, `scenario_players`, `locked_players` e `lineup_scenarios`;
- `source_registry` e `data_quality_issues`.

### Regole ingegneristiche

- raw data immutabili, normalizzazione separata;
- cache aggressiva e chiamate incrementali;
- snapshot delle quote e delle probabili formazioni;
- ID interni stabili e mapping con intervalli di validità;
- test su completezza, unicità, range, lineup e somma minuti;
- versionamento di dataset, feature e modello;
- ogni previsione riproducibile con un `as_of_timestamp`;
- niente nomi come chiave primaria.

### Audit iniziale delle API

Prima di sviluppare il modello, per ciascuna API candidata:

1. scaricare una stagione/giornata campione;
2. contare copertura partite e giocatori;
3. confrontare 50 partite con fonte indipendente;
4. verificare minuti, titolari, sostituzioni, cartellini, rigori e correzioni;
5. misurare ritardo di aggiornamento;
6. verificare storico, paginazione e limiti reali;
7. archiviare termini, data e piano;
8. stimare richieste/giorno con caching;
9. decidere fonte primaria, fallback e regola di conflitto.

## 10. Roadmap consigliata

### Fase 0 — regole e raccolta dei file

- definizione esatta del voto usato dalla lega;
- definizione assist light;
- formula esatta modificatore;
- fonte ufficiale di ruoli e quotazioni;
- trattamento SV e bonus compensativo;
- definizione della policy locale per export e archivi community;
- raccolta dei file storici delle aste e delle rose.
- gestione esplicita delle liste top ancora ignote, provvisorie e definitive.

### Fase 1 — data audit (1–2 settimane)

- attivare i trial di Sportmonks e API-Football;
- testarli sullo stesso campione di almeno 100 partite e costruire il dizionario campi;
- importare un campione Understat e verificare copertura, stabilità degli ID e missingness;
- importare StatsBomb Serie A 2015/16 e Wyscout 2017/18;
- importare football-data.co.uk;
- creare identity resolver;
- produrre report di copertura e anomalie.

### Fase 2 — baseline (2–3 settimane)

- modello Elo/Dixon–Coles;
- previsione minuti semplice;
- per-90 shrinkato per gol/assist/cartellini;
- voto medio gerarchico, se le etichette sono disponibili;
- simulatore del regolamento;
- forecast stagionale con intervalli.

### Fase 3 — MVP serio (3–5 settimane)

- boosting per ruolo e target;
- probabilità calibrate;
- xG/xA e quote;
- Monte Carlo con dipendenze di squadra;
- backtest temporale e ablation study;
- dashboard con valore atteso, floor, ceiling e rischio.
- costruttore visuale della rosa e dell'undici, con giocatori bloccati e modulo scelto o ottimizzato.

### Fase 4 — avanzata

- modello ordinale del voto da eventi simulati;
- trasferimento cross-league per nuovi acquisti;
- NLP news autorizzato;
- aggiornamenti live e override;
- valore marginale nella rosa e collegamento al motore d'asta.
- apprendimento online dei prezzi d'asta e profili di spesa avversari.

## 11. Decisione raccomandata sulle fonti

### Stack pragmatico iniziale

1. **File admin:** regolamento, liste, offerte, assegnazioni, crediti, rose e storico della lega.
2. **Export manuali e archivi community Fantacalcio:** target, ruoli e quotazioni, sempre con provenienza e quality tier.
3. **Trial Sportmonks contro API-Football:** stesso campione di almeno 100 partite per scegliere il feed di lineup, minuti, eventi e infortuni.
4. **Understat:** xG/xA e produzione offensiva per il prototipo privato.
5. **football-data.co.uk:** storico di risultati, statistiche match-level e quote.
6. **OpenFootball + football-data.org:** riconciliazione gratuita di fixture e risultati.
7. **ClubElo + Elo/Dixon–Coles interno:** forza squadra e benchmark.
8. **StatsBomb + Wyscout open:** sviluppo e validazione delle feature event-level.
9. **Wikidata:** supporto al crosswalk delle identità.
10. **Open-Meteo e dataset Transfermarkt derivati:** moduli opzionali, ammessi solo se migliorano le metriche fuori campione.

### Principio di degradazione controllata

Il sistema deve funzionare anche quando una fonte manca. Senza un voto Fantacalcio omogeneo produce una **proxy fantasy** chiaramente etichettata; senza xG usa baseline per-90 shrinkate; senza quote usa Elo/Dixon–Coles; senza infortuni applica lo stato manuale. La dashboard deve mostrare quali moduli sono attivi e quanto sono aggiornati.

## 12. Questioni ancora da chiudere nel regolamento

Per implementare il motore servono risposte deterministiche:

- quale fonte/redazione assegna voto, assist e assist light;
- esatta definizione di “contributo al gol”;
- quali voti entrano nel modificatore (portiere + migliori tre difensori? tutti?);
- trattamento dei difensori senza voto e sostituzioni;
- fair play: zero ammoniti tra quali giocatori;
- bonus compensativo definitivo: 3,5, proposta 4,5–5,5 o altra formula;
- doppia formulazione seconda fase: fino a 5 o fino a 6 calciatori;
- numero di preferenze prima fase: 5 o 6;
- regola amministrativa esatta per completamento rose;
- composizione definitiva delle liste top e momento in cui diventano ufficiali.

### Struttura d'asta corrente da implementare

La specifica di lavoro più recente prevede quattro giri; prevale sul testo storico allegato ai fini della progettazione, ma deve restare versionata perché potrebbe cambiare:

| Giro | Modalità | Pool | Budget disponibile |
|---|---|---|---|
| G1 | Busta chiusa | Blocco portieri + top 60 difensori | 200 |
| G2 | Busta chiusa | Top 60 centrocampisti + top 40 attaccanti | Residuo G1 + 100 |
| G3 | Asta aperta | Giocatori rimanenti | Residuo G2 + 40 |
| G4 | Asta aperta | Giocatori rimanenti | Residuo G3 |

Il motore e l'interfaccia non devono hardcodare questi valori: round, pool, incremento di budget, modalità e vincoli vanno letti dal file YAML del regolamento versionato.

### Liste top non ancora note

La composizione reale delle liste top non è ancora disponibile e il testo allegato dichiara che la struttura storica potrebbe cambiare. L'applicazione deve quindi distinguere senza ambiguità tre stati:

| Stato | Significato | Uso consentito |
|---|---|---|
| `unknown` | l'admin non ha ancora comunicato la lista | nessun vincolo di eleggibilità; solo simulazioni per scenario |
| `provisional` | lista stimata dal modello o ricostruita da ranking/quotazioni | preparazione, shortlist e analisi di sensibilità |
| `official` | lista importata dal file dell'admin | unica fonte valida per pool, preferenze e offerte reali |

Il ranking tecnico del modello e la lista ufficiale d'asta sono oggetti separati. Un giocatore può essere molto forte per il modello ma non apparire nella lista top dell'admin, o viceversa. Quando la lista è ignota, il sistema deve:

- produrre liste provvisorie con probabilità di inclusione, non una classificazione certa;
- permettere soglie e scenari alternativi (`top 20`, `top 40`, `top 60` o struttura personalizzata);
- evidenziare i giocatori vicini al confine della lista;
- ricalcolare strategie, budget e costo-opportunità appena viene importata la lista ufficiale;
- conservare lo snapshot provvisorio per misurare quanto la strategia fosse sensibile all'errore di classificazione.

L'interfaccia deve mostrare sempre un badge `LISTA NON UFFICIALE` finché lo stato non diventa `official`.

## 13. Esperienza utente e feature di prodotto

L'interfaccia deve separare tre contesti: **preparazione**, **asta live** e **gestione post-asta**. Tutte le viste usano le stesse funzioni del motore; la dashboard non contiene formule statistiche proprie.

### 13.1 Navigazione principale

| Area | Decisione che deve facilitare | Feature principali |
|---|---|---|
| Home | Cosa richiede attenzione adesso? | stato dati/modello, countdown asta, alert, ultime modifiche e azioni rapide |
| Giocatori | Chi vale la pena considerare? | ricerca istantanea, filtri, ranking, confronto e scheda dettagliata |
| Costruttore rosa | Che combinazione di giocatori regge meglio? | slot, moduli coperti, budget, replacement e scenari |
| Asta live | Quanto posso offrire adesso? | stato asta, max bid dinamico, costo-opportunità, inserimento rapido e undo |
| Giornata | Chi schiero e perché? | formazione ottima, panchina, capitano, sostituzioni simulate e rischio SV |
| Dati e modello | Posso fidarmi dell'output? | freschezza, copertura, anomalie, versione, fonti e quality tier |

### 13.2 Scheda giocatore orientata alla decisione

Ogni scheda mostra prima un riepilogo compatto:

- valore atteso stagionale e per giornata di calendario;
- mediana, P10–P90 e probabilità di voto;
- valore sopra il replacement e valore marginale per la rosa corrente;
- prezzo atteso di mercato, offerta consigliata e massimo dinamico;
- compatibilità con gli slot ancora scoperti;
- tre driver positivi, tre rischi e grado di confidenza;
- stato aggiornamento e provenienza dei dati;
- confronto con massimo tre alternative dello stesso tier o prezzo.

Le metriche avanzate, le distribuzioni e l'andamento storico restano in pannelli espandibili. L'incertezza non viene nascosta dietro un singolo numero.

### 13.3 Costruttore rosa e laboratorio scenari

- drag-and-drop dei giocatori negli slot, con supporto anche da tastiera;
- vista grafica del campo mentre la rosa viene composta, con undici titolare, panchina e giocatori ancora da acquistare chiaramente distinti;
- passaggio immediato fra vista `rosa completa` e vista `formazione titolare`;
- verifica immediata di composizione 3P–8D–8C–5A, con fallback configurabile a 4A, e blocco portieri;
- indicatore delle formazioni realmente copribili fra gli otto moduli ammessi: 3-4-3, 3-5-2, 4-5-1, 4-4-2, 4-3-3, 5-4-1, 5-3-2 e 5-2-3;
- budget totale, impegnato, residuo e minimo da preservare per completare la rosa;
- profondità per ruolo, rischio combinato di mancato voto e dipendenze dalla stessa squadra;
- confronto affiancato fra due rose o fra scenario “acquisto/non acquisto”;
- scenari di mercato `prudente`, `centrale` e `aggressivo`, senza falsa precisione;
- salvataggio di shortlist, tag personali, note e giocatori da evitare;
- snapshot nominati per tornare a una strategia precedente.

#### Ottimizzazione attorno alle scelte dell'utente

L'utente può selezionare liberamente uno o più giocatori e marcarli come `bloccati`. Il sistema costruisce la migliore soluzione possibile intorno a loro senza rimuoverli, distinguendo due problemi:

1. **undici ideale:** completa la formazione titolare per una giornata o uno scenario;
2. **rosa ideale:** completa tutti i 24 slot rispettando ruoli, blocco portieri, budget, disponibilità nel pool e costo atteso d'asta.

Sono previste due modalità:

- `modulo fisso`: l'utente sceglie uno degli otto moduli consentiti e l'ottimizzatore riempie gli slot rimasti;
- `modulo libero`: l'ottimizzatore confronta tutti i moduli validi e propone quello con utilità attesa maggiore.

L'obiettivo non deve essere soltanto massimizzare la media. L'utente può scegliere profili `prudente`, `bilanciato` e `aggressivo`, che pesano diversamente punti attesi, floor, ceiling, probabilità di voto, modificatore difesa, bonus rendimento, concentrazione per squadra e flessibilità futura. Ogni proposta deve spiegare quali vincoli sono attivi, quali giocatori sono acquistati o soltanto ipotetici e quale alternativa produce il maggiore costo-opportunità.

Se i giocatori bloccati rendono impossibile completare una rosa o un modulo, l'app non deve modificarli silenziosamente: mostra il vincolo incompatibile e la modifica minima necessaria.

### 13.4 Cockpit dell'asta live

Durante l'asta la vista deve privilegiare velocità e prevenzione degli errori:

```text
offerta consigliata: 23
massimo dinamico: 29
prezzo di mercato atteso: 18–24
budget dopo l'acquisto: 171
guadagno atteso rosa finale: +34,2
costo-opportunità principale: attaccante tier 1
```

Feature prioritarie:

- command palette per trovare un giocatore e registrare acquisto/prezzo senza cambiare pagina;
- registro cronologico di offerte e assegnazioni con modifica e `undo` immediato;
- import di un foglio dell'admin e modalità manuale di emergenza;
- aggiornamento automatico di disponibilità, budget, slot e prezzi massimi;
- tabellone delle 20 squadre con giocatori acquistati, slot occupati, spesa e crediti residui;
- inserimento rapido di squadra acquirente, giocatore e prezzo per ogni assegnazione osservata;
- avvisi non bloccanti per budget futuro insufficiente, duplicati, ruolo pieno e concentrazione eccessiva;
- coda dei prossimi obiettivi con alternative già ordinate;
- modalità “focus” ad alto contrasto, numeri grandi e nessun grafico non essenziale;
- autosalvataggio locale e ripristino dello stato dopo refresh o interruzione.

#### Apprendimento online del mercato e tracciamento avversari

Ogni assegnazione inserita aggiorna in tempo reale sia la contabilità sia le previsioni di mercato. Per ciascuna squadra avversaria il sistema mantiene:

- budget iniziale, incrementi di round, spesa cumulata e crediti residui esatti;
- minimo necessario per completare gli slot e budget realmente spendibile;
- giocatori, ruoli e tier già acquistati;
- fabbisogno residuo per ruolo e compatibilità con i moduli;
- profilo di aggressività stimato, preferenze osservate e tendenza a pagare sopra/sotto mercato.

Il modello dei prezzi parte da prior costruiti con quotazioni, FVM, ranking, ruolo, tier e aste storiche disponibili. Dopo ogni acquisto aggiorna almeno:

```text
inflazione complessiva del mercato
inflazione per ruolo e tier
distribuzione del prezzo del giocatore
probabilità che ciascun avversario competa
prezzo atteso e quantili P25/P50/P75
massimo dinamico coerente con la nostra rosa
```

L'aggiornamento deve essere incrementale e riproducibile: una correzione o un `undo` nel ledger ricostruisce lo stato a partire dagli eventi validi. Nelle prime osservazioni il sistema applica forte shrinkage verso il prior e mostra intervalli ampi; non deve dichiarare di avere “imparato gli avversari” da due o tre acquisti. Le stime diventano più personalizzate via via che aumentano prezzi osservati, ruoli coperti e scelte delle singole squadre.

Il tabellone deve offrire due livelli di lettura:

- **operativo:** crediti esatti, slot e acquisti noti;
- **predittivo:** domanda residua, aggressività e probabile pressione sul prossimo giocatore, sempre con confidenza visibile.

L'output deve aiutare la decisione, non simulare certezza sul comportamento umano: prezzo e probabilità di concorrenza restano distribuzioni aggiornate, non valori deterministici.

### 13.5 Formazione settimanale e post-asta

- proposta di formazione con punti attesi, floor, ceiling e probabilità di voto;
- scelta assistita di capitano e ordine della panchina;
- simulazione esplicita delle cinque sostituzioni, del no-switch e dei giocatori mancanti;
- probabilità di modificatore difesa, bonus rendimento e fair play per ogni modulo;
- confronto “mia scelta vs ottimo del modello”, senza sostituire automaticamente le decisioni dell'utente;
- storico delle decisioni e relativo regret, utile anche per migliorare il modello.

### 13.6 Fiducia, accessibilità e controllo

- indicatore globale `as of` e badge per dati obsoleti o incompleti;
- spiegazione breve di ogni raccomandazione e link al dettaglio del calcolo;
- override manuali con autore, motivazione, confidenza e scadenza;
- colori mai usati come unico segnale; layout leggibile anche su laptop durante l'asta;
- scorciatoie da tastiera, conferma soltanto per azioni ad alto impatto e undo per le altre;
- export/import completo dello stato in JSON e report finale in CSV;
- modalità demo con dati fittizi per provare il flusso prima dell'asta reale.

### 13.7 Priorità di implementazione UX

**P0 — necessarie per usare davvero l'app:** ricerca e filtri, scheda giocatore compatta, gestione liste `unknown/provisional/official`, costruttore visuale rosa/formazione, giocatori bloccati, modulo fisso o libero, budget/slot, ledger di tutte le 20 squadre con crediti residui e undo, max bid spiegato, autosalvataggio e stato `as of`.

**P1 — forte vantaggio decisionale:** confronto giocatori, shortlist e note, scenari di mercato, ottimizzazione completa della rosa attorno alle scelte dell'utente, apprendimento online di inflazione/prezzi/profili avversari, alternative automatiche, alert di costo-opportunità, import file admin e dashboard qualità dati.

**P2 — dopo la prima asta completa:** formazione settimanale, notifiche di cambi rilevanti, regret analysis, NLP delle news e personalizzazione avanzata del layout.

## 14. Verdetto

Il progetto è tecnicamente fattibile e può essere molto più sofisticato di un ranking da asta. Per l'uso esclusivamente privato, l'autorizzazione Fantacalcio non deve bloccare l'MVP: i veri colli di bottiglia sono la coerenza storica del voto, l'identità dei giocatori fra fonti e la copertura reale dei dati giocatore-partita.

La scelta migliore è partire da modelli probabilistici modulari e interpretabili, con baseline forti, partial pooling e validazione temporale. XGBoost, ensemble e metodi profondi vanno aggiunti solo quando migliorano previsioni calibrate e decisioni d'asta fuori campione. Il prodotto finale deve conoscere la propria incertezza: per un'asta, sapere che un calciatore vale in media 70 ma con un intervallo 35–105 è più utile che assegnargli falsamente un valore “preciso” di 72.

## Fonti principali

- [Fantacalcio — statistiche storiche](https://www.fantacalcio.it/statistiche-serie-a/2025-26)
- [Fantacalcio — termini e condizioni](https://www.fantacalcio.it/termini-e-condizioni)
- [API-Football — pricing](https://www.api-football.com/pricing/)
- [API-Football — terms](https://www.api-football.com/terms)
- [API-Football — coverage](https://www.api-football.com/coverage/)
- [Sportmonks — Serie A API](https://www.sportmonks.com/football-api/serie-a-api/)
- [Sportmonks — terms](https://www.sportmonks.com/terms-of-service/)
- [Understat — Serie A](https://understat.com/league/Serie_A)
- [OpenFootball Italy](https://github.com/openfootball/italy)
- [ClubElo](http://clubelo.com/)
- [Wikidata — licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)
- [football-data.org — pricing e coverage](https://www.football-data.org/pricing)
- [Big Balls — Serie A API](https://bigballsdata.com/serie-a-api)
- [StatsBomb Open Data](https://github.com/hudl/open-data)
- [Wyscout public soccer event dataset](https://www.nature.com/articles/s41597-019-0247-7)
- [football-data.co.uk — dati italiani](https://www.football-data.co.uk/italym.php)
- [Open-Meteo — pricing/licenza d'uso API](https://open-meteo.com/en/pricing)
- [OpenFPL](https://arxiv.org/html/2508.09992v1)
- [PlayeRank](https://dl.acm.org/doi/fullHtml/10.1145/3343172)
- [Dixon–Coles](https://academic.oup.com/jrsssc/article-abstract/46/2/265/6990546)
- [Expected goals: improving model performance](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0282295)
- [Bayes-xG](https://arxiv.org/abs/2311.13707)
- [Plus-minus player ratings for soccer](https://livrepository.liverpool.ac.uk/3063562/)
- [Probabilistic forecasts, calibration and sharpness](https://academic.oup.com/jrsssb/article/69/2/243/7109375)
- [scikit-learn — TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
- [scikit-learn — probability calibration](https://scikit-learn.org/stable/modules/calibration.html)
