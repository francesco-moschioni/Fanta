"""Coverage/missingness/drift metrics for a staged ingestion sample.

Per docs/ROADMAP.md M1 gate: every source audit must report coverage, missingness,
mapping confidence, and drift; no join may be silent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MissingnessReport:
    row_count: int
    missing_by_column: dict[str, int]
    missing_pct_by_column: dict[str, float]


def missingness_report(frame: pd.DataFrame, columns: list[str]) -> MissingnessReport:
    missing = {col: int(frame[col].isna().sum()) for col in columns}
    n = len(frame)
    pct = {col: (round(count / n, 4) if n else 1.0) for col, count in missing.items()}
    return MissingnessReport(row_count=n, missing_by_column=missing, missing_pct_by_column=pct)


@dataclass(frozen=True)
class CrossSourceMatchResult:
    total_candidates: int
    matched: int
    unmatched_sample: list[dict]

    @property
    def match_rate(self) -> float:
        return round(self.matched / self.total_candidates, 4) if self.total_candidates else 0.0


def cross_source_match_rate(
    results_frame: pd.DataFrame,
    fixtures_frame: pd.DataFrame,
    results_team_id_cols: tuple[str, str],
    fixtures_team_id_cols: tuple[str, str],
    date_tolerance_days: int = 1,
    unmatched_sample_size: int = 10,
) -> CrossSourceMatchResult:
    """Match football-data.co.uk results against OpenFootball fixtures by resolved
    team_id pair and a date window, as an independent cross-source consistency check
    (not a join used downstream — this is an audit-only comparison).
    """
    r_home_col, r_away_col = results_team_id_cols
    f_home_col, f_away_col = fixtures_team_id_cols

    fixtures = fixtures_frame.dropna(subset=[f_home_col, f_away_col]).copy()
    fixtures["date"] = pd.to_datetime(fixtures["date"])

    matched = 0
    unmatched: list[dict] = []
    total = 0

    for _, row in results_frame.dropna(subset=[r_home_col, r_away_col]).iterrows():
        total += 1
        date = pd.to_datetime(row["Date"])
        window = fixtures[
            (fixtures["date"] >= date - pd.Timedelta(days=date_tolerance_days))
            & (fixtures["date"] <= date + pd.Timedelta(days=date_tolerance_days))
        ]
        hit = window[
            (window[f_home_col] == row[r_home_col]) & (window[f_away_col] == row[r_away_col])
        ]
        if len(hit) > 0:
            matched += 1
        elif len(unmatched) < unmatched_sample_size:
            unmatched.append(
                {
                    "date": str(date.date()),
                    "home_team_id": row[r_home_col],
                    "away_team_id": row[r_away_col],
                }
            )

    return CrossSourceMatchResult(total_candidates=total, matched=matched, unmatched_sample=unmatched)
