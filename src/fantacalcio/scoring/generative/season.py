"""Sub-module 7 — the season simulator: ``season != matchday-1 x 38``.

Per ``docs/research/priorart_stage4.md`` §2 and the §"Recommended" season-
simulator loop. For each of ``n_sims`` season paths:

1. draw an **appearance path** over the fixture list (participation module);
2. draw minutes per appearance (participation module);
3. draw the **shared** club-match scoreline once per matchday, cached — seeded
   from the *club* id so teammates share it (sub-module 6 v1);
4. resample a whole historical ``(voto, events)`` row per appearance (base voto,
   Level 0) and, when the corresponding module is active, override
   goals/assists/penalties (events), cards/own goals (discipline) and
   ``team_goals_conceded`` (scoreline);
5. score each appearance through ``scoring.engine.score_fantavoto`` (unchanged,
   deterministic);
6. aggregate along the path.

With ``active_modules = ()`` — no scoreline, no events, no discipline, Level-0
voto, participation forced to a flat rate — the season mean degrades to
``E[N] x bootstrap_mean`` within Monte-Carlo noise (ADR-2026-077 degradation
contract), while the season *variance* still carries the
``Var[S] = E[N] sigma^2 + Var[N] mu^2`` count term that naive 38x scaling drops.

**Deferred** (ADR-2026-077): availability Markov chain with spell durations,
in-path context drift (form autocorrelation, role / penalty-duty / manager
changes), endogenous yellow-card suspensions, real 2026/27 calendar wiring
(``default_season_fixtures`` is a neutral 38-fixture stand-in until a calendar
source exists).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ..engine import PlayerMatchdayEvents, score_fantavoto
from ..monte_carlo import DEFAULT_SEED
from ._seed import (
    MODULE_BASE_VOTO,
    MODULE_DISCIPLINE,
    MODULE_EVENTS,
    MODULE_MINUTES,
    MODULE_PARTICIPATION,
    MODULE_SCORELINE,
    module_rng,
)
from .base_voto import DEFAULT_PRIOR_GAMES, sample_appearance_scores
from .discipline import DisciplineRates, sample_discipline
from .goals_assists import PlayerRates, sample_events
from .participation import PlayerSeasonParticipation, sample_appearance, sample_minutes
from .scoreline import TeamMatchPrior, sample_team_match

MATCHDAYS_PER_SEASON = 38

# Names accepted in ``active_modules``.
MODULE_NAMES = frozenset({"scoreline", "events", "discipline"})


@dataclass(frozen=True)
class Fixture:
    """One matchday for the player's club. Neutral by default."""

    matchday: int
    is_home: bool = True
    opponent_strength: float = 0.0
    team_prior: TeamMatchPrior | None = None


def default_season_fixtures(n_matchdays: int = MATCHDAYS_PER_SEASON) -> list[Fixture]:
    """A neutral ``n_matchdays``-fixture list (alternating home/away, no priors).

    Placeholder until a real 2026/27 calendar source exists (ADR-2026-077).
    """
    return [Fixture(matchday=md, is_home=(md % 2 == 1)) for md in range(1, n_matchdays + 1)]


@dataclass(frozen=True)
class GenerativeConfig:
    """Everything the season simulator needs for one player.

    ``player_pools`` / ``role_pools`` are the ``build_event_pools`` dicts (used
    for the Level-0 per-appearance row resample). ``rates`` / ``discipline`` are
    only consulted when their module name is in ``active_modules``.
    """

    role: str
    participation: PlayerSeasonParticipation
    player_pools: dict
    role_pools: dict
    rates: PlayerRates | None = None
    discipline: DisciplineRates | None = None
    prior_games: float = DEFAULT_PRIOR_GAMES


@dataclass(frozen=True)
class SeasonSimResult:
    """Seasonal predictive distribution and its components."""

    player_code: int
    role: str
    n_sims: int
    n_matchdays: int
    season_totals: np.ndarray
    appearance_counts: np.ndarray
    status_counts: np.ndarray  # (n_sims, 3): [n_unused, n_bench, n_start]
    per_matchday_points: np.ndarray  # (n_sims, n_matchdays), 0 where no appearance
    team_goals_against: np.ndarray  # (n_sims, n_matchdays), -1 where not drawn
    minutes: np.ndarray  # (n_sims, n_matchdays)
    active_modules: tuple[str, ...] = ()

    # -- seasonal summary --------------------------------------------------- #
    @property
    def mean(self) -> float:
        return float(np.mean(self.season_totals))

    @property
    def median(self) -> float:
        return float(np.median(self.season_totals))

    @property
    def p10(self) -> float:
        return float(np.percentile(self.season_totals, 10))

    @property
    def p90(self) -> float:
        return float(np.percentile(self.season_totals, 90))

    @property
    def downside(self) -> float:
        """Mean of the worst decile of season paths."""
        s = np.sort(self.season_totals)
        cut = max(1, self.n_sims // 10)
        return float(np.mean(s[:cut]))

    @property
    def upside(self) -> float:
        """Mean of the best decile of season paths."""
        s = np.sort(self.season_totals)
        cut = max(1, self.n_sims // 10)
        return float(np.mean(s[-cut:]))

    @property
    def variance(self) -> float:
        return float(np.var(self.season_totals))

    # -- participation summary ------------------------------------------------ #
    @property
    def expected_appearances(self) -> float:
        return float(np.mean(self.appearance_counts))

    @property
    def titolare_prob(self) -> float:
        """Per-fixture probability the player starts."""
        return float(np.mean(self.status_counts[:, 2]) / self.n_matchdays)

    @property
    def subentro_prob(self) -> float:
        """Per-fixture probability the player comes on as a bench cameo."""
        return float(np.mean(self.status_counts[:, 1]) / self.n_matchdays)

    @property
    def no_vote_prob(self) -> float:
        """Per-fixture probability the player is unused / absent."""
        return float(np.mean(self.status_counts[:, 0]) / self.n_matchdays)

    @property
    def minutes_mean(self) -> float:
        return float(np.mean(self.minutes))

    @property
    def minutes_p10(self) -> float:
        return float(np.percentile(self.minutes, 10))

    @property
    def minutes_p90(self) -> float:
        return float(np.percentile(self.minutes, 90))

    def naive_38x_variance(self, single_match_var: float) -> float:
        """The (wrong) ``n_matchdays x Var(single match)`` scaling, for contrast."""
        return float(self.n_matchdays * single_match_var)


def simulate_season(
    player_code: int,
    config: GenerativeConfig,
    fixtures: Sequence[Fixture] | None = None,
    n_sims: int = 1000,
    *,
    base_seed: int = DEFAULT_SEED,
    club_id: int | None = None,
    active_modules: Sequence[str] = (),
    team_priors: Sequence[TeamMatchPrior | None] | None = None,
    first_md_participation: PlayerSeasonParticipation | None = None,
) -> SeasonSimResult:
    """Monte-Carlo a player's season over ``fixtures``.

    Parameters
    ----------
    club_id:
        Entity id the shared scoreline stream is seeded from. Two players with
        the same ``club_id`` (same ``base_seed``, ``fixtures`` / ``team_priors``,
        ``n_sims``) see the identical ``(gf, ga)`` sequence — the sub-module 6
        dependency. Defaults to ``player_code`` (independent scorelines).
    active_modules:
        Any of ``{"scoreline", "events", "discipline"}``. Base voto is always
        Level-0 row-resample. With none active the result degrades to the
        row-bootstrap scaled by the appearance path.
    team_priors:
        Optional per-fixture ``TeamMatchPrior`` overriding ``fixture.team_prior``.
    """
    fx = list(fixtures) if fixtures is not None else default_season_fixtures()
    n_md = len(fx)
    if n_md == 0:
        raise ValueError("fixtures must be non-empty")
    active = set(active_modules)
    unknown = active - MODULE_NAMES
    if unknown:
        raise ValueError(f"unknown module name(s) {sorted(unknown)}; allowed: {sorted(MODULE_NAMES)}")
    club = int(club_id) if club_id is not None else int(player_code)

    priors: list[TeamMatchPrior | None]
    if team_priors is not None:
        priors = list(team_priors)
        if len(priors) != n_md:
            raise ValueError("team_priors length must match fixtures")
    else:
        priors = [f.team_prior for f in fx]

    role = config.role
    season_totals = np.zeros(n_sims, dtype=float)
    appearance_counts = np.zeros(n_sims, dtype=int)
    status_counts = np.zeros((n_sims, 3), dtype=int)
    per_matchday_points = np.zeros((n_sims, n_md), dtype=float)
    team_goals_against = np.full((n_sims, n_md), -1, dtype=int)
    minutes_out = np.zeros((n_sims, n_md), dtype=float)

    for s in range(n_sims):
        r_part = module_rng(base_seed, player_code, s, MODULE_PARTICIPATION)
        if first_md_participation is None:
            status = sample_appearance(config.participation, role, n_md, r_part)
        else:
            # Stage 7: an availability report caps the first fixture only; later
            # matchdays keep the season rate. Only reached when a real report
            # exists for this player, so the default path stays byte-identical.
            s0 = sample_appearance(first_md_participation, role, 1, r_part)
            if n_md > 1:
                s_rest = sample_appearance(config.participation, role, n_md - 1, r_part)
                status = np.concatenate([s0, s_rest])
            else:
                status = s0

        r_min = module_rng(base_seed, player_code, s, MODULE_MINUTES)
        minutes = sample_minutes(status, role, r_min)

        # Shared club-match scoreline: one draw per matchday, seeded from the club.
        r_team = module_rng(base_seed, club, s, MODULE_SCORELINE)
        gf_arr = np.empty(n_md, dtype=int)
        ga_arr = np.empty(n_md, dtype=int)
        for i, prior in enumerate(priors):
            gf_arr[i], ga_arr[i] = sample_team_match(prior, r_team)

        appear_idx = np.where(minutes > 0.0)[0]
        n_app = appear_idx.size

        r_voto = module_rng(base_seed, player_code, s, MODULE_BASE_VOTO)
        scores, rows = sample_appearance_scores(
            config.player_pools, config.role_pools, player_code, role, n_app, r_voto,
            prior_games=config.prior_games,
        )

        ev = None
        if "events" in active and config.rates is not None:
            r_evt = module_rng(base_seed, player_code, s, MODULE_EVENTS)
            ev = sample_events(config.rates, role, minutes[appear_idx], gf_arr[appear_idx], r_evt)
        dis = None
        if "discipline" in active and config.discipline is not None:
            r_dis = module_rng(base_seed, player_code, s, MODULE_DISCIPLINE)
            dis = sample_discipline(config.discipline, role, minutes[appear_idx], r_dis)

        override = (ev is not None) or (dis is not None) or ("scoreline" in active)

        for a, md in enumerate(appear_idx):
            row = rows[a]
            if not override:
                pts = float(scores[a])
            else:
                g = int(ev["goals"][a]) if ev is not None else row.goals_scored
                assists = int(ev["assists"][a]) if ev is not None else row.assists
                pen_missed = int(ev["penalties_missed"][a]) if ev is not None else row.penalties_missed
                yellow = int(dis["yellow"][a]) if dis is not None else row.yellow_cards
                red = int(dis["red"][a]) if dis is not None else row.red_cards
                own_goal = int(dis["own_goal"][a]) if dis is not None else row.own_goals
                if "scoreline" in active:
                    tgc: int | None = int(ga_arr[md])
                    gc = int(ga_arr[md])
                else:
                    tgc = int(row.team_goals_conceded) if row.team_goals_conceded is not None else None
                    gc = row.goals_conceded
                pmev = PlayerMatchdayEvents(
                    role=role,
                    played=True,
                    goals_scored=g,
                    assists=assists,
                    goals_conceded=gc,
                    own_goals=own_goal,
                    yellow_cards=yellow,
                    red_cards=red,
                    penalties_missed=pen_missed,
                    team_goals_conceded=tgc,
                )
                pts = score_fantavoto(row.voto, pmev)
            per_matchday_points[s, md] = pts
            team_goals_against[s, md] = int(ga_arr[md])
            minutes_out[s, md] = minutes[md]

        season_totals[s] = per_matchday_points[s].sum()
        appearance_counts[s] = n_app
        status_counts[s] = [int((status == 0).sum()), int((status == 1).sum()), int((status == 2).sum())]

    return SeasonSimResult(
        player_code=player_code,
        role=role,
        n_sims=n_sims,
        n_matchdays=n_md,
        season_totals=season_totals,
        appearance_counts=appearance_counts,
        status_counts=status_counts,
        per_matchday_points=per_matchday_points,
        team_goals_against=team_goals_against,
        minutes=minutes_out,
        active_modules=tuple(sorted(active)),
    )


__all__ = [
    "Fixture",
    "GenerativeConfig",
    "SeasonSimResult",
    "default_season_fixtures",
    "simulate_season",
    "MATCHDAYS_PER_SEASON",
]
