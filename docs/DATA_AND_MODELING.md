# Specifica canonica dati e modeling

## Output e orizzonti

Produrre tre forecast distinti: pre-asta/stagionale, rolling 3–6 giornate e settimanale. Per giocatore mostrare almeno:

- probabilità titolare/subentro/no voto e distribuzione minuti;
- voto base e componenti evento;
- punti per giornata di calendario e per giornata a voto;
- distribuzione stagionale, mediana, P10–P90, downside e upside;
- disponibilità, rischio, qualità/freschezza dati e moduli di fallback attivi;
- valore sopra replacement e contributo marginale alla rosa;
- prezzo atteso, quantili e massimo dinamico separati dal forecast sportivo.

## Modello generativo

Per giocatore-partita stimare con moduli separati ma coerenti:

1. partecipazione e minuti;
2. gol, assist/xA, assist light e rigori;
3. scoreline, vittoria/pareggio, clean sheet e gol subiti;
4. cartellini, autogol e fair play;
5. voto base, preferibilmente ordinale/gerarchico;
6. dipendenze fra compagni e avversari.

Il motore applica il regolamento a scenari Monte Carlo. Lo stagionale non è la prima giornata moltiplicata per 38.

## Baseline e metodi

Baseline obbligatorie: stagione precedente, media per ruolo, minuti-only, per-90 shrinkato, Elo/Dixon–Coles e quotazione/mercato quando legalmente disponibile. Confrontare regressioni gerarchiche/ordinali e conteggi Poisson/negative-binomial con CatBoost/LightGBM/XGBoost. Aggiungere ensemble, deep learning o NLP solo se migliorano metriche, calibrazione e decisioni fuori campione.

Feature: recency e carriera shrinkata; ruolo/uso tattico; minuti, partenze e gerarchie; xG/xA/tiri; set pieces e rigori; disciplina; forza squadra/avversario; casa, riposo, congestione e calendario; trasferimenti/allenatore; infortunio/squalifica/convocazione; quote senza margine; qualità/missingness della fonte; override umano versionato con autore, scadenza e confidenza.

## Livelli dati

1. `raw`: snapshot immutabili, checksum e metadati di accesso.
2. `staged`: parsing tipizzato per fonte.
3. `curated`: ID canonici, crosswalk e campi riconciliati.
4. `features`: variabili `as_of` con lineage.
5. `models`: config, fit, fold, seed, metriche e artifact.
6. `outputs`: previsioni, valutazioni, scenari e report.

Tabelle minime: `players`, `teams`, `seasons`, `competitions`, crosswalk ID; fixture/snapshot; lineup, availability, injuries, transfers; stats/eventi; fantasy votes/events/roles; odds/weather; override; features as-of; predictions/intervalli; auction rounds/pools/versions/events/team state; market snapshots/opponent profiles; roster/lineup scenarios e locked players; source registry e data-quality issues.

## Identità e provenienza

Mai usare il nome come chiave primaria. Ogni mapping conserva fonte, ID, label, validità, metodo, confidenza e review. Gli ambigui vanno in coda manuale; niente drop o force-match silenziosi.

Ogni record conserva almeno `source_name`, `source_record_id`, `event_time`, `available_time`, `ingested_time`, `source_version`, `source_file_hash`, `quality_tier` e `quality_status`.

Quality tier:

- A: export diretto/provider documentato, completo e riconciliato;
- B: archivio community completo, coerente e riconciliato;
- C: aggregato, incompleto o provenienza incerta; solo parser, controlli aggregati e sensitivity.

Il training deve poter escludere una fonte o un tier intero.

## Validazione

- Split rolling-origin/expanding-window; mai random fold attraverso il tempo.
- Preprocessing, imputazione, selezione, tuning e calibrazione dentro ogni training fold.
- Test automatici che nessun campo abbia `available_time` successivo al decision timestamp.
- MAE/RMSE per punti, rank correlation/NDCG per ranking, log loss/Brier per probabilità, CRPS/coverage per distribuzioni.
- Breakdown per ruolo, stagione, orizzonte, minuti, prezzo/tier, trasferiti/promossi e qualità dati.
- Backtest di decisione: replay asta e giornate, budget/slot reali, replacement e regret.
- Ablation per famiglie di feature/fonti e intervalli di incertezza sulle metriche.

## Forecast-to-bid

Il valore d’asta usa distribuzioni predittive, replacement, scarsità, covariance/complementarity, profilo di rischio, budget ombra, offerta futura, domanda avversaria e regole del round. Validare con replay storico e Monte Carlo seeded. Non confondere accuratezza di punti con utilità d’asta.

## Degradazione controllata

Senza target Fantacalcio omogeneo: output `proxy fantasy`; xG da import manuale Understat quando presente (ADR-2026-075: per-90 shrinkato + propensione gol/assist nel Monte Carlo via `scoring/xg_propensity.py`), altrimenti per-90 shrinkato senza xG; senza feed infortuni: stato manuale. La UI espone modulo attivo, timestamp e impatto sulla confidenza.

xG nel Monte Carlo (ADR-2026-075, Engine v2 Stage 3, **default OFF**):

- **Understat presente** (import manuale, `data/staged/understat/`) → il tasso gol/assist realizzato storico viene fuso col tasso implicito da xG/xA con lo stesso `w = n/(n+prior)` usato ovunque, poi resample SIR dell'ensemble bootstrap (`scoring/odds_conditioning` pattern). Colonna di provenienza `xg_data_present` nell'output.
- **Understat assente** → peso 0 sul termine xG → output **bit-identico** allo Stage 2 (contratto di degradazione controllata).

Gate deferito: non eseguibile ora senza export Understat reali; il wiring è spedito absent-safe e resta OFF finché un backtest non mostra che batte il no-xG su CRPS gol/assist A/C.

Aggiustamento squadra nel Monte Carlo (ADR-2026-074, Engine v2 Stage 2):

- **quote presenti** (football-data.co.uk, stagione già prezzata) → priori da quote: de-vig Shin del mercato medio 1X2 (+ O/U 2.5), inversione supremacy+total su griglia Dixon–Coles con `rho` fisso negativo, marginali clean-sheet / gol subiti dal grid congiunto, condizionamento dell'ensemble bootstrap per reweighting/SIR (`scoring/odds_conditioning.py`). Sostituisce lo shift scalare.
- **quote assenti** (o stagione non ancora prezzata, es. il numero pre-asta 2026/27) → shift scalare Dixon–Coles come oggi (`scoring/team_strength_adjustment.apply_adjustment`), invariato.

Il path priori-da-quote è **default OFF** finché non supera il ship gate OOS (batte lo shift scalare su CRPS_fair per P/D e sul Brier clean-sheet nel walk-forward rolling-origin, senza regressione PIT).
