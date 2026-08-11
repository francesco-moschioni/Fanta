"""Team-concentration risk: too many players from the same real club in one
roster (docs/UX_PRODUCT.md: "concentrazione di squadra").

A single bad result (injury to a key player, a heavy loss, a coaching change)
can drag down several fantasy players at once if they're concentrated at the
same real club -- this module counts that exposure, it doesn't predict
anything. Pure grouping over data the caller already has (player_code,
team_name pairs from the combined real+locked roster); no new stats.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

# Explicit, documented default -- not a hidden magic number. A team has at
# most 8 defenders/midfielders (config/auction_rules.v1.yaml), so 3+ from one
# club is a meaningful share of a single role bucket, not an arbitrary cutoff.
DEFAULT_WARNING_THRESHOLD = 3


@dataclass(frozen=True)
class ClubConcentration:
    team_name: str
    player_codes: tuple[int, ...]

    @property
    def player_count(self) -> int:
        return len(self.player_codes)


def compute_club_concentration(player_club_pairs: list[tuple[int, str]]) -> list[ClubConcentration]:
    """`player_club_pairs`: (player_code, team_name) for every player in the
    roster being checked (real + locked, or any other combination the caller
    wants). Returns one entry per club with 2+ players, sorted by count desc
    then club name -- clubs with only one player aren't concentration risk."""
    by_club: dict[str, list[int]] = defaultdict(list)
    for player_code, team_name in player_club_pairs:
        by_club[team_name].append(player_code)

    return sorted(
        (
            ClubConcentration(team_name=club, player_codes=tuple(codes))
            for club, codes in by_club.items()
            if len(codes) >= 2
        ),
        key=lambda c: (-c.player_count, c.team_name),
    )
