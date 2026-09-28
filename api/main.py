# -*- coding: utf-8 -*-
"""
FastAPI proof-of-concept for Trener Biegowy AI.

Endpoints:
    GET /health       — health check
    GET /readiness    — current readiness score and breakdown

Run: uvicorn api.main:app --reload
"""
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from config import DATA_LATEST
from logging_config import setup_logging

logger = logging.getLogger(__name__)
from services.data_extract import SnapshotStatus, read_snapshot_status
from services.readiness import compute_readiness_breakdown


app = FastAPI(
    title="Trener Biegowy AI",
    description="Personal running training system with AI coach",
    version="0.1.0",
)


@app.on_event("startup")
def startup():
    setup_logging(level=logging.INFO)
    logger.info("Trener Biegowy AI API starting")


# --- Response models ---

class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessDetail(BaseModel):
    metric: str
    status: str
    message: str


class ReadinessResponse(BaseModel):
    score: float
    max_score: float
    raw_score: float
    available_max_score: float
    insufficient_data: bool
    missing_metrics: List[str]
    available_metrics: List[str]
    data_coverage: float
    confidence: str
    level: str
    rhr: Optional[float]
    hrv_status: Optional[str]
    hrv_last: Optional[float]
    hrv_baseline: Optional[str]
    sleep_score_val: Optional[float]
    sleep_total: Optional[float]
    stress: Optional[float]
    details: List[ReadinessDetail]


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/readiness", response_model=ReadinessResponse)
def readiness():
    """Get current readiness score and breakdown.

    Requires data_latest.json to exist (run data_sync.py first).
    """
    logger.debug("Loading data from %s", DATA_LATEST)
    snapshot = read_snapshot_status()
    if snapshot.status is SnapshotStatus.MISSING:
        logger.warning("data_latest.json not found")
        raise HTTPException(
            status_code=404,
            detail="data_latest.json not found. Run data_sync.py first."
        )
    if snapshot.status is SnapshotStatus.INVALID:
        logger.error("Invalid snapshot: %s", snapshot.error)
        raise HTTPException(
            status_code=500,
            detail=f"Invalid data snapshot: {snapshot.error}"
        )
    if snapshot.status is SnapshotStatus.STALE:
        raise HTTPException(
            status_code=409,
            detail="Data snapshot is stale. Run data_sync.py before requesting readiness."
        )

    breakdown = compute_readiness_breakdown(snapshot.data)
    logger.info("Readiness: score=%.1f, level=%s", breakdown['score'], breakdown['level'])
    return ReadinessResponse(**breakdown)
