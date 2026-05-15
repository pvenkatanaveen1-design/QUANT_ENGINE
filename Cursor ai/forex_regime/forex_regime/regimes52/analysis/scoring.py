"""Composite scores for regime × strategy rows (kept free of matplotlib / PDF deps)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_rank_columns(tbl: pd.DataFrame) -> pd.DataFrame:
    """
    Same blend as `regime_pdf.enrich_strategy_table`: MFE win-rate mix × small-sample taper.

    Expects columns: wr_1r..wr_4r, trades.
    """
    out = tbl.copy()
    out["score_wr_blend"] = (
        0.20 * out["wr_1r"]
        + 0.35 * out["wr_2r"]
        + 0.30 * out["wr_3r"]
        + 0.15 * out["wr_4r"]
    )
    out["sample_factor"] = np.where(out["trades"] < 8, 0.82, 1.0)
    out["rank_score"] = (out["score_wr_blend"] * out["sample_factor"]).round(4)
    return out
