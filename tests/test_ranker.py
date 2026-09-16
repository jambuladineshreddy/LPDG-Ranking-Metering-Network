"""Unit tests for src.ranking.sigma_ranker.SigmaRanker."""

from __future__ import annotations

import datetime as dt
import pathlib

from src.data.loader import DataLoader
from src.ranking.sigma_ranker import SigmaRanker
from tests.fixtures.generate_fixtures import create_synthetic_telemetry


def test_sigma_ranker_detection(tmp_path: pathlib.Path) -> None:
    """Test that SigmaRanker correctly identifies anomalous gateway."""
    create_synthetic_telemetry(tmp_path, anomaly_gateway="TEST_GW_001")

    loader = DataLoader(data_dir=tmp_path)
    df = loader.load_telemetry()

    ranker = SigmaRanker()
    target_monday = dt.date(2026, 2, 9)

    rankings = ranker.rank_week(df, target_monday)
    assert len(rankings) > 0

    top_gw = rankings[0]
    assert top_gw.gateway_id == "TEST_GW_001"
    assert top_gw.rank == 1
    assert top_gw.score > 0
    assert "offline_duration_sec" in top_gw.breached_metrics


def test_sigma_ranker_deterministic_sort(tmp_path: pathlib.Path) -> None:
    """Test that gateways with equal scores are deterministically sorted by gateway_id ascending."""
    create_synthetic_telemetry(tmp_path, anomaly_gateway=None)  # No anomalies, all scores = 0

    loader = DataLoader(data_dir=tmp_path)
    df = loader.load_telemetry()

    ranker = SigmaRanker()
    target_monday = dt.date(2026, 2, 9)

    rankings = ranker.rank_week(df, target_monday)
    gw_ids = [r.gateway_id for r in rankings]

    # Verify alphabetical tie-break order when scores are equal
    assert gw_ids == sorted(gw_ids)
