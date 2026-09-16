"""3-Sigma Baseline implementation of the Ranker abstraction."""

from __future__ import annotations

import datetime as dt
from typing import Sequence

import numpy as np
import pandas as pd

from src.ranking.base import GatewayRanking, Ranker

METRICS = ["offline_duration_sec", "disconnection_cnt", "reboot_cnt"]
VISITS_PER_WEEK = 15
BASELINE_DAYS = 28
RECENT_DAYS = 7
SIGMA = 3.0


class SigmaRanker(Ranker):
    """Wraps baseline 3-sigma statistical anomaly calculation unchanged."""

    def rank_week(self, frame: pd.DataFrame, monday: dt.date) -> list[GatewayRanking]:
        """Rank gateways for a given Monday based on trailing 28-day baseline."""
        end = pd.Timestamp(monday, tz="UTC")
        window = frame[(frame["ts"] >= end - dt.timedelta(days=BASELINE_DAYS)) & (frame["ts"] < end)]
        if window.empty:
            return []

        stats = window.groupby("gateway_id")[METRICS].agg(["mean", "std"])
        recent = window[window["ts"] >= end - dt.timedelta(days=RECENT_DAYS)].copy()

        if recent.empty:
            return []

        flags = pd.Series(0, index=recent.index, dtype=int)
        worst = pd.Series("", index=recent.index, dtype=object)

        # Track breached metrics per row / gateway
        breached_metrics_per_gw: dict[str, set[str]] = {gw: set() for gw in recent["gateway_id"].unique()}

        for metric in METRICS:
            mean = recent["gateway_id"].map(stats[(metric, "mean")])
            std = recent["gateway_id"].map(stats[(metric, "std")]).replace(0, np.nan)
            exceeded = (recent[metric] - mean) > SIGMA * std
            exceeded = exceeded.fillna(False)

            flags = flags + exceeded.astype(int)
            worst = worst.where(~exceeded | (worst != ""), metric)

            for gw in recent.loc[exceeded, "gateway_id"].unique():
                breached_metrics_per_gw[gw].add(metric)

        recent["flagged"] = flags
        recent["worst_metric"] = worst
        grouped = recent.groupby("gateway_id").agg(
            flagged_hours=("flagged", "sum"),
            worst_metric=("worst_metric", lambda s: next((v for v in s if v), "")),
        )

        sorted_df = grouped.sort_values(
            ["flagged_hours", "gateway_id"], ascending=[False, True], kind="mergesort"
        ).reset_index()

        rankings: list[GatewayRanking] = []
        top_n = sorted_df.head(VISITS_PER_WEEK)

        for rank_idx, row in enumerate(top_n.itertuples(index=False), 1):
            gw_id = str(row.gateway_id)
            flagged_hours = int(row.flagged_hours)
            worst_m = row.worst_metric or "no metric over 3 sigma"

            reason = (
                f"{flagged_hours} hour(s) beyond 3 sigma of this gateway's own "
                f"28-day baseline in the last 7 days; first breach on {worst_m}"
            )

            breached_list = sorted(list(breached_metrics_per_gw.get(gw_id, set())))

            rankings.append(
                GatewayRanking(
                    week_start=monday,
                    rank=rank_idx,
                    gateway_id=gw_id,
                    score=float(flagged_hours),
                    reason=reason,
                    worst_metric=worst_m,
                    flagged_hours=flagged_hours,
                    breached_metrics=breached_list,
                )
            )

        return rankings

    def rank_all(
        self, frame: pd.DataFrame, week_starts: Sequence[dt.date]
    ) -> dict[dt.date, list[GatewayRanking]]:
        """Rank gateways across all provided week_start dates."""
        results: dict[dt.date, list[GatewayRanking]] = {}
        for monday in week_starts:
            results[monday] = self.rank_week(frame, monday)
        return results
