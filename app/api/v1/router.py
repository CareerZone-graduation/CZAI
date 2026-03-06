from fastapi import APIRouter

from app.api.v1.endpoints import (
    embedding,
    interview,
    recommendation,
    similar_jobs,
    simli,
    copilot,
)

api_router = APIRouter()

# interview endpoints go to top level /api/chat etc.
api_router.include_router(interview.router, tags=["Interview"])
api_router.include_router(simli.router, prefix="/simli", tags=["Simli"])
api_router.include_router(
    embedding.router, prefix="/embeddings", tags=["Embeddings"])
api_router.include_router(
    similar_jobs.router, prefix="/embeddings", tags=["Similar Jobs"])
api_router.include_router(recommendation.router, tags=["Recommendations"])
api_router.include_router(copilot.router, prefix="/copilot", tags=["Copilot"])
