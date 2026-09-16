"""Unit tests for src.data.loader.DataLoader."""

from __future__ import annotations

import pathlib
import pytest

from src.data.loader import DataLoader, DataLoaderError
from tests.fixtures.generate_fixtures import create_synthetic_telemetry


def test_load_telemetry_success(tmp_path: pathlib.Path) -> None:
    """Test successful loading of parquet telemetry files."""
    create_synthetic_telemetry(tmp_path)

    loader = DataLoader(data_dir=tmp_path)
    df = loader.load_telemetry()

    assert not df.empty
    assert "gateway_id" in df.columns
    assert "ts" in df.columns
    assert "offline_duration_sec" in df.columns
    assert "disconnection_cnt" in df.columns
    assert "reboot_cnt" in df.columns


def test_load_telemetry_missing_directory(tmp_path: pathlib.Path) -> None:
    """Test DataLoader raising DataLoaderError when telemetry directory is missing."""
    missing_dir = tmp_path / "does_not_exist"
    loader = DataLoader(data_dir=missing_dir)

    with pytest.raises(DataLoaderError, match="Telemetry directory does not exist"):
        loader.load_telemetry()
