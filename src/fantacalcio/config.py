"""Loader and validator for the versioned auction ruleset (config/auction_rules.v1.yaml).

Per CLAUDE.md, rounds/budgets/pools/formations/roster constraints must never be
hardcoded in domain logic; they are always read from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the ruleset file is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class RosterComposition:
    total_players: int
    goalkeeper_block_size: int
    goalkeeper_same_club: bool
    defenders: int
    midfielders: int
    forwards: int
    forwards_fallback: int


@dataclass(frozen=True)
class Round:
    id: str
    order: int
    mode: str  # "sealed_bid" | "open_auction"
    budget_increment: int
    budget_available_expr: str
    pools: tuple[str, ...]


@dataclass(frozen=True)
class Ruleset:
    schema_version: int
    ruleset_id: str
    status: str
    effective_from: str
    teams: int
    roster: RosterComposition
    formations: tuple[str, ...]
    list_states: tuple[str, ...]
    official_pool_authority: str
    model_ranking_is_official_pool: bool
    rounds: tuple[Round, ...]
    runtime_invariants: dict[str, bool]
    uncertain_historical_fields: dict[str, Any]

    def round_by_id(self, round_id: str) -> Round:
        for r in self.rounds:
            if r.id == round_id:
                return r
        raise ConfigError(
            f"Unknown round id {round_id!r}; known rounds: {[r.id for r in self.rounds]}"
        )

    def is_field_confirmed(self, field_name: str) -> bool:
        """A historical field counts as confirmed only once it holds a non-null value,
        which requires an approved ADR per docs/OPEN_QUESTIONS.md."""
        return self.uncertain_historical_fields.get(field_name) is not None


_SUPPORTED_MODES = ("sealed_bid", "open_auction")
_REQUIRED_LIST_STATES = frozenset({"unknown", "provisional", "official"})


def _require(d: dict[str, Any], key: str, path: str) -> Any:
    if not isinstance(d, dict):
        raise ConfigError(f"Expected a mapping at {path}, got {type(d).__name__}")
    if key not in d or d[key] is None:
        raise ConfigError(f"Missing required field '{key}' at {path}")
    return d[key]


def load_ruleset(path: str | Path) -> Ruleset:
    """Load and validate the ruleset. Raises ConfigError on any missing/malformed/
    inconsistent field. Never fills in a missing value with a guessed default."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Ruleset file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigError(f"Ruleset root must be a mapping, got {type(raw).__name__}")

    schema_version = _require(raw, "schema_version", "root")
    if schema_version != 1:
        raise ConfigError(
            f"Unsupported schema_version {schema_version!r}; this loader only supports 1"
        )

    league = _require(raw, "league", "root")
    roster_raw = _require(league, "roster", "league")
    gk_raw = _require(roster_raw, "goalkeeper_block", "league.roster")

    roster = RosterComposition(
        total_players=_require(roster_raw, "total_players", "league.roster"),
        goalkeeper_block_size=_require(gk_raw, "players", "league.roster.goalkeeper_block"),
        goalkeeper_same_club=bool(
            _require(gk_raw, "same_club", "league.roster.goalkeeper_block")
        ),
        defenders=_require(roster_raw, "defenders", "league.roster"),
        midfielders=_require(roster_raw, "midfielders", "league.roster"),
        forwards=_require(roster_raw, "forwards", "league.roster"),
        forwards_fallback=_require(
            roster_raw, "forwards_fallback_if_supply_insufficient", "league.roster"
        ),
    )
    expected_total = (
        roster.goalkeeper_block_size + roster.defenders + roster.midfielders + roster.forwards
    )
    if expected_total != roster.total_players:
        raise ConfigError(
            "Roster composition does not sum to total_players: "
            f"{roster.goalkeeper_block_size}+{roster.defenders}+{roster.midfielders}"
            f"+{roster.forwards} = {expected_total} != {roster.total_players}"
        )

    formations = tuple(_require(league, "formations", "league"))
    if not formations:
        raise ConfigError("league.formations must not be empty")

    auction = _require(raw, "auction", "root")
    list_states = tuple(_require(auction, "list_states", "auction"))
    if set(list_states) != _REQUIRED_LIST_STATES:
        raise ConfigError(
            f"auction.list_states must be exactly {sorted(_REQUIRED_LIST_STATES)}, "
            f"got {list(list_states)}"
        )

    rounds_raw = _require(auction, "rounds", "auction")
    if not isinstance(rounds_raw, list) or not rounds_raw:
        raise ConfigError("auction.rounds must be a non-empty list")

    rounds: list[Round] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for i, r in enumerate(rounds_raw):
        rpath = f"auction.rounds[{i}]"
        rid = _require(r, "id", rpath)
        if rid in seen_ids:
            raise ConfigError(f"{rpath}: duplicate round id {rid!r}")
        seen_ids.add(rid)

        order = _require(r, "order", rpath)
        if order in seen_orders:
            raise ConfigError(f"{rpath}: duplicate round order {order}")
        seen_orders.add(order)

        mode = _require(r, "mode", rpath)
        if mode not in _SUPPORTED_MODES:
            raise ConfigError(f"{rpath}: unsupported mode {mode!r}, expected one of {_SUPPORTED_MODES}")

        pools = tuple(_require(r, "pools", rpath))
        if not pools:
            raise ConfigError(f"{rpath}: pools must not be empty")

        rounds.append(
            Round(
                id=rid,
                order=order,
                mode=mode,
                budget_increment=_require(r, "budget_increment", rpath),
                budget_available_expr=str(_require(r, "budget_available", rpath)),
                pools=pools,
            )
        )

    rounds.sort(key=lambda r: r.order)
    if [r.order for r in rounds] != list(range(1, len(rounds) + 1)):
        raise ConfigError(
            f"auction.rounds orders must be a contiguous 1..N sequence, "
            f"got {[r.order for r in rounds]}"
        )
    # Every non-first round's budget expression must reference only earlier rounds,
    # so evaluate_budget_expr can never be asked to resolve a forward/circular reference.
    known_ids: set[str] = set()
    for r in rounds:
        for ref in _extract_round_refs(r.budget_available_expr):
            if ref not in known_ids:
                raise ConfigError(
                    f"Round {r.id!r} budget expression {r.budget_available_expr!r} references "
                    f"{ref!r}, which is not an earlier round"
                )
        known_ids.add(r.id)

    runtime_invariants = _require(raw, "runtime_invariants", "root")
    uncertain = raw.get("uncertain_historical_fields", {}) or {}

    return Ruleset(
        schema_version=schema_version,
        ruleset_id=_require(raw, "ruleset_id", "root"),
        status=_require(raw, "status", "root"),
        effective_from=str(_require(raw, "effective_from", "root")),
        teams=_require(league, "teams", "league"),
        roster=roster,
        formations=formations,
        list_states=list_states,
        official_pool_authority=_require(auction, "official_pool_authority", "auction"),
        model_ranking_is_official_pool=bool(
            _require(auction, "model_ranking_is_official_pool", "auction")
        ),
        rounds=tuple(rounds),
        runtime_invariants=runtime_invariants,
        uncertain_historical_fields=uncertain,
    )


_EXPR_TOKEN_RE = re.compile(
    r"remaining_(?P<rid>[A-Za-z0-9_]+)|(?P<num>\d+)|(?P<plus>\+)"
)


def _extract_round_refs(expr: str) -> list[str]:
    return [m.group("rid") for m in _EXPR_TOKEN_RE.finditer(expr) if m.group("rid")]


def evaluate_budget_expr(expr: str, remaining_by_round: dict[str, int]) -> int:
    """Evaluate a `budget_available` expression like "200" or "remaining_G1 + 100".

    Deliberately not a general-purpose expression evaluator (no eval()): only integer
    literals, `remaining_<round_id>` references, and `+` are supported, which is all the
    current ruleset format allows.
    """
    expr = expr.strip()
    pos = 0
    total = 0
    expect_operand = True
    for m in _EXPR_TOKEN_RE.finditer(expr):
        gap = expr[pos : m.start()]
        if gap.strip():
            raise ConfigError(f"Unparseable budget expression: {expr!r}")
        pos = m.end()

        if m.group("rid"):
            if not expect_operand:
                raise ConfigError(f"Unexpected token in budget expression: {expr!r}")
            rid = m.group("rid")
            if rid not in remaining_by_round:
                raise ConfigError(
                    f"Budget expression references a round with no recorded remaining "
                    f"budget yet: {rid!r} in {expr!r}"
                )
            total += remaining_by_round[rid]
            expect_operand = False
        elif m.group("num"):
            if not expect_operand:
                raise ConfigError(f"Unexpected token in budget expression: {expr!r}")
            total += int(m.group("num"))
            expect_operand = False
        elif m.group("plus"):
            if expect_operand:
                raise ConfigError(f"Unexpected '+' in budget expression: {expr!r}")
            expect_operand = True

    trailing = expr[pos:].strip()
    if trailing:
        raise ConfigError(f"Unparseable trailing content in budget expression: {expr!r}")
    if expect_operand:
        raise ConfigError(f"Budget expression ends with an operator: {expr!r}")
    return total
