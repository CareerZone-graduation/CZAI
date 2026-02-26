from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
import datetime
from app.core.config import settings
from app.core.database import get_db

router = APIRouter()


class SimilarJobsRequest(BaseModel):
    job_id: str = Field(..., description="Source job ID to find similar jobs for")
    limit: int = Field(default=6, ge=1, le=20, description="Number of results")


class SimilarJobResult(BaseModel):
    job_id: str
    similarity_score: float


class SimilarJobsResponse(BaseModel):
    success: bool = True
    data: list[SimilarJobResult]


@router.post("/similar-jobs", response_model=SimilarJobsResponse)
async def find_similar_jobs(
    request: SimilarJobsRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    """
    Find similar jobs by job ID using MongoDB Atlas $vectorSearch.
    
    Flow:
    1. Fetch source job's embedding from MongoDB
    2. Calculate average embedding from chunks
    3. Perform $vectorSearch on jobs collection
    4. Return array of job IDs with similarity scores
    """
    # Auth check
    if x_internal_secret != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = get_db()
    jobs_collection = db["jobs"]

    # Validate job_id format
    try:
        source_object_id = ObjectId(request.job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    # 1. Fetch source job and its embeddings
    job = jobs_collection.find_one(
        {"_id": source_object_id},
        {"chunks": 1, "title": 1}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # 2. Extract embeddings from chunks
    chunks = job.get("chunks", [])
    embeddings = [
        chunk["embedding"]
        for chunk in chunks
        if chunk.get("embedding") and len(chunk["embedding"]) > 0
    ]

    if not embeddings:
        return SimilarJobsResponse(data=[])

    # 3. Calculate average embedding
    dim = len(embeddings[0])
    avg_embedding = [0.0] * dim
    for emb in embeddings:
        for i in range(dim):
            avg_embedding[i] += emb[i]
    for i in range(dim):
        avg_embedding[i] /= len(embeddings)

    # 4. Perform $vectorSearch
    num_candidates = max(request.limit * 20, 200)

    pipeline = [
        {
            "$vectorSearch": {
                "index": "vt",
                "path": "chunks.embedding",
                "queryVector": avg_embedding,
                "numCandidates": num_candidates,
                "limit": request.limit + 5,
                "filter": {
                    "status": {"$eq": "ACTIVE"},
                    "moderationStatus": {"$eq": "APPROVED"},
                },
            }
        },
        {"$addFields": {"similarityScore": {"$meta": "vectorSearchScore"}}},
        # Exclude source job manually
        {"$match": {
            "_id": {"$ne": source_object_id},
            "deadline": {"$gte": datetime.datetime.utcnow()},
        }},
        {"$project": {"_id": 1, "similarityScore": 1}},
        {"$limit": request.limit},
    ]

    results = list(jobs_collection.aggregate(pipeline))

    return SimilarJobsResponse(
        data=[
            SimilarJobResult(
                job_id=str(r["_id"]),
                similarity_score=round(r["similarityScore"], 4),
            )
            for r in results
        ]
    )
