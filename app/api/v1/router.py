from fastapi import APIRouter
from app.api.v1.endpoints import interview, avatar

api_router = APIRouter()

# interview endpoints go to top level /api/chat etc.
api_router.include_router(interview.router, tags=["Interview"])

# avatar endpoints go to /api/did/...
api_router.include_router(avatar.router, prefix="/did", tags=["Avatar"])
