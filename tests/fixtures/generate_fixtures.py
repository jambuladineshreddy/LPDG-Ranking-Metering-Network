"""Synthetic telemetry fixture generator for unit and integration testing.

IMPORTANT: Contains hand-crafted synthetic data only. Zero rows are copied
from the official competition dataset.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import pandas as pd


def create_synthetic_telemetry(
    output_dir: pathlib.Path,
    gateways: list[str] | None = None,
    start_date: dt.date = dt.date(2026, 1, 5),
    num_days: int = 35,
    anomaly_gateway: str | None = "TEST_GW_001",
) -> pathlib.Path:
    """Generate a synthetic parquet partition under output_dir/telemetry/month=2026-01."""
    gws = gateways or [f"TEST_GW_{i:03d}" for i in range(1, 21)]
    telemetry_dir = output_dir / "telemetry" / "month=2026-01"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    records = []
    base_time = dt.datetime.combine(start_date, dt.time(0, 0), tzinfo=dt.timezone.utc)

    for day in range(num_days):
        for hour in range(24):
            ts = base_time + dt.timedelta(days=day, hours=hour)
            ts_str = ts.isoformat()

            for gw in gws:
                # Normal baseline metrics
                offline_sec = 10.0
                disc_cnt = 0
                reboot_cnt = 0

                # Inject anomaly into recent window (last 7 days, days >= 28)
                if gw == anomaly_gateway and day >= 28 and hour < 5:
                    offline_sec = 1000.0  # Spikes above mean (~30) + 3*std (~150)
                    disc_cnt = 20
                    reboot_cnt = 5

                records.append(
                    {
                        "gateway_id": gw,
                        "ts_utc": ts_str,
                        "offline_duration_sec": offline_sec,
                        "disconnection_cnt": disc_cnt,
                        "reboot_cnt": reboot_cnt,
                    }
                )

    df = pd.DataFrame(records)
    parquet_path = telemetry_dir / "part-0.parquet"
    df.to_parquet(parquet_path, index=False)
    return parquet_path
