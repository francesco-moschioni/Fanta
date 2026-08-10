#!/usr/bin/env python3
"""Data-quality audit over all staged Voti_Fantacalcio CSVs.

Reads data/staged/fantacalcio_voti_manual/*.csv (produced by
scripts/ingest_voti_folder.py) and reports coverage, missingness, cross-panel
agreement, and identity-stability checks, per the audit requirements in
docs/SOURCE_REGISTER.md and docs/DATA_AND_MODELING.md.

Output stays under data/staged/ (gitignored): this is derived from a source whose
own licence text restricts it to personal use, so nothing built from its content
belongs in git, aggregate or not.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

STAGED_DIR = Path("data/staged/fantacalcio_voti_manual")
REPORT_PATH = STAGED_DIR / "_quality_report.md"

EXPECTED_ROLES = {"P", "D", "C", "A", "ALL"}
EXPECTED_MATCHDAYS_PER_SEASON = 38


def load_all() -> pd.DataFrame:
    files = sorted(STAGED_DIR.glob("voti_*.csv"))
    if not files:
        raise SystemExit(f"No staged voti CSVs found in {STAGED_DIR}")
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    return df


def main() -> None:
    df = load_all()
    lines = ["# Voti Fantacalcio — quality audit", ""]
    lines.append(f"Loaded {len(df)} rows from {df['source_file_hash'].nunique()} files "
                 f"across {df['season_label'].nunique()} seasons.")
    lines.append("")

    # --- Coverage: matchdays per season -------------------------------------------------
    lines.append("## Coverage per season")
    lines.append("")
    lines.append("| Season | Matchdays present | Missing matchdays | Rows |")
    lines.append("|---|---:|---|---:|")
    for season, g in df.groupby("season_label"):
        present = sorted(g["matchday"].unique())
        missing = sorted(set(range(1, EXPECTED_MATCHDAYS_PER_SEASON + 1)) - set(present))
        lines.append(f"| {season} | {len(present)}/{EXPECTED_MATCHDAYS_PER_SEASON} | "
                     f"{missing if missing else '—'} | {len(g)} |")
    lines.append("")

    # --- Missingness on key fields --------------------------------------------------------
    lines.append("## Missingness on key fields (excluding legitimate no-vote rows)")
    lines.append("")
    rated = df[~df["voto_no_vote"]]
    lines.append("| Field | Missing | Missing % (of rated rows) |")
    lines.append("|---|---:|---:|")
    for col in ["player_code", "role", "display_name", "voto"]:
        missing = rated[col].isna().sum()
        lines.append(f"| {col} | {missing} | {missing / len(rated):.3%} |")
    lines.append("")
    no_vote_rate = df["voto_no_vote"].mean()
    provisional_rate = df["voto_provisional"].mean()
    lines.append(f"`voto_no_vote` rate overall: {no_vote_rate:.2%}. "
                 f"`voto_provisional` rate overall: {provisional_rate:.2%}.")
    lines.append("")

    # --- Role sanity ------------------------------------------------------------------------
    lines.append("## Role values")
    lines.append("")
    role_counts = df["role"].value_counts(dropna=False)
    unexpected_roles = set(role_counts.index) - EXPECTED_ROLES
    lines.append("| Role | Count |")
    lines.append("|---|---:|")
    for role, count in role_counts.items():
        flag = " ⚠️ unexpected" if role in unexpected_roles else ""
        lines.append(f"| {role}{flag} | {count} |")
    lines.append("")

    # --- Voto distribution sanity -----------------------------------------------------------
    lines.append("## Voto distribution (rated rows only)")
    lines.append("")
    voto = rated["voto"].dropna()
    lines.append(f"min={voto.min()}, max={voto.max()}, mean={voto.mean():.2f}, "
                 f"median={voto.median()}, std={voto.std():.2f}")
    out_of_range = voto[(voto < 0) | (voto > 12)]
    lines.append(f"Values outside a plausible [0, 12] range: {len(out_of_range)} "
                 f"({sorted(out_of_range.unique().tolist())[:20] if len(out_of_range) else 'none'})")
    lines.append("")

    # --- Duplicate rows within a (file, panel) ----------------------------------------------
    lines.append("## Duplicate player rows within the same file+panel")
    lines.append("")
    dup_key = ["source_file_hash", "panel", "player_code"]
    dup_counts = df.groupby(dup_key).size()
    dups = dup_counts[dup_counts > 1]
    lines.append(f"{len(dups)} (file, panel, player_code) combinations appear more than once.")
    if len(dups):
        lines.append("")
        lines.append("Sample:")
        lines.append("")
        lines.append("| source_file_hash | panel | player_code | count |")
        lines.append("|---|---|---:|---:|")
        for (fh, panel, code), count in dups.head(10).items():
            lines.append(f"| {fh[:12]}... | {panel} | {code} | {count} |")
    lines.append("")

    # --- Identity stability: does player_code ever map to >1 display_name? ------------------
    lines.append("## Identity stability: player_code -> display_name")
    lines.append("")
    players = df[df["role"] != "ALL"].dropna(subset=["player_code"])
    name_counts = players.groupby("player_code")["display_name"].nunique()
    unstable = name_counts[name_counts > 1]
    lines.append(f"{len(unstable)} player_code values map to more than one display_name "
                 f"across the dataset (expected from real transfers/name changes; a review "
                 f"candidate for the entity resolver, not necessarily an error).")
    if len(unstable):
        lines.append("")
        lines.append("Sample (player_code -> distinct names seen):")
        lines.append("")
        lines.append("| player_code | names |")
        lines.append("|---:|---|")
        for code in unstable.index[:15]:
            names = sorted(players[players["player_code"] == code]["display_name"].unique())
            lines.append(f"| {code} | {', '.join(names)} |")
    lines.append("")

    # --- Cross-panel agreement ---------------------------------------------------------------
    lines.append("## Cross-panel voto agreement (Fantacalcio vs Statistico vs Italia)")
    lines.append("")
    pivot = rated.pivot_table(
        index=["season_label", "matchday", "player_code"], columns="panel", values="voto"
    )
    complete = pivot.dropna()
    if len(complete):
        spread = complete.max(axis=1) - complete.min(axis=1)
        lines.append(f"{len(complete)} (season, matchday, player) triples rated by all three panels.")
        lines.append(f"Max-min spread across panels: mean={spread.mean():.3f}, "
                     f"median={spread.median():.2f}, max={spread.max():.2f}.")
        lines.append(f"Exact agreement (spread=0): {(spread == 0).mean():.2%}. "
                     f"Spread > 1.0 point: {(spread > 1.0).mean():.2%}.")
    else:
        lines.append("No rows with all three panels present for the same player/matchday.")
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
