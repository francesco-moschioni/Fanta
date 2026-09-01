# Prior art — Engine v2 Stage 2: odds-conditioned goal/clean-sheet priors

Status: research note (non-binding). Feeds the design of Stage 2 (conditioning the
Monte-Carlo fantavoto ensemble on market-derived match-outcome / team-goals /
clean-sheet distributions, replacing the current scalar Dixon–Coles shift).
Scope: `football-data.co.uk` 1X2 + Over/Under 2.5 (+ optional Asian handicap) for
Serie A (`I1`), ~2015–2026.

Everything below is a description of published methods so we reimplement them
ourselves. No licensed code is copied. Citations are author/year + URL.

---

## 0. Problem statement and where Stage 2 sits

Today the engine draws player base voto from a bootstrap/empirical ensemble and
then nudges team-level scoring/conceding with a **scalar** derived from a
Dixon–Coles/Elo strength model (`docs/DATA_AND_MODELING.md` §"degradazione":
"senza quote: Elo/Dixon–Coles"). Stage 2 replaces that scalar with a **full
match-conditional distribution**: read pre-match odds (1X2 always; O/U 2.5
usually; AH sometimes) -> de-vig to `(pH, pD, pA)` and `P(Over 2.5)` (§1) -> map
to attacking rates `(lambda_home, lambda_away)` via a supremacy+total /
bivariate-Poisson inversion (§2) -> derive the marginals we need
(`team_goals`, `team_goals_conceded`, `P(clean sheet)`, `P(W/D/L)`; §3) ->
condition the empirical fantavoto ensemble on them by weighted resampling / SIR
without a parametric shape on base voto (§4) -> validate with CRPS / PIT / Brier
that this beats the scalar shift out-of-sample (§5). §6 = fantasy-specific prior
art, §7 = football-data.co.uk columns, §8 = the recommendation.

---

## 1. De-vigging 1X2 odds (removing the bookmaker margin)

Notation: decimal odds `o_i` for outcomes `i in {H, D, A}`; raw implied
probabilities `r_i = 1 / o_i`; **booksum** (overround) `B = sum_i r_i > 1`;
margin `M = B - 1`; number of outcomes `n = 3`; fair probabilities `p_i` with
`sum_i p_i = 1`.

### 1a. Normalisation / proportional / multiplicative

    p_i = r_i / B = (1/o_i) / sum_j (1/o_j)

- **Assumption**: the bookmaker applies the margin as a constant multiplicative
  loading on every fair probability (`r_i = (1+M) p_i` for all `i`).
- **Pros**: trivial, always in `(0,1)`, sums to 1 by construction, no solver.
- **Cons**: ignores the **favourite–longshot bias** — empirically the loading is
  heavier on longshots, so this method understates favourites and overstates
  longshots.
- **When preferred**: efficient, low-margin markets (Pinnacle, market average of
  many books) where the bias is small; as a robust default and as the fallback.
- Source: Štrumbelj (2014), "On determining probability forecasts from betting
  odds", *International Journal of Forecasting* 30(4)
  <https://www.researchgate.net/publication/264349990_On_determining_probability_forecasts_from_betting_odds>;
  `implied` R package vignette
  <https://cran.r-project.org/web/packages/implied/vignettes/introduction.html>.

### 1b. Additive / balanced

    p_i = r_i - (B - 1) / n = r_i - M/n

- **Assumption**: the margin is spread as an equal *additive* slice across
  outcomes.
- **Pros**: simple; for `n = 2` it is *identical* to Shin's method.
- **Cons**: can produce **negative** probabilities for strong longshots (`r_i`
  small, `M/n` not); over-corrects the bias relative to multiplicative.
- **When preferred**: rarely for 3-way 1X2; occasionally for 2-way markets
  (O/U, AH) where it coincides with Shin and is cheap.
- Source: `implied` vignette (as above); Clarke, Kovalchik & Ingram summaries in
  penaltyblog docs <https://penaltyblog.readthedocs.io/en/latest/implied/implied.html>.

### 1c. Power / logarithmic method ("Wisdom of the Crowd")

    p_i = r_i ^ (1/k),  solve k so that  sum_i r_i^(1/k) = 1

- `k > 1` typically. Because `x -> x^(1/k)` is concave on `(0,1)`, it shrinks
  large `r_i` less and small `r_i` more, i.e. **removes more margin from
  longshots** — the favourite–longshot correction.
- **Assumption**: the true-to-implied map is a power law; equivalently the
  bookmaker's margin is multiplicative in *log-odds*.
- **Solver**: 1-D monotone root find on `k` (bisection or Brent on `[0.5, 5]`);
  `sum_i r_i^(1/k)` is strictly decreasing in `k`, so it is well-behaved.
- **When preferred**: single-book odds from a margin-heavy book (bet365, local
  books) where the bias is material.
- Source: "Wisdom of the Crowd" method attributed to Joseph Buchdahl / Keith
  Cheung; `implied` vignette; penaltyblog docs (as above).

### 1d. Odds-ratio method (Cheung)

    p_i = r_i / ( OR + r_i - OR * r_i ),  solve OR so that  sum_i p_i = 1

where the odds-ratio parameter `OR` satisfies
`OR = [p_i (1 - r_i)] / [r_i (1 - p_i)]` for every `i`.

- Same "wisdom of the crowd" family as the power method; corrects the bias in a
  similar direction. `OR = 1` recovers `p_i = r_i` (no adjustment).
- **Solver**: 1-D root find on `OR` in `(0, few]`.
- Source: `implied` vignette; Cheung, "Fixed-odds betting and traditional
  odds" (Wisdom of the Crowd doc) via penaltyblog docs.

### 1e. Shin (1992/1993) model

Shin models the bookmaker as setting odds against a fraction `z` of **insider**
(perfectly informed) bettors, the rest betting in proportion to true
probabilities. Inverting the bookmaker's zero-expected-profit condition gives, for
each outcome,

    p_i = ( sqrt( z^2 + 4 (1 - z) * r_i^2 / B ) - z ) / ( 2 (1 - z) )

with `B = sum_j r_j` the booksum, and `z in [0, 1)` chosen so that
`sum_i p_i = 1`.

- **2-outcome closed form** (`n = 2`): `z` is available analytically and the
  result equals the additive method.
- **3-outcome (1X2)**: no closed form; solve for `z` by a fixed-point iteration
  or 1-D root find on `g(z) = sum_i p_i(z) - 1` (monotone in `z` on the relevant
  range; Newton or bisection on `[0, 0.5]`). Practical implementations:
  Jullien & Salanié (1994) fixed-point, or the Jensen–Shannon variant in the
  `implied` package; convergence threshold ~1e-10, <20 iterations.
- **Interpretation of `z`**: estimated share of "informed"/insider money. For
  football 1X2 typical fitted `z` is small, roughly **0.02–0.06** (a few
  percent); larger for thin markets. `z -> 0` recovers multiplicative
  normalisation.
- **Assumption**: the entire margin arises from adverse selection against
  insiders; the loading is therefore heavier where an insider edge is more
  damaging (longshots) — again a favourite–longshot correction, derived rather
  than assumed functional form.
- Sources: Shin, H.S. (1993), "Measuring the Incidence of Insider Trading in a
  Market for State-Contingent Claims", *Economic Journal* 103(420), 1141–1153;
  Štrumbelj (2014) (as above); Karl Whelan (2024), "On Estimates of Insider
  Trading in Sports Betting" <https://www.karlwhelan.com/Papers/ShinzNov24.pdf>;
  mberk/shin Python implementation notes <https://github.com/mberk/shin>;
  `implied` vignette.

### 1f. What the literature/practice favours for football 1X2

- **Štrumbelj (2014)** and subsequent replications: **Shin** and the
  **power/odds-ratio** family produce better-calibrated 1X2 forecasts than plain
  normalisation *for single-book, margin-heavy odds*, because they undo the
  favourite–longshot bias. Basic normalisation is consistently "the least
  accurate" (`implied` vignette).
- **On efficient odds** (Pinnacle, or a broad market average such as
  football-data.co.uk `AvgH/D/A`), the differences are **small**. The penaltyblog
  2024/25 EPL experiment found multiplicative RPS 0.19724 vs Shin 0.19731 vs
  logarithmic/odds-ratio 0.19730 — a spread of <0.0001, i.e. negligible
  (<https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/>).
- **Consensus takeaway**: use a bias-correcting method (Shin or power) when
  working from one margin-heavy book; the choice barely matters when working from
  Pinnacle or the market average. Shin has the extra benefit of returning `z`,
  a cheap data-quality signal (implausible `z` => bad odds row).

---

## 2. From de-vigged 1X2 (+ O/U 2.5, + AH) to a scoreline / team-goals distribution

Goal: recover two attacking rates `lambda_H` (home expected goals) and
`lambda_A` (away expected goals) — plus optionally a dependence parameter — such
that the induced scoreline grid reproduces `(pH, pD, pA)` and, when available,
the total-goals line.

### 2a. Dixon & Coles (1997) bivariate Poisson with low-score correction

Joint pmf of `(X, Y)` = (home goals, away goals):

    P(X = x, Y = y) = tau_{lambda,mu}(x, y) * Pois(x; lambda) * Pois(y; mu)

with `Pois(k; r) = exp(-r) r^k / k!` and the low-score correction

    tau(0,0) = 1 - lambda * mu * rho
    tau(0,1) = 1 + lambda * rho
    tau(1,0) = 1 + mu * rho
    tau(1,1) = 1 - rho
    tau(x,y) = 1                     otherwise

`rho` (the dependence parameter, "rho" in the DC paper) is usually slightly
**negative** for football, which *adds* mass to 0–0 and 1–1 and removes it from
1–0 / 0–1, fixing the independent-Poisson under-prediction of draws.
Admissibility constraints: `max(-1/lambda, -1/mu) <= rho <= min(1/(lambda mu), 1)`.

Rate parametrisation (team-strength form):

    log lambda = c + attack_home  + defence_away + gamma      (gamma = home edge)
    log mu     = c + attack_away  + defence_home

**Time-decay weighting** (DC 1997 §4): fit by maximising a *weighted*
log-likelihood

    L(theta) = sum_{matches k}  phi(t_now - t_k) * log P(x_k, y_k; theta)
    phi(dt)  = exp( -xi * dt )

with `dt` in days. DC estimate `xi` by maximising out-of-sample predictive
likelihood; the widely-quoted value is `xi ≈ 0.0065` per **half-week**
(≈ 0.0031/day), i.e. a half-life near **half a season** (~110 days). Sources:
Dixon & Coles (1997), "Modelling Association Football Scores and Inefficiencies
in the Football Betting Market", *JRSS-C* 46(2), 265–280; dashee87 walk-through
<https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/>;
opisthokonta time-weighting notes <https://opisthokonta.net/?p=1013>.

For **Stage 2 we do not fit DC to results** — we use the *DC scoreline shape*
(the `tau` correction) but pin `lambda, mu` from the odds (2c). The DC fit stays
relevant only as (i) the fallback strength model when odds are missing and (ii) a
source of a plausible `rho` (use a small fixed negative `rho`, e.g. `-0.03` to
`-0.13`, or a value fit once on historical Serie A).

### 2b. Karlis & Ntzoufras (2003) bivariate Poisson (and diagonal inflation)

True bivariate Poisson (not just a correction): let
`X = W1 + W3`, `Y = W2 + W3` with independent `W_j ~ Pois(lambda_j)`.

    P(X = x, Y = y) = exp(-(l1+l2+l3)) * (l1^x / x!) * (l2^y / y!)
                      * sum_{k=0}^{min(x,y)} C(x,k) C(y,k) k! * ( l3 / (l1 l2) )^k

Properties: `E[X] = l1 + l3`, `E[Y] = l2 + l3`, `Cov(X, Y) = l3 >= 0`. So the
model can only express **non-negative** score correlation; `l3 = 0` collapses to
independent Poisson. Regression: `log l1, log l2` on attack/defence/home as in DC;
`l3` either constant or a log-linear function of covariates.

**Diagonal-inflated** extension (needed because empirically the draw correction
must go *up* and `l3 >= 0` cannot over-weight draws enough):
`P(x,y) = (1-p) BP(x,y; l1,l2,l3)` for `x != y`, plus `p * D(x; theta)` added on
the diagonal `x = y`, with `D` a discrete distribution (geometric/Poisson) and
`p in [0,1]`.

**Fitting**: EM (the `W3` count is latent; E-step imputes `E[W3 | x, y]`, M-step
runs weighted Poisson GLMs). Karlis & Ntzoufras (2003),
"Analysis of sports data by using bivariate Poisson models", *The Statistician*
52(3), 381–393
<http://www2.stat-athens.aueb.gr/~jbn/papers2/08_Karlis_Ntzoufras_2003_RSSD.pdf>
(and the 2003 working paper
<http://www2.stat-athens.aueb.gr/~karlis/Bivariate%20Poisson%20Regression.pdf>).

For Stage 2, Karlis–Ntzoufras matters mainly as the **theory** behind the
supremacy+total inversion; the `l3 >= 0` restriction is a reason to keep the DC
`tau` (which allows the empirically-correct *negative* draw correction) for the
scoreline shape.

### 2c. Supremacy + total parametrisation (the odds inversion we want)

Re-parametrise the two rates as

    supremacy  s = lambda_H - lambda_A        (goal superiority)
    total      T = lambda_H + lambda_A        (expected goals in the match)
    =>  lambda_H = (T + s) / 2,   lambda_A = (T - s) / 2

Then:

1. **Pin `T` from the Over/Under 2.5 line.** Under independent Poisson the match
   total `N = X + Y ~ Pois(T)`. Given de-vigged `q = P(Over 2.5) = P(N >= 3)`,
   solve the scalar equation

       1 - exp(-T) * (1 + T + T^2/2)  =  q

   for `T` by 1-D root find (LHS strictly increasing in `T`, so bisection on
   `[0.3, 6]` is safe). With the DC `tau` the total is no longer exactly Poisson;
   either (a) ignore the tiny `tau` effect on `P(N>=3)` and solve as above, or
   (b) root-find on the full grid `P(N>=3; lambda_H, lambda_A, rho)` jointly with
   step 2. (a) is accurate to ~1e-3 and is enough.
   *Fallback when O/U absent*: set `T` = league/season average total for Serie A
   (historically ≈ 2.6–2.9 goals/match; compute per-season from
   football-data.co.uk `FTHG+FTAG`), optionally tilted by the two clubs'
   season-to-date for/against rates.

2. **Pin `s` from de-vigged 1X2.** Given `T` (fixed) and a candidate `s`, build
   `lambda_H, lambda_A`, form the DC scoreline grid up to e.g. 10x10 (>=8x8 is
   enough; tail mass < 1e-4), and compute model
   `P_hat_H(s), P_hat_D(s), P_hat_A(s)` by summing the grid. Define the **1-D
   residual**

       f(s) = [P_hat_H(s) - P_hat_A(s)] - [pH - pA]

   `f` is smooth and monotone increasing in `s` (more supremacy => more home,
   less away), so a bracketed root find (Brent on `s in [-3, 3]`) converges in
   ~6–10 iterations. This matches the home/away *margin* exactly; the draw
   probability is then whatever the model implies. Because with `T` fixed there is
   only one free scalar, you can match *either* `pH - pA` *or* `pD` but not both —
   matching the supremacy (H vs A) is the standard choice and the draw comes out
   close (a good check: `|P_hat_D - pD| < ~0.02` on efficient odds; larger means
   `T` or `rho` is off).

3. **Optional refinement with two free parameters.** If you want to hit all three
   of `(pH, pD, pA)` (2 independent constraints) *and* the O/U line (a 3rd), you
   have 3 free knobs `(lambda_H, lambda_A, rho)`; solve the 3x3 system with a
   damped Newton / `scipy.optimize.least_squares`. This is the "full" fit — more
   accurate, less robust (2f).

4. **Asian handicap as a cross-check or `T`-free supremacy source.** A quoted AH
   line `h` with (de-vigged, 2-way, so Shin = additive) home price implies
   `P(X - Y > h) ≈ 0.5` at the *balanced* line; more generally the de-vigged AH
   probability `P(X - Y + h > 0)` is another equation in `(lambda_H, lambda_A)`.
   The goal difference `X - Y` under (bivariate) Poisson is **Skellam**-distributed,
   so `P(X - Y = d)` has the closed form
   `exp(-(lambda_H+lambda_A)) (lambda_H/lambda_A)^{d/2} I_{|d|}(2 sqrt(lambda_H lambda_A))`
   with `I` the modified Bessel function; handy for AH and for the win/draw/loss
   split without building the full grid. Use AH, when present, as an independent
   estimate of `s` and average it with the 1X2-derived `s` (or just as a
   validation gate). Karlis & Ntzoufras (2009), "Bayesian modelling of football
   outcomes: using the Skellam's distribution for the goal difference"
   <https://www.researchgate.net/publication/228621612>.

### 2d. Independent-Poisson approximation (robust fallback)

Drop `tau` (`rho = 0`): `X ~ Pois(lambda_H)`, `Y ~ Pois(lambda_A)` independent.
Everything in 2c still works and is faster (grids factorise; Skellam closed form
exact). Accuracy cost vs DC/bivariate:

- Match-outcome probabilities: independent Poisson **under-predicts draws** by
  roughly 1–3 percentage points (the 0–0/1–1 deficit), over-predicting the
  favourite slightly. RPS/Brier differences reported in the literature between
  independent Poisson and DC are **small** (order 0.001–0.005 RPS) — DC is a
  refinement, not a different regime (dashee87, opisthokonta; Ley, Van de Wiele &
  Van Eetvelde (2019), "Ranking soccer teams on the basis of their current
  strength: a comparison of maximum likelihood approaches", *Statistical
  Modelling*).
- For **clean sheet / team-goals** marginals specifically, the `tau` correction
  mostly moves mass *between* 0–0 and 1–0/0–1, so it *does* shift
  `P(opp scores 0)` by ~1–2 pts — worth keeping `tau` for the CS number even if
  we tolerate independence elsewhere.

Verdict: independent Poisson is a fully acceptable fallback; carry a small fixed
negative `rho` in the primary path.

### 2e. Clean expressions once you have `(lambda_H, lambda_A, rho)`

- Scoreline grid `P(x, y)` up to `K x K` (`K = 10`), renormalised to sum 1.
- Home/Draw/Away by summing `x>y`, `x=y`, `x<y`.
- Team goals scored: `P(X = k) = sum_y P(k, y)` (with `tau` this is *not* exactly
  `Pois(k; lambda_H)`, differs only at `k in {0,1}`).
- Team goals conceded by home team = `P(Y = k)` marginal.

### 2f. Known instabilities of the fit and how practitioners constrain it

- **Draw over-fit / `rho` blow-up**: free `rho` in a per-match 3-parameter fit
  drifts to the admissibility boundary when 1X2 and O/U are mutually
  inconsistent (stale line, palpable error). Fix: **fix `rho`** to a
  Serie-A-historical constant (fit once, offline) and only free `(lambda_H,
  lambda_A)`; clamp `rho` to the admissible interval each iteration.
- **Total/supremacy identifiability**: with only 1X2 (no O/U) the total `T` is
  weakly identified — many `(T, s)` pairs give similar `(pH, pD, pA)` because the
  draw rate carries the total information. Never free `T` on 1X2 alone; pin it
  from O/U or a prior.
- **Grid truncation**: `K` too small biases high-scoring tails; use `K >= 8`,
  renormalise, and check residual tail mass `< 1e-4`.
- **Degenerate odds rows**: booksum `B` far from typical (e.g. `< 1.01` or
  `> 1.15` for a 3-book average), missing one of H/D/A, or Shin `z` outside
  `[0, 0.15]` => reject the row, fall back to the strength model.
- **Root-find robustness**: always *bracket* (Brent/bisection), never bare
  Newton; the supremacy residual `f(s)` is monotone so bracketing always works.
- **Sanity gates** post-solve: `0.05 < P_hat_D < 0.40`, `|P_hat_D - pD| < 0.03`,
  `0.7 < T < 4.5`, `|s| < 2.5`. Failing any => fallback.
- Sources: opisthokonta Dixon–Coles series <https://opisthokonta.net/?cat=48>;
  Whitaker, "The Bivariate Poisson Distribution and its Applications to Football"
  <https://gawhitaker.github.io/project.pdf>; Buchdahl / betting practitioner
  notes on odds->supremacy
  <https://www.thefreelibrary.com/Translating+odds+into+supremacy.-a060164652>.

---

## 3. Clean-sheet and goals-conceded probabilities

For a club playing at home with opponent-goal rate `lambda_A` and dependence
`rho`:

    P(clean sheet, home) = P(Y = 0) = sum_{x >= 0} P(X = x, Y = 0)

With the DC correction only `x in {0,1}` differ from independence:

    P(Y = 0) = exp(-lambda_A) * [ (1 - lambda_H lambda_A rho) exp(-lambda_H)
                                  + (1 + lambda_H rho) lambda_H exp(-lambda_H)
                                  + sum_{x>=2} Pois(x; lambda_H) ]
             = exp(-lambda_A) * ( 1 + lambda_A rho lambda_H exp(-lambda_H) * (something) )

i.e. **not** simply `exp(-lambda_A)`. Practically: compute it from the grid, do
not use the marginal Poisson shortcut when `rho != 0`.

Goals conceded distribution for the home club = the `Y` marginal:
`P(concede = k) = sum_x P(x, k)`.

**The correlation issue.** A clean sheet is `P(opponent_goals = 0)`, a property of
the **joint** distribution, not of the opponent's marginal alone, because
`X` and `Y` are dependent (`rho != 0`, or `l3 > 0` in Karlis–Ntzoufras). Under
independence `P(CS) = exp(-lambda_A)` exactly; under negative `rho` the true
`P(CS)` is slightly **higher** at low scores (mass piled on 0–0). Concretely the
error from using the marginal shortcut is ~1–2 percentage points — small but
one-directional, and clean sheets are worth a discrete +1 in the fantavoto
mapping for D/P, so keep the joint calculation.

For the fantavoto engine we need, per club per gameweek:
`P(CS)`, `E[goals conceded]`, and ideally the full `P(concede = k)` vector for
`k = 0..5+` (the +1/-1 modifiers and the D/P clean-sheet bonus depend on the
count, not just the mean).

---

## 4. Conditioning the empirical Monte-Carlo ensemble on a target marginal

Setup: we already draw an ensemble `{X^(1), ..., X^(S)}` of full-season / gameweek
scenarios by bootstrap over historical player performances. Each scenario carries,
among many quantities, a realised team value `g_s = team_goals_conceded` (or
`team_goals`, or a clean-sheet indicator) for the club of interest. We now have an
**externally specified target distribution** `pi(g)` for that quantity (from
§2–3). We want the *reweighted* ensemble's `g`-marginal to match `pi`, **without**
assuming any parametric form for the thing we ultimately care about (player base
voto), and while preserving the joint dependence the bootstrap captured between
`g` and everything else.

### 4a. Importance reweighting (SIR without the resampling step)

Let `hat_f(g)` be the ensemble's current (empirical) marginal of `g` — e.g. a
histogram over integer conceded counts, or a KDE. Assign each scenario a weight

    w_s  ∝  pi(g_s) / hat_f(g_s) ,     then normalise  sum_s w_s = 1.

Any downstream expectation (mean fantavoto, quantiles, `P(fantavoto > x)`) is then
the **weighted** statistic over the unchanged scenarios. This is plain importance
sampling with the target = "bootstrap joint, but with the `g`-marginal replaced by
`pi`". Because we only touch the marginal of `g`, the conditional
`p(everything | g)` is inherited from the bootstrap — exactly the "don't assume a
shape for base voto" requirement.

- **Discrete `g` (conceded counts)**: `hat_f(g_s)` = fraction of scenarios with
  that count; `w_s = (pi(k) / hat_f(k)) / S` for a scenario with `g_s = k`. This
  is equivalent to **post-stratification / raking** on the conceded-count
  variable.
- **Continuous `g`**: use a smooth `hat_f` (KDE or fine histogram) to avoid
  division noise.

### 4b. Weighted resampling / SIR (when you need an equal-weight ensemble)

Draw `S'` scenarios **with replacement** from `{X^(s)}` with probabilities
`w_s`. Result: an unweighted ensemble whose `g`-marginal ≈ `pi`. Use this when
downstream code expects equal-weight draws (e.g. feeds another sampler, or plots
that assume uniform weights). Standard multinomial resampling; systematic /
residual resampling reduces resampling noise.

Rao–Blackwellised alternative: keep weights for expectations, only resample for
display / for code paths that cannot take weights.

### 4c. Effective sample size and weight degeneracy

    ESS = 1 / sum_s w_s^2        (w normalised),   1 <= ESS <= S

- Report `ESS / S`. Rule of thumb: `ESS/S > 0.5` fine; `0.2–0.5` usable with
  caution; `< 0.1` the conditioning is fighting the ensemble — the target `pi`
  puts mass where the bootstrap has almost no scenarios.
- Degeneracy causes here: (i) `pi` much sharper than `hat_f` (a strong favourite:
  odds say `P(CS) = 0.55` but the bootstrap club rarely kept clean sheets);
  (ii) tail mismatch (`pi` has mass at 4+ conceded, ensemble caps at 3).
- Mitigations, in order of preference:
  1. **Weight clipping / trimming**: cap `w_s` at a multiple (e.g. 10x) of the
     mean weight; small bias, large variance reduction.
  2. **Tempering**: raise the likelihood ratio to a power `alpha in (0,1]`,
     `w_s ∝ (pi(g_s)/hat_f(g_s))^alpha`; `alpha < 1` partially conditions,
     trading bias for ESS. Choose `alpha` to hit a target ESS floor.
  3. **Widen the proposal**: increase bootstrap `S`, or add scenario diversity
     (block bootstrap, opponent-strength jitter) so the ensemble covers `pi`'s
     support before reweighting.
  4. **Match a coarser functional**: condition on `E[g]` and `Var[g]` (two
     moment constraints via exponential tilting / max-entropy weights
     `w_s ∝ exp(theta1 g_s + theta2 g_s^2)`, solve `theta` to match) instead of
     the full `pi`. Far more ESS-friendly, still nonparametric in base voto.
- **Reweight vs resample**: prefer **reweighting** (keeps all information, no
  Monte-Carlo resampling noise, ESS is transparent). Resample only when a
  downstream consumer cannot accept weights, and then resample `S' = S` (or more)
  with systematic resampling.

### 4d. Football-specific precedent

Little *published* work SIR-conditions a fantasy ensemble on market-implied
marginals; it is mostly FPL-community practice (§6). Closest formal analogues:
market-calibrated models that shift a model to match bookmaker probabilities
(Wheatcroft in-play AFT <https://arxiv.org/pdf/2605.16066>; the "odds as
calibration target" stance in Štrumbelj 2014); odds as an informative prior on
team strength in Bayesian football models (Karlis–Ntzoufras Bayesian variants,
Egidi et al.); particle-filter team-strength models (Baio & Blangiardo) that use
the same SIR/ESS machinery on states rather than on a fantasy ensemble. The
method is standard SIR; the novelty for us is the *object* reweighted (a
nonparametric fantavoto ensemble) and the *target* (odds-implied conceded-goal
marginal) — document it as our own construction.

---

## 5. Scoring / validation — deciding "odds-conditioned beats the scalar shift"

### 5a. CRPS

Definition (Gneiting & Raftery 2007, "Strictly Proper Scoring Rules,
Prediction, and Estimation", *JASA* 102(477), 359–378
<https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf>):

    CRPS(F, y) = ∫_{-inf}^{inf} ( F(t) - 1{ y <= t } )^2 dt
               = E_F |Z - y| - 1/2 E_F |Z - Z'|          (energy form)

with `Z, Z'` iid from the predictive `F`. Lower is better; reduces to MAE for a
deterministic forecast; proper.

- **Real-valued predictive (fantavoto)**: use the energy form with the ensemble.
- **Count predictive (goals, goals conceded)**: CRPS is still well-defined on the
  integer CDF. Closed forms exist:
  - **Poisson(`lambda`)**: `crps_pois` in the `scoringRules` package
    (Jordan, Krüger, Lerch, *JSS* 2019; Wei & Held 2014, "Calibration tests for
    count data", *TEST*) —
    <https://search.r-project.org/CRAN/refmans/scoringRules/html/crps.numeric.html>.
    Closed form:
    `CRPS = lambda (2 F_P(y-1; lambda) - 1) + y (1 - 2 F_P(y; lambda))
            + 2 lambda exp(-2 lambda) ( I_0(2 lambda) + I_1(2 lambda) )`
    (with `F_P` the Poisson CDF, `I_j` modified Bessel) — Wei & Held (2014).
  - **Negative binomial**: `crps_nbinom`, same references.
- **Ensemble / empirical CRPS estimator** (what we use for the conditioned
  ensemble): for members `x_1..x_m` sorted,

    CRPS_hat = (1/m) sum_i |x_i - y|  -  1/(2 m^2) sum_{i,j} |x_i - x_j|

  This is the "fair"/NRG-style estimator. It has a **negative-of-order-1/m bias**
  for small `m` (it rewards under-dispersion): the second term underestimates
  `E|Z - Z'|`. The **unbiased ("fair", PWM)** version divides the double sum by
  `m(m-1)` instead of `m^2`:

    CRPS_fair = (1/m) sum_i |x_i - y| - 1/(2 m (m-1)) sum_{i,j} |x_i - x_j|

  Zamo & Naveau (2018), "Estimation of the Continuous Ranked Probability Score
  with Limited Information and Applications to Ensemble Weather Forecasts",
  *Mathematical Geosciences* 50, 209–234
  <https://link.springer.com/article/10.1007/s11004-017-9709-7>; also
  Ferro (2014), Fricker et al. (2013). With our `S` in the hundreds/thousands the
  bias is tiny, but **use `CRPS_fair`** anyway (free) and keep `m` fixed across
  the models being compared so any residual bias cancels.

### 5b. Calibration diagnostics

- **PIT histogram** (continuous / fantavoto): `u_k = F_k(y_k)` for each fixture
  `k`; if calibrated, `{u_k}` ~ Uniform(0,1). U-shape => under-dispersed
  (over-confident), hump => over-dispersed, slope => bias. For an ensemble use the
  **randomised PIT** or the **verification rank histogram** (Talagrand): rank of
  the observation among the `m` members; flat = calibrated, U = under-dispersed,
  dome = over-dispersed, sloped = biased. (Gneiting, Balabdaoui & Raftery 2007,
  "Probabilistic forecasts, calibration and sharpness", *JRSS-B* 69(2), 243–268.)
- **Coverage**: empirical coverage of central `(1-alpha)` predictive intervals vs
  nominal, per horizon.
- **Reliability diagram + Brier decomposition** for the binary/categorical
  targets (clean sheet; win/draw/loss):

    Brier = 1/N sum (p - o)^2
    Brier = Reliability - Resolution + Uncertainty
          (Murphy 1973 decomposition)

  Report reliability (calibration, lower better) and resolution (sharpness,
  higher better) separately; a lower Brier that comes only from resolution with
  worse reliability is a red flag.
- **RPS** (ordered 1X2): standard in the football-odds literature, but
  **Wheatcroft (2021), "Evaluating probabilistic forecasts of football matches:
  the case against the ranked probability score"**
  <https://researchonline.lse.ac.uk/id/eprint/111494/3/Wheatcroft_evaluating_probabilistic_forecasts_published.pdf>
  argues log-loss / Brier + explicit calibration+sharpness are preferable for
  football. Report RPS for comparability but decide on log-loss/Brier + CRPS.

### 5c. What to report to justify replacing the scalar shift

Walk-forward (expanding-window, gameweek-by-gameweek, seeded) over multiple Serie
A seasons, three arms:

1. **baseline**: current Dixon–Coles/Elo scalar shift;
2. **odds-conditioned**: §2–4 pipeline;
3. **null**: no shift (raw bootstrap ensemble).

Metrics, per arm, with paired differences and a Diebold–Mariano / bootstrap CI on
the difference vs baseline:

| target | primary metric | secondary |
|---|---|---|
| player fantavoto (main output) | `CRPS_fair` (ensemble) | MAE of mean, interval coverage, PIT/rank histogram |
| team goals scored / conceded | CRPS (Poisson/NB closed form or ensemble) | rank histogram |
| clean sheet (D/P) | Brier + reliability/resolution | log-loss, calibration curve |
| match W/D/L | log-loss, Brier | RPS (for comparability) |
| roster/auction decision utility | replayed auction value delta, top-k rank corr (NDCG@k) | — |

Decision rule: odds-conditioning "wins" if it improves player-fantavoto
`CRPS_fair` **and** clean-sheet Brier out-of-sample, with no material calibration
regression (PIT/rank histogram not visibly worse), and the improvement survives
on the seasons where odds completeness is good. Also gate on **ESS/S** (§4c)
staying healthy on the bulk of fixtures — a metric win bought with `ESS/S < 0.1`
everywhere is fragile.

The project already has `src/fantacalcio/modeling/metrics.py` (CRPS empirico, PIT,
coverage, Brier, log-loss multinomiale, NDCG, MAE/RMSE, Spearman — Stage 1,
ADR-2026-071). Add `CRPS_fair` (unbiased double-sum) and a rank-histogram helper
if not already present.

---

## 6. Prior art specific to fantasy football / fantacalcio

- **No peer-reviewed "market odds -> player fantasy points prior" paper** for
  fantacalcio specifically (Italian Mantra/Classic scoring). The academic
  fantasy-football literature (Bonomo et al.; Matthews, Ramchurn & Chalkiadakis
  2012 on FPL as MDP; Gupta 2019) forecasts points from form/fixtures, not from
  odds directly.
- **FPL analytics community** (directly transferable): converting bookmaker
  markets into player point priors is standard practice:
  - **Clean-sheet odds -> defender/keeper points**: sites publish de-vigged
    team clean-sheet probabilities weekly and multiply by the CS point value;
    e.g. Fantasy Football Scout, FPL Review's "Rate My Team" / projections,
    "nevermanagealone", fplrotationplanner "Odds" page
    <https://www.fplrotationplanner.com/odds>, allfantasytips clean-sheet odds.
    Method: (team implied goals against from 1X2 + O/U) -> `P(CS) = exp(-lambda_against)`
    (usually the *independent* shortcut) -> expected CS points.
  - **Anytime-goalscorer (ATGS) and to-score-2+ markets** -> attacking-return
    point priors: de-vig the ATGS 2-way market per player, combine with team
    total via a "goal share" model. FPL Review and the "FPL Optimized" /
    "Fantasy Football Hub" projection engines blend model + odds this way.
  - **Over/Under and 1X2** -> team expected goals -> per-player expected
    goal involvements via historical share; the "Poisson + odds" tutorials
    (Smarkets, penaltyblog, dashee87) are the community reference implementations.
  - Buchdahl (Football-Data's own author), *Squares & Pari-mutuel* and
    joseph-buchdahl.com articles: de-vig methods, value of Pinnacle/closing line,
    supremacy-from-odds — the practitioner canon behind football-data.co.uk.
- **Takeaway for us**: the community consensus recipe is exactly the Stage 2
  pipeline (de-vig -> team lambdas -> Poisson marginals -> point mapping); our
  additions are (a) DC `tau` instead of the independent shortcut for the CS
  number, (b) SIR conditioning of a *nonparametric* ensemble instead of a
  closed-form point expectation, (c) formal CRPS/PIT validation.

---

## 7. football-data.co.uk specifics (Serie A = `I1`, ~2015–2026)

Source: football-data.co.uk notes/key
<https://www.football-data.co.uk/notes.txt>; football-docs `search_docs`
(free-sources / football-data.co.uk overview). URL pattern
`https://www.football-data.co.uk/mmz4281/{SSSS}/I1.csv` (e.g. `2425` for
2024/25). Results columns: `Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG,
HTAG, HTR, HS, AS, HST, AST, ...`.

### 7a. 1X2 (match-odds) columns

| bookmaker / aggregate | Home | Draw | Away | notes |
|---|---|---|---|---|
| Bet365 | `B365H` | `B365D` | `B365A` | present every season |
| Pinnacle | `PSH` (older `PH`) | `PSD`/`PD` | `PSA`/`PA` | sharpest; occasional gaps early seasons |
| Bet&Win/bwin | `BWH` | `BWD` | `BWA` | mostly present |
| Interwetten | `IWH` | `IWD` | `IWA` | patchier |
| William Hill | `WHH` | `WHD` | `WHA` | present most seasons |
| VC/BetVictor | `VCH` | `VCD` | `VCA` | |
| **market max** | `MaxH` | `MaxD` | `MaxA` | best price across books, from ~2019/20 |
| **market average** | `AvgH` | `AvgD` | `AvgA` | mean across books, from ~2019/20 |
| **Betbrain avg (legacy)** | `BbAvH` | `BbAvD` | `BbAvA` | up to ~2018/19 only |
| **Betbrain max (legacy)** | `BbMxH` | `BbMxD` | `BbMxA` | up to ~2018/19 only |
| Betbrain book count | `Bb1X2` | | | # books in the Bb averages |

Closing-line variants exist for some books/seasons with a `C` suffix
(`B365CH`, `PSCH`, `AvgCH`, `MaxCH`, ...); when present these are the **closing**
odds and are the ones to prefer for a leak-free `as_of` (kickoff) feature.

### 7b. Over/Under 2.5 goals columns

| source | Over 2.5 | Under 2.5 | notes |
|---|---|---|---|
| Bet365 | `B365>2.5` | `B365<2.5` | present most seasons from ~2013/14 |
| Pinnacle | `P>2.5` | `P<2.5` | |
| market max | `Max>2.5` | `Max<2.5` | from ~2019/20 |
| market average | `Avg>2.5` | `Avg<2.5` | from ~2019/20 |
| Betbrain avg (legacy) | `BbAv>2.5` | `BbAv<2.5` | up to ~2018/19 |
| Betbrain max (legacy) | `BbMx>2.5` | `BbMx<2.5` | up to ~2018/19 |
| Betbrain O/U book count | `BbOU` | | |
| closing variants | `B365C>2.5`, `AvgC>2.5`, ... | | some seasons |

Only the **2.5** line is published; no 1.5/3.5 in this dataset. Completeness is
good for `I1` from ~2013/14 onward; a handful of early rows miss it.

### 7c. Asian handicap columns

| field | meaning |
|---|---|
| `AHh` | market-consensus handicap line (home), from ~2019/20 |
| `B365AHH` / `B365AHA` | Bet365 home/away AH prices |
| `B365AH` | Bet365's quoted handicap size (older seasons) |
| `PAHH` / `PAHA` | Pinnacle AH prices |
| `AvgAHH` / `AvgAHA`, `MaxAHH` / `MaxAHA` | market avg / max AH prices, ~2019/20+ |
| `BbAHh`, `BbAvAHH`, `BbMxAHH`, `BbAH` (legacy) | Betbrain AH line/prices, up to ~2018/19 |
| closing: `AHCh`, `B365CAHH`, `PCAHH`, `AvgCAHH` | closing AH line/prices, some seasons |

AH coverage for `I1` is **less complete and less consistent** than 1X2/O2.5,
especially pre-2016 and in the Betbrain->Max/Avg transition; treat AH as
*optional enrichment / cross-check*, never a hard dependency.

### 7d. Completeness by era and what is safe for `I1` 2015–2026

- **2015/16 – 2018/19**: rely on `B365H/D/A`, `B365>2.5`/`B365<2.5`, and the
  **Betbrain** aggregates `BbAvH/D/A`, `BbAv>2.5`/`BbAv<2.5` (plus `PSH/D/A`
  where present). `Bb1X2`/`BbOU` tell you how many books backed each average.
- **2019/20 – 2025/26**: Betbrain columns **disappear**; use `AvgH/D/A`,
  `Avg>2.5`/`Avg<2.5` (and `MaxH/D/A`). `B365*` and `PS*` continue throughout.
- **Recommended primary de-vig input**: the **market average** (`BbAv*` pre-2019,
  `Avg*` from 2019) for 1X2 and O/U 2.5 — it is already a multi-book consensus,
  low margin, so de-vig method choice barely matters (§1f). Keep `B365*` as
  fallback when the average is missing, and `PS*` as a sharpness reference.
- **Always safe across the whole 2015–2026 span for `I1`**: `B365H/D/A`. Nearly
  always: `B365>2.5`/`B365<2.5`. Use a season-aware column resolver:
  `1X2_avg = coalesce(AvgH, BbAvH, B365H)` etc.
- **Leakage / `as_of`**: football-data.co.uk odds are pre-match "day-before"
  prices (opening-ish), except the explicit `*C*` closing columns. Both are
  available strictly before kickoff, so either is safe for a kickoff-time
  `available_time`; prefer closing (`*C*`) when present as it is the more
  efficient line, else the opening average. Record which column won in the
  feature lineage (`quality_tier`: A = closing average, B = opening average,
  C = single-book fallback).

---

## 8. Recommended for our Stage 2

**De-vig.** Input = **market average** 1X2 (`Avg*` / `BbAv*` / `B365*` coalesced)
and average O/U 2.5. Method = **Shin** (3-outcome, JS/Jullien–Salanié solver),
with **multiplicative normalisation as the fallback** and as a cross-check. On the
market average the two agree to <0.001 in probability; Shin is chosen mainly for
the `z` diagnostic (reject rows with `z` outside `[0, 0.15]`). For the 2-way O/U
and AH markets Shin == additive, computed in closed form.

**Goals model.** Supremacy + total parametrisation (§2c): pin the expected total
`T` from de-vigged `P(Over 2.5)` via the 1-D Poisson-tail root find; pin supremacy
`s` from `pH - pA` via a bracketed root find on the **Dixon–Coles** scoreline grid
(`K = 10`) with a **fixed** negative `rho` fit once on historical Serie A
(expect ≈ -0.03 to -0.10); clamp `rho` to its admissible interval. When O/U 2.5 is
missing, set `T` from the season-to-date Serie A average total tilted by the two
clubs' for/against rates. **Fallback model**: independent Poisson (`rho = 0`) when
the DC grid solve fails a sanity gate (§2f) or odds are single-book only; accepted
accuracy loss ≈ 0.001–0.005 RPS and ~1–2 pts on clean sheet. AH columns, when
present, give an independent `s` estimate used only as a validation gate, not
blended in v1.

**Clean sheet / conceded.** Always from the **joint** DC grid, never the
`exp(-lambda_against)` marginal shortcut (§3). Emit per club per gameweek:
`P(concede = k)` for `k = 0..6+`, `P(CS)`, `E[concede]`.

**Conditioning.** **Importance reweighting (SIR without resampling)** of the
existing bootstrap ensemble: `w_s ∝ pi(g_s) / hat_f(g_s)` on the
`team_goals_conceded` (and `team_goals`) count marginal, `hat_f` a smoothed
histogram, weights normalised, **clipped at 10x mean**. No parametric assumption
on player base voto — the bootstrap's `p(base voto | conceded)` is inherited.
Report `ESS/S` per fixture; if `ESS/S < 0.1`, **temper** with `alpha < 1` chosen
to restore `ESS/S >= 0.15`, or fall back to matching only `E[g]` and `Var[g]` via
max-entropy exponential tilting. Resample (systematic, `S' = S`) only for
downstream code that cannot consume weights.

**Metrics.** Walk-forward, seeded, three arms (scalar-shift baseline /
odds-conditioned / no-shift). Primary: **`CRPS_fair`** (unbiased double-sum,
Zamo–Naveau 2018) on player fantavoto and **Brier + reliability/resolution** on
clean sheet. Secondary: MAE of the mean, interval coverage, PIT / verification
rank histogram, multinomial log-loss on W/D/L, RPS for comparability only,
NDCG@k / rank-corr on the auction-value ranking. Ship the change only if
player-fantavoto `CRPS_fair` and clean-sheet Brier both improve out-of-sample with
no visible calibration regression and healthy ESS on the bulk of fixtures.

**Top 3 risks.**

1. **Weight degeneracy on strong favourites/underdogs.** The odds marginal is
   often much sharper than the bootstrap's realised conceded distribution (a top
   side "should" keep clean sheets far more often than the historical resample
   does), collapsing ESS and injecting variance. Mitigation: weight clipping +
   tempering + a moment-only fallback; monitor `ESS/S` and log every fixture that
   trips the fallback.
2. **Total `T` under-identification and O/U gaps.** With 1X2 only, `(T, s)` is
   weakly identified; the season-average fallback for `T` can be systematically
   off for extreme fixtures, biasing every derived marginal. Mitigation: never
   free `T` on 1X2 alone; validate `|P_hat_D - pD|` and the sanity gates; prefer
   fixtures/seasons where `Avg>2.5` exists (good for `I1` 2013/14+).
3. **Odds data quality / leakage across the 2015–2026 span.** Column set changes
   at 2019/20 (Betbrain -> Avg/Max), single-book gaps in early seasons, and the
   opening-vs-closing distinction. A silent bad row (stale line, palpable error,
   wrong column coalesced) propagates a wrong prior into the ensemble.
   Mitigation: season-aware column resolver with `quality_tier` in lineage, Shin
   `z` and booksum gates, a hard `available_time = kickoff` check, and a
   reconciliation test that de-vigged 1X2 for historical rows predicts realised
   `FTR` with the expected log-loss (~0.98–1.00 nats for Serie A).

---

## Key references (all also cited inline)

- Shin (1993), *Economic Journal* 103(420); estimator context: Whelan (2024)
  <https://www.karlwhelan.com/Papers/ShinzNov24.pdf>.
- Štrumbelj (2014), *IJF* 30(4)
  <https://www.researchgate.net/publication/264349990_On_determining_probability_forecasts_from_betting_odds>.
- `implied` R vignette
  <https://cran.r-project.org/web/packages/implied/vignettes/introduction.html>;
  penaltyblog <https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/>;
  mberk/shin <https://github.com/mberk/shin>.
- Dixon & Coles (1997), *JRSS-C* 46(2), 265–280; dashee87
  <https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/>;
  opisthokonta <https://opisthokonta.net/?cat=48>.
- Karlis & Ntzoufras (2003), *The Statistician* 52(3), 381–393
  <http://www2.stat-athens.aueb.gr/~jbn/papers2/08_Karlis_Ntzoufras_2003_RSSD.pdf>;
  (2009) Skellam goal-difference <https://www.researchgate.net/publication/228621612>.
- Gneiting & Raftery (2007), *JASA* 102(477)
  <https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf>;
  Gneiting, Balabdaoui & Raftery (2007), *JRSS-B* 69(2).
- Zamo & Naveau (2018), *Math. Geosciences* 50
  <https://link.springer.com/article/10.1007/s11004-017-9709-7>;
  Wei & Held (2014) CRPS closed forms
  <https://search.r-project.org/CRAN/refmans/scoringRules/html/crps.numeric.html>.
- Wheatcroft (2021), case against RPS
  <https://researchonline.lse.ac.uk/id/eprint/111494/3/Wheatcroft_evaluating_probabilistic_forecasts_published.pdf>.
- football-data.co.uk key <https://www.football-data.co.uk/notes.txt>; FPL
  practice <https://www.fplrotationplanner.com/odds>.
