"""
Recommendation endpoints:
  - POST /interactions          — record a user-job interaction
  - GET  /recommendations/{id}  — personalised job recommendations
  - POST /retrain               — trigger full model retrain
  - POST /partial-update        — trigger incremental update
  - GET  /health                — model health / status
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.database import get_db
from app.models.recommendation import (
    InteractionRequest,
    JobScore,
    RecommendationResponse,
)
from app.services.recommendation.model_manager import engine

logger = logging.getLogger(__name__)
router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rec-api")


def _verify_internal(secret: str | None) -> None:
    if secret != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Record interaction ────────────────────────────────────────────────────────

@router.post("/interactions")
async def record_interaction(
    req: InteractionRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    _verify_internal(x_internal_secret)

    db = get_db()
    doc = {
        "userId": req.userId,
        "jobId": req.jobId,
        "type": req.type.value,
        "createdAt": datetime.now(timezone.utc),
    }
    await db[settings.INTERACTIONS_COLLECTION].insert_one(doc)
    return {"status": "ok"}


# ── Get recommendations ───────────────────────────────────────────────────────

@router.get("/recommendations/{user_id}", response_model=RecommendationResponse)
async def get_recommendations(
    user_id: str,
    x_internal_secret: Optional[str] = Header(None),
):
    # _verify_internal(x_internal_secret)

    if not engine.is_ready:
        raise HTTPException(
            status_code=503,
            detail="Model is not ready yet. Please try again later.",
        )

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        _executor,
        lambda: engine.predict(user_id, n=settings.TOP_N, exclude_applied=False),
    )

    # Determine source label based on actual predict outcome
    source = "model"
    if results and results[0]["score"] == 0.0:
        # popular fallback always returns score=0.0
        source = "popular"
    else:
        user_map, _, _, _ = engine.dataset.mapping()
        if user_id not in user_map:
            source = "cold_start"

    return RecommendationResponse(
        userId=user_id,
        recommendations=[JobScore(**r) for r in results],
        source=source,
    )


# ── Admin: retrain ────────────────────────────────────────────────────────────

@router.post("/retrain")
async def retrain(x_internal_secret: Optional[str] = Header(None)):
    _verify_internal(x_internal_secret)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, engine.full_retrain)
    return result


# ── Admin: partial update ─────────────────────────────────────────────────────

@router.post("/partial-update")
async def partial_update(x_internal_secret: Optional[str] = Header(None)):
    _verify_internal(x_internal_secret)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, engine.partial_update)
    return result


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return engine.get_status()
