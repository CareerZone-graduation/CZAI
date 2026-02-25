from fastapi import APIRouter
from app.api.v1.endpoints import interview, simli, embedding

api_router = APIRouter()

# interview endpoints go to top level /api/chat etc.
api_router.include_router(interview.router, tags=["Interview"])
api_router.include_router(simli.router, prefix="/simli", tags=["Simli"])
api_router.include_router(embedding.router, prefix="/embeddings", tags=["Embeddings"])
