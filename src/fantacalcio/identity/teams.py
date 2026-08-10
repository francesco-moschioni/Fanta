"""Team entity resolution: crosswalk source-specific names to a canonical team_id.

Per docs/DATA_AND_MODELING.md: never join on display name alone, and ambiguous or
low-confidence matches go to a manual review queue rather than being force-matched
or silently dropped. This module only ever *proposes* a crosswalk; nothing here is
authoritative until reviewed (or auto-accepted above a high confidence bar).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

AUTO_ACCEPT_THRESHOLD = 0.90

# Tokens that vary across sources for the same club (legal-form suffixes/prefixes)
# and carry no identifying information once the base name is known.
_NOISE_TOKENS = {
    "fc", "cfc", "ac", "ssc", "us", "u.s.", "ussd", "ssd", "calcio", "spa", "s.p.a.",
    "football", "club", "1907", "1909", "1913",
}


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation, drop legal-form noise tokens."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = re.sub(r"[^a-zA-Z0-9\s]", " ", ascii_only).lower()
    tokens = [t for t in ascii_only.split() if t not in _NOISE_TOKENS]
    return " ".join(tokens).strip()


def _slugify(name: str) -> str:
    norm = normalize_name(name)
    return re.sub(r"\s+", "-", norm) or "unknown"


@dataclass(frozen=True)
class CrosswalkEntry:
    team_id: str
    canonical_source_id: str
    canonical_name: str
    matched_source_id: str
    matched_name: str
    confidence: float
    match_method: str  # "exact_normalized" | "fuzzy_auto"
    status: str  # "confirmed"


@dataclass(frozen=True)
class ReviewQueueEntry:
    matched_source_id: str
    matched_name: str
    best_candidate_team_id: str | None
    best_candidate_name: str | None
    confidence: float
    reason: str


@dataclass(frozen=True)
class ResolutionResult:
    crosswalk: list[CrosswalkEntry]
    review_queue: list[ReviewQueueEntry]


def resolve_against_anchor(
    anchor_names: list[str],
    anchor_source_id: str,
    other_names: list[str],
    other_source_id: str,
    auto_accept_threshold: float = AUTO_ACCEPT_THRESHOLD,
) -> ResolutionResult:
    """Resolve `other_names` (from `other_source_id`) against a canonical anchor list.

    The anchor list itself defines the canonical team_id space (one entry per unique
    anchor name, slugified). Every other-source name is matched by exact normalized
    match first, then by best fuzzy ratio; anything below `auto_accept_threshold`
    goes to the review queue instead of being auto-committed.
    """
    anchor_unique = sorted(set(anchor_names))
    anchor_index: dict[str, tuple[str, str]] = {}  # normalized -> (team_id, canonical_name)
    for name in anchor_unique:
        norm = normalize_name(name)
        team_id = _slugify(name)
        if norm in anchor_index and anchor_index[norm][1] != name:
            # team_id is derived from `norm`, so it would trivially match here too;
            # the real signal is two *different* raw anchor names collapsing to the
            # same normalized form, which could silently merge two distinct clubs.
            raise ValueError(
                f"Anchor names {name!r} and {anchor_index[norm][1]!r} collide after "
                f"normalization to {norm!r}; anchor list must be disambiguated before resolution"
            )
        anchor_index[norm] = (team_id, name)

    crosswalk: list[CrosswalkEntry] = []
    review_queue: list[ReviewQueueEntry] = []

    for other_name in sorted(set(other_names)):
        other_norm = normalize_name(other_name)

        if other_norm in anchor_index:
            team_id, canonical_name = anchor_index[other_norm]
            crosswalk.append(
                CrosswalkEntry(
                    team_id=team_id,
                    canonical_source_id=anchor_source_id,
                    canonical_name=canonical_name,
                    matched_source_id=other_source_id,
                    matched_name=other_name,
                    confidence=1.0,
                    match_method="exact_normalized",
                    status="confirmed",
                )
            )
            continue

        best_norm, best_ratio = None, 0.0
        for anchor_norm in anchor_index:
            ratio = difflib.SequenceMatcher(None, other_norm, anchor_norm).ratio()
            if ratio > best_ratio:
                best_norm, best_ratio = anchor_norm, ratio

        best_team_id, best_name = (None, None)
        if best_norm is not None:
            best_team_id, best_name = anchor_index[best_norm]

        if best_ratio >= auto_accept_threshold:
            crosswalk.append(
                CrosswalkEntry(
                    team_id=best_team_id,
                    canonical_source_id=anchor_source_id,
                    canonical_name=best_name,
                    matched_source_id=other_source_id,
                    matched_name=other_name,
                    confidence=round(best_ratio, 4),
                    match_method="fuzzy_auto",
                    status="confirmed",
                )
            )
        else:
            review_queue.append(
                ReviewQueueEntry(
                    matched_source_id=other_source_id,
                    matched_name=other_name,
                    best_candidate_team_id=best_team_id,
                    best_candidate_name=best_name,
                    confidence=round(best_ratio, 4),
                    reason=f"Below auto-accept threshold ({auto_accept_threshold})",
                )
            )

    return ResolutionResult(crosswalk=crosswalk, review_queue=review_queue)
