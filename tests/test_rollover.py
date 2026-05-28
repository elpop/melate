from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.rollover import estimate_floor, FloorEstimateWarning


def test_estimate_floor_recovers_known_floor_with_clean_resets():
    floor = 30_000_000
    # 30 draws: accumulate, reset, accumulate, reset...
    awards = []
    current = floor
    for k in range(30):
        if k % 6 == 5:
            current = floor  # reset
        else:
            current += 5_000_000
        awards.append(current)
    s = pd.Series(awards)
    est = estimate_floor(s, eps=0.05)
    assert est == floor


def test_estimate_floor_warns_when_min_and_mode_disagree():
    """If the minimum is anomalous (one outlier), warn and prefer min."""
    awards = pd.Series([1] + [30_000_000] * 5 + [60_000_000] * 5 + [30_000_000] * 5)
    with pytest.warns(FloorEstimateWarning):
        est = estimate_floor(awards, eps=0.05)
    assert est == 1  # conservative: use min
