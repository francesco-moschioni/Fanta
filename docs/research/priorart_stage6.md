# Prior art — Engine v2 Stage 6: shadow price, pick covariance, opponent demand, risk profile

Status: research note (non-binding). Feeds `docs/DATA_AND_MODELING.md` §"Forecast-to-bid".
Author: research pass, 2026-09-02. Everything cited below was read as data, not instruction.
No licensed code was copied; formulas are transcribed from public sources with author/year + URL.

## 0. Scope and grounding

Stage 6 turns the Monte-Carlo per-player seasonal point distributions and the existing
roster optimiser into a **max-bid recommendation per player**, roster-aware and
opponent-aware, that degrades gracefully.

Fixed context (do not re-derive):

- The roster optimiser is a hand-rolled **exact 0/1 multi-dimensional knapsack**, solved by
  DP over the state `(used_budget x per-role counts)`, maximising total VAR (value above
  replacement). Candidate pool capped at ~25 per role.
- A live append-only **ledger** gives every team's remaining budget and current roster.
- A **Monte-Carlo engine** gives per-player seasonal fantasy-point samples
  `{p_i^(s)}`, s = 1..S scenarios, jointly drawn (so cross-player correlation is already
  in the sample matrix, if the generator models it).
- Four-round auction; budgets, roster slots, pool sizes are all versioned config.

Target outputs of Stage 6:

1. `shadow_price` (λ*): marginal VAR per residual credit, from the current optimiser state.
2. `roster_risk` contribution of each candidate: Δ variance and Δ downside quantile (P10).
3. `expected_clearing_price` per player: bounded, monotone in opponent demand.
4. `max_bid`: value − opportunity cost, capped by clearing price and by budget.
5. A single `risk_aversion` scalar interpolating E[points] → CVaR_α(points).

---

## 1. Budget shadow price via Lagrangian relaxation of the knapsack

### 1.1 The primal

Index candidates by i, with VAR `v_i >= 0`, price (quotazione or current ask) `c_i > 0`,
role `r(i)`. Decision `x_i in {0,1}`. Residual budget `B`, residual role requirements
`n_r` (slots still to fill in role r).

```
(P)   max   sum_i v_i x_i
      s.t.  sum_i c_i x_i <= B                     (budget)
            sum_{i : r(i)=r} x_i = n_r    for all r (role counts)
            x_i in {0,1}
```

This is exactly what the DP solves. The DP state carries the budget axis and one count
axis per role, so the *role* constraints are handled combinatorially and are cheap. The
expensive axis is budget (pseudo-polynomial: `O(|pool| * B * prod_r n_r)`).

### 1.2 Dualising only the budget constraint

Lagrangian relaxation (Everett 1963; Geoffrion 1974; Fisher 1981/2004) moves the *hard*
(linking) constraint into the objective with a multiplier λ ≥ 0 and keeps the *easy*
constraints explicit:

```
L(λ) = max_x  sum_i (v_i - λ c_i) x_i  +  λ B
       s.t.   sum_{i:r(i)=r} x_i = n_r  for all r,   x_i in {0,1}
```

Because the budget axis is gone, the inner problem **decomposes by role**: for each role r
pick the `n_r` candidates with the largest *reduced value* `v_i - λ c_i` (ties/negatives:
if fewer than `n_r` have positive reduced value you are still forced to take `n_r` because
the role count is an equality — take the least-negative ones). Cost:
`O(|pool| log |pool|)`, no budget dimension. This is the key computational win: **the
shadow price is obtained without ever adding an LP solver**, by re-running a budget-free
version of the pick that the engine can already do.

For each λ, let `x(λ)` be the maximiser and

```
g(λ) = B - sum_i c_i x_i(λ)          (subgradient of L at λ: budget slack)
```

`g(λ) > 0`  under-spends the budget  ⇒  λ too high;
`g(λ) < 0`  over-spends              ⇒  λ too low;
`g(λ) = 0`  (or a sign change across a breakpoint) ⇒ λ*.

### 1.3 The Lagrangian dual and how to scan λ

The dual is `min_{λ >= 0} L(λ)`. `L(λ)` is the upper envelope of finitely many affine
functions of λ (one per feasible `x` w.r.t. role counts), hence **piecewise-linear, convex,
non-increasing then flat/increasing**, with at most as many breakpoints as distinct
role-pick combinations (Ilker Birbil, *Lagrangian Relaxation* lecture notes,
https://personal.eur.nl/birbil/bolbilim/teaa/02_Lag_Rel.pdf ; Utrecht course notes on the
knapsack Lagrangian, https://ics-websites.science.uu.nl/docs/vakken/stt/Lagrange.pdf ).

`g(λ)` is monotone non-decreasing in λ (raising the credit penalty never increases spend),
so **bisection on λ works**:

```
lo = 0
hi = max_i v_i / min_i c_i      # any player alone is unattractive at this λ
repeat ~30-40 times:
    mid = (lo+hi)/2
    solve role-decomposed pick at λ=mid, get spend = sum c_i x_i(mid)
    if spend > B:  lo = mid      # need a bigger penalty
    else:          hi = mid
λ* ≈ hi
```

30–40 iterations give machine-precision λ* in well under a millisecond; this is trivially
"live under time pressure". A subgradient/dual-ascent update
`λ_{k+1} = [ λ_k − α_k g(λ_k) ]^+` with a Polyak or diminishing step
`α_k = (L(λ_k) − L_best_primal) / ||g(λ_k)||^2`, resp. `α_k = a/(b+k)`
(Boyd, *Subgradient Methods*, https://web.stanford.edu/class/ee364b/lectures/subgrad_method_notes.pdf )
is the standard alternative and generalises to several dualised constraints, but for a
**single** monotone constraint bisection is simpler, derivative-free, and monotone-safe.
Adapted step-size schemes for exactly this "relax one knapsack constraint" setting:
Fréville & Hanafi / da Silva et al., *An adapted step size algorithm for a 0-1 biknapsack
Lagrangean dual*, Ann. Oper. Res. 2005, https://link.springer.com/article/10.1007/s10479-005-3454-x .

### 1.4 Shadow price = λ* = dV*/dB

At the optimum, the multiplier is the **sensitivity of the optimal value to the
right-hand side**:

```
λ*  ≈  dV*(B) / dB      (marginal VAR gained per extra credit of budget)
```

For an integer program `V*(B)` is a non-decreasing **step function** of B, so the
derivative is only a right/left difference; λ* from the dual is the slope of the
*concave envelope* of `V*(B)` at the current B — i.e. the marginal value of budget under
the LP-style relaxation, which is the correct quantity for a "should I spend one more
credit here" decision. Interpretation for bids:

```
reduced value of player i  =  v_i - λ* c_i
```

A player is "worth more than its price at the margin" iff `v_i - λ* c_i > 0`. This gives
the bid-rule family:

```
max_sensible_bid_i  =  c_i + (v_i - λ* c_i) / λ*   =   v_i / λ*        (λ* > 0)
```

Reading: **convert the player's VAR into credits at the exchange rate λ\*** (VAR per
credit). Never pay more than `v_i / λ*`, because beyond that price the marginal credits are
better spent elsewhere in the roster. Equivalent framing: pay up to
`price_opt_i + surplus_i / λ*` where `price_opt_i` is what the optimiser currently has
budgeted for that slot and `surplus_i = v_i − λ* c_i`.

### 1.5 LP-relaxation dual and the integer duality gap

- **Relation to the LP dual.** For the *pure* knapsack (drop integrality, `0 <= x_i <= 1`),
  strong duality holds and the optimal Lagrange multiplier on the budget row equals the LP
  dual price, which equals `v_k / c_k` of the **fractional ("break") item** k — the item
  that straddles the capacity when candidates are sorted by density `v_i / c_i`
  (Dantzig 1957). So λ* has a concrete meaning: *the value density of the marginal player
  you'd be buying a fraction of.*
- **With integrality + role equalities**, Lagrangian relaxation of only the budget row has
  the **integrality property** (the inner problem is a trivial selection, whose polytope is
  integral), therefore `min_λ L(λ) = LP-relaxation optimum >= IP optimum`. The
  **Lagrangian bound equals the LP bound** here; it does *not* close the gap
  (Geoffrion 1974). The gap is the classic knapsack **integrality gap**.
- **Size of the gap.** For 0/1 knapsack the LP/IP ratio is `< 2` and this is tight in the
  worst case (integrality gap `2 − ε`); level-t Lasserre tightening gives `1 + 1/(t−1)`
  (Karlin, Mathieu & Nguyen, *Integrality Gaps of LP and SDP Relaxations for Knapsack*,
  IPCO 2011, https://homes.cs.washington.edu/~karlin/papers/knapsack.pdf ). **In practice**
  with many small items relative to B (our case: ~25 candidates/role, most quotazioni far
  below residual budget) the gap is *one item's worth of value* — `V*_LP − V*_IP <= v_k`
  for the break item k (Demassey, *Relaxations and Bounds: Knapsack*,
  https://sofdem.github.io/teach/oro/m2oro-ilp-demassey-notes-lec7-8.pdf ). It "bites" only
  when a single expensive player consumes a large fraction of B (early rounds, a top
  striker) — then rounding the fractional item up or down changes the plan materially.
- **How practitioners handle it.** (a) Report λ* from the dual as the price signal but take
  the **integer** roster from the DP for the actual plan; (b) compute the gap explicitly
  `gap = V*_LP(from λ*) − V*_IP(from DP)` and surface it as a confidence flag — a large gap
  means "the shadow price is soft here, one pick swing changes it"; (c) local repair: for
  the break item, solve the DP twice with that player forced in / forced out and keep the
  better — this is an exact 2-way branch that removes the dominant source of gap. Our DP is
  cheap enough to just do (c) for the 1–2 most expensive live candidates.

### 1.6 Cross-check (test only)

Build the same (P) as an LP in PuLP/`scipy.linprog`, read the dual value of the budget
constraint, and assert it matches bisection λ* to tolerance; assert
`V*_LP >= V*_IP` and that the gap is `<= max v_i` over the pool. This is a **test
fixture**, never on the live path (CLAUDE.md: no new heavy solver dependency in the engine).

---

## 2. When the budget is non-binding

If the budget-free pick at `λ = 0` already satisfies `sum_i c_i x_i(0) <= B`, the budget
constraint is slack, complementary slackness gives `λ* = 0`, and there is **no opportunity
cost** to spending: every marginal credit is free because you cannot use it all anyway.

Detection (order matters, cheapest first):

1. Solve the role-decomposed pick at λ = 0 (top-`n_r` by raw `v_i` per role). If its total
   cost `<= B` ⇒ `λ* = 0`, non-binding. Report `budget_binding = false`.
2. Otherwise bisection returns `λ* > 0` and the lower bracket stays strictly positive.
3. Numerical guard: treat `λ* < ε` (e.g. `ε = 1e-6` VAR/credit, or `< 0.01 *` median
   density) as effectively zero.

Degradation when non-binding — the bid rule must **not** divide by ~0
(`v_i / λ*` → ∞). Fall back to the existing conventions:

- **`$1 rule`**: bid the league minimum (1 credit) on any player the optimiser does not
  need; bid `min(expected_clearing_price + 1, quotazione + small)` on players it does need,
  because there is no scarcity pressure to justify overpaying.
- More generally, when `λ*` is tiny the cap that binds is **expected clearing price**
  (Section 5), not the shadow-price ceiling. `max_bid = min(remaining_budget − (slots_left − 1),
  expected_clearing_price + buffer)`. The `slots_left − 1` term reserves 1 credit per
  still-open slot (hard floor from auction rules).
- Surface it in the UI as "budget not the binding constraint — recommendations driven by
  supply/among-opponent demand, not by credit scarcity", per the CLAUDE.md rule that the
  UI must show which constraint is active.

Late-auction this is the *normal* regime for filler roles (you have more credits than
useful players to spend them on); early-auction for scarce roles `λ*` is large.

---

## 3. Pick covariance / complementarity — a portfolio of players

### 3.1 Roster point total as a random variable

Let `x` be the roster indicator, `P_i` the (random) seasonal points of player i with
`μ_i = E[P_i]`, and `Σ` the `S x S`-sample covariance matrix
`Σ_ij = (1/(S−1)) Σ_s (p_i^(s) − μ_i)(p_j^(s) − μ_j)`. Roster total
`T(x) = Σ_i P_i x_i` has

```
E[T]   = Σ_i μ_i x_i
Var[T] = x^T Σ x  = Σ_i Σ_j x_i x_j Σ_ij
       = Σ_i x_i Var[P_i]  +  Σ_{i≠j} x_i x_j Cov(P_i, P_j)
```

This is Markowitz mean–variance (Markowitz, *Portfolio Selection*, J. Finance 1952,
https://www.jstor.org/stable/2975974 ) applied to a roster instead of a $-weighted asset
book. The weights are binary and constrained (roles, budget) rather than a simplex, but the
risk algebra is identical.

### 3.2 Where the correlation comes from (fantacalcio-specific)

- **Same club**: shared clean-sheet / conceded events → defenders + GK of one team are
  strongly positively correlated (clean-sheet bonus lands on all of them at once, goals
  conceded penalise the modifier for all). Attackers of the same team co-move with team
  scoreline and with each other via assist chains, and *negatively* with own-team
  defenders' clean-sheet in blow-out games (weak). Penalty-taker designation concentrates
  bonus.
- **Same fixture**: two players on opposite sides of one match have negatively correlated
  clean-sheet outcomes; a GK vs the opposing striker is the fantacalcio analogue of the DFS
  "goalie vs opposing skater" anti-correlation (Hunter, Vielma & Zaman,
  *Picking Winners in Daily Fantasy Sports Using Integer Programming*, INFORMS J. Opt.
  2019 / arXiv:1604.01455, https://arxiv.org/pdf/1604.01455 ).
- **Common shocks**: calendar congestion, refereeing/VAR regime, rule changes to the
  bonus/malus table hit whole cohorts. Rotation risk within a club is negatively correlated
  across that club's interchangeable players (minutes are zero-sum).

If the MC generator already draws players jointly with a club/fixture factor structure,
`Σ` from the sample matrix captures all of this for free. If it draws players
independently, `Σ` is diagonal and Stage 6 must **inject** a factor model
`P_i = μ_i + β_i F_{club(i)} + γ_i F_{fixture(i)} + ε_i` before covariance means anything.
Check which regime we are in before trusting `x^T Σ x`.

### 3.3 Marginal contribution of a candidate

Given a current roster set `R`, adding candidate j:

```
ΔVar_j = Var[T(R ∪ j)] − Var[T(R)]
       = Var[P_j] + 2 Σ_{i in R} Cov(P_i, P_j)
```

The `2 Σ Cov` term is the **complementarity signal**: negative ⇒ j diversifies (hedge),
positive ⇒ j stacks (amplifies both tails). Analogous to the portfolio "marginal
contribution to risk" `MCR_j = (Σ x)_j / sqrt(x^T Σ x)` used in risk-parity work
(Palomar, *Risk Parity Portfolio*,
https://palomar.home.ece.ust.hk/ELEC5470_lectures/slides_risk_parity_portfolio.pdf ;
Cesarone et al., *Portfolio optimization and marginal contribution to risk*, Ann. Oper.
Res. 2022, https://link.springer.com/article/10.1007/s10479-022-04613-7 ), but here we want
the **discrete** finite difference, not the derivative, because picks are 0/1.

**Downside version (preferred for the UI).** Work directly on scenarios. Let
`t_R^(s) = Σ_{i in R} p_i^(s)` be the roster total in scenario s. Define roster P10 as the
empirical 10th percentile `q_0.10({t_R^(s)})`. Then

```
ΔP10_j = q_0.10({ t_R^(s) + p_j^(s) })  −  q_0.10({ t_R^(s) })
```

is the change in the "bad-season floor" from adding j. A player with high mean but whose
low scenarios coincide with the roster's low scenarios (same club, e.g. relegation-fight
defence) has small or negative `ΔP10_j` despite good `μ_j` — the number the manager should
see. This needs no covariance matrix, only the sample matrix we already have, and it is
robust to non-Gaussian, skewed point distributions (fantacalcio points are skewed:
capped downside per game, long upside tail via bonus).

### 3.4 Diversification vs stacking — what transfers from DFS

DFS lineup optimisation (Hunter–Vielma–Zaman 2019; Mlčoch et al., *Competing in DFS using
generative models*, ITOR 2024, https://onlinelibrary.wiley.com/doi/full/10.1111/itor.13344 )
deliberately **stacks** positively correlated players (e.g. a QB with his WRs) because the
contest is **top-heavy**: you are paid only for the extreme upper tail of one lineup among
tens of thousands, so you *want* variance and co-movement, and you diversify *across your
many entries*, not within one.

Transferable to a season-long auction:

- The **covariance machinery** (sample `Σ`, `ΔVar_j`, scenario stacks) is identical.
- Same-team / same-fixture correlation **signs and sources** are the same football facts.
- The integer-programming formulation with **linear stacking constraints** ("at most k from
  one club", "if GK_c then not striker of c's round-1 opponent") ports directly as extra
  constraints on our DP/branching.

Not transferable:

- **Objective shape.** A 20-team season league pays roughly linearly in total points and
  you keep one roster all year ⇒ you are a **risk-averse single-portfolio** holder, not a
  tail-hunting multi-entry player. You should generally **cap** same-club exposure
  (diversify), the opposite of DFS stacking, *unless* the manager explicitly wants a
  high-variance "swing for the title" build late in a losing season.
- **No re-draw.** DFS diversifies across entries; you cannot. All risk control is
  within the one roster.
- **Minutes/rotation risk** dominates season-long and is nearly absent from single-slate
  DFS.

Net: borrow the math and the constraint language, invert the default (diversify, don't
stack), expose stacking as an opt-in aggressive mode.

---

## 4. CVaR / downside-risk optimisation

### 4.1 Rockafellar–Uryasev CVaR

For loss `L(x, P)` (here `L = −T(x)`, negative roster points), confidence `α` (e.g. 0.90),
VaR is the α-quantile of loss and CVaR_α is the mean loss in the worst `(1−α)` tail.
Rockafellar & Uryasev (*Optimization of Conditional Value-at-Risk*, J. Risk 2000,
https://uryasev.ams.stonybrook.edu/wp-content/uploads/2011/11/kro_CVaR.pdf ; and *CVaR for
General Loss Distributions*, J. Banking & Finance 2002,
https://sites.math.washington.edu/~rtr/papers/rtr187-CVaR2.pdf ) show CVaR is the value of
a convex program in an auxiliary scalar ζ (which optimises to VaR):

```
CVaR_α(x) = min_ζ  F_α(x, ζ),
F_α(x, ζ) = ζ + (1 / (1 − α)) · E[ (L(x, P) − ζ)^+ ]
```

Minimising CVaR over x and ζ **jointly** is equivalent to minimising `F_α`. Key properties:
CVaR is **coherent** (sub-additive, so it rewards diversification — unlike VaR), and
`F_α` is convex in `(x, ζ)`; with linear loss and linear/binary constraints it is an
LP / MILP.

### 4.2 Sample-based (scenario) formulation — the one we want

We already hold S equiprobable MC scenarios. Replace the expectation by the sample mean.
With loss `L^(s)(x) = −Σ_i p_i^(s) x_i` and one non-negative auxiliary `z_s` per scenario:

```
min_{x, ζ, z}   ζ + (1 / ((1 − α) S)) · Σ_{s=1}^{S} z_s
s.t.            z_s >= L^(s)(x) − ζ          for all s        (i.e. z_s >= −Σ_i p_i^(s) x_i − ζ)
                z_s >= 0                       for all s
                Σ_i c_i x_i <= B
                Σ_{i:r(i)=r} x_i = n_r         for all r
                x_i in {0,1},   ζ free
```

At the optimum `ζ* = VaR_α`, `z_s = (L^(s) − ζ*)^+`, objective `= CVaR_α`. This is the
standard scenario LP of Rockafellar–Uryasev; adding the 0/1 and role constraints makes it a
MILP but keeps the CVaR part linear (S extra continuous vars + S rows).

### 4.3 One `risk_aversion` knob: E[points] → CVaR

Use a convex combination of the two objectives (Krokhmal, Palmquist & Uryasev,
*Portfolio optimization with CVaR objective and constraints*, J. Risk 2002 — same PDF as
above):

```
maximise   (1 − ρ) · E[T(x)]  −  ρ · CVaR_α( −T(x) )
         = (1 − ρ) · (1/S) Σ_s Σ_i p_i^(s) x_i
           − ρ · [ ζ + (1 / ((1 − α) S)) Σ_s z_s ]
```

`ρ = risk_aversion in [0, 1]`:

- `ρ = 0` → pure expected points → **exactly today's VAR maximiser** (VAR is an affine
  transform of E[T] once replacement level is fixed), so Stage 6 is backward-compatible.
- `ρ = 1` → maximise the worst-tail mean → most defensive roster.
- intermediate → smoothly trades a bit of mean for a higher P10/tail floor.

`α` is a second, rarely-touched config (default 0.90; `1−α` = fraction of seasons treated
as "bad"). Keep **one** user-facing scalar per CLAUDE.md ("uncertainty, not false
precision") — `ρ`.

### 4.4 Fitting it to our engine without an LP solver

The clean implementation is the MILP above in PuLP, but CLAUDE.md discourages a heavy
solver on the live path. Two engine-native routes:

1. **Scenario-mean surrogate in the existing DP.** Replace each player's scalar VAR by a
   **risk-adjusted VAR**
   `v_i^ρ = (1−ρ) μ_i^VAR − ρ · λ_i^tail`, where `λ_i^tail` is player i's average
   contribution to roster tail loss, estimated by a first pass (see 2 below) or by a static
   proxy `E[ (τ − P_i)^+ ]` with `τ` a low threshold. Then run the unchanged DP. Cheap,
   approximate, ignores cross-player tail covariance.
2. **Greedy/local CVaR polish.** Take the `ρ = 0` DP roster, then do swap-based local
   search evaluating the true scenario CVaR objective on each candidate swap (each eval is
   `O(S)` over cached scenario totals). 1–2 passes remove most of the gap to the MILP
   optimum in practice, and it uses the real joint samples. This is the recommended path:
   exact objective, no solver, reuses the DP.

`PuLP MILP = test cross-check only`, on small pools, asserting the local-search roster is
within a few % of the MILP CVaR optimum.

---

## 5. Opponent demand → expected clearing price

### 5.1 What we can observe from the ledger

For a player about to be auctioned in role r:

- `m` = number of opponent teams that still **need** role r (open slots > 0) and can
  afford a real bid.
- For each such team k: `bpos_k = remaining_budget_k / open_slots_k` — budget per open
  slot ("max average affordability"). The classic fantasy heuristic
  (DraftSharks, *Best Auction Draft Strategy*,
  https://www.draftsharks.com/kb/best-auction-draft-strategy-salary-cap ;
  smartfantasybaseball, *Auction dollar values and inflation*,
  https://www.smartfantasybaseball.com/2014/03/how-to-calculate-auction-dollar-values-and-account-for-inflation/ ).
- `aggr_k` = revealed aggressiveness of team k: ratio of prices they've actually paid to
  our model's `quotazione`/value for those players, smoothed over the auction so far
  (a behavioural profile the codebase already builds for G2/G3 opponents).
- `q_i` = our baseline value anchor for the player: quotazione, or model VAR converted to
  credits at the league's global `$/point`.

### 5.2 Common-value vs private-value and the winner's curse

A fantasy player's true fantasy output is a **common value** (same for whoever wins) but
each manager has a **private** roster fit and risk profile on top — a
common-value-with-private-adjustment auction. In common-value ascending auctions the
winner is the most optimistic estimator ⇒ **winner's curse**: naive "bid your estimate"
overpays systematically, the bias **grows with the number of bidders `m`**
(Kagel & Levin, *Common Value Auctions and the Winner's Curse*, Cambridge/Ohio State,
https://www.asc.ohio-state.edu/kagel.4/WEBPROMO.PDF ). With an **uncertain / varying** `m`,
winning with a low price is less bad news about value when few rivals are present, so the
correction should scale with *effective* competition, not raw team count
(Kim & Che-Lin Su style; Aycinena–Rentschler–Sheremeta, *Bidding in Common-Value Auctions
with an Unknown Number of Competitors*, Econometrica 2023,
https://www.econometricsociety.org/publications/econometrica/2023/03/01/Bidding-in-Common-Value-Auctions-with-an-Unknown-Number-of-Competitors/file/ecta200519.pdf ).
Practical consequence: apply a **bid-shading discount** to our own valuation that
*increases* with `m`, and predict the *clearing price* (2nd-highest willingness) rather
than the max.

### 5.3 A bounded, monotone functional form

Requirements (CLAUDE.md-style): monotone increasing in demand pressure, **bounded above**
by what opponents can actually pay, never used to justify a bid above our budget or the
shadow-price ceiling.

Let

```
D_i = demand pressure
    = Σ_{k in need(r)}  w_k ,   w_k = f( bpos_k / q_i )  ·  aggr_k
```

with `f` a saturating link (e.g. `f(u) = u / (1 + u)` or `min(u, u_max)`), so a single
super-rich team cannot send `D_i` unbounded. Then a bounded monotone clearing-price model:

```
E[clear_i]  =  q_i · [ 1  +  (g_max − 1) · ( 1 − exp(−κ · (D_i − D0)^+ ) ) ]
```

- `q_i` = value anchor (floor as `D_i → 0`: nobody wants him ⇒ ~quotazione, or the `$1`
  floor for fringe players).
- `g_max` = max multiple of anchor ever observed for that role tier (hard ceiling on the
  premium, calibrated, e.g. 1.8–2.5 for elite strikers, ~1.1 for filler).
- `κ > 0` sets how fast the premium saturates; `D0` a demand deadband (need ≥ 2 real
  bidders before price moves off anchor).
- Additionally clip: `E[clear_i] <= 1 + max_{k in need(r)} ( remaining_budget_k
  − (open_slots_k − 1) )` — the true hard cap, since the price cannot exceed the richest
  rival's max legal bid.

Logistic / exponential-saturation forms are what practitioners use for the "premium players
take a super-linear share of budget, tail is all \$1" shape
(Fitzgerald, *Solving the Auction Draft with Excel*,
https://medium.com/@bobbybfitzgerald/solving-the-auction-having-fun-with-excel-ai-to-optimize-an-auction-draft-strategy-ae41b6c49cdb ;
log-regression of price on rank is the common fit).

### 5.4 Calibration on earlier rounds

We have realised prices for G1/G2 (and within-round, every prior lot). Fit, per role tier:

```
log(price_j / q_j)  =  β0 + β1 · log(D_j^pre)  +  β2 · scarcity_j  +  β3 · early_round_j + ε_j
```

where `D_j^pre` is the demand pressure **reconstructed as of just before lot j cleared**
(leakage rule: only ledger state available at that timestamp — CLAUDE.md `available_at`).
Robust/quantile regression (median and, say, 0.8-quantile) gives both `E[clear]` and an
upper band for the "might go higher" warning. Re-fit `κ, g_max, β` after each completed
round; before any realised data, fall back to priors from historical league price sheets
(`Liste Fantacalcio` / research corpus) with wide bands. Simultaneous-ascending-auction
price-prediction work uses exactly this "regress closing price on pre-auction context,
then bid against the prediction" loop
(*Bidding efficiently in Simultaneous Ascending Auctions ... SM-MCTS*, arXiv:2307.11428,
https://arxiv.org/pdf/2307.11428 ).

### 5.5 Guarantees to enforce in code

- `E[clear_i]` monotone non-decreasing in each `bpos_k`, in `aggr_k`, and in `m`
  (assert on the fitted params: `β1 >= 0`, `f` non-decreasing).
- `E[clear_i] >= $1` and `<= richest legal rival bid` (Section 5.3 clip).
- The clearing price is a **cap on our recommendation**, never a floor: we never recommend
  bidding *up to* clearing price just because we can; we bid the min of (our value ceiling,
  clearing price + 1).

---

## 6. Putting it together — the max-bid recommendation

Per live candidate i, given current optimiser state (λ*, roster R), risk knob ρ, α:

```
1. value_i        = risk-adjusted VAR
                   = (1−ρ)·VAR_i  −  ρ·tailContribution_i(R)          # §3.3 / §4.3
                     (ρ = 0 ⇒ plain VAR, backward compatible)

2. opp_cost_i     = λ* · c_i                                          # §1.4 shadow price
   surplus_i      = value_i − opp_cost_i        (credits of VAR advantage at the margin)

3. value_ceiling_i = c_i + surplus_i / λ*   =   value_i / λ*   (λ* > 0)
                   = remaining_budget − (open_slots − 1)        (λ* ≈ 0, §2)

4. market_cap_i   = E[clear_i] + overpay_buffer                       # §5.3, buffer e.g. +1..+2
                    clipped to richest legal rival bid

5. budget_cap_i   = remaining_budget − Σ_{other open slots} min_price_reserve

6. max_bid_i      = min( value_ceiling_i , market_cap_i , budget_cap_i )
   recommend "let go" if  max_bid_i < E[clear_i]     (we will be outbid below our ceiling)
   recommend "target"  if  value_ceiling_i  >  E[clear_i] + margin  (we can win value-positive)
```

Also surface, not just the scalar:

- `shadow_price = λ*` and `budget_binding` flag;
- `integer_gap` from §1.5 as a "shadow price is soft" confidence flag;
- `ΔP10_i` (roster floor change) and same-club exposure count;
- `E[clear_i]` with its quantile band, and which cap bound `max_bid_i`.

### 6.1 Worked-example structure (numbers illustrative)

- Residual `B = 180`, need 1 attacker + 3 midfielders + 2 defenders.
- Bisection ⇒ `λ* = 0.42` VAR/credit; `budget_binding = true`; integer gap `= 3.1` VAR
  (small).
- Candidate striker: `VAR = 46`, `c = 90`. `ρ = 0.3`, tail contribution `= 12` (he stacks
  with our two owned defenders of a weak club) ⇒ `value = 0.7·46 − 0.3·12 = 28.6`.
- `opp_cost = 0.42·90 = 37.8` ⇒ `surplus = 28.6 − 37.8 = −9.2` (negative!) ⇒
  `value_ceiling = 28.6 / 0.42 ≈ 68`.
- `m = 4` rivals need an attacker, richest `bpos = 61`, aggressive profile ⇒
  `E[clear] ≈ 90·(1 + 1.1·(1−e^{−…})) ≈ 118`, band [104, 133].
- `budget_cap = 180 − (5 other slots · ~4 reserve) ≈ 160`.
- `max_bid = min(68, 120, 160) = 68`. `E[clear] 118 > 68` ⇒ **let him go**; the model says
  he is priced ~50 credits above where he is value-positive for *our* roster, and stacking
  risk makes it worse. Redeploy the 68→credits toward a midfielder where `λ*`-adjusted
  surplus is positive.

---

## 7. Recommended for our Stage 6

Concrete and opinionated.

### 7.1 Shadow price

- **Primary: Lagrangian-on-the-existing-DP.** Dualise **only** the budget row; the inner
  problem decomposes to top-`n_r`-by-`(v_i − λ c_i)` per role. **Bisection** on λ
  (30–40 iters, monotone `g(λ)`), no subgradient tuning, no LP solver. Output
  `λ* = shadow_price` = marginal VAR/credit.
- Compute the **integer gap** explicitly (`V*_LP(λ*) − V*_IP(DP)`) and the **break item**;
  do the exact forced-in/forced-out 2-way DP branch on the 1–2 priciest live candidates to
  kill the dominant gap. Surface the residual gap as a soft-confidence flag.
- **Non-binding detection first** (pick at λ = 0 fits in B ⇒ `λ* = 0`): degrade to the
  `$1 rule` / `min(clearing+buffer, budget floor)`; never divide by ~0.
- **PuLP LP dual = CI test only**: assert bisection λ* == LP budget dual price; assert
  `V*_LP >= V*_IP` and gap `<= max_i v_i`. Not a runtime dependency.

### 7.2 Risk profile

- **Scenario CVaR with one `risk_aversion` scalar `ρ ∈ [0,1]`**, objective
  `(1−ρ)·E[T] − ρ·CVaR_α(−T)`, Rockafellar–Uryasev sample form, `α = 0.90` config default.
  `ρ = 0` reproduces today's VAR maximiser exactly (regression-lock this).
- **Implementation: DP for `ρ = 0` roster, then scenario-CVaR local swap-search** (each
  eval `O(S)` on cached scenario totals) for `ρ > 0`. Uses the real joint MC samples,
  no solver. MILP in PuLP is a small-pool cross-check only.
- Also report per-candidate `ΔP10` (roster bad-season floor change) and **same-club
  exposure count**; default policy **diversify** (cap same-club picks), with an opt-in
  "aggressive/stack" mode that lifts the cap for a deliberately high-variance build.
- Covariance/complementarity from the **sample matrix** (`ΔVar_j = Var[P_j] + 2 Σ_{i∈R}
  Cov`). First verify the MC generator draws players jointly with club/fixture factors; if
  it draws independently, add an explicit factor model before covariance is meaningful.

### 7.3 Opponent-demand price

- One **bounded, monotone, saturating** form:
  `E[clear_i] = q_i · [1 + (g_max−1)(1 − exp(−κ·(D_i − D0)^+))]`,
  `D_i = Σ_k f(bpos_k / q_i)·aggr_k`, `f(u) = u/(1+u)`, hard-clipped to the richest legal
  rival bid.
- **Calibrate** per role tier by (quantile) regression of `log(price/q)` on
  `log(D^pre)`, scarcity, round dummy, using leakage-safe pre-lot ledger state; re-fit
  after every completed round; historical league price sheets as the cold-start prior.
- Winner's-curse discipline: predict the **clearing** price (2nd willingness), apply a
  shading discount to our own value that grows with effective `m`; the price is a **cap**,
  never a reason to bid up.

### 7.4 The three main risks

1. **MC samples don't carry real cross-player correlation.** If the generator is
   effectively independent per player, `Σ` is diagonal, CVaR ≈ mean-shift, stacking/hedge
   signals are noise, and `ΔP10` is over-optimistic (tails don't co-fall). *Mitigation:*
   audit the generator for a club/fixture factor structure before Stage 6 trusts any
   covariance; if absent, add an explicit factor model or ship §3/§4 as "diagonal-only,
   correlation TODO" and say so in the UI.
2. **Integer duality gap makes λ\* unstable early.** When one striker eats a big share of
   B, `V*(B)` has a large step and λ* swings between adjacent picks, so `value/λ*` bid
   ceilings jump around lot-to-lot and mislead under time pressure. *Mitigation:* the
   forced-in/out 2-way branch on top candidates, report the gap as low-confidence, and
   damp λ* changes (EMA) across consecutive recommendations.
3. **Opponent-demand model mis-calibrated / gamed.** Early auction has almost no realised
   prices, `aggr_k` is noisy, and a single bluff nomination can distort `D_i`; an
   over-tight `E[clear]` makes us fold on players we could win, an over-loose one makes us
   overpay into the winner's curse. *Mitigation:* wide quantile bands until ≥ ~30 realised
   lots, clip to hard budget facts (richest legal bid, our budget floor), keep the price as
   a one-directional cap, and never let it override the shadow-price ceiling.

---

## References

- Markowitz, H. (1952). Portfolio Selection. *Journal of Finance*.
  https://www.jstor.org/stable/2975974
- Everett, H. (1963). Generalized Lagrange multiplier method for resource allocation.
  *Operations Research*.
- Geoffrion, A.M. (1974). Lagrangean relaxation for integer programming.
  *Mathematical Programming Study 2*.
- Fisher, M.L. (1981, reprinted 2004). The Lagrangian relaxation method for solving integer
  programming problems. *Management Science*.
- Birbil, Ş.İ. (2016). Lagrangian Relaxation — lecture notes.
  https://personal.eur.nl/birbil/bolbilim/teaa/02_Lag_Rel.pdf
- Utrecht Univ. course notes — the knapsack Lagrangian.
  https://ics-websites.science.uu.nl/docs/vakken/stt/Lagrange.pdf
- Demassey, S. Relaxations and Bounds: Applications to Knapsack Problems.
  https://sofdem.github.io/teach/oro/m2oro-ilp-demassey-notes-lec7-8.pdf
- Karlin, A., Mathieu, C., Nguyen, T. (2011). Integrality Gaps of LP and SDP Relaxations
  for Knapsack. *IPCO*. https://homes.cs.washington.edu/~karlin/papers/knapsack.pdf
- da Silva, C., Fréville, A., et al. (2005). An adapted step size algorithm for a 0-1
  biknapsack Lagrangean dual. *Annals of Operations Research*.
  https://link.springer.com/article/10.1007/s10479-005-3454-x
- (Lagrangian dual of the knapsack, approximation view). Approximating Solutions to the
  Knapsack Problem using the Lagrangian Dual. https://arxiv.org/html/2312.03413
- Boyd, S. & Park, J. Subgradient Methods — EE364b notes.
  https://web.stanford.edu/class/ee364b/lectures/subgrad_method_notes.pdf
- Rockafellar, R.T. & Uryasev, S. (2000). Optimization of Conditional Value-at-Risk.
  *Journal of Risk*.
  https://uryasev.ams.stonybrook.edu/wp-content/uploads/2011/11/kro_CVaR.pdf
- Rockafellar, R.T. & Uryasev, S. (2002). Conditional Value-at-Risk for General Loss
  Distributions. *Journal of Banking & Finance*.
  https://sites.math.washington.edu/~rtr/papers/rtr187-CVaR2.pdf
- Krokhmal, P., Palmquist, J., Uryasev, S. (2002). Portfolio optimization with CVaR
  objective and constraints. *Journal of Risk*. (same PDF host as above)
- Cesarone, F. et al. (2022). Portfolio optimization and marginal contribution to risk.
  *Annals of Operations Research*.
  https://link.springer.com/article/10.1007/s10479-022-04613-7
- Palomar, D. Risk Parity Portfolio — ELEC5470 slides.
  https://palomar.home.ece.ust.hk/ELEC5470_lectures/slides_risk_parity_portfolio.pdf
- Hunter, D.S., Vielma, J.P., Zaman, T. (2019). Picking Winners in Daily Fantasy Sports
  Using Integer Programming. *INFORMS Journal on Optimization* / arXiv:1604.01455.
  https://arxiv.org/pdf/1604.01455
- Mlčoch, L. et al. (2024). Competing in daily fantasy sports using generative models.
  *International Transactions in Operational Research*.
  https://onlinelibrary.wiley.com/doi/full/10.1111/itor.13344
- Kagel, J.H. & Levin, D. Common Value Auctions and the Winner's Curse.
  https://www.asc.ohio-state.edu/kagel.4/WEBPROMO.PDF
- Aycinena, D., Rentschler, L., Sheremeta, R. (2023). Bidding in Common-Value Auctions with
  an Unknown Number of Competitors. *Econometrica*.
  https://www.econometricsociety.org/publications/econometrica/2023/03/01/Bidding-in-Common-Value-Auctions-with-an-Unknown-Number-of-Competitors/file/ecta200519.pdf
- Bidding efficiently in Simultaneous Ascending Auctions with budget and eligibility
  constraints using SM-MCTS. arXiv:2307.11428. https://arxiv.org/pdf/2307.11428
- DraftSharks. Best Auction Draft Strategy (Salary Cap).
  https://www.draftsharks.com/kb/best-auction-draft-strategy-salary-cap
- smartfantasybaseball. How to Calculate Auction Dollar Values and Account For Inflation.
  https://www.smartfantasybaseball.com/2014/03/how-to-calculate-auction-dollar-values-and-account-for-inflation/
- FanGraphs Community. Replacing Replacement Value in Fantasy Auctions.
  https://community.fangraphs.com/replacing-replacement-value-in-fantasy-auctions/
- Fitzgerald, B. Solving the Auction: Excel/AI auction draft optimisation.
  https://medium.com/@bobbybfitzgerald/solving-the-auction-having-fun-with-excel-ai-to-optimize-an-auction-draft-strategy-ae41b6c49cdb
