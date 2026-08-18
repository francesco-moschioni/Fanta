"""Post-round opponent/market model (ADR-2026-056): turns a closed round's ledger
events into a per-opponent profile (roster gaps, budget headroom, quality of what
they've bought) and a per-role price-inflation estimate, both read from
`domain.replay()` state / round events directly rather than recomputed ad hoc.

Explicitly NOT a bid recommendation: `bid_recommendation.py` already owns "how much
should I bid"; this module only describes what happened and what it implies about
opponents, to be read by a human (or wired into `recommend_max_bid` later) before
deciding. No forecast, no single "the answer" number -- inflation is reported as a
range with a sample-size caveat, never a bare point estimate, per CLAUDE.md ("show
uncertainty, never false precision").
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import Ruleset
from ..domain import AssignmentEvent, LeagueState, Role as DomainRole, TeamState, effective_events
from ..persistence.player_table import effective_quotazione
from .bid_recommendation import VOTI_TO_DOMAIN_ROLE, budget_remaining_for_round, remaining_roster_slots

# Below this many observations, an inflation estimate is too noisy to act on --
# shown to the user as a caveat, never hidden or silently trusted the same as a
# well-sampled one.
MIN_RELIABLE_SAMPLE = 8


@dataclass(frozen=True)
class OpponentProfile:
    team_id: str
    round_id: str
    slots_needed: dict[str, int]  # voti role code (P/D/C/A) -> slots still open
    budget_remaining: int
    budget_per_open_slot: float | None  # None if roster already full
    quality_signal: dict[str, float]  # voti role code -> avg (paid effective_quotazione - league avg for role), players bought so far this role
    players_bought: int


@dataclass(frozen=True)
class RoleInflation:
    role: str  # voti role code
    n: int
    mean_ratio: float  # mean(amount / effective_quotazione) across purchases
    low_ratio: float  # min observed
    high_ratio: float  # max observed
    reliable: bool  # False if n < MIN_RELIABLE_SAMPLE


def opponent_profile(
    league_state: LeagueState,
    ruleset: Ruleset,
    player_conn,
    team_id: str,
    round_id: str,
) -> OpponentProfile:
    team_state = league_state.team(team_id)
    slots = remaining_roster_slots(team_state, ruleset)
    remaining_budget = budget_remaining_for_round(team_state, round_id, ruleset)
    total_open = sum(slots.values())
    budget_per_slot = (remaining_budget / total_open) if total_open > 0 else None

    quality = _quality_signal_by_role(team_state, player_conn)
    players_bought = sum(team_state.role_count(r) for r in DomainRole)

    return OpponentProfile(
        team_id=team_id,
        round_id=round_id,
        slots_needed=slots,
        budget_remaining=remaining_budget,
        budget_per_open_slot=budget_per_slot,
        quality_signal=quality,
        players_bought=players_bought,
    )


def all_opponent_profiles(
    league_state: LeagueState,
    ruleset: Ruleset,
    player_conn,
    round_id: str,
    team_ids: list[str],
) -> list[OpponentProfile]:
    return [opponent_profile(league_state, ruleset, player_conn, tid, round_id) for tid in team_ids]


def _quality_signal_by_role(team_state: TeamState, player_conn) -> dict[str, float]:
    """For each voti role code, avg(paid effective_quotazione of this team's picks
    in that role) minus the league-wide average effective_quotazione for that role
    (over the full player pool, not just drafted players -- a stable yardstick that
    doesn't shift as the round progresses). Positive: this team has been buying
    above-average (likely quality/starters). Negative: below-average (likely
    bench-tier depth, plausibly still hunting a starter). Empty dict entry (role
    omitted) if the team hasn't bought anyone in that role yet -- never a fabricated
    zero, since zero would imply "average", not "no data"."""
    signal: dict[str, float] = {}
    for voti_role, domain_role in VOTI_TO_DOMAIN_ROLE.items():
        player_codes = team_state.roster[domain_role]
        if not player_codes:
            continue
        paid_values = []
        for pid in player_codes:
            row = _get_player_row(player_conn, pid)
            if row is not None:
                paid_values.append(effective_quotazione(row))
        if not paid_values:
            continue
        league_avg = _league_avg_quotazione(player_conn, voti_role)
        if league_avg is None:
            continue
        signal[voti_role] = (sum(paid_values) / len(paid_values)) - league_avg
    return signal


def get_player_row(player_conn, player_code) -> pd.Series | None:
    """Public lookup by player_code (any stringifiable type -- the ledger stores
    ids as strings, pandas pools typically as int), used by other modules
    (e.g. bid_recommendation) that need a single player's row without a second
    connection helper."""
    return _get_player_row(player_conn, player_code)


def _get_player_row(player_conn, player_code: str) -> pd.Series | None:
    result = player_conn.execute(
        "SELECT * FROM players WHERE CAST(player_code AS VARCHAR) = ?", [str(player_code)]
    ).df()
    if result.empty:
        return None
    return result.iloc[0]


def _league_avg_quotazione(player_conn, voti_role: str) -> float | None:
    df = player_conn.execute("SELECT * FROM players WHERE role = ?", [voti_role]).df()
    if df.empty:
        return None
    values = df.apply(effective_quotazione, axis=1)
    return float(values.mean())


def round_role_inflation(
    events: list,
    player_conn,
    round_id: str,
) -> list[RoleInflation]:
    """Per voti role code, the distribution of (amount paid / effective_quotazione)
    across every individual-player purchase in `round_id` (goalkeeper blocks
    excluded -- a block's single price isn't comparable to a per-player
    quotazione). Reads `effective_events()` so a corrected/voided purchase never
    counts twice."""
    ratios_by_role = _purchase_ratios_by_role(events, player_conn, round_id=round_id, exclude_round_id=None)
    return [_to_role_inflation(voti_role, ratios) for voti_role, ratios in sorted(ratios_by_role.items())]


def role_price_inflation(
    events: list,
    player_conn,
    voti_role: str,
    exclude_round_id: str | None = None,
) -> RoleInflation | None:
    """Cross-round price/quotazione ratio for a single voti role code, used to
    correct a forward-looking bid estimate: e.g. bidding in G3 for a defender,
    informed by how much defenders actually cost in G1 (the only round where
    defenders were priced) rather than the static quotazione alone. `round_id`
    of the round you're bidding IN should be passed as `exclude_round_id` so an
    in-progress/target round never contaminates its own historical baseline.
    Returns None (not a zero-observation RoleInflation) when there is no
    historical data yet for this role -- "no data" and "data with ratio 0" must
    never be confused."""
    ratios_by_role = _purchase_ratios_by_role(events, player_conn, round_id=None, exclude_round_id=exclude_round_id)
    ratios = ratios_by_role.get(voti_role)
    if not ratios:
        return None
    return _to_role_inflation(voti_role, ratios)


def _purchase_ratios_by_role(
    events: list,
    player_conn,
    round_id: str | None,
    exclude_round_id: str | None,
    with_quotazione: bool = False,
) -> dict[str, list]:
    """Returns {voti_role: [ratio, ...]}, or {voti_role: [(ratio, quotazione), ...]}
    when `with_quotazione=True` (needed to bucket purchases into price tiers)."""
    ratios_by_role: dict[str, list] = {}
    for event in effective_events(events):
        if not isinstance(event, AssignmentEvent):
            continue
        if round_id is not None and event.round_id != round_id:
            continue
        if exclude_round_id is not None and event.round_id == exclude_round_id:
            continue
        if event.role is DomainRole.GK:
            continue  # block price, not a per-player price -- not comparable
        if len(event.item.player_ids) != 1:
            continue
        row = _get_player_row(player_conn, event.item.player_ids[0])
        if row is None:
            continue
        quotazione = effective_quotazione(row)
        if quotazione <= 0:
            continue
        voti_role = row["role"]
        ratio = event.amount / quotazione
        entry = (ratio, quotazione) if with_quotazione else ratio
        ratios_by_role.setdefault(voti_role, []).append(entry)
    return ratios_by_role


def _to_role_inflation(voti_role: str, ratios: list[float]) -> RoleInflation:
    n = len(ratios)
    return RoleInflation(
        role=voti_role,
        n=n,
        mean_ratio=sum(ratios) / n,
        low_ratio=min(ratios),
        high_ratio=max(ratios),
        reliable=n >= MIN_RELIABLE_SAMPLE,
    )


# Below this many observations, a tier/regime split is not even attempted --
# splitting a handful of purchases into sub-groups would produce cells of 1-2
# observations, noise dressed up as precision.
MIN_SAMPLE_FOR_SPLIT = 6


@dataclass(frozen=True)
class TierInflation:
    """Price/quotazione ratio within one price bracket of a role (or, when
    `voti_role` is None, of the whole market) -- e.g. "the cheapest third of
    defenders sold for 1.6x quotazione, the most expensive third for 1.05x": a
    single role-wide mean_ratio hides exactly this kind of split, which is
    common in real auctions (minimum-bid effects inflate cheap players
    disproportionately)."""

    voti_role: str | None  # None = pooled across every role (market-wide shape)
    tier_label: str  # "bassa", "media", "alta" quotazione
    quotazione_min: int
    quotazione_max: int
    n: int
    mean_ratio: float
    low_ratio: float
    high_ratio: float
    reliable: bool


def price_tier_inflation(
    events: list,
    player_conn,
    exclude_round_id: str | None = None,
    voti_role: str | None = None,
    n_tiers: int = 3,
) -> list[TierInflation]:
    """Historical purchases (GK blocks excluded), split into `n_tiers` quotazione
    brackets (roughly equal-sized by observation count, via pandas.qcut) and a
    ratio computed within each. `voti_role=None` pools every role together --
    the fallback "market shape" to use when the target's own role has no
    historical purchases yet at all (e.g. forecasting a G2 midfielder from G1,
    which only ever priced defenders: no midfielder-specific data exists, but
    the general cheap-players-overpay-more shape, if present, still informs the
    forecast). Returns [] if there's too little data to split without the
    tiers being noise (`MIN_SAMPLE_FOR_SPLIT`)."""
    ratios_by_role = _purchase_ratios_by_role(
        events, player_conn, round_id=None, exclude_round_id=exclude_round_id, with_quotazione=True
    )
    if voti_role is not None:
        pairs = ratios_by_role.get(voti_role, [])
    else:
        pairs = [p for role_pairs in ratios_by_role.values() for p in role_pairs]
    if len(pairs) < MIN_SAMPLE_FOR_SPLIT:
        return []

    df = pd.DataFrame(pairs, columns=["ratio", "quotazione"])
    try:
        df["tier"] = pd.qcut(df["quotazione"], q=n_tiers, duplicates="drop")
    except ValueError:
        return []  # not enough distinct quotazione values to form n_tiers groups

    tier_labels_by_order = ["bassa", "media", "alta"] if n_tiers == 3 else [f"fascia {i+1}" for i in range(n_tiers)]
    ordered_intervals = sorted(df["tier"].cat.categories, key=lambda iv: iv.left)

    results = []
    for i, interval in enumerate(ordered_intervals):
        sub = df[df["tier"] == interval]
        if sub.empty:
            continue
        ratios = sub["ratio"].tolist()
        n = len(ratios)
        label = tier_labels_by_order[i] if i < len(tier_labels_by_order) else f"fascia {i+1}"
        results.append(TierInflation(
            voti_role=voti_role,
            tier_label=label,
            quotazione_min=int(sub["quotazione"].min()),
            quotazione_max=int(sub["quotazione"].max()),
            n=n,
            mean_ratio=sum(ratios) / n,
            low_ratio=min(ratios),
            high_ratio=max(ratios),
            reliable=n >= MIN_RELIABLE_SAMPLE,
        ))
    return results


def _tier_for_quotazione(tiers: list[TierInflation], quotazione: int) -> TierInflation | None:
    if not tiers:
        return None
    for tier in tiers:
        if tier.quotazione_min <= quotazione <= tier.quotazione_max:
            return tier
    # outside every observed range (e.g. cheaper than anything sold so far):
    # clamp to the nearest edge tier rather than returning nothing.
    return min(tiers, key=lambda t: min(abs(quotazione - t.quotazione_min), abs(quotazione - t.quotazione_max)))


@dataclass(frozen=True)
class RegimeSummary:
    """Single aggregate price/quotazione ratio across every historical purchase
    (any role, GK blocks included via the sum of the block's own quotazioni) --
    the coarsest, always-available fallback: "is the market overall running hot
    or cold" when no role- or tier-specific data exists yet."""

    n: int
    mean_ratio: float
    low_ratio: float
    high_ratio: float
    reliable: bool


def market_regime_ratio(events: list, player_conn, exclude_round_id: str | None = None) -> RegimeSummary | None:
    ratios = _all_purchase_ratios(events, player_conn, exclude_round_id)
    if not ratios:
        return None
    n = len(ratios)
    return RegimeSummary(
        n=n,
        mean_ratio=sum(ratios) / n,
        low_ratio=min(ratios),
        high_ratio=max(ratios),
        reliable=n >= MIN_RELIABLE_SAMPLE,
    )


@dataclass(frozen=True)
class TeamAggressiveness:
    """How far this team's own price/quotazione ratio (any role, any round so
    far) sits from the league-wide `market_regime_ratio` -- a bidding-style
    signal that carries across roles, unlike role-specific inflation: a team
    that overpaid on defenders in G1 is plausibly a team that overpays in
    general, not specifically on defenders, so this is usable to anticipate
    behaviour on G2's brand-new roles even though no direct G2 data exists yet."""

    team_id: str
    n: int
    team_mean_ratio: float
    delta_vs_market: float  # team_mean_ratio - market-wide mean_ratio; positive = more aggressive than average
    reliable: bool


def team_aggressiveness_index(
    events: list,
    player_conn,
    team_ids: list[str],
    exclude_round_id: str | None = None,
) -> dict[str, TeamAggressiveness]:
    regime = market_regime_ratio(events, player_conn, exclude_round_id)
    market_mean = regime.mean_ratio if regime is not None else None

    by_team: dict[str, list[float]] = {}
    for event in effective_events(events):
        if not isinstance(event, AssignmentEvent):
            continue
        if exclude_round_id is not None and event.round_id == exclude_round_id:
            continue
        ratio = _event_ratio(event, player_conn)
        if ratio is None:
            continue
        by_team.setdefault(event.team_id, []).append(ratio)

    result = {}
    for team_id in team_ids:
        ratios = by_team.get(team_id, [])
        if not ratios:
            continue
        n = len(ratios)
        team_mean = sum(ratios) / n
        result[team_id] = TeamAggressiveness(
            team_id=team_id,
            n=n,
            team_mean_ratio=team_mean,
            delta_vs_market=(team_mean - market_mean) if market_mean is not None else 0.0,
            reliable=n >= MIN_SAMPLE_FOR_SPLIT,
        )
    return result


def _event_ratio(event: AssignmentEvent, player_conn) -> float | None:
    """amount / total effective_quotazione of everything in this single
    purchase (one player, or the whole goalkeeper block)."""
    total_quotazione = 0
    for pid in event.item.player_ids:
        row = _get_player_row(player_conn, pid)
        if row is None:
            return None
        total_quotazione += effective_quotazione(row)
    if total_quotazione <= 0:
        return None
    return event.amount / total_quotazione


def _all_purchase_ratios(events: list, player_conn, exclude_round_id: str | None) -> list[float]:
    ratios = []
    for event in effective_events(events):
        if not isinstance(event, AssignmentEvent):
            continue
        if exclude_round_id is not None and event.round_id == exclude_round_id:
            continue
        ratio = _event_ratio(event, player_conn)
        if ratio is not None:
            ratios.append(ratio)
    return ratios


@dataclass(frozen=True)
class PriceCorrection:
    """The best available historical price/quotazione estimate for a specific
    (role, quotazione) target, picked by cascading from most to least specific:
    role+tier -> role only -> role-agnostic tier -> overall market regime ->
    none. Always names which level was actually used (`source`) so a caller
    can show it, never silently blend levels into one opaque number."""

    ratio: float
    n: int
    reliable: bool
    source: str  # human-readable label of which level was used
    low_ratio: float  # observed range at the chosen level, for Monte Carlo sampling (g3_simulation.py)
    high_ratio: float


def estimate_price_correction(
    events: list,
    player_conn,
    voti_role: str,
    quotazione: int,
    exclude_round_id: str | None = None,
) -> PriceCorrection | None:
    role_tiers = price_tier_inflation(events, player_conn, exclude_round_id, voti_role=voti_role)
    role_tier_match = _tier_for_quotazione(role_tiers, quotazione)

    role_flat = role_price_inflation(events, player_conn, voti_role, exclude_round_id)

    market_tiers = price_tier_inflation(events, player_conn, exclude_round_id, voti_role=None)
    market_tier_match = _tier_for_quotazione(market_tiers, quotazione)

    regime = market_regime_ratio(events, player_conn, exclude_round_id)

    candidates: list[tuple[str, RoleInflation | TierInflation | RegimeSummary | None]] = [
        (f"ruolo {voti_role}, fascia di quotazione '{role_tier_match.tier_label}'" if role_tier_match else "", role_tier_match),
        (f"ruolo {voti_role} (tutte le fasce)", role_flat),
        (f"mercato generale, fascia di quotazione '{market_tier_match.tier_label}' (ruoli misti)" if market_tier_match else "", market_tier_match),
        ("regime di mercato generale (tutti i ruoli, nessuna fascia)", regime),
    ]

    # Prefer the most specific RELIABLE candidate; if none are reliable, fall
    # back to the most specific one that exists at all, flagged unreliable --
    # never hide a usable-if-noisy signal, never blend two levels together.
    reliable_candidates = [(label, c) for label, c in candidates if c is not None and c.reliable]
    if reliable_candidates:
        label, chosen = reliable_candidates[0]
    else:
        any_candidates = [(label, c) for label, c in candidates if c is not None]
        if not any_candidates:
            return None
        label, chosen = any_candidates[0]

    return PriceCorrection(
        ratio=chosen.mean_ratio, n=chosen.n, reliable=chosen.reliable, source=label,
        low_ratio=chosen.low_ratio, high_ratio=chosen.high_ratio,
    )


@dataclass(frozen=True)
class CompetitionSignal:
    voti_role: str
    teams_needing: int
    teams_total: int
    avg_budget_per_open_slot: float | None  # among the teams_needing, None if none need it


def opponents_needing_role(
    league_state: LeagueState,
    ruleset: Ruleset,
    round_id: str,
    voti_role: str,
    opponent_ids: list[str],
) -> CompetitionSignal:
    """How many of `opponent_ids` still have an open slot in `voti_role`, and how
    much budget-per-open-slot they have on average -- informational context about
    "who's likely still shopping for this role and how flush they are", not folded
    into `max_bid` itself: turning this into a numeric price adjustment is a real
    strategy decision (how much should competition raise your ceiling?) that needs
    an explicit user-approved rule, not an invented multiplier (CLAUDE.md: no
    invented tie-breakers/formulas without approval)."""
    needing_budgets: list[float] = []
    for team_id in opponent_ids:
        team_state = league_state.team(team_id)
        slots = remaining_roster_slots(team_state, ruleset)
        if slots.get(voti_role, 0) <= 0:
            continue
        remaining_budget = budget_remaining_for_round(team_state, round_id, ruleset)
        total_open = sum(slots.values())
        needing_budgets.append(remaining_budget / total_open if total_open > 0 else float(remaining_budget))
    return CompetitionSignal(
        voti_role=voti_role,
        teams_needing=len(needing_budgets),
        teams_total=len(opponent_ids),
        avg_budget_per_open_slot=(sum(needing_budgets) / len(needing_budgets)) if needing_budgets else None,
    )


@dataclass(frozen=True)
class TeamPreferenceProfile:
    """Behavioural profile of one team's sealed-bid strategy, built from the
    FULL preference history (won/lost/never-reached) -- not just the ledger's
    winning outcomes. Confirmed with the user 2026-08-18: this is purely a
    behaviour/strategy signal, never used to infer future demand for a
    specific player."""
    team_id: str
    n_preferences_observed: int
    n_won: int
    n_lost: int
    n_not_reached: int
    avg_overbid_ratio_won: float | None  # mean(bid_amount / effective_quotazione) on WON preferences
    avg_overbid_ratio_lost: float | None  # same, on LOST preferences (attempted, didn't win)
    avg_preference_rank_won: float | None  # how far down its own list a team typically has to go to win (1 = always wins first choice)


def team_preference_profiles(history: pd.DataFrame, player_conn) -> list[TeamPreferenceProfile]:
    """`history` is the curated dataset produced by
    `scripts/ingest_preference_bid_history.py` (columns: team_id, player_code,
    preference_rank, bid_amount, outcome). One profile per team present in the
    data -- a team missing from the source lists (e.g. genuinely not
    submitted, or excluded by unresolved names) simply doesn't appear, never a
    fabricated zero-row profile."""
    profiles = []
    for team_id, team_rows in history.groupby("team_id"):
        won = team_rows[team_rows["outcome"] == "won"]
        lost = team_rows[team_rows["outcome"] == "lost"]
        not_reached = team_rows[team_rows["outcome"] == "not_reached"]

        won_ratios = [r for r in (_row_ratio(row, player_conn) for _, row in won.iterrows()) if r is not None]
        lost_ratios = [r for r in (_row_ratio(row, player_conn) for _, row in lost.iterrows()) if r is not None]

        profiles.append(TeamPreferenceProfile(
            team_id=team_id,
            n_preferences_observed=len(team_rows),
            n_won=len(won),
            n_lost=len(lost),
            n_not_reached=len(not_reached),
            avg_overbid_ratio_won=(sum(won_ratios) / len(won_ratios)) if won_ratios else None,
            avg_overbid_ratio_lost=(sum(lost_ratios) / len(lost_ratios)) if lost_ratios else None,
            avg_preference_rank_won=(won["preference_rank"].mean()) if len(won) else None,
        ))
    return profiles


def team_price_multiplier(
    team_id: str,
    aggressiveness: dict[str, TeamAggressiveness],
    regime_mean_ratio: float | None,
    preference_profiles: dict[str, TeamPreferenceProfile] | None = None,
) -> tuple[float, str]:
    """Best-available per-team price multiplier (relative to the league-wide
    market regime), for simulating a specific opponent's behaviour
    (`g3_simulation.py`). Cascades from most to least specific, same principle
    as `estimate_price_correction`'s role/tier cascade -- never blends two
    sources into one opaque number, always names which was used:

    1. `preference_profiles[team_id]` (ADR-2026-065): the richest signal, since
       it includes LOST preferences too, not just wins -- but only trusted with
       enough observations (>= MIN_SAMPLE_FOR_SPLIT combined won+lost), and only
       covers the ~80% of teams/rounds resolved during curation.
    2. `aggressiveness[team_id]` (`team_aggressiveness_index`, ADR-2026-058):
       ledger-only (wins only), but complete coverage and already reliability-gated.
    3. `1.0` (no adjustment) when neither has enough data for this team.
    """
    profile = (preference_profiles or {}).get(team_id)
    if profile is not None:
        n_priced = profile.n_won + profile.n_lost
        if n_priced >= MIN_SAMPLE_FOR_SPLIT and regime_mean_ratio is not None and regime_mean_ratio > 0:
            parts = [
                (profile.n_won, profile.avg_overbid_ratio_won),
                (profile.n_lost, profile.avg_overbid_ratio_lost),
            ]
            weighted = [(n, r) for n, r in parts if r is not None and n > 0]
            if weighted:
                blended = sum(n * r for n, r in weighted) / sum(n for n, _ in weighted)
                return blended / regime_mean_ratio, "profilo da preferenze complete (vinte+perse)"

    team_agg = (aggressiveness or {}).get(team_id)
    if team_agg is not None and team_agg.reliable and regime_mean_ratio is not None and regime_mean_ratio > 0:
        return team_agg.team_mean_ratio / regime_mean_ratio, "aggressività da ledger reale (solo vittorie)"

    return 1.0, "nessun dato di stile per questa squadra (nessuna correzione)"


def _row_ratio(row: pd.Series, player_conn) -> float | None:
    player_row = _get_player_row(player_conn, str(row["player_code"]))
    if player_row is None:
        return None
    quot = effective_quotazione(player_row)
    if quot is None or quot <= 0:
        return None
    return row["bid_amount"] / quot
