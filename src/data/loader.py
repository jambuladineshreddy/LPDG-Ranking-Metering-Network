"""Data loader module providing dynamic, re-readable parquet dataset access."""

from __future__ import annotations

import pathlib

import pandas as pd

METRICS = ["offline_duration_sec", "disconnection_cnt", "reboot_cnt"]


class DataLoaderError(Exception):
    """Custom exception raised when telemetry data loading fails."""

    pass


class DataLoader:
    """Handles loading telemetry data dynamically from disk.

    Ensures data freshness by re-reading parquet partitions directly from disk
    on demand, avoiding stale in-memory caching when new files are added.
    """

    def __init__(self, data_dir: pathlib.Path | str = "data"):
        self.data_dir = pathlib.Path(data_dir)

    def load_telemetry(self) -> pd.DataFrame:
        """Re-read parquet telemetry files from the data directory.

        Returns:
            pd.DataFrame: Cleaned telemetry data with 'gateway_id', 'ts' (UTC Datetime),
                          'offline_duration_sec', 'disconnection_cnt', 'reboot_cnt'.

        Raises:
            DataLoaderError: If the data directory or parquet files are missing or unreadable.
        """
        telemetry_dir = self.data_dir / "telemetry"
        if not telemetry_dir.exists():
            raise DataLoaderError(f"Telemetry directory does not exist: {telemetry_dir}")

        try:
            frame = pd.read_parquet(
                telemetry_dir, columns=["gateway_id", "ts_utc", *METRICS]
            )
        except Exception as exc:
            raise DataLoaderError(
                f"Failed to read parquet telemetry files from {telemetry_dir}: {exc}"
            ) from exc

        if frame.empty:
            raise DataLoaderError(f"No telemetry records found in {telemetry_dir}")

        frame["ts"] = pd.to_datetime(frame["ts_utc"], utc=True)
        return frame.drop(columns=["ts_utc"])
