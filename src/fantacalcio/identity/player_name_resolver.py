"""Player entity resolution: crosswalk a display-name-only source to `player_code`.

Per docs/DATA_AND_MODELING.md and CLAUDE.md: never join players on display name
alone. This module only ever *proposes* a crosswalk against the known `player_code`
anchor list (from fantacalcio_listone); ambiguous or low-confidence matches go to a
manual review queue rather than being force-matched or silently dropped. Role is
used as a disambiguating signal (many surnames repeat, e.g. "Esposito F.P." vs
"Esposito Se."), never inferred from name alone.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from fantacalcio.identity.teams import normalize_name

AUTO_ACCEPT_THRESHOLD = 0.90


@dataclass(frozen=True)
class AnchorPlayer:
    player_code: int
    display_name: str
    role: str
    team_name: str


@dataclass(frozen=True)
class PlayerCrosswalkEntry:
    player_code: int
    anchor_display_name: str
    matched_display_name: str
    role: str
    confidence: float
    match_method: str  # "exact_normalized" | "fuzzy_auto"
    status: str  # "confirmed"


@dataclass(frozen=True)
class PlayerReviewQueueEntry:
    matched_display_name: str
    role: str | None
    best_candidate_player_code: int | None
    best_candidate_display_name: str | None
    confidence: float
    reason: str


@dataclass(frozen=True)
class PlayerResolutionResult:
    crosswalk: list[PlayerCrosswalkEntry]
    review_queue: list[PlayerReviewQueueEntry]


def resolve_against_anchor(
    anchor_players: list[AnchorPlayer],
    other_names: list[tuple[str, str | None]],
    auto_accept_threshold: float = AUTO_ACCEPT_THRESHOLD,
) -> PlayerResolutionResult:
    """Resolve `other_names` (display_name, role) pairs against the anchor roster.

    Matching is restricted to anchor players sharing the same role when a role is
    given (role mismatch is a strong signal of a different person, e.g. a coach or
    an unrelated homonym), then by exact normalized name, then by best fuzzy ratio.
    Anything below `auto_accept_threshold` — including duplicate normalized names
    within the same role (unresolved homonyms) — goes to the review queue.
    """
    by_role: dict[str | None, dict[str, list[AnchorPlayer]]] = {}
    for anchor in anchor_players:
        role_bucket = by_role.setdefault(anchor.role, {})
        role_bucket.setdefault(normalize_name(anchor.display_name), []).append(anchor)

    crosswalk: list[PlayerCrosswalkEntry] = []
    review_queue: list[PlayerReviewQueueEntry] = []

    for other_name, other_role in sorted(set(other_names)):
        other_norm = normalize_name(other_name)
        candidates = by_role.get(other_role, {})

        exact = candidates.get(other_norm)
        if exact and len(exact) == 1:
            anchor = exact[0]
            crosswalk.append(
                PlayerCrosswalkEntry(
                    player_code=anchor.player_code,
                    anchor_display_name=anchor.display_name,
                    matched_display_name=other_name,
                    role=anchor.role,
                    confidence=1.0,
                    match_method="exact_normalized",
                    status="confirmed",
                )
            )
            continue
        if exact and len(exact) > 1:
            review_queue.append(
                PlayerReviewQueueEntry(
                    matched_display_name=other_name,
                    role=other_role,
                    best_candidate_player_code=None,
                    best_candidate_display_name=None,
                    confidence=1.0,
                    reason=f"Ambiguous: {len(exact)} anchor players share normalized name and role",
                )
            )
            continue

        best_norm, best_ratio = None, 0.0
        for anchor_norm in candidates:
            ratio = difflib.SequenceMatcher(None, other_norm, anchor_norm).ratio()
            if ratio > best_ratio:
                best_norm, best_ratio = anchor_norm, ratio

        best_matches = candidates.get(best_norm, []) if best_norm else []

        if best_ratio >= auto_accept_threshold and len(best_matches) == 1:
            anchor = best_matches[0]
            crosswalk.append(
                PlayerCrosswalkEntry(
                    player_code=anchor.player_code,
                    anchor_display_name=anchor.display_name,
                    matched_display_name=other_name,
                    role=anchor.role,
                    confidence=round(best_ratio, 4),
                    match_method="fuzzy_auto",
                    status="confirmed",
                )
            )
        else:
            best_anchor = best_matches[0] if len(best_matches) == 1 else None
            reason = (
                f"Below auto-accept threshold ({auto_accept_threshold})"
                if len(best_matches) <= 1
                else f"Ambiguous: {len(best_matches)} anchor players tie on best fuzzy match"
            )
            review_queue.append(
                PlayerReviewQueueEntry(
                    matched_display_name=other_name,
                    role=other_role,
                    best_candidate_player_code=best_anchor.player_code if best_anchor else None,
                    best_candidate_display_name=best_anchor.display_name if best_anchor else None,
                    confidence=round(best_ratio, 4),
                    reason=reason,
                )
            )

    return PlayerResolutionResult(crosswalk=crosswalk, review_queue=review_queue)
