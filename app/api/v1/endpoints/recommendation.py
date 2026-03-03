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
    CandidateScore,
    CandidateRecommendationResponse,
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
    results, source = await loop.run_in_executor(
        _executor,
        lambda: engine.predict(user_id, n=settings.TOP_N, exclude_applied=False),
    )

    return RecommendationResponse(
        userId=user_id,
        recommendations=[JobScore(**r) for r in results],
        source=source,
    )


# ── Get candidates for a job (Vector Search + MaxSim) ────────────────────────

import numpy as np
from bson import ObjectId

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

@router.get("/recommendations/candidates/{job_id}", response_model=CandidateRecommendationResponse)
async def get_candidate_recommendations(
    job_id: str,
    x_internal_secret: Optional[str] = Header(None),
):
    # _verify_internal(x_internal_secret)
    db = get_db()
    
    # 1. Fetch Job and Average Embedding
    try:
        job_obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await db["jobs"].find_one({"_id": job_obj_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    chunks = job.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=400, detail="Job has no embeddings yet (chunks missing)")

    valid_embeddings = [c.get("embedding") for c in chunks if c.get("embedding")]
    if not valid_embeddings:
        raise HTTPException(status_code=400, detail="Job has no valid embeddings")

    # Average embedding
    dim = len(valid_embeddings[0])
    avg_embedding = [0.0] * dim
    for emb in valid_embeddings:
        for i in range(dim):
            avg_embedding[i] += emb[i]
    for i in range(dim):
        avg_embedding[i] /= len(valid_embeddings)

    # 2. Vector Search Pipeline on Users collection
    pipeline = [
        {
            "$vectorSearch": {
                "index": "default",
                "path": "embedding",
                "queryVector": avg_embedding,
                "numCandidates": 200,
                "limit": 100,
                "filter": {
                    "role": {"$eq": "candidate"},
                    "allowSearch": {"$eq": True}
                }
            }
        },
        {
            "$addFields": {
                "similarityScore": {"$meta": "vectorSearchScore"}
            }
        },
        {
            "$project": {
                "_id": 1,
                "similarityScore": 1,
                "chunks": 1
            }
        }
    ]

    matched_users = await db["users"].aggregate(pipeline).to_list(length=100)
    
    if not matched_users:
        return CandidateRecommendationResponse(
            jobId=job_id,
            recommendations=[],
            source="vector_search"
        )
        
    # 3. MaxSim Re-ranking
    for user in matched_users:
        best_score = user.get("similarityScore", 0)
        user_chunks = user.get("chunks", [])
        
        if user_chunks:
            max_chunk_score = -1.0
            for chunk in user_chunks:
                emb = chunk.get("embedding")
                if emb and len(emb) == dim:
                    score = cosine_similarity(avg_embedding, emb)
                    if score > max_chunk_score:
                        max_chunk_score = score
            
            if max_chunk_score > best_score:
                best_score = max_chunk_score
                
        user["finalScore"] = best_score
        
    # Sort descending
    matched_users.sort(key=lambda x: x["finalScore"], reverse=True)
    
    # Format response
    recommendations = [
        CandidateScore(userId=str(u["_id"]), score=u["finalScore"])
        for u in matched_users
    ]

    return CandidateRecommendationResponse(
        jobId=job_id,
        recommendations=recommendations,
        source="vector_search_maxsim"
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
