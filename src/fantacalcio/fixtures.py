"""Synthetic demo fixture generator for tests and local smoke-checks.

Not real auction data: player/club identifiers are placeholders. Deterministic given
a fixed seed, per docs/CURRENT_TASK.md.
"""

from __future__ import annotations

import random

from .config import Ruleset
from .domain import AssignmentEvent, AssignmentItem, Event, Role


def generate_demo_events(ruleset: Ruleset, seed: int = 42) -> list[Event]:
    """Build a valid, deterministic event ledger exercising all four rounds.

    Every team buys a goalkeeper block and one defender in G1, and one midfielder and
    one forward in G2. The first team additionally buys one player each in the G3/G4
    open-auction rounds, to exercise that round type without hand-authoring a full
    synthetic market.
    """
    rng = random.Random(seed)
    teams = [f"team-{i:02d}" for i in range(1, ruleset.teams + 1)]

    events: list[Event] = []
    ts = f"{ruleset.effective_from}T00:00:00Z"
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"evt-{counter:04d}"

    for i, team_id in enumerate(teams, start=1):
        gk_players = tuple(f"gk-{i:02d}-{k}" for k in range(1, ruleset.roster.goalkeeper_block_size + 1))
        events.append(
            AssignmentEvent(
                event_id=next_id(),
                ts=ts,
                round_id="G1",
                team_id=team_id,
                pool_id="goalkeeper_blocks",
                role=Role.GK,
                item=AssignmentItem(player_ids=gk_players),
                amount=rng.randint(1, 20),
                source="demo_fixture",
                author="fixture",
            )
        )
        events.append(
            AssignmentEvent(
                event_id=next_id(),
                ts=ts,
                round_id="G1",
                team_id=team_id,
                pool_id="defenders_top_1_60",
                role=Role.DEF,
                item=AssignmentItem(player_ids=(f"def-{i:02d}",)),
                amount=rng.randint(1, 30),
                source="demo_fixture",
                author="fixture",
            )
        )

    for i, team_id in enumerate(teams, start=1):
        events.append(
            AssignmentEvent(
                event_id=next_id(),
                ts=ts,
                round_id="G2",
                team_id=team_id,
                pool_id="midfielders_top_1_20",
                role=Role.MID,
                item=AssignmentItem(player_ids=(f"mid-{i:02d}",)),
                amount=rng.randint(1, 30),
                source="demo_fixture",
                author="fixture",
            )
        )
        events.append(
            AssignmentEvent(
                event_id=next_id(),
                ts=ts,
                round_id="G2",
                team_id=team_id,
                pool_id="forwards_top_1_20",
                role=Role.FWD,
                item=AssignmentItem(player_ids=(f"fwd-{i:02d}",)),
                amount=rng.randint(1, 30),
                source="demo_fixture",
                author="fixture",
            )
        )

    first_team = teams[0]
    events.append(
        AssignmentEvent(
            event_id=next_id(),
            ts=ts,
            round_id="G3",
            team_id=first_team,
            pool_id="remaining_players",
            role=Role.MID,
            item=AssignmentItem(player_ids=("mid-extra-01",)),
            amount=rng.randint(1, 15),
            source="demo_fixture",
            author="fixture",
        )
    )
    events.append(
        AssignmentEvent(
            event_id=next_id(),
            ts=ts,
            round_id="G4",
            team_id=first_team,
            pool_id="remaining_players",
            role=Role.FWD,
            item=AssignmentItem(player_ids=("fwd-extra-01",)),
            amount=rng.randint(1, 10),
            source="demo_fixture",
            author="fixture",
        )
    )

    return events
