"""Range validators for biometric readings.

Each metric has a plausible-physiology range. Values outside the range
are *dropped* (counted as skipped), not rejected outright, so a single
bad row from a noisy scale doesn't poison the whole CSV upload.

Ranges are intentionally generous so legitimate outliers (athletes,
post-surgery patients) are not silently discarded.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

RANGES: dict[str, tuple[float, float]] = {
    "weight_kg": (30.0, 200.0),
    "body_fat_pct": (3.0, 70.0),
    "bmi": (10.0, 60.0),
    "resting_hr": (30.0, 120.0),
    "total_minutes": (0.0, 1440.0),
    "deep_minutes": (0.0, 1440.0),
    "rem_minutes": (0.0, 1440.0),
    "count": (0.0, 100_000.0),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(value: float | int | None, name: str) -> bool:
    """Return True iff `value` is inside the named range.

    `None` is treated as *missing*, not invalid: callers should skip
    the field rather than report it as out-of-range.
    """
    if value is None:
        return True  # missing, not out-of-range
    if name not in RANGES:
        raise KeyError(f"Unknown range key: {name!r}")
    lo, hi = RANGES[name]
    return lo <= float(value) <= hi


def reject_out_of_range(rows: list[dict]) -> list[dict]:
    """Filter rows that contain out-of-range values for known metrics.

    A row is dropped if *any* of its recognised fields is non-None and
    fails `validate`. Rows with no recognised fields pass through.
    """
    cleaned: list[dict] = []
    for row in rows:
        keep = True
        for key in RANGES:
            if key in row and row[key] is not None and not validate(row[key], key):
                keep = False
                break
        if keep:
            cleaned.append(row)
    return cleaned