from enum import Enum

from pydantic import BaseModel


class InteractionType(str, Enum):
    VIEW = "VIEW"
    SAVE = "SAVE"
    APPLY = "APPLY"


class InteractionRequest(BaseModel):
    userId: str
    jobId: str
    type: InteractionType


class JobScore(BaseModel):
    jobId: str
    score: float


class RecommendationResponse(BaseModel):
    userId: str
    recommendations: list[JobScore]
    source: str  # "model", "cold_start", "popular"
