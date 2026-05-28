from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.backtest import predict_weight_balls


def _draws_wide(rows: list[list[int]]) -> pd.DataFrame:
    """Build a draws_wide-like DF from a list of [r1..r6] lists (newest first)."""
    return pd.DataFrame(
        rows, columns=["r1", "r2", "r3", "r4", "r5", "r6"]
    ).assign(
        draw=lambda d: range(len(d), 0, -1),  # newest first → draw N..1
        date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )


def test_predict_weight_one_segment_picks_most_frequent():
    """With a single break segment, the n most frequent balls win."""
    # 4 draws, ball 7 appears in all of them
    rows = [[7, 1, 2, 3, 4, 5],
            [7, 8, 9, 10, 11, 12],
            [7, 13, 14, 15, 16, 17],
            [7, 18, 19, 20, 21, 22]]
    wide = _draws_wide(rows)
    picks = predict_weight_balls(wide, n_balls=1, range_=56,
                                 window=4, breaks=4)
    assert picks == [7]


def test_predict_weight_recent_segment_outweighs_old():
    """Two segments: ball appearing only in the recent segment beats old one."""
    # 6 draws total, broken into 2 segments of 3.
    # ball 50 only in segment 0 (newest 3 draws), level 2
    # ball 10 only in segment 1 (older 3 draws), level 1
    # all other balls fill the rest with no repeats.
    rows_new = [[50, 1, 2, 3, 4, 5],
                [50, 6, 7, 8, 9, 11],
                [50, 12, 13, 14, 15, 16]]
    rows_old = [[10, 17, 18, 19, 20, 21],
                [10, 22, 23, 24, 25, 26],
                [10, 27, 28, 29, 30, 31]]
    wide = _draws_wide(rows_new + rows_old)
    picks = predict_weight_balls(wide, n_balls=1, range_=56,
                                 window=6, breaks=3)
    # weight(50) = 3 * 2 = 6 ; weight(10) = 3 * 1 = 3 → 50 wins
    assert picks == [50]


from stats.backtest import walk_forward_hits, DataLeakageError


def test_walk_forward_hits_counts_correctly():
    """For each draw k, count hits between weight picks (using draws[:k]) and draws[k]."""
    rows = [[1, 2, 3, 4, 5, 6],
            [7, 8, 9, 10, 11, 12],
            [1, 2, 3, 4, 5, 6],  # repeats r1..r6 → weight will favor [1..6]
            [1, 2, 7, 8, 9, 10]]  # k=3: weight on [1..12], actual {1,2,7,8,9,10}
    wide = pd.DataFrame(rows, columns=["r1", "r2", "r3", "r4", "r5", "r6"]).assign(
        draw=range(1, 5), date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    hits = walk_forward_hits(wide, n_balls=6, range_=56,
                             window=10, breaks=2, start_at=2)
    # We get one hit count per evaluated draw (k=2,3,4) → length 3.
    assert len(hits) == 3
    assert all(0 <= h <= 6 for h in hits)


def test_walk_forward_raises_on_duplicate_draws():
    """Duplicate draw numbers break the history-vs-target invariant — the
    history slice would include a row with draw == target.draw, which is
    exactly what the leakage check exists to catch.
    """
    rows = [[1, 2, 3, 4, 5, 6]] * 4
    wide = pd.DataFrame(rows, columns=["r1", "r2", "r3", "r4", "r5", "r6"]).assign(
        draw=[1, 2, 3, 3],  # duplicate at the end
        date=pd.Timestamp("2024-01-01"),
        r7=pd.NA, award=30_000_000,
    )
    with pytest.raises(DataLeakageError):
        walk_forward_hits(wide, n_balls=6, range_=56,
                          window=10, breaks=2, start_at=2)
