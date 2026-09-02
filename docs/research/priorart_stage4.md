# Prior art for Engine v2 Stage 4 — decomposed generative Monte-Carlo and a real season simulator

Status: research note. DATA for design, not binding. Precedence unchanged (latest ADR > canonical docs/config > research design). Nothing here is adopted until an ADR records it.

## 0. Purpose and grounding

Stage 4 replaces the current monolithic bootstrap with coherent generative sub-modules and a season simulator in which *season ≠ matchday-1 × 38*.

What the engine does **today** (do not re-derive):

- A player-match draw resamples a whole historical `(voto, events)` row from that player's own history (block/stationary bootstrap of rows), then a deterministic rules engine scores that row. Base voto and confirmed event bonuses therefore always co-move exactly as they did in some real past match.
- Participation is *computed* (season appearance rate with recency decay, keeper logic partly special-cased) but **not folded into the per-match sim** — every simulated matchday effectively assumes the player features.
- Team context enters as a **small additive Dixon–Coles shift** to scoring rates (`scoring/team_strength_adjustment.apply_adjustment`), or, when a season is already priced, as odds-implied priors conditioning the ensemble (ADR-2026-074, default OFF).
- xG, when a manual Understat import exists, blends a per-90 goal/assist propensity into the resample (ADR-2026-075, default OFF).

`docs/DATA_AND_MODELING.md` §"Modello generativo" asks for six separate-but-coherent modules per player-match: (1) participation & minutes, (2) goals / assists / xA / penalties, (3) scoreline / win-draw / clean-sheet / conceded, (4) cards / own goals / fair-play, (5) base voto (ordinal/hierarchical preferred), (6) teammate/opponent dependencies; the ruleset is then applied to Monte-Carlo scenarios.

This note surveys prior art for each, plus the season-aggregation problem and validation, and ends with a concrete, opinionated **"Recommended for our Stage 4"**.

---

## 1. Participation / minutes models

### 1.1 The three-way appearance outcome

Every source that projects fantasy value treats playing time as the dominant driver and models it as a **mixture over appearance types**, not a single number. The FPL analytics idiom "xMins" (expected minutes) is explicitly a probability-weighted average across scenarios: start / bench-cameo / unused-or-absent. Worked example from the community write-ups: a 70% starter averaging 72′ when starting, 20% bench averaging 25′, 10% absent → xMins = 0.70·72 + 0.20·25 + 0.10·0 = 55.4 (goaliqai, "Expected Minutes Explained", 2024, https://www.goaliqai.com/expected-minutes-explained-why-playing-time-matters-in-football-analytics-and-fpl/). FPLReview computes xMins as the mean of ~1,000 simulations that fold in rotation events, injury-proneness (which inflates decay), and "how securely a player owns his role" (FPLReview docs, "xMins", https://docs.fplreview.com/the-model/projections/xmins/). The closed form is proprietary but the *structure* is public: a categorical appearance state followed by a conditional minutes draw.

### 1.2 Hurdle / two-part structure

The natural statistical frame is a **hurdle (two-part) model** (Cragg 1971, "Some Statistical Models for Limited Dependent Variables…", Econometrica 39(5):829–844, https://www.jstor.org/stable/1909582; Mullahy 1986, "Specification and testing of some modified count data models", J. Econometrics 33:341–365, https://doi.org/10.1016/0304-4076(86)90002-3):

1. **Availability hurdle** — Bernoulli `a ∈ {available, out}`. "Out" = injured / suspended / not in squad. Feed-driven when an injury/suspension feed exists; otherwise a versioned manual state (`docs/DATA_AND_MODELING.md` "override umano versionato"). When only a manual state exists, treat it as a point mass with an analyst-set confidence, and let the residual uncertainty flow through a small `p_out` prior by role and age.
2. **Selection given available** — categorical `s ∈ {start, bench, unused}` via multinomial/ordered logit on: recent starts share (shrunk), role/rotation-slot security, congestion (see 1.4), opponent tier, home/away, manager tendency, days since last match.
3. **Minutes given on the pitch** — conditional distribution:
   - if `start`: minutes concentrated near 90 with a left tail for early subs / red cards. A **Beta scaled to [0,96]** or a censored-at-90 model fits the "mostly full, occasionally hooked" shape; a two-component mixture (completes vs. substituted-off, the latter roughly Normal around 60–70′) is the pragmatic choice.
   - if `bench`: minutes in [0, ~40], right-skewed; Exponential/Gamma truncated, or empirical resample of historical sub-on minutes by role.
   - if `unused`: 0.

This is exactly the "binary availability × minutes-given-played" decomposition used across sports two-part playing-time work, and the ordered `{unused, cameo, partial, full}` version is the ordinal alternative (a single cumulative-link model on a latent "involvement" scale, see §5 for the machinery).

### 1.3 Season appearance-count as Beta-Binomial or availability Markov chain

Two complementary framings for *how many* matches a player features in over 38:

- **Beta-Binomial** on appearance count `N ~ BetaBin(38, α, β)`, with `(α, β)` from a role/price/age prior updated by career history. This captures that the per-match appearance probability is itself uncertain and that appearances are over-dispersed relative to Binomial (a nailed-on starter and a squad rotation option with the same mean 25 appearances have very different spreads). Beta-Binomial is the standard over-dispersed count-with-known-trials model and is used for sports availability/exposure counts (see e.g. injurytools, "Model injury data as counts", https://lzumeta.github.io/injurytools/articles/model-injury-data-i.html).
- **Availability Markov chain** over the fixture list: states `{fit-starter, fit-rotation, minor-knock, injured, suspended}` with weekly transition matrix. Injury spells then have realistic *duration* and *path dependence* — one transition into `injured` costs a contiguous run of matches, not 1/38 of every match. Hidden/latent-state versions of this are the current direction in sports-injury modelling (Wu et al. 2025, "Next Generation Models for Subsequent Sports Injuries", Applied Stochastic Models in Business and Industry, https://doi.org/10.1002/asmb.70034; predictive injury modelling review, Rossi et al. 2016, arXiv:1609.07480, https://arxiv.org/pdf/1609.07480).

The Markov chain is strictly more expressive (it *generates* correlated absence runs); the Beta-Binomial is a cheap marginal check and a good fallback when we have no spell-length data. They are not mutually exclusive: fit the chain, and use Beta-Binomial on simulated `N` as a calibration target.

### 1.4 Rotation and fixture congestion

Congestion is a measurable minutes shifter and is position-specific. Empirically, when a midweek European or cup game sits between league matches the share of players completing 75–90′ drops; wide midfielders and forwards are rotated most, central defenders least (Sky Sports / Hud studies summarised at https://www.hud.ac.uk/news/2020/november/football-fixture-congestion-new-study/; congestion vs. match-play performance, Julian et al. 2021, PMC7846542, https://pmc.ncbi.nlm.nih.gov/articles/PMC7846542/). Squad-level availability during congested blocks runs ~78% vs. ~84% in uncongested periods (performance/medical-team availability study, 2024, PMC12278155, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12278155/). Practical encoding for the selection logit: `days_rest`, `two_games_in_week` flag, `european_competition` flag, interacted with role and a per-player "is rotated" propensity.

### 1.5 Injuries/suspensions: feed vs. manual

- **Feed present**: injury status and expected return date set the availability hurdle directly, with a decay back to baseline around the return date (proneness lengthens the decay tail, per FPLReview).
- **Feed absent (our current reality)**: manual `availability` state with author, expiry, confidence (already specified). The sim reads it as a near-point-mass; the degradation UI flags "manual availability, as_of …". Suspensions from yellow-card accumulation *can* be simulated endogenously once the card module (§6) exists — track simulated bookings against the 5/9/13 thresholds and force `out` for the next match.

---

## 2. Why season ≠ 38 × matchday

Scaling a single-match point distribution by 38 (or by expected appearances) is wrong for four compounding reasons.

### 2.1 Random number of appearances — law of total variance

Let `N` = number of appearances (random) and `X_i` = fantasy points in appearance `i`, iid-ish with mean `μ` and variance `σ²`, independent of `N`. Season total `S = Σ_{i=1}^{N} X_i` is a **random sum**. Wald's identity gives the mean (Wald's equation, https://en.wikipedia.org/wiki/Wald%27s_equation):

```
E[S] = E[N] · μ
```

and the **law of total variance / Blackwell–Girshick identity** gives (https://en.wikipedia.org/wiki/Law_of_total_variance):

```
Var[S] = E[N] · σ²  +  Var[N] · μ²
```

The second term is exactly what naive scaling drops. For a rotation forward with `E[N]=22`, `Var[N]≈30` (Beta-Binomial spread), `μ≈6.2`, `σ²≈9`: appearance-variance contributes `22·9 ≈ 198`, appearance-*count* variance contributes `30·6.2² ≈ 1153` — **~85% of the seasonal variance comes from not knowing how many games he plays**, and a fixed-N model understates the seasonal sd by a factor of ~2.7 here. This single fact is the main quantitative argument for Stage 4.

### 2.2 Participation path dependence

Absences are contiguous runs, not independent per-match coin flips. A model that injures a player independently each week with probability `q` and one that draws a Poisson number of spells with Gamma-distributed durations can share the same `E[N]` but produce very different seasonal shapes — the spell model has fatter tails (a lost 8-week run) and correlated "dead" stretches that also change *team context* for teammates. Only an appearance-path simulation over the real fixture list reproduces this.

### 2.3 Autocorrelation of form

Per-appearance outcomes are not iid: base voto and event rates have positive serial correlation (hot/cold streaks, tactical role changes, knocks played through). Positive autocorrelation *inflates* `Var[S]` beyond the iid `E[N]·σ²` term (sum-of-correlated-variables: `Var ≈ E[N]·σ²·(1 + 2Σρ_k)`). The current row-bootstrap captures within-row voto/event coupling but resamples rows independently, so it misses run-level persistence.

### 2.4 Team-context drift

Team strength, the penalty-taker designation, the manager, and a player's role all drift across a season. A December fixture should be simulated with December's context, not August's. Season simulation lets context evolve along the path (new manager bump, January signing displacing a starter, promoted-team regression).

### 2.5 Consequence: simulate the path, don't scale

The correct and *simplest* approach is Monte-Carlo over the actual remaining fixture list:

```
for s in 1..S_sims:
    context = initial_context
    season_points[s] = 0
    for gw in remaining_fixtures:
        advance availability Markov state
        if features(gw):
            draw appearance-type and minutes           # module 1
            draw team-match scoreline for player's club # modules 3 + 6
            draw individual events conditional on minutes & scoreline  # modules 2, 4
            draw base voto conditional on context       # module 5
            pts = rules_engine(voto, events, minutes)   # deterministic
            season_points[s] += pts
        update context (rolling form, role, penalty duty, injuries)
```

Analytic compound-distribution results (Panjer recursion, saddlepoint approximations for random sums) exist but buy nothing here: the per-appearance distribution is itself a simulation output, context is path-dependent, and we already own a deterministic rules engine. Monte-Carlo is both simpler and more faithful. Keep `S_sims` (season paths) and the per-appearance inner draw explicit and separately seeded (§7).

---

## 3. Goals / assists / xA at player-match level

### 3.1 Rate per 90, shrunk

Standard practice: a player-level scoring rate `λ_goal` per 90 minutes, estimated with shrinkage toward a role/position mean. Empirical-Bayes / Stein shrinkage `λ̂ = w·λ_raw + (1−w)·λ_role` with `w = n/(n + k)` (appearances `n`, prior strength `k`) is the same estimator the engine already uses elsewhere (Efron & Morris 1975, "Data Analysis Using Stein's Estimator and Its Generalizations", JASA 70:311–319, https://doi.org/10.1080/01621459.1975.10479864; Morris 1983, "Parametric Empirical Bayes Inference", JASA 78:47–55). Poisson is the default count law; **Negative Binomial** if the per-90 counts are over-dispersed, which football goal counts generally are (Greenhough et al. 2002, "Football goal distributions and extremal statistics", Physica A 316:615–624, https://warwick.ac.uk/fac/sci/physics/research/cfsa/people/sandrac/publications/footy.pdf; "Goal-scoring and the negative binomial distribution", Reep/Pollard-tradition, summarised at https://www.researchgate.net/publication/270311475). NB adds one dispersion parameter `r`; `Var = λ + λ²/r`.

### 3.2 Minutes → count

Given sampled minutes `m` and rate `λ` per 90, the match count is `Poisson(λ · m/90)` (or NB with the mean thinned the same way). This is the clean coupling between module 1 and module 2: no minutes, no expected goal contribution; a 25′ cameo gets ~28% of the per-90 rate. Thinning a Poisson by `m/90` is exact; for NB it is an approximation (the dispersion doesn't scale linearly) but adequate.

### 3.3 xG / xA informing the rate

When Understat is imported (ADR-2026-075), blend realised rate with xG-implied rate at the same `w = n/(n+prior)` and resample the ensemble. xG is a lower-variance estimate of the underlying rate, so it mostly *tightens* `λ̂` and pulls streaky finishers toward their chances. Keep the provenance column `xg_data_present`. Absent Understat, weight 0 → identical to the no-xG path (degradation contract).

### 3.4 Penalties as a separate Bernoulli × conversion

Penalties are structurally different and should not be inside open-play `λ`:

- `is_pen_taker(player, gw)` — designation, path-dependent (changes with injuries, transfers, missed pens). A near-deterministic state with a small switch probability.
- team penalties awarded per match `~ Poisson(λ_pen_team ≈ 0.12–0.18)`, or drawn from the odds grid if priced.
- conversion `~ Bernoulli(p ≈ 0.75–0.79)` — the near-universal static-xG value for penalties is 0.76–0.78 (Hudl StatsBomb, https://www.hudl.com/blog/expected-goals-xg-explained; SportMonks glossary, https://www.sportmonks.com/glossary/penalty-conversion-rate/). Optionally shade by taker history once ≥10 attempts.

The penalty taker thus carries a structural goal (and, under many fantasy rulesets, penalty-miss malus) edge that open-play xG understates.

### 3.5 Assists and correlation with team goals

An assist requires a teammate to score, so player assists must be **conditioned on the sampled team goal count** (module 3), not drawn free-standing. Practical form: `assists_i ~ Binomial(team_goals_from_open_play, π_i)` where `π_i` is player `i`'s shrunk share of team chances created (from key-passes / xA per 90, minutes-scaled). This automatically produces the empirical positive correlation between a creator's assist haul and his team's goal output, and it makes teammates' assists compete for the same goals (mild negative dependence among creators, correct). Zero-inflation is largely handled by the Binomial-on-team-goals structure (many matches the team scores 0–1 open-play goals); an explicit ZIP/ZINB (Groll et al. 2022, "Nested Zero-Inflated Generalized Poisson Regression for FIFA World Cup 2022", arXiv:2205.04173, https://arxiv.org/abs/2205.04173) is only worth it if residual excess zeros remain for low-minute wide players.

### 3.6 "Assist light" (fanta assist)

Same machinery with a higher `π` base rate and a looser link to goals (the Italian fanta-assist also rewards the pass before the assist and some won-set-piece situations); calibrate its per-90 rate directly from fanta-vote event history rather than from Opta key passes.

---

## 4. Scoreline / clean sheet as one shared team-match draw

### 4.1 The dependency this fixes

Clean sheet, goals conceded, and (under Serie A fantacalcio) the defensive-modifier inputs are **team-match** outcomes. If every defender and the keeper of the same club draw their own independent clean-sheet coin, a back line's fantasy outcomes are wrongly decorrelated, roster variance is understated, and stacking a defence looks free. The minimal fix: **one scoreline draw per club per simulated matchday, shared by all that club's players**. This is Stage 4 §6 v1.

### 4.2 Model forms

- **Bivariate Poisson / Dixon–Coles**: `(goals_for, goals_against) ` from team attack/defence strengths, home advantage, and the low-score correlation correction `τ(x,y;ρ)` that reweights the (0-0),(1-0),(0-1),(1-1) cells (Dixon & Coles 1997, "Modelling Association Football Scores and Inefficiencies in the Football Betting Market", Applied Statistics 46(2):265–280, http://www.math.ku.dk/~rolf/teaching/thesis/DixonColes.pdf). The genuinely bivariate-Poisson version with a shared component `λ_3` is Karlis & Ntzoufras 2003 ("Analysis of sports data by using bivariate Poisson models", JRSS D 52(3):381–393, https://doi.org/10.1111/1467-9884.00366). Either produces a full joint scoreline grid `P(x,y)`.
- **Odds-implied grid**: when the season is priced, de-vig the 1X2 (+ O/U 2.5) market and invert supremacy/total onto a Dixon–Coles grid with fixed negative `ρ` — exactly the ADR-2026-074 path. Clean-sheet and goals-conceded marginals fall out of the grid. This is preferred when odds exist because it is auto-calibrated to the market.
- **Dynamic / time-varying strength**: Rue & Salvesen 2000 and dynamic bivariate Poisson (Koopman & Lit 2012, https://papers.tinbergen.nl/12099.pdf) let attack/defence drift across the season — relevant for §2.4 context drift.

### 4.3 How it plugs in

Per simulated matchday, for each club: draw `(gf, ga)` once. Then:

- keeper & defenders: `clean_sheet = 1{ga = 0}`; `goals_conceded = ga` feeds the per-goal-conceded malus; keeper save points from shots-on-target conditional on `ga` if the ruleset uses them.
- all players: `team_goals = gf` feeds the assist Binomial (§3.5) and any team-result bonus.
- opponent strength is the *same* draw viewed from the other side — if we ever simulate whole matchdays jointly, one match = one `(gf,ga)` shared by both clubs' players, giving the natural negative correlation between opposing defences.

Correlation among a club's defenders is now exactly the correlation induced by the shared `ga`; no per-player clean-sheet parameter. This is the "minimal teammate/opponent dependency" and it is enough for v1. Copula-based refinements (Schaake shuffle / ensemble copula coupling, Schefzik et al. 2013, arXiv:1302.7149, https://arxiv.org/pdf/1302.7149) can restore finer within-team dependence later without touching the marginals.

---

## 5. Base voto as ordinal / hierarchical

### 5.1 Why not OLS on the mean

The raw match rating (pagella / fanta base voto) lives on a bounded, discretised scale (~4.5–8, quarter-point steps). OLS ignores the ceiling/floor, can predict impossible values, assumes constant variance across the scale (false — ratings bunch near 6.0), and gives symmetric intervals for a skewed bounded variable. The current empirical-Bayes shrinkage of the *mean* rating is defensible for a point estimate but throws away shape.

### 5.2 Cumulative-link (ordered logit/probit)

Treat the rating as ordinal with a latent continuous "performance" `y* = x'β + u_player + u_role + ε`, and cut it into rating bands by estimated thresholds `θ_1 < θ_2 < … < θ_K`:

```
P(rating ≤ k) = F(θ_k − x'β − u_player − u_role)
```

with `F` logistic or probit (Agresti 2010, "Analysis of Ordinal Categorical Data", 2nd ed., Wiley; Christensen 2019, `ordinal` R package vignette, https://cran.r-project.org/web/packages/ordinal/vignettes/clm_article.pdf). This respects the scale, produces a proper probability over rating bands (which the rules engine can consume directly), and naturally yields asymmetric uncertainty. A **proportional-odds relaxation** (partial or non-proportional thresholds) lets covariates shift the low tail (a bad-performance/benched risk) differently from the top.

### 5.3 Hierarchical Bayesian version

Random effects for player and role (and optionally club and season) with partial pooling — the same logic as Bayesian hierarchical football models (Baio & Blangiardo 2010, "Bayesian hierarchical model for the prediction of football results", J. Applied Statistics 37(2):253–264, https://discovery.ucl.ac.uk/id/eprint/16040/1/16040.pdf) and Bayesian hierarchical xG with player/position correction (Cefis & Carpita 2024, "Bayes-xG", PMC11214280, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11214280/). Partial pooling handles thin histories (promoted-team players, new signings) gracefully and returns full posterior predictive rating bands. Cost: fit time, MCMC reproducibility care, and a real leakage-safe `as_of` training pipeline.

### 5.4 Level-0 vs Level-1 split (recommended framing)

- **Level 0 (v1, keep)**: current empirical-Bayes shrinkage of the mean base voto, but sample the per-match voto from a shrunk *distribution* (e.g. resample the player's own centred rating residuals, or a fitted skew-normal truncated to the scale) so the season sim gets shape, not just a mean. Byte-comparable degradation path to today's bootstrap when new inputs are stripped.
- **Level 1 (later)**: a cumulative-link model with player + role random effects, shipped behind a flag, adopted only if it beats Level 0 on rating-band log-loss / CRPS and PIT in rolling-origin backtests.

The row-bootstrap's key virtue — voto and confirmed events co-moving as they did in a real match — is partly lost when voto is modelled separately. Mitigate by keeping the **voto↔event coupling** as a conditional: draw events partly conditional on the drawn voto band (a 7.5 match is more likely to carry a goal/assist), or retain row-bootstrap for the joint `(voto, minor events)` core and layer the generative modules on top for the pieces that need new inputs (participation, team scoreline). See §7.

---

## 6. Cards / own goals / fair-play

### 6.1 In scope: individual low-rate event draws

- **Yellow cards**: `Poisson(λ_yc · m/90)` with `λ_yc` position-dependent (defensive midfielders and full-backs highest, forwards and keepers lowest), shrunk per player, optionally shaded by referee strictness and match importance. Second-yellow / straight red as a much smaller `λ_rc`; a red truncates minutes in module 1 (feed the sampled sending-off minute back).
- **Own goals**: very low-rate `Bernoulli(p_og)` per defensive player-match, `p_og` roughly `0.02–0.04 · (m/90)` for centre-backs and keepers, ~0 for forwards; can be mildly scaled by opponent attack strength / `ga` from module 3.
- **Missed penalty**, **penalty conceded**: tie to the penalty module (§3.4) and to fouls in the box (rare; a small per-defender rate).

All of these are per-90 rates thinned by sampled minutes, same pattern as goals/assists, just with tiny `λ`.

### 6.2 Out of scope: team-level fair-play / defensive modifier

The Serie A fair-play bonus and the *modificatore difesa* are **team-level** and currently **BLOCKED** on unresolved rules (`docs/OPEN_QUESTIONS.md`). They stay blocked. Stage 4 only delivers the *individual* card and own-goal draws; the team aggregation that would turn them into a fair-play/defence modifier is not built until the rules question is resolved and an ADR records the aggregation. The sim should still *record* per-club simulated bookings so the modifier can be switched on later without re-running.

---

## 7. Composition and determinism

### 7.1 Sampling order (fixed, documented)

Per season path `s`, per remaining fixture `gw`, per club:

1. **Availability / participation** — advance the availability Markov state; if available, draw appearance-type and minutes `m` (module 1).
2. **Team-match scoreline** — one `(gf, ga)` draw for the club (module 3 via DC/odds grid), shared by all its players; this is the module-6 v1 dependency.
3. **Individual events** — conditional on `m` and `(gf, ga)`: open-play goals (module 2), assists as Binomial on `gf` (module 2), penalties (module 2), cards and own goals (module 4).
4. **Base voto** — draw the rating / rating-band conditional on context and (Level-1) on the drawn events; Level-0 resamples shrunk residuals (module 5).
5. **Score** — deterministic `rules_engine(voto, events, minutes)` → player-match fantasy points.
6. **Aggregate** — sum along the path; update rolling form, role, penalty duty, injury/suspension state for the next `gw`.

### 7.2 Determinism / reproducibility

- **Hierarchical seeding**: master seed → per-season-path seed → per-fixture seed → per-module substream. Use counter-based / independent-stream RNG (PCG64 / Philox `SeedSequence.spawn`) so modules draw from non-overlapping streams and adding a module does not shift another module's draws. This is what preserves the "default path byte-identical" contract style used in Stage 6 (ADR-2026-076).
- **Config-versioned**: every module's parameters, priors, shrinkage `k`, fixture list, and seed live in versioned config; an output carries the `(config, data snapshot, model fit, seed)` tuple.
- **Rules engine stays pure** — no RNG inside scoring; all randomness is upstream.

### 7.3 Testing

- **Per-module marginal-matching**: each module, run in isolation against held-out data, must reproduce its marginal — appearance-rate calibration, goals-per-90 mean/var, clean-sheet frequency by team tier, card rate by position, rating-band histogram. These are cheap unit-level invariants.
- **End-to-end**: seasonal totals distribution vs. completed seasons (§8).
- **Degradation regression**: with all new inputs stripped (no injury feed, flat team strength, no xG, Level-0 voto, participation forced on), the season sim must reproduce the current bootstrap's per-matchday and seasonal distributions **within Monte-Carlo noise** (e.g. two-sample checks on P10/P50/P90, CRPS within a tolerance band). This is the explicit contract that lets Stage 4 ship additively.
- **Coupling stress test**: vary the strength of the shared-scoreline dependency (module 6) from 0 (independent) to full and record seasonal roster-level variance — guard against variance blow-up (Risk 1).

---

## 8. Validation for a generative seasonal forecast

### 8.1 Proper scoring on seasonal totals

- **CRPS** on each player's seasonal fantasy total against realised totals from completed seasons — the primary metric; it is the probabilistic analogue of MAE and rewards sharp *and* calibrated predictive distributions (Gneiting & Raftery 2007, "Strictly Proper Scoring Rules, Prediction, and Estimation", JASA 102:359–378, https://doi.org/10.1198/016214506000001437).
- **PIT histograms** on seasonal totals — should be uniform; U-shape = under-dispersed (the naive-scaling failure mode), hump = over-dispersed (dependency coupling too strong). (Gneiting, Balabdaoui & Raftery 2007, "Probabilistic forecasts, calibration and sharpness", JRSS B 69:243–268, https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf; Dawid 1984 prequential principle.)

### 8.2 Per-matchday and component calibration

- Per-matchday points: reliability curves / PIT by matchday bucket, by role, by minutes bucket, by price tier (`docs/DATA_AND_MODELING.md` validation breakdown).
- **Appearance-count calibration** — simulated `N` distribution vs. realised appearances, PIT on `N`, and a Beta-Binomial fit check. This is the arm that regressed in Stage 2 (keeper participation gap) and must have its own dashboard.
- Component marginals: Brier on clean sheet, log-loss on rating bands, mean/variance ratio on goals & cards per 90.

### 8.3 Backtesting protocol

- Rolling-origin / expanding-window over completed seasons; never random folds across time; all preprocessing, shrinkage, threshold estimation, and calibration inside each training fold (`docs/DATA_AND_MODELING.md`).
- **Decision backtest**: replay the auction and matchdays with real budgets/slots; measure regret vs. an oracle and vs. the current engine. Accuracy on points is not utility at auction.
- Compare against the mandated baselines: previous season, role mean, minutes-only, per-90 shrunk, Elo/Dixon–Coles, market quote when legal. A season simulator that cannot beat "per-90 shrunk × predicted minutes" on seasonal CRPS is not earning its complexity.
- Season-simulation-specific summaries analogous to rating-framework practice (point MAE, rank error, Spearman, tail-accuracy): see the adaptive Glicko-2 season-simulation framework for the metric menu (2026, arXiv:2607.01722, https://arxiv.org/pdf/2607.01722).

### 8.4 Degradation check (restated as a gate)

Stripped of all new inputs, Stage 4 ⇒ current bootstrap within MC noise. This is both a correctness test and the ship gate: new modules turn **on** one at a time, each behind a flag, each adopted only after it beats Level-0 / no-module on OOS CRPS + calibration without a PIT regression — the same pattern as ADR-2026-074/075.

---

## Recommended for our Stage 4

Opinionated picks. Bias: the simplest form that fixes a *real, measured* deficiency of the current engine.

### Module 1 — participation & minutes: **hurdle + ordered selection + conditional minutes, over an appearance path**

- Availability hurdle `Bernoulli(available)`: feed-driven if/when a feed exists; today a versioned manual state read as a near-point-mass with analyst confidence, plus a small role/age `p_out` prior.
- Selection `{start, bench, unused}`: ordered logit on shrunk recent-starts share, rotation-slot security, congestion flags (`days_rest`, midweek-European, two-in-week) × role, opponent tier, home/away.
- Minutes | start: two-component mixture (completes ≈ 90 vs. substituted-off ≈ N(68, 12²)), red-card left tail from module 4. Minutes | bench: empirical resample of role-specific sub-on minutes.
- **Keeper special-case fixed**: keepers get their own selection model — near-binary `{starter, backup}` with a low in-season switch hazard and cup-rotation flag — because the generic rotation logit is what made the Stage 2 P arm regress (Risk 3).
- Season layer: an availability Markov chain `{fit-starter, fit-rotation, knock, injured, suspended}` over the real fixture list; Beta-Binomial on simulated `N` as a calibration target, and the fallback when no spell-length data exists.

### Module 2 — goals / assists / xA / penalties: **shrunk per-90 Poisson, thinned by minutes; penalties separate**

- `goals_openplay ~ Poisson(λ_goal · m/90)`, `λ_goal` empirical-Bayes shrunk to role mean with `w = n/(n+k)`; switch that marginal to Negative Binomial only if the per-90 dispersion test fails.
- `assists ~ Binomial(team_open_play_goals, π_i)`, `π_i` = shrunk share of team chance creation — conditioned on module 3, so assist/team-goal correlation and creator competition are automatic.
- Penalties: `is_taker` state (small switch prob) × team pens awarded (`Poisson(0.15)` or odds grid) × `Bernoulli(0.77)` conversion; miss feeds the ruleset malus.
- xG: keep ADR-2026-075 wiring — blend at `w = n/(n+prior)` when Understat present, weight 0 (bit-identical) when absent.

### Module 3 / 6 — team scoreline & the minimal dependency: **one shared Dixon–Coles / odds-grid `(gf, ga)` draw per club per matchday**

- Season priced ⇒ de-vig 1X2 + O/U 2.5 → Dixon–Coles grid with fixed negative `ρ` (ADR-2026-074 path). Season not priced (e.g. pre-auction 2026/27) ⇒ scalar Dixon–Coles strength shift as today, but drawn *once per club-match* and shared.
- Every defender + keeper of the club reads `clean_sheet = 1{ga=0}` and `goals_conceded = ga` from that one draw; every player reads `team_goals = gf`. Opponent strength = the same draw seen from the other side.
- This *is* module 6 v1. No per-player clean-sheet parameter. Copula refinements deferred.

### Module 4 — cards / own goals / fair-play: **tiny per-90 Poisson/Bernoulli, position-keyed; team modifier stays BLOCKED**

- `yellow ~ Poisson(λ_yc · m/90)`, `λ_yc` position-dependent + per-player shrink; `red ~ Poisson(λ_rc · m/90)` truncates minutes and triggers the next-match suspension via threshold tracking.
- `own_goal ~ Bernoulli(~0.03 · m/90)` for CB/GK, ~0 otherwise.
- Record per-club simulated bookings but do **not** compute the fair-play / defensive modifier — blocked on `docs/OPEN_QUESTIONS.md`; wire it absent-safe for later.

### Module 5 — base voto: **keep Level-0 empirical-Bayes shrinkage for v1, but sample a shape**

- v1: current EB-shrunk mean, but per-match voto sampled from a shrunk residual distribution (resample the player's centred rating residuals, or a truncated skew-normal on the 4.5–8 scale), lightly conditioned on the drawn events so a goal/assist nudges the rating band up.
- Level-1 (flagged, later): cumulative-link ordered logit with player + role random effects; adopt only on OOS rating-band log-loss / CRPS win with no PIT regression.

### Season-simulator loop (the deliverable)

```
seed_seq = SeedSequence(master_seed)
for s in 1..S_SEASON_PATHS:
    rng_path = seed_seq.spawn()[s]
    ctx = initial_context(as_of)
    total = 0
    for gw in remaining_fixtures(as_of):
        avail_state = advance_markov(avail_state, ctx, rng_path.gw.avail)
        if avail_state in {fit-starter, fit-rotation}:
            app_type, minutes = participation_draw(player, ctx, rng_path.gw.part)   # M1
            if minutes > 0:
                gf, ga = team_scoreline_draw(club, opp, ctx, rng_path.gw.team)      # M3/M6  (once per club-match, cached)
                ev = event_draws(player, minutes, gf, ga, ctx, rng_path.gw.evt)     # M2 + M4
                voto = voto_draw(player, ctx, ev, rng_path.gw.voto)                 # M5
                total += rules_engine(voto, ev, minutes)                            # deterministic
        ctx = update_context(ctx, gw, sim_results)   # form, role, pen duty, suspensions, transfers/manager if scheduled
    season_total[s] = total
report: median, P10, P90, downside/upside, CRPS vs. realised, PIT, appearance-count calibration
```

Team-scoreline draws are cached per `(club, gw)` within a path so all of a club's players share one `(gf, ga)`.

### Degradation contract

With: no injury feed (participation forced on), flat/scalar team strength, no xG, Level-0 voto, generic (non-keeper-special) participation disabled → the season simulator must reproduce the current row-bootstrap's per-matchday and seasonal P10/P50/P90 **within Monte-Carlo noise**, verified by a committed regression test (two-sample distance on quantiles + CRPS within tolerance). Each new module turns on individually, behind a flag, and is adopted only after an OOS win on CRPS + calibration with no PIT regression, recorded in an ADR — same discipline as ADR-2026-074/075/076.

### Top 3 risks

1. **Variance blow-up from dependency coupling.** The shared team-scoreline draw is correct but it *adds* the `Var[N]·μ²`-style cross-player terms that the independent bootstrap silently dropped. If also combined with autocorrelated form and a too-strong shared shock, roster-level seasonal variance can balloon and PIT goes hump-shaped, making every bid look risky and collapsing the optimizer's differentiation. Mitigation: introduce dependence one channel at a time (scoreline first, form autocorrelation later), keep a coupling-strength knob, and gate on seasonal PIT + roster-variance stress tests before raising it.
2. **Compounding mis-calibration across six modules.** Each module can be individually well-calibrated and the *product* still be biased (e.g. minutes slightly long × goals-per-90 slightly high × voto slightly generous → seasonal totals systematically high). Mitigation: mandatory per-module marginal-matching tests *and* end-to-end seasonal CRPS/PIT; never ship a module on its own marginal alone.
3. **Keeper (and nailed-starter) participation gap — the Stage 2 regression, repeated.** A generic rotation model badly misfits players whose minutes are near-deterministic; Stage 2's participation arm regressed exactly here. Under-stating a first-choice keeper's appearances feeds straight into clean-sheet and save totals. Mitigation: a dedicated near-binary keeper selection model with a low in-season switch hazard, an explicit "nailed" class for outfield mainstays, and appearance-count calibration broken out by role with the keeper bucket watched specifically.
