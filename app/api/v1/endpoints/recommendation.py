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

def extract_matched_skills(job_skills: list[str], candidate_skills: list[dict]) -> list[str]:
    if not job_skills or not candidate_skills: return []
    job_skills_lower = [s.lower().strip() for s in job_skills]
    matched = []
    for cs in candidate_skills:
        name = cs.get("name", "")
        if name and name.lower().strip() in job_skills_lower:
            matched.append(name)
    return matched[:5]

def calculate_experience_years(experiences: list[dict]) -> int:
    if not experiences: return 0
    total_months = 0
    for exp in experiences:
        start_str = exp.get("startDate")
        end_str = exp.get("endDate")
        if not start_str: continue
        
        # Format can be '2020-01-01T00:00:00.000Z'
        if isinstance(start_str, str) and start_str.endswith("Z"):
            start_str = start_str[:-1] + "+00:00"
        if isinstance(end_str, str) and end_str.endswith("Z"):
            end_str = end_str[:-1] + "+00:00"
            
        try:
            start_date = datetime.fromisoformat(start_str) if isinstance(start_str, str) else start_str
            if end_str:
                end_date = datetime.fromisoformat(end_str) if isinstance(end_str, str) else end_str
            else:
                end_date = datetime.now(timezone.utc)
            
            months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            total_months += max(0, months)
        except Exception:
            pass
    return round(total_months / 12)

@router.get("/recommendations/candidates/{job_id}", response_model=CandidateRecommendationResponse)
async def get_candidate_recommendations(
    job_id: str,
    page: int = 1,
    limit: int = 10,
    minScore: float = 0.5,
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
            pagination={"currentPage": page, "totalPages": 0, "totalItems": 0, "limit": limit, "hasNextPage": False, "hasPrevPage": False},
            source="vector_search"
        )
        
    # 3. Fetch CandidateProfiles
    user_ids = [u["_id"] for u in matched_users]
    profiles = await db["candidateprofiles"].find({"userId": {"$in": user_ids}}).to_list(length=100)
    profile_map = {str(p["userId"]): p for p in profiles}
        
    # 4. MaxSim Re-ranking & Rule-based Scoring
    scored_candidates = []
    
    job_skills_list = job.get("skills", [])
    job_skills_lower = [s.lower().strip() for s in job_skills_list if isinstance(s, str)]
    job_category = str(job.get("category", ""))
    job_location = job.get("location", {})
    job_experience = str(job.get("experience", ""))
    job_work_type = str(job.get("workType", ""))
    
    for user in matched_users:
        user_id_str = str(user["_id"])
        profile = profile_map.get(user_id_str)
        if not profile:
            continue
            
        best_score = user.get("similarityScore", 0)
        user_chunks = user.get("chunks", [])
        
        if user_chunks:
            max_chunk_score = -1.0
            for chunk in user_chunks:
                emb = chunk.get("embedding")
                if emb and len(emb) == dim:
                    s = cosine_similarity(avg_embedding, emb)
                    if s > max_chunk_score:
                        max_chunk_score = s
            if max_chunk_score > best_score:
                best_score = max_chunk_score
                
        # Base AI score (normalized up to 40 points)
        ai_score_val = min(float(best_score), 1.0)
        score = ai_score_val * 40
        match_reasons = [{
            "type": "ai_match",
            "value": "Phù hợp với mô tả công việc (AI đánh giá)",
            "weight": round(score)
        }]
        
        # Rule 1: Skills matching (max 30 points)
        prof_skills = profile.get("skills", [])
        if job_skills_list and prof_skills:
            candidate_skills_lower = [s.get("name", "").lower().strip() for s in prof_skills if isinstance(s, dict) and s.get("name")]
            exact_matches = 0
            partial_matches = 0
            matched_skill_names = []
            
            for c_skill in candidate_skills_lower:
                if c_skill in job_skills_lower:
                    exact_matches += 1
                    matched_skill_names.append(c_skill)
                else:
                    has_partial = any(js in c_skill or c_skill in js for js in job_skills_lower)
                    if has_partial:
                        partial_matches += 1
                        
            skill_score = min(30, (exact_matches * 8) + (partial_matches * 3))
            score += skill_score
            
            if exact_matches > 0:
                short_matched = ", ".join(matched_skill_names[:3])
                suffix = "..." if len(matched_skill_names) > 3 else ""
                match_reasons.append({
                    "type": "skill_match",
                    "value": f"Khớp {exact_matches} kỹ năng: {short_matched}{suffix}",
                    "weight": skill_score
                })
                
        # Rule 2: Category matching (max 10 points)
        if job_category and job_category in profile.get("preferredCategories", []):
            score += 10
            match_reasons.append({
                "type": "category_match",
                "value": "Đúng ngành nghề mong muốn",
                "weight": 10
            })
            
        # Rule 3: Location matching (max 10 points)
        job_province = job_location.get("province")
        if job_province and profile.get("preferredLocations"):
            loc_match = next((loc for loc in profile.get("preferredLocations", []) if loc.get("province") == job_province), None)
            if loc_match:
                loc_score = 7
                job_district = job_location.get("district")
                if loc_match.get("district") and job_district and loc_match.get("district") == job_district:
                    loc_score = 10
                score += loc_score
                
                dist_str = f", {loc_match.get('district')}" if loc_match.get("district") else ""
                match_reasons.append({
                    "type": "location_match",
                    "value": f"Vị trí phù hợp: {job_province}{dist_str}",
                    "weight": loc_score
                })
                
        # Rule 4: Experience Level matching (max 5 points)
        if job_experience and job_experience in profile.get("workPreferences", {}).get("experienceLevel", []):
            score += 5
            match_reasons.append({
                "type": "experience_match",
                "value": "Cấp độ kinh nghiệm phù hợp",
                "weight": 5
            })
            
        # Rule 5: Work type matching (max 5 points)
        if job_work_type and job_work_type in profile.get("workPreferences", {}).get("workTypes", []):
            score += 5
            match_reasons.append({
                "type": "worktype_match",
                "value": "Hình thức làm việc phù hợp",
                "weight": 5
            })
            
        normalized_score = score / 100.0
        
        if normalized_score >= minScore:
            scored_candidates.append(CandidateScore(
                userId=user_id_str,
                candidateProfileId=str(profile.get("_id", "")),
                score=normalized_score,
                similarityPercentage=round(normalized_score * 100),
                matchedSkills=extract_matched_skills(job_skills_list, prof_skills),
                experienceYears=calculate_experience_years(profile.get("experiences", [])),
                matchReasons=match_reasons
            ))
            
    # Sort descending
    scored_candidates.sort(key=lambda x: x.score, reverse=True)
    
    total_items = len(scored_candidates)
    skip = (page - 1) * limit
    paginated = scored_candidates[skip:skip + limit]
    
    import math
    total_pages = math.ceil(total_items / limit) if limit > 0 else 0
    
    return CandidateRecommendationResponse(
        jobId=job_id,
        recommendations=paginated,
        pagination={
            "currentPage": page,
            "totalPages": total_pages,
            "totalItems": total_items,
            "limit": limit,
            "hasNextPage": (page * limit) < total_items,
            "hasPrevPage": page > 1
        },
        source="vector_search_maxsim_rulebased"
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
