"""Feasibility checks for locking a player as a pre-auction target
(docs/CURRENT_TASK.md, M4 slice 5).

Per CLAUDE.md: "Locked players remain locked. If infeasible, explain the
conflicting constraint and minimum relaxation." This module never silently
allows a lock that couldn't possibly become real -- it explains why, in terms
a user can act on (which existing lock to drop, why a player is unavailable).
Pure function, no I/O: callers pass in state already loaded from the ledger
and locks store.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Ruleset
from ..domain import LeagueState
from ..persistence.locks_store import LockedPlayer
from .bid_recommendation import VOTI_TO_DOMAIN_ROLE

_ROLE_TARGET_FIELD = {
    "P": "goalkeeper_block_size",
    "D": "defenders",
    "C": "midfielders",
    "A": "forwards",
}


@dataclass(frozen=True)
class LockFeasibilityResult:
    ok: bool
    reason: str | None = None


def check_lock_feasibility(
    team_id: str,
    player_code: int,
    role: str,
    ruleset: Ruleset,
    league_state: LeagueState,
    existing_locks: list[LockedPlayer],
) -> LockFeasibilityResult:
    """`role` is a voti/listone role code (P/D/C/A). `existing_locks` should be
    this team's current locks (from `locks_store.list_locks(conn, team_id)`),
    not locking the same player twice or exceeding role capacity."""
    player_code_str = str(player_code)

    if player_code_str in league_state.team(team_id).roster.get(VOTI_TO_DOMAIN_ROLE[role], []):
        return LockFeasibilityResult(
            ok=False, reason="Il giocatore è già nella rosa reale di questa squadra: non serve bloccarlo."
        )

    for other_team_id, other_team in league_state.teams.items():
        if other_team_id == team_id:
            continue
        if player_code_str in other_team.roster.get(VOTI_TO_DOMAIN_ROLE[role], []):
            return LockFeasibilityResult(
                ok=False,
                reason=f"Il giocatore è già stato assegnato alla squadra {other_team_id!r} nel ledger reale: "
                "obiettivo non più disponibile.",
            )

    if any(lock.player_code == player_code for lock in existing_locks):
        return LockFeasibilityResult(ok=False, reason="Il giocatore è già bloccato per questa squadra.")

    target_field = _ROLE_TARGET_FIELD[role]
    role_cap = getattr(ruleset.roster, target_field)
    domain_role = VOTI_TO_DOMAIN_ROLE[role]
    real_count = league_state.team(team_id).role_count(domain_role)
    locked_count = sum(1 for lock in existing_locks if lock.role == role)

    if real_count + locked_count >= role_cap:
        other_locks = [lock for lock in existing_locks if lock.role == role]
        relaxation = (
            f"rimuovi uno dei {len(other_locks)} lock già presenti per il ruolo {role!r} per fare spazio"
            if other_locks
            else f"{real_count} slot per il ruolo {role!r} sono già coperti dalla rosa reale: nessun lock possibile per questo ruolo"
        )
        return LockFeasibilityResult(
            ok=False,
            reason=(
                f"Capacità di ruolo {role!r} superata: {real_count} già in rosa reale + {locked_count} già "
                f"bloccati >= {role_cap} slot totali. {relaxation}."
            ),
        )

    return LockFeasibilityResult(ok=True)
