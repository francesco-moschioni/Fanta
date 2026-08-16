"""Curated official admin list: resolves the staged Markdown admin list into three
separate, honestly-labeled objects, never a single silently-merged table.

Per CLAUDE.md ("l'admin list ufficiale e il ranking del modello sono oggetti
separati", `unknown`/`provisional`/`official` states) and the raw/staged/curated
layering in docs/DATA_AND_MODELING.md, this is the `curated` step: it takes the
`staged` frame from `fantacalcio.ingest.admin_list_markdown` and the resolution
from `fantacalcio.identity.player_name_resolver` / `fantacalcio.identity.teams`,
and produces:

- `resolved_players`: rows with a confirmed `player_code`, list_state="official".
- `new_players`: rows confirmed by the user (2026-08-15, ADR-2026-044 follow-up)
  to be real players missing from the 2026/27 Quotazioni export (not yet quoted
  admin-side) -- kept with `player_code=None` rather than a fabricated ID, so
  nothing downstream can accidentally join them to the wrong player.
- `goalkeeper_blocks`: Lista 1's per-club goalkeeper-block quotation (confirmed by
  the user: those rows are club names, not individual keepers -- see
  config/auction_rules.v1.yaml's `goalkeeper_block` roster rule and
  docs/AUCTION_RULES.md's G1 pool), resolved against team identity, never against
  `player_code`.

Nothing here overwrites the model's own ranking (`_m3_replacement_values.csv` /
the `players` DuckDB table) -- this is a strictly additive, separate object.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fantacalcio.identity.player_name_resolver import AnchorPlayer, resolve_against_anchor
from fantacalcio.identity.teams import normalize_name
from fantacalcio.ingest.admin_list_markdown import StagedAdminList

LIST_STATE_OFFICIAL = "official"

# Players the user confirmed (2026-08-15) are real but not yet in the 2026/27
# Quotazioni export -- transfers/signings too recent for that file. Confirmed
# per-name, not inferred, per CLAUDE.md's ban on joining by display name alone:
# these are deliberately kept unresolved to any player_code.
CONFIRMED_NEW_PLAYERS = frozenset(
    {
        "Molina N.",
        "Obrador",
        "Schmid",
        "Spence",
    }
)

# These 5 were originally miscategorized as "new" by the automatic resolver,
# but ARE already in the 2026/27 Quotazioni anchor -- verified manually
# 2026-08-16 (ADR-2026-051) by cross-checking the anchor CSV directly plus
# independent web sources confirming the same person/club. Two different
# failure modes, both legitimate for the automatic resolver to have rejected:
#   - Isaksen / Rodriguez Je.: the admin list classifies them as "A"
#     (attaccante), the anchor Quotazioni classifies them as "C" (centrocampista,
#     classic wide-role code) -- the resolver's same-role constraint correctly
#     refuses to guess across a role disagreement between two independent
#     sources; here it's resolved by a human-equivalent check, not loosened
#     for every future case.
#   - Sucic / Chalobah / Jimenez: same role on both sides, but the anchor name
#     carries a disambiguating initial ("Sucic P.", "Chalobah T.", "Jimenez A.")
#     that pushes the fuzzy ratio just under the 0.90 auto-accept threshold
#     (0.8889 / 0.875) -- a near-miss, not a wrong guess.
# (display_name in the admin list, role in the admin list) -> real player_code.
MANUAL_VERIFIED_CROSSWALK: dict[tuple[str, str], int] = {
    ("Isaksen", "A"): 6398,
    ("Rodriguez Je.", "A"): 7129,
    ("Sucic", "C"): 7070,
    ("Chalobah", "D"): 5641,
    ("Jimenez", "D"): 6531,
}


@dataclass(frozen=True)
class CuratedAdminList:
    resolved_players: pd.DataFrame
    new_players: pd.DataFrame
    review_queue: pd.DataFrame
    goalkeeper_blocks: pd.DataFrame
    unmatched_teams: pd.DataFrame
    source_file_sha256: str
    as_of: str


def build_curated_admin_list(
    staged: StagedAdminList,
    anchor_players_df: pd.DataFrame,
    team_names: list[str],
) -> CuratedAdminList:
    """`anchor_players_df` needs `player_code`, `display_name`, `role`, `team_name`
    (the 2026/27 Quotazioni staged CSV). `team_names` is the canonical team-name
    list from the same source, used as the identity anchor for goalkeeper blocks."""
    frame = staged.frame

    players = frame[frame["entity_type"] == "player"].copy()
    anchors = [
        AnchorPlayer(int(r.player_code), r.display_name, r.role, r.team_name)
        for r in anchor_players_df.itertuples()
    ]
    pairs = list(zip(players["display_name"], players["role"]))
    result = resolve_against_anchor(anchors, pairs)

    crosswalk_by_name_role = {
        (e.matched_display_name, e.role): e.player_code for e in result.crosswalk
    }
    players["player_code"] = [
        crosswalk_by_name_role.get((row.display_name, row.role))
        or MANUAL_VERIFIED_CROSSWALK.get((row.display_name, row.role))
        for row in players.itertuples()
    ]

    resolved_mask = players["player_code"].notna()
    resolved_players = players[resolved_mask].copy()
    resolved_players["player_code"] = resolved_players["player_code"].astype(int)
    resolved_players["list_state"] = LIST_STATE_OFFICIAL

    unresolved = players[~resolved_mask].copy()
    confirmed_new_mask = unresolved["display_name"].isin(CONFIRMED_NEW_PLAYERS)
    new_players = unresolved[confirmed_new_mask].drop(columns=["player_code"]).copy()
    new_players["list_state"] = LIST_STATE_OFFICIAL
    new_players["identity_status"] = "new_player_pending_code"

    still_unreviewed = unresolved[~confirmed_new_mask]
    review_queue = pd.DataFrame(
        [
            {
                "display_name": e.matched_display_name,
                "role": e.role,
                "best_candidate_player_code": e.best_candidate_player_code,
                "best_candidate_display_name": e.best_candidate_display_name,
                "confidence": e.confidence,
                "reason": e.reason,
            }
            for e in result.review_queue
            if e.matched_display_name not in CONFIRMED_NEW_PLAYERS
            and (e.matched_display_name, e.role) not in MANUAL_VERIFIED_CROSSWALK
        ]
    )
    if len(review_queue) != len(still_unreviewed):
        raise ValueError(
            "Internal inconsistency: unresolved-minus-confirmed-new count "
            f"({len(still_unreviewed)}) doesn't match the resolver's review queue "
            f"minus confirmed-new ({len(review_queue)})."
        )

    team_blocks = frame[frame["entity_type"] == "team"].copy()
    team_index = {normalize_name(name): name for name in team_names}
    team_blocks["team_name_canonical"] = team_blocks["display_name"].map(
        lambda n: team_index.get(normalize_name(n))
    )
    matched_mask = team_blocks["team_name_canonical"].notna()
    goalkeeper_blocks = team_blocks[matched_mask].copy()
    goalkeeper_blocks["list_state"] = LIST_STATE_OFFICIAL
    unmatched_teams = team_blocks[~matched_mask].copy()

    return CuratedAdminList(
        resolved_players=resolved_players.reset_index(drop=True),
        new_players=new_players.reset_index(drop=True),
        review_queue=review_queue.reset_index(drop=True),
        goalkeeper_blocks=goalkeeper_blocks.reset_index(drop=True),
        unmatched_teams=unmatched_teams.reset_index(drop=True),
        source_file_sha256=staged.file_sha256,
        as_of=datetime.now(timezone.utc).isoformat(),
    )


def write_curated_csvs(curated: CuratedAdminList, curated_root: Path = Path("data/curated")) -> dict[str, Path]:
    out_dir = curated_root / "admin_list_2026_27"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {}
    for name, df in (
        ("resolved_players", curated.resolved_players),
        ("new_players", curated.new_players),
        ("review_queue", curated.review_queue),
        ("goalkeeper_blocks", curated.goalkeeper_blocks),
        ("unmatched_teams", curated.unmatched_teams),
    ):
        out_path = out_dir / f"{name}.csv"
        df.to_csv(out_path, index=False)
        paths[name] = out_path

    meta_path = out_dir / "_meta.csv"
    pd.DataFrame(
        [{"source_file_sha256": curated.source_file_sha256, "as_of": curated.as_of}]
    ).to_csv(meta_path, index=False)
    paths["_meta"] = meta_path

    return paths
