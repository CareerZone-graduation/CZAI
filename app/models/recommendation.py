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


class MatchReason(BaseModel):
    type: str
    value: str
    weight: int


class CandidateScore(BaseModel):
    userId: str
    candidateProfileId: str | None = None
    score: float
    similarityPercentage: int = 0
    matchedSkills: list[str] = []
    experienceYears: int = 0
    matchReasons: list[MatchReason] = []


class PaginationInfo(BaseModel):
    currentPage: int
    totalPages: int
    totalItems: int
    limit: int
    hasNextPage: bool
    hasPrevPage: bool


class CandidateRecommendationResponse(BaseModel):
    jobId: str
    recommendations: list[CandidateScore]
    pagination: PaginationInfo | None = None
    source: str


class SimilarJobCFResponse(BaseModel):
    """Response for Item-Item CF similar jobs endpoint."""
    jobId: str
    data: list[JobScore]
    source: str  # "model_cf", "popular"
