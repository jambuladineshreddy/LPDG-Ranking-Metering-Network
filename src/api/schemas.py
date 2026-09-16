"""Pydantic schemas for API request validation and response models."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class GatewayRankingItem(BaseModel):
    """Schema for an individual gateway ranking prediction item."""

    week_start: str = Field(..., json_schema_extra={"example": "2026-02-02"}, description="Monday week start date (YYYY-MM-DD)")
    rank: int = Field(..., ge=1, le=15, json_schema_extra={"example": 1}, description="Rank within the week (1 to 15)")
    gateway_id: str = Field(..., json_schema_extra={"example": "GW001"}, description="Unique gateway identifier")
    score: float = Field(..., json_schema_extra={"example": 42.0}, description="Flagged-hour score beyond 3 sigma")
    reason: str = Field(..., json_schema_extra={"example": "42 hour(s) beyond 3 sigma..."}, description="Explanation text (<=300 chars)")


class PredictionsResponse(BaseModel):
    """Response model for GET /predictions/{week_start}."""

    week_start: str
    count: int
    predictions: List[GatewayRankingItem]


class GatewayExplanationResponse(BaseModel):
    """Response model for GET /gateways/{gateway_id}/explain."""

    week_start: str
    gateway_id: str
    rank: Optional[int] = Field(None, description="Rank if in top 15, else None")
    score: float = Field(..., description="Flagged hours score")
    reason: str = Field(..., description="Explanation string for operations")
    breached_metrics: List[str] = Field(..., description="List of metrics exceeding 3 sigma")
    is_top_15: bool = Field(..., description="True if gateway is ranked in top 15 for the week")


class RunResponse(BaseModel):
    """Response model for POST /run."""

    status: str = Field(..., json_schema_extra={"example": "success"})
    message: str = Field(..., json_schema_extra={"example": "Pipeline re-executed and predictions refreshed."})
    refreshed_weeks: List[str] = Field(..., description="List of refreshed week_start dates")
    total_predictions: int = Field(..., description="Total predictions generated across all weeks")


class ErrorResponse(BaseModel):
    """Standardized error payload."""

    detail: str
    error_code: Optional[str] = None
