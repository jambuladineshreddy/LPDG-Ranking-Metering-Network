"""FastAPI Web API application for LPDG Gateway Ranking Service."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import pathlib
from typing import Dict, List, Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from src.api.schemas import (
    ErrorResponse,
    GatewayExplanationResponse,
    GatewayRankingItem,
    PredictionsResponse,
    RunResponse,
)
from src.data.loader import DataLoader, DataLoaderError
from src.ranking.base import GatewayRanking, Ranker
from src.ranking.sigma_ranker import SigmaRanker

from contextlib import asynccontextmanager

SCORED_WEEKS = [dt.date(2026, 2, 2) + dt.timedelta(days=7 * i) for i in range(8)]
DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data"))

# In-memory predictions store (populated on startup and refreshed by /run)
_PREDICTIONS_CACHE: Dict[dt.date, List[GatewayRanking]] = {}
_RUN_LOCK = asyncio.Lock()


def get_ranker() -> Ranker:
    """Dependency provider returning the Ranker abstraction interface.

    Allows swapping ranker implementations without touching API handler code.
    """
    return SigmaRanker()


def get_data_loader() -> DataLoader:
    """Dependency provider returning a fresh DataLoader instance."""
    return DataLoader(data_dir=DATA_DIR)


def _parse_and_validate_monday(week_str: str) -> dt.date:
    """Parse week_start string and ensure it represents a valid Monday."""
    try:
        parsed_date = dt.date.fromisoformat(week_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid date format '{week_str}'. Must be YYYY-MM-DD format.",
        )

    if parsed_date.weekday() != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Date '{week_str}' is a {parsed_date.strftime('%A')}. week_start must be a Monday.",
        )

    return parsed_date


def _execute_pipeline(
    data_loader: DataLoader,
    ranker: Ranker,
    target_weeks: Optional[List[dt.date]] = None,
) -> Dict[dt.date, List[GatewayRanking]]:
    """Execute ranking pipeline by re-reading disk telemetry data."""
    weeks_to_run = target_weeks or SCORED_WEEKS
    frame = data_loader.load_telemetry()
    return ranker.rank_all(frame, weeks_to_run)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager initializing predictions cache on startup if data exists."""
    loader = get_data_loader()
    ranker = get_ranker()
    if loader.data_dir.exists():
        try:
            results = _execute_pipeline(loader, ranker, SCORED_WEEKS)
            _PREDICTIONS_CACHE.update(results)
        except DataLoaderError:
            pass
    yield


app = FastAPI(
    title="LPDG Gateway Ranking API",
    description="Web API service for LPDG operational gateway anomaly ranking.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get(
    "/predictions/{week_start}",
    response_model=PredictionsResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_predictions(
    week_start: str,
    ranker: Ranker = Depends(get_ranker),
    loader: DataLoader = Depends(get_data_loader),
) -> PredictionsResponse:
    """GET /predictions/{week_start} — Return top 15 ranked gateways for specified Monday."""
    target_monday = _parse_and_validate_monday(week_start)

    # Re-evaluate or retrieve from cache
    if target_monday not in _PREDICTIONS_CACHE:
        try:
            results = _execute_pipeline(loader, ranker, [target_monday])
            if results.get(target_monday):
                _PREDICTIONS_CACHE[target_monday] = results[target_monday]
        except DataLoaderError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Telemetry data unavailable for week {week_start}: {exc}",
            )

    predictions = _PREDICTIONS_CACHE.get(target_monday, [])
    if not predictions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No predictions or telemetry found for week_start '{week_start}'.",
        )

    items = [
        GatewayRankingItem(
            week_start=r.week_start.isoformat(),
            rank=r.rank,
            gateway_id=r.gateway_id,
            score=r.score,
            reason=r.reason,
        )
        for r in predictions
    ]

    return PredictionsResponse(
        week_start=target_monday.isoformat(),
        count=len(items),
        predictions=items,
    )


@app.get(
    "/gateways/{gateway_id}/explain",
    response_model=GatewayExplanationResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def explain_gateway(
    gateway_id: str,
    week: str = Query(..., alias="week", description="Monday date string (YYYY-MM-DD)"),
    ranker: Ranker = Depends(get_ranker),
    loader: DataLoader = Depends(get_data_loader),
) -> GatewayExplanationResponse:
    """GET /gateways/{gateway_id}/explain?week={week_start} — Explain gateway ranking status."""
    target_monday = _parse_and_validate_monday(week)

    try:
        frame = loader.load_telemetry()
    except DataLoaderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Telemetry data unavailable: {exc}",
        )

    # Check if gateway exists in dataset for that week's trailing baseline window
    end = pd.Timestamp(target_monday, tz="UTC")
    window = frame[
        (frame["gateway_id"] == gateway_id)
        & (frame["ts"] >= end - dt.timedelta(days=28))
        & (frame["ts"] < end)
    ]

    if window.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway '{gateway_id}' not found in dataset for week starting {week}.",
        )

    # Rank target week using injected ranker abstraction
    week_rankings = ranker.rank_week(frame, target_monday)
    match = next((r for r in week_rankings if r.gateway_id == gateway_id), None)

    if not match:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Gateway '{gateway_id}' is present in the dataset for week starting {week}, "
                "but was NOT ranked in that week's top 15 (rank > 15 / zero threshold breaches)."
            ),
        )

    return GatewayExplanationResponse(
        week_start=target_monday.isoformat(),
        gateway_id=gateway_id,
        rank=match.rank,
        score=match.score,
        reason=match.reason,
        breached_metrics=match.breached_metrics,
        is_top_15=True,
    )


@app.post(
    "/run",
    response_model=RunResponse,
    responses={
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def run_pipeline(
    week: Optional[str] = Query(None, alias="week", description="Optional specific week to regenerate"),
    ranker: Ranker = Depends(get_ranker),
    loader: DataLoader = Depends(get_data_loader),
) -> RunResponse:
    """POST /run?week={week_start} — Re-execute ranking pipeline with fresh disk telemetry."""
    if _RUN_LOCK.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A ranking pipeline execution is already in progress. Please wait for it to finish.",
        )

    async with _RUN_LOCK:
        if week:
            target_monday = _parse_and_validate_monday(week)
            weeks_to_process = [target_monday]
        else:
            weeks_to_process = SCORED_WEEKS

        try:
            # Re-read telemetry from disk (explicit freshness requirement)
            results = await asyncio.to_thread(_execute_pipeline, loader, ranker, weeks_to_process)
        except DataLoaderError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Pipeline execution failed due to telemetry loading error: {exc}",
            )

        _PREDICTIONS_CACHE.update(results)

        total_preds = sum(len(preds) for preds in _PREDICTIONS_CACHE.values())
        refreshed_str_list = [w.isoformat() for w in weeks_to_process]

        return RunResponse(
            status="success",
            message=f"Pipeline re-executed successfully for {len(weeks_to_process)} week(s).",
            refreshed_weeks=refreshed_str_list,
            total_predictions=total_preds,
        )
