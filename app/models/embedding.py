from pydantic import BaseModel
from typing import Optional

class QueryEmbeddingRequest(BaseModel):
    query: str
    model: Optional[str] = "models/gemini-embedding-001"
