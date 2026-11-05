"""Hunting-spot selection that maximises cultivation (pure, no I/O).

Source data: ``data/meta.json`` spots (``expPerCycle``, ``reqLevel``). The game only pays
the per-cycle experience when the fight is won (``state.activity.win``), so the best spot
is the highest-yield one we can actually beat -- not the one whose recommended level
matches ours. The client cannot tell us the win chance, so Mini probes upward and learns:

* take the unlocked spot with the largest ``expPerCycle`` (``reqLevel`` is the only hard gate);
* when the game reports a loss there, remember it and use the next-best spot;
* retry the lost spot only after a cool-down, or earlier when our power grew enough,
  so a lucky/unlucky single result does not lock us out forever or cause ping-pong.
"""

from __future__ import annotations

import math
from typing import Any

LOSS_RETRY_MS = 30 * 60_000
POWER_GAIN_RETRY = 1.10  # retry a lost spot early once power is 10% above the loss
# Non-regular spot families share exp values with the regular ones but have other rules.
_EXCLUDED_PREFIXES = ("x2_", "spot_puppet_")


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def candidate_spots(spots: dict[str, dict], unlocked_regions: set, level: float) -> list[dict]:
    """Regular spots we may enter: region unlocked, level met, and yielding experience."""
    return [
        s for s in spots.values()
        if s.get("regionId") in unlocked_regions
        and _num(s.get("reqLevel")) <= level
        and _num(s.get("expPerCycle")) > 0
        and not str(s.get("id", "")).startswith(_EXCLUDED_PREFIXES)
    ]


def is_blocked(loss: dict | None, *, now_ms: float, power: float | None) -> bool:
    """True while a remembered loss should still keep us away from that spot."""
    if not isinstance(loss, dict):
        return False
    lost_at = _num(loss.get("at"), -math.inf)
    if lost_at == -math.inf or now_ms - lost_at >= LOSS_RETRY_MS:
        return False
    lost_power = _num(loss.get("power"))
    return not (power and lost_power > 0 and power >= lost_power * POWER_GAIN_RETRY)


def rank_spots(
    spots: dict[str, dict],
    unlocked_regions: set,
    level: float,
    *,
    losses: dict[str, Any] | None = None,
    now_ms: float = 0,
    power: float | None = None,
    avoid_losses: bool = True,
) -> list[dict]:
    """Spots ordered best-first: by experience per cycle, skipping recently lost ones."""
    losses = losses or {}
    ranked = sorted(
        candidate_spots(spots, unlocked_regions, level),
        # Larger exp first; the tie-break keeps the choice stable (higher required level, then id).
        key=lambda s: (-_num(s.get("expPerCycle")), -_num(s.get("reqLevel")), str(s.get("id"))),
    )
    if not avoid_losses:
        return ranked
    return [s for s in ranked if not is_blocked(losses.get(s.get("id")), now_ms=now_ms, power=power)]


def update_losses(losses: dict[str, Any] | None, activity: dict | None, *, now_ms: float,
                  power: float | None) -> dict[str, Any]:
    """Record/clear the result the game reported for the spot we are farming right now."""
    losses = {k: v for k, v in (losses or {}).items() if isinstance(v, dict)}
    activity = activity or {}
    spot_id = activity.get("targetId")
    if activity.get("type") == "farm" and isinstance(spot_id, str):
        if activity.get("win") is False:
            losses[spot_id] = {"at": now_ms, "power": power or 0}
        elif activity.get("win") is True:
            losses.pop(spot_id, None)
    # Forget entries that can no longer block anything.
    return {k: v for k, v in losses.items() if now_ms - _num(v.get("at"), -math.inf) < LOSS_RETRY_MS}
