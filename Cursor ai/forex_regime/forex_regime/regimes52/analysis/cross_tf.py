"""
Cross–timeframe summaries: pick best strategy per (regime, tf), aggregate stability across TFs.

Not tied to MT5 — pass a long-form scorecard with column `tf_minutes`.
"""

from __future__ import annotations

import pandas as pd


def best_strategy_per_regime_tf(multi: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    """
    For each (regime_id, tf_minutes), keep the strategy row with highest `rank_score`
    among rows with `trades >= min_trades`.
    """
    need = {"regime_id", "tf_minutes", "rank_score", "trades"}
    miss = need - set(multi.columns)
    if miss:
        raise ValueError(f"multi scorecard missing columns: {miss}")
    m = multi[multi["trades"] >= int(min_trades)].copy()
    if m.empty:
        return pd.DataFrame()
    idx = m.groupby(["regime_id", "tf_minutes"], sort=False)["rank_score"].idxmax()
    return m.loc[idx].reset_index(drop=True)


def _most_common(s: pd.Series) -> str | None:
    s = s.dropna()
    if s.empty:
        return None
    vc = s.astype(str).value_counts()
    return str(vc.index[0])


def regime_cross_tf_summary(best_per_tf: pd.DataFrame) -> pd.DataFrame:
    """
    One row per regime: how strong the *winning* strategy is per TF, summarized across TFs.

    `dominant_winner_key` = strategy_key that won the argmax most often across TFs.
    """
    if best_per_tf.empty:
        return pd.DataFrame()
    agg = best_per_tf.groupby(["regime_id", "regime_name", "quadrant"], sort=False).agg(
        median_best_rank=("rank_score", "median"),
        mean_best_rank=("rank_score", "mean"),
        std_best_rank=("rank_score", "std"),
        n_tf=("tf_minutes", "count"),
        mean_wr2_of_winner=("wr_2r", "mean"),
        dominant_winner_key=("strategy_key", _most_common),
        dominant_winner_title=("strategy_title", _most_common),
    )
    return agg.reset_index().sort_values("median_best_rank", ascending=False)


def strategy_pairs_cross_tf(multi: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    """
    Rank (regime, strategy_key) pairs by robustness: median rank_score across TFs.

    Useful for “best regime + its strategy” when you want one named playbook that
    does not have to win every single timeframe.
    """
    need = {
        "regime_id",
        "regime_name",
        "quadrant",
        "strategy_key",
        "strategy_title",
        "tf_minutes",
        "rank_score",
        "trades",
        "wr_2r",
    }
    miss = need - set(multi.columns)
    if miss:
        raise ValueError(f"multi scorecard missing columns: {miss}")
    m = multi[multi["trades"] >= int(min_trades)].copy()
    if m.empty:
        return pd.DataFrame()
    g = (
        m.groupby(["regime_id", "regime_name", "quadrant", "strategy_key", "strategy_title"], sort=False)
        .agg(
            median_rank=("rank_score", "median"),
            mean_rank=("rank_score", "mean"),
            std_rank=("rank_score", "std"),
            n_tf=("tf_minutes", "nunique"),
            trades_sum=("trades", "sum"),
            median_wr2=("wr_2r", "median"),
        )
        .reset_index()
    )
    return g.sort_values(["median_rank", "n_tf"], ascending=[False, False])


def pivot_best_rank_heatmap(best_per_tf: pd.DataFrame) -> pd.DataFrame:
    """Rows regime_id, columns tf_minutes, values rank_score of per-TF winner."""
    if best_per_tf.empty:
        return pd.DataFrame()
    return best_per_tf.pivot_table(
        index="regime_id",
        columns="tf_minutes",
        values="rank_score",
        aggfunc="first",
    )


def tf_label(minutes: int) -> str:
    if minutes < 60:
        return f"M{minutes}"
    if minutes % 60 == 0:
        return f"H{minutes // 60}"
    return f"{minutes}m"
