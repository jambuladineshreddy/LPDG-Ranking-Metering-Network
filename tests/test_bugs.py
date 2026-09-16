"""Bug-driven regression tests.

Each test in this file catches a specific real-world edge case or architectural bug
identified during baseline analysis and development.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import pandas as pd
from fastapi.testclient import TestClient

from src.api.main import app, get_data_loader
from src.data.loader import DataLoader
from src.ranking.sigma_ranker import SigmaRanker


def test_zero_variance_gateway_masked_anomaly(tmp_path: pathlib.Path) -> None:
    """REAL BUG DISCOVERY: Zero-variance baseline masking first-time anomalies.

    Explanation:
        In baseline_3sigma logic, std for a gateway with constant 0 reboot count
        across the 28-day baseline is 0.
        The line `std = recent['gateway_id'].map(stats[(metric, 'std')]).replace(0, np.nan)`
        converts std=0 into NaN.
        Subsequent `(recent[metric] - mean) > SIGMA * std` evaluates to NaN (False),
        which `.fillna(False)` silently treats as "not exceeded" — EVEN IF the gateway
        suddenly reboots 10 times in the recent 7-day window!

    This test asserts that zero-variance gateways currently result in 0 flagged hours,
    documenting this known limitation of the 3-sigma baseline logic.
    """
    telemetry_dir = tmp_path / "telemetry" / "month=2026-01"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    base_time = dt.datetime(2026, 1, 5, 0, 0, tzinfo=dt.timezone.utc)
    records = []

    # 28 days of zero reboots (std = 0) + 7 days of constant reboots (10 reboots/hr)
    for day in range(35):
        for hour in range(24):
            ts = base_time + dt.timedelta(days=day, hours=hour)
            reboot_cnt = 10 if day >= 28 else 0

            records.append(
                {
                    "gateway_id": "ZERO_VAR_GW",
                    "ts_utc": ts.isoformat(),
                    "offline_duration_sec": 0.0,
                    "disconnection_cnt": 0,
                    "reboot_cnt": reboot_cnt,
                }
            )

    df = pd.DataFrame(records)
    df.to_parquet(telemetry_dir / "part-0.parquet", index=False)

    loader = DataLoader(data_dir=tmp_path)
    telemetry_df = loader.load_telemetry()

    ranker = SigmaRanker()
    target_monday = dt.date(2026, 2, 9)

    rankings = ranker.rank_week(telemetry_df, target_monday)
    gw_rank = next((r for r in rankings if r.gateway_id == "ZERO_VAR_GW"), None)

    # Assert that zero variance masked the 10-reboot anomaly (score = 0)
    assert gw_rank is None or gw_rank.score == 0.0


def test_stale_cache_invalidation_on_run_endpoint(tmp_path: pathlib.Path) -> None:
    """REAL BUG DISCOVERY: Stale data returned by /run if data loader caches immutably.

    Explanation:
        If the data access layer loads telemetry once into a module-level global on startup,
        new parquet partitions dropped into `./data/telemetry/` while the service runs
        will never be picked up by POST /run without a process restart.

    This test writes an initial parquet partition, calls POST /run, drops a NEW partition
    with new telemetry into the directory, calls POST /run again, and verifies the API
    reflects the fresh partition without restarting the server.
    """
    telemetry_dir = tmp_path / "telemetry" / "month=2026-01"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    base_time = dt.datetime(2026, 1, 5, 0, 0, tzinfo=dt.timezone.utc)

    # Initial telemetry partition with GW_OLD
    records_1 = []
    for day in range(35):
        for hour in range(24):
            ts = base_time + dt.timedelta(days=day, hours=hour)
            records_1.append(
                {
                    "gateway_id": "GW_OLD",
                    "ts_utc": ts.isoformat(),
                    "offline_duration_sec": 10.0,
                    "disconnection_cnt": 0,
                    "reboot_cnt": 0,
                }
            )

    pd.DataFrame(records_1).to_parquet(telemetry_dir / "part-1.parquet", index=False)

    # Override DataLoader dependency in FastAPI app
    app.dependency_overrides[get_data_loader] = lambda: DataLoader(data_dir=tmp_path)

    try:
        client = TestClient(app)

        # Initial /run execution
        res1 = client.post("/run?week=2026-02-09")
        assert res1.status_code == 200

        # Drop NEW partition with GW_NEW containing high anomaly
        records_2 = []
        for day in range(35):
            for hour in range(24):
                ts = base_time + dt.timedelta(days=day, hours=hour)
                records_2.append(
                    {
                        "gateway_id": "GW_NEW",
                        "ts_utc": ts.isoformat(),
                        "offline_duration_sec": 3600.0 if day >= 28 else 10.0,
                        "disconnection_cnt": 0,
                        "reboot_cnt": 0,
                    }
                )

        pd.DataFrame(records_2).to_parquet(telemetry_dir / "part-2.parquet", index=False)

        # Second /run execution — must re-read disk and capture GW_NEW
        res2 = client.post("/run?week=2026-02-09")
        assert res2.status_code == 200

        # Fetch predictions for the week
        preds_res = client.get("/predictions/2026-02-09")
        assert preds_res.status_code == 200

        prediction_gws = [p["gateway_id"] for p in preds_res.json()["predictions"]]
        assert "GW_NEW" in prediction_gws
    finally:
        app.dependency_overrides.clear()
