"""Stage 7 (ADR-2026-079): availability feature + participation cap."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fantacalcio.features.availability import (
    apply_availability_to_participation,
    player_availability,
)
from fantacalcio.features.leakage import assert_available_before_decision
from fantacalcio.features.schema import validate_feature_frame
from fantacalcio.scoring.generative.participation import (
    PlayerSeasonParticipation,
    sample_appearance,
)

AS_OF = pd.Timestamp("2026-09-03")


def _anchors() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_code": [101, 102, 103, 104],
            "display_name": ["Rossi", "Bianchi", "Verdi", "Neri"],
            "role": ["D", "C", "A", "A"],
        }
    )


def _missing(rows) -> pd.DataFrame:
    cols = ["player_name", "role", "status", "reason", "expected_return", "report_time"]
    return pd.DataFrame(rows, columns=cols)


def test_suspended_player_is_zero():
    df = _missing([("Rossi", "D", "suspended", "cards", None, "2026-09-01")])
    frame, review = player_availability(df, as_of=AS_OF, anchor_players=_anchors())
    validate_feature_frame(frame)
    assert review == []
    row = frame[frame["entity_id"] == "101"].iloc[0]
    assert row["value"] == 0.0
    assert row["quality_tier"] == "B"


def test_out_returning_next_week_is_low_and_ramps():
    far = _missing([("Verdi", "A", "out", "acl", "2026-09-20", "2026-09-01")])
    near = _missing([("Verdi", "A", "out", "acl", "2026-09-05", "2026-09-01")])
    within = _missing([("Verdi", "A", "out", "acl", "2026-09-08", "2026-09-01")])

    p_far = player_availability(far, as_of=AS_OF, anchor_players=_anchors())[0]["value"].iloc[0]
    p_near = player_availability(near, as_of=AS_OF, anchor_players=_anchors())[0]["value"].iloc[0]
    p_within = player_availability(within, as_of=AS_OF, anchor_players=_anchors())[0]["value"].iloc[0]

    assert p_far == pytest.approx(0.05)  # return after the 7d horizon
    assert p_near > p_within > p_far  # ramps up as the return date approaches
    assert p_near <= 1.0


def test_doubtful_decays_toward_base_rate_as_report_ages():
    fresh = _missing([("Bianchi", "C", "doubtful", "knock", None, "2026-09-02")])
    stale = _missing([("Bianchi", "C", "doubtful", "knock", None, "2026-08-13")])

    p_fresh = player_availability(fresh, as_of=AS_OF, anchor_players=_anchors())[0]["value"].iloc[0]
    p_stale = player_availability(stale, as_of=AS_OF, anchor_players=_anchors())[0]["value"].iloc[0]

    assert p_fresh == pytest.approx(0.5, abs=0.05)
    # base rate default 0.75 -> stale report drifts up toward it
    assert p_stale > p_fresh
    assert p_stale < 0.75


def test_player_with_no_row_is_absent_from_frame():
    df = _missing([("Rossi", "D", "out", "x", None, "2026-09-01")])
    frame, _ = player_availability(df, as_of=AS_OF, anchor_players=_anchors())
    assert set(frame["entity_id"]) == {"101"}
    assert "102" not in set(frame["entity_id"])  # caller falls back to season rate


def test_ambiguous_name_goes_to_review_queue_never_a_code():
    anchors = _anchors()
    anchors.loc[len(anchors)] = [201, "Esposito", "A"]
    anchors.loc[len(anchors)] = [202, "Esposito", "A"]
    df = _missing([("Esposito", "A", "out", "x", None, "2026-09-01")])
    frame, review = player_availability(df, as_of=AS_OF, anchor_players=anchors)
    codes = set(frame["entity_id"].astype(str)) if not frame.empty else set()
    assert "201" not in codes and "202" not in codes
    assert any(e.matched_display_name == "Esposito" for e in review)


def test_availability_report_time_precedes_matchday_decision_time():
    df = _missing([("Rossi", "D", "doubtful", "x", None, "2026-09-01T10:00:00")])
    frame, _ = player_availability(df, as_of=AS_OF, anchor_players=_anchors())
    assert_available_before_decision(frame, AS_OF)
    assert (frame["available_time"] < AS_OF).all()


# --------------------------------------------------------------------------- #
# apply_availability_to_participation                                         #
# --------------------------------------------------------------------------- #
def test_apply_none_returns_input_unchanged():
    psp = PlayerSeasonParticipation(0.8, start_share=0.9)
    out = apply_availability_to_participation(psp, None)
    assert out is psp  # bit-comparable degradation contract


def test_apply_zero_kills_next_matchday_start_prob_only():
    base = PlayerSeasonParticipation(0.85, start_share=0.9)
    capped = apply_availability_to_participation(base, 0.0)

    rng = np.random.default_rng(0)
    md1 = np.concatenate([sample_appearance(capped, "A", 1, rng) for _ in range(400)])
    assert md1.sum() == 0  # never on the pitch next matchday

    # matchday 5 uses the untouched season-rate object
    rng2 = np.random.default_rng(0)
    later = np.concatenate([sample_appearance(base, "A", 1, rng2) for _ in range(400)])
    assert (later == 2).mean() > 0.5  # unaffected: still a regular starter


def test_apply_partial_caps_between_zero_and_one():
    base = PlayerSeasonParticipation(0.9, start_share=1.0)
    capped = apply_availability_to_participation(base, 0.4)
    rng = np.random.default_rng(1)
    draws = np.concatenate([sample_appearance(capped, "A", 1, rng) for _ in range(4000)])
    play_rate = (draws > 0).mean()
    assert 0.3 < play_rate < 0.5
