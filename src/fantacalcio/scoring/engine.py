"""Deterministic individual scoring engine — applies the confirmed components of
docs/SCORING_RULES.md to real per-matchday player events.

Per CLAUDE.md, scoring is deterministic code, never LLM output, and unresolved rules
are never guessed. This module only implements what is BOTH rule-confirmed AND
computable from the data we actually have; everything else is either an explicitly
documented approximation or a hard-blocked component (raises, doesn't silently
return 0).

What's implemented (individual-level, confirmed in docs/SCORING_RULES.md):
  goal (+3), assist (+1, see approximation note below), goal conceded (-1 per the
  data's own Gs value), clean sheet (+1, GK only — see note below), penalty missed (-3), own
  goal (-2), yellow card (-0.5), red card (-1).

Approximation (documented, not hidden): docs/SCORING_RULES.md distinguishes "Assist"
(+1) from "Assist light / contributo al gol" (+0.5) as separate events, but the
voti export has a single `assists` column that doesn't distinguish them. Every
assist is scored at the full +1 rate here; this is a known upward bias for
whichever of those events were actually assist-light, not a resolved rule.

Blocked (never computed, raise ScoringComponentBlocked):
  - penalty saved / penalty won: the data has `penalties_saved`/`penalties_won`
    columns, but docs/SCORING_RULES.md's confirmed point table has NO entry for
    either event. This is a rule gap, not a data gap.
  - equalizing/winning goal bonus: needs goal-by-goal match timing and final
    scoreline, which we don't have per player-matchday row. Data gap.
  - captain bonus: needs to know who was captain; not present in the data. Data gap.
  - fair play, defense modifier, performance bonus, under-11 relief: team-level
    modifiers whose exact formula is still open in docs/OPEN_QUESTIONS.md. Rule gap.
"""

from __future__ import annotations

from dataclasses import dataclass


class ScoringComponentBlocked(NotImplementedError):
    """Raised when asked to compute a component that is either not rule-confirmed
    or not computable from available data. See module docstring for the exact list."""


@dataclass(frozen=True)
class PlayerMatchdayEvents:
    role: str  # "P" | "D" | "C" | "A"
    played: bool
    goals_scored: int = 0
    assists: int = 0
    goals_conceded: int = 0
    own_goals: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    penalties_missed: int = 0


@dataclass(frozen=True)
class ScoreBreakdown:
    goal_points: float
    assist_points: float
    goal_conceded_points: float
    clean_sheet_points: float
    own_goal_points: float
    card_points: float
    penalty_missed_points: float

    @property
    def total(self) -> float:
        return (
            self.goal_points
            + self.assist_points
            + self.goal_conceded_points
            + self.clean_sheet_points
            + self.own_goal_points
            + self.card_points
            + self.penalty_missed_points
        )


_GOAL_POINTS = 3.0
_ASSIST_POINTS = 1.0  # approximation: assist-light (+0.5) not distinguishable, see module docstring
_GOAL_CONCEDED_POINTS = -1.0
_CLEAN_SHEET_POINTS = 1.0
_OWN_GOAL_POINTS = -2.0
_YELLOW_CARD_POINTS = -0.5
_RED_CARD_POINTS = -1.0
_PENALTY_MISSED_POINTS = -3.0

_CLEAN_SHEET_ROLES = frozenset({"P"})
# Defenders excluded (data check, 2026-08-11): the voti export's `goals_conceded`
# field is populated almost exclusively for goalkeepers (71% nonzero) and is
# essentially always 0 for defenders (0.005% nonzero) — not because their team
# usually kept a clean sheet, but because this source doesn't track it at the
# individual-defender level. Treating that as a real clean sheet signal wrongly
# credited nearly every defender's every matchday, inflating scores well above
# Fantacalcio.it's own Fm. A real defender clean-sheet bonus needs team-level
# match results (available from football-data.co.uk, not yet joined here).


def score_player_matchday(events: PlayerMatchdayEvents) -> ScoreBreakdown:
    """Compute the confirmed individual-level components for one player's matchday.
    Does not include team-level modifiers (defense modifier, performance bonus,
    fair play, under-11 relief) or captain bonus — call those separately once their
    formulas are confirmed; see module docstring."""
    if not events.played:
        return ScoreBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    clean_sheet = events.role in _CLEAN_SHEET_ROLES and events.goals_conceded == 0

    return ScoreBreakdown(
        goal_points=_GOAL_POINTS * events.goals_scored,
        assist_points=_ASSIST_POINTS * events.assists,
        goal_conceded_points=_GOAL_CONCEDED_POINTS * events.goals_conceded,
        clean_sheet_points=_CLEAN_SHEET_POINTS if clean_sheet else 0.0,
        own_goal_points=_OWN_GOAL_POINTS * events.own_goals,
        card_points=_YELLOW_CARD_POINTS * events.yellow_cards + _RED_CARD_POINTS * events.red_cards,
        penalty_missed_points=_PENALTY_MISSED_POINTS * events.penalties_missed,
    )


def score_fantavoto(voto: float, events: PlayerMatchdayEvents) -> float:
    """Base voto plus the confirmed individual bonus/malus components. This is NOT
    the full fantamedia: team-level modifiers and captain bonus are excluded (see
    module docstring) and would need to be added on top by a separate function once
    their formulas are confirmed."""
    breakdown = score_player_matchday(events)
    return voto + breakdown.total


def penalty_saved_points(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "docs/SCORING_RULES.md has no confirmed point value for 'rigore parato', "
        "even though the data has a penalties_saved field. Do not guess a value; "
        "record an approved ADR first."
    )


def penalty_won_points(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "docs/SCORING_RULES.md has no confirmed point value for 'rigore procurato', "
        "even though the data has a penalties_won field. Do not guess a value; "
        "record an approved ADR first."
    )


def equalizing_or_winning_goal_bonus(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Requires goal-by-goal match timing and final scoreline, not available "
        "per player-matchday in the current data. Data gap, not a rule gap."
    )


def captain_bonus(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Requires knowing which player was captain; not present in current data. "
        "Data gap, not a rule gap."
    )


def fair_play_bonus(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Exact perimeter ('quali giocatori devono avere zero ammonizioni') is "
        "still open in docs/OPEN_QUESTIONS.md. Rule gap, not a data gap."
    )


def defense_modifier(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Exact formula (which votes count, goalkeeper handling, best-3-defenders "
        "vs all) is still open in docs/OPEN_QUESTIONS.md. Rule gap, not a data gap."
    )


def performance_bonus(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Formula itself is confirmed (9/10/11 players >=6 -> +0.5/+1/+1.5) but "
        "requires the full team roster's voti for the matchday, which this "
        "single-player function does not have access to — compute at the team "
        "level, not per player. Not wired up yet."
    )


def under_11_relief(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Two competing values exist (+3.5 confirmed historical vs. +4.5 proposed, "
        "unapproved) — see docs/SCORING_RULES.md. Rule gap: which one applies is "
        "not yet decided by an ADR."
    )
