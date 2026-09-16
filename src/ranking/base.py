"""Abstract Ranker interface seam for gateway ranking algorithm decoupling."""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import pandas as pd


@dataclass(frozen=True)
class GatewayRanking:
    """Represents a single gateway ranking result."""

    week_start: dt.date
    rank: int
    gateway_id: str
    score: float
    reason: str
    worst_metric: str = ""
    flagged_hours: int = 0
    breached_metrics: list[str] = field(default_factory=list)


class Ranker(ABC):
    """Abstract ranker seam.

    The API layer depends exclusively on this abstraction, enabling alternate
    ranking algorithms (e.g. ML models, heuristics) to be swapped without
    modifying API routes or handler logic.
    """

    @abstractmethod
    def rank_week(self, frame: pd.DataFrame, monday: dt.date) -> list[GatewayRanking]:
        """Compute gateway rankings for a specific Monday week_start.

        Args:
            frame: Telemetry DataFrame containing columns gateway_id, ts (UTC Timestamp),
                   offline_duration_sec, disconnection_cnt, reboot_cnt.
            monday: Target Monday date.

        Returns:
            List of GatewayRanking items (top N ranked gateways for the week).
        """
        ...

    @abstractmethod
    def rank_all(
        self, frame: pd.DataFrame, week_starts: list[dt.date]
    ) -> dict[dt.date, list[GatewayRanking]]:
        """Compute gateway rankings for multiple target week_start dates.

        Args:
            frame: Telemetry DataFrame.
            week_starts: List of target Monday dates.

        Returns:
            Dictionary mapping week_start date to list of GatewayRanking items.
        """
        ...
