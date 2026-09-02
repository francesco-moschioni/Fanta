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

Stage 6 (ADR-2026-076, Engine v2 — tutti i pezzi **additivi, path di default byte-identico**, provati da regression test):

- **Prezzo ombra del budget** (`auction/budget_shadow_price.py`): rilassamento Lagrangiano del knapsack DP esistente dualizzando **solo** la riga di budget → il problema interno si decompone per ruolo ("prendi i top-`k_r` per `VAR_i − λ·prezzo_i`"); bisezione sullo slack monotono `g(λ) = budget − costo(λ)` per il più piccolo `λ*` la cui scelta ottima rientra nel budget. `λ*` = VAR marginale per credito residuo; tetto di offerta di valore = `VAR_i / λ*`. `binding=False` + `λ*=0` quando la scelta a `λ=0` già rientra (nessun costo-opportunità → si torna alla regola dollar/$1). Nessun solver LP sul path di produzione; `_pulp_dual_crosscheck` (extra `solver`) solo in un test `skipif`. `duality_gap_estimate` = gap di interezza del knapsack, segnalato come confidenza debole.
- **Covarianza/complementarità delle scelte** (`auction/pick_covariance.py`): rosa come portafoglio; `ΔVar_j = Var[P_j] + 2·Σ Cov` e la versione downside per scenario `q10(t_R+p_j) − q10(t_R)`. **Caveat: floor** — il Monte Carlo oggi campiona i giocatori in modo indipendente, quindi la covarianza è di fatto diagonale e **sottostima** la correlazione cross-giocatore reale (stesso club/stessa partita/shock comuni); si raffinerà con le joint sims dello Stage 4.
- **Profilo di rischio** (`auction/risk_profile.py`): CVaR di coda inferiore su scenari (Rockafellar–Uryasev) e un solo knob `risk_aversion = ρ ∈ [0,1]`, `obiettivo = (1−ρ)·media + ρ·CVaR_α` (α default 0.10). `ρ=0` riproduce esattamente il massimizzatore VAR odierno. Integrazione nell'ottimizzatore via valore per-candidato aggiustato (`optimize_roster_completion(value_col=...)` / `value_fn=...`), DP invariato.
- **Prezzo di aggiudicazione da domanda avversaria** (`auction/opponent_demand_price.py`): forma **limitata e saturante** `E[clear] = q·role_inflation·(1 + (g_max−1)(1 − e^{−κ·(D−d0)^+}))`, poi clip al `richest_rival_bid`. `D` = somma sugli avversari che hanno ancora lo slot di ruolo scoperto, pesati per budget-per-slot e (se disponibile) `market_model.team_aggressiveness_index`, da stato `replay` (leakage-safe). Monotona non decrescente in `D`, `≥ q·role_inflation`, finita, `D=0 → q·role_inflation`. `calibrate_clearing_form` è un fit pinball opzionale, non richiesto dal path.
- **Pipeline max-bid** in `recommend_max_bid` (arg tutti opzionali, `None`/`0` → comportamento odierno): `max_bid = min( VAR_term/λ* (o valore regola-$1 se non binding), prezzo_di_aggiudicazione + margine, budget residuo )`, `≥ 1`; `risk_aversion` sposta `VAR_term` verso la VAR aggiustata per il rischio (media→CVaR) quando si passano i campioni del giocatore. Campi nuovi: `shadow_price_ceiling`, `clearing_price_ceiling`, `binding_constraint`, righe di spiegazione in italiano che nominano la fonte di ogni segnale.
- **Reversal di ADR-2026-057**: incorporare la domanda avversaria **nel** prezzo (invece di riportarla a fianco) è **opt-in** (`opponent_demand=None` di default = comportamento vecchio); firma esplicita del project owner registrata in ADR-2026-076.

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
