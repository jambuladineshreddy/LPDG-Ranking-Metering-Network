#!/usr/bin/env python3
"""Validate a gateway-ranking submission CSV for the LPDG challenge."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = ["week_start", "rank", "gateway_id", "score", "reason"]
MIN_ROWS = 120
REQUIRED_WEEK_COUNT = 8
REQUIRED_RANKS = list(range(1, 16))
MAX_REASON_LEN = 300


def validate_submission(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"submission file not found: {path}")

    df = pd.read_csv(path)

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(
            "columns must be exactly in order: "
            + ", ".join(EXPECTED_COLUMNS)
        )

    if len(df) != MIN_ROWS:
        raise ValueError(f"expected {MIN_ROWS} rows, found {len(df)}")

    if df["week_start"].nunique() != REQUIRED_WEEK_COUNT:
        raise ValueError(
            f"expected {REQUIRED_WEEK_COUNT} distinct week_start values, found "
            f"{df['week_start'].nunique()}"
        )

    for week, group in df.groupby("week_start"):
        if sorted(group["rank"].tolist()) != REQUIRED_RANKS:
            raise ValueError(f"week {week} does not contain ranks 1..15 exactly once")

        if group["rank"].duplicated().any():
            raise ValueError(f"week {week} contains duplicate ranks")

        if group["gateway_id"].duplicated().any():
            raise ValueError(f"week {week} contains duplicate gateway_id values")

    if not pd.api.types.is_numeric_dtype(df["score"]):
        raise ValueError("score column must be numeric")

    if df["reason"].isna().any() or (df["reason"].astype(str).str.strip() == "").any():
        raise ValueError("reason column must not be blank")

    if (df["reason"].astype(str).str.len() > MAX_REASON_LEN).any():
        raise ValueError(f"reason values must be <= {MAX_REASON_LEN} characters")

    print(f"OK: {len(df)} rows across {df['week_start'].nunique()} weeks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path("predictions.csv"))
    args = parser.parse_args()

    try:
        validate_submission(args.path)
        return 0
    except Exception as exc:  # pragma: no cover - CLI error handling
        raise SystemExit(f"VALIDATION FAILED: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
