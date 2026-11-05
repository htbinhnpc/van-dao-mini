"""Arena opponent selection (pure, no I/O).

Rules come from the public game client (see game_bundle_knowledge.md, section 3 and
the arena component of main-Bmv0z3VX.js); they are client-side observations, not
server guarantees:

* ``GET /api/arena?pick=N`` -> ``{arena: {rating, bracket, rankedLeft, opponents[], history[]}}``.
  ``pick`` is a refresh counter: each new value draws 5 other opponents from the 20
  closest by rating.
* ``POST /api/cmd/arena.fight`` with ``{defenderId, ranked}``; ranked fights need the
  same bracket and the daily limit (``rankedLeft`` of 10); the character needs level 10.
* The fight is simulated by the server, so ``power`` is only an indicator. Mini therefore
  demands a configurable power lead (default 5,000) and avoids re-fighting a loss.
"""

from __future__ import annotations

import math
from typing import Any

ARENA_MIN_LEVEL = 10
ARENA_DAILY_RANKED = 10
DEFAULT_POWER_EDGE = 5_000
LOSS_AVOID_MS = 3_600_000


def _number(value: Any) -> float | None:
    """Parse a finite number; booleans, NaN and garbage are not evidence."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def my_power(state: dict) -> float | None:
    """Own combat power as reported by the server (``state.power``); None if unknown."""
    power = _number((state or {}).get("power"))
    return power if power is not None and power > 0 else None


def pick_opponent(
    arena: dict,
    power: float,
    *,
    min_edge: float = DEFAULT_POWER_EDGE,
    avoid: dict[str, Any] | None = None,
    now_ms: float = 0,
) -> dict | None:
    """Return the safest ranked opponent whose power is at least ``min_edge`` below ours.

    The largest power margin wins (the goal is to win); higher rating breaks ties
    because ranked wins on stronger rating are worth at least as much. Opponents of
    another bracket (``sameBracket`` is not True), without an id or a numeric power,
    or lost against recently are skipped.
    """
    edge = max(0.0, _number(min_edge) or 0.0)
    avoid = avoid or {}
    best: tuple[float, float, dict] | None = None
    for opponent in (arena or {}).get("opponents") or []:
        if not isinstance(opponent, dict):
            continue
        defender_id = opponent.get("characterId")
        their = _number(opponent.get("power"))
        if not isinstance(defender_id, str) or not defender_id or their is None:
            continue
        if opponent.get("sameBracket") is not True:
            continue
        lost_at = _number(avoid.get(defender_id))
        if now_ms and lost_at is not None and now_ms - lost_at < LOSS_AVOID_MS:
            continue
        margin = power - their
        if margin < edge:
            continue
        key = (margin, _number(opponent.get("rating")) or 0.0)
        if best is None or key > best[:2]:
            best = (*key, opponent)
    return best[2] if best else None


def ranked_left(arena: dict) -> int:
    left = _number((arena or {}).get("rankedLeft"))
    return int(left) if left is not None and left > 0 else 0


def last_fight_lost(arena: dict, defender_id: str) -> bool:
    """True when the newest history entry is our attack on ``defender_id`` that we lost."""
    for entry in (arena or {}).get("history") or []:
        if isinstance(entry, dict):
            return entry.get("attacker") is True and entry.get("opponentId") == defender_id and entry.get("won") is False
    return False
