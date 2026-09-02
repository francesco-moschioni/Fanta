"""Historical defence modifier -- UNRATIFIED (ADR-2026-080).

⚠️  The formula in this module is the **historical** defensive-modifier formula
transcribed in ``docs/SCORING_RULES.md`` (§"Componenti di formazione storiche"):

    "Modificatore difesa disponibile con almeno 4 difensori: da media 6,25 vale
     +1 e cresce di +1 per ogni 0,25; il testo cita 6 -> +0, 6,25 -> +1,
     6,5 -> +2."

Its exact operational form is an **open question** -- ``docs/OPEN_QUESTIONS.md``
§"Motore partita" lists as unresolved: which votes enter, how the goalkeeper is
handled, best-three defenders vs all, SV defenders, substitutions. It is NOT
approved configuration and is NOT written anywhere in ``config/``. The
"Formazione" tool exposes it only behind an explicit opt-in toggle, always with
:data:`MODIFIER_DISCLAIMER` shown next to it, purely so a user can compare
defence-heavy shapes -- never as a scoring guarantee.

Judgement calls made here, to be revisited by the ADR that eventually ratifies
this component:

* **All starting defenders + the goalkeeper** are averaged (not "best three").
  The doc is ambiguous ("migliori tre difensori o tutti"); averaging everyone
  who actually starts is the least surprising reading and matches how the tool
  already picks the XI.
* Input values are the players' ``sim_mean`` (simulated fantavoto). Historically
  the modifier keys off the *base vote*, not the bonus-inclusive fantavoto; we
  do not have a separate per-player base-vote distribution surfaced in the
  player table, so ``sim_mean`` is used as a documented proxy. This is one more
  reason the number is a rough comparison aid, not a prediction.
* Linear in the average (``(avg - 6.0) / 0.25``), clamped at 0 below 6.0, with
  no upper cap. The three worked points in the doc (6.0->0, 6.25->+1, 6.5->+2)
  lie exactly on this line.
"""

from __future__ import annotations

from collections.abc import Sequence

MODIFIER_DISCLAIMER = (
    "Modificatore difesa: formula STORICA non ratificata (docs/OPEN_QUESTIONS.md). "
    "Stima approssimata dalla media dei voti simulati di portiere + difensori "
    "titolari, solo per confrontare moduli con difese diverse. Non è una regola "
    "di punteggio approvata e non viene scritta in configurazione."
)

_BASELINE = 6.0
_STEP = 0.25
_MIN_DEFENDERS = 4  # doc: "disponibile con almeno 4 difensori"


def historical_defence_modifier(
    gk_and_def_sim_means: Sequence[float], *, n_defenders: int | None = None
) -> float:
    """Estimated historical defence modifier from starting GK + defender values.

    ``avg = mean(gk_and_def_sim_means)``; result ``= max(0, (avg - 6.0) / 0.25)``.
    Monotone non-decreasing in every input. Returns ``0.0`` for an empty
    sequence, and — when ``n_defenders`` is given — ``0.0`` for a shape with
    fewer than 4 defenders (the doc: "disponibile con almeno 4 difensori"), so
    the opt-in toggle genuinely rewards 4-5 defender shapes over a back-three.
    """
    if n_defenders is not None and n_defenders < _MIN_DEFENDERS:
        return 0.0
    values = [float(v) for v in gk_and_def_sim_means]
    if not values:
        return 0.0
    avg = sum(values) / len(values)
    return max(0.0, (avg - _BASELINE) / _STEP)


__all__ = ["historical_defence_modifier", "MODIFIER_DISCLAIMER"]
