import httpx
from fastapi import APIRouter, HTTPException, Header
from typing import Annotated
from app.models.embedding import QueryEmbeddingRequest, BatchEmbeddingRequest
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/query-embedding")
async def generate_query_embedding(req: QueryEmbeddingRequest, x_internal_secret: Annotated[str | None, Header()] = None):
    if x_internal_secret != settings.INTERNAL_API_KEY:
        logger.warning("Unauthorized access attempt to /query-embedding endpoint")
        raise HTTPException(status_code=403, detail="Forbidden")

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set in .env")

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Text input is required and must be a non-empty string")

    url = f"https://generativelanguage.googleapis.com/v1beta/{req.model}:embedContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "model": req.model,
        "content": {
            "parts": [{"text": req.query.strip()}]
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if "embedding" not in data or "values" not in data["embedding"]:
                logger.error(f"Invalid response from Gemini API: {data}")
                raise HTTPException(status_code=500, detail="Invalid response format from Gemini API")
                
            return {"embedding": data["embedding"]["values"]}
            
        except httpx.HTTPStatusError as e:
            error_data = e.response.text
            logger.error(f"Gemini API error: {e.response.status_code} {e.response.reason_phrase} - {error_data}")
            raise HTTPException(status_code=502, detail=f"Gemini API error: {e.response.status_code} {error_data}")
        except httpx.RequestError as e:
            logger.error(f"Network error communicating with Gemini API: {str(e)}")
            raise HTTPException(status_code=503, detail="Network error communicating with Gemini API")

@router.post("/batch-embedding")
async def generate_batch_embedding(req: BatchEmbeddingRequest, x_internal_secret: Annotated[str | None, Header()] = None):
    if x_internal_secret != settings.INTERNAL_API_KEY:
        logger.warning("Unauthorized access attempt to /batch-embedding endpoint")
        raise HTTPException(status_code=403, detail="Forbidden")

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set in .env")

    if not req.queries or not isinstance(req.queries, list):
        raise HTTPException(status_code=400, detail="queries must be a non-empty list of strings")

    url = f"https://generativelanguage.googleapis.com/v1beta/{req.model}:batchEmbedContents"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    requests_payload = []
    for q in req.queries:
        if q and q.strip():
            requests_payload.append({
                "model": req.model,
                "content": {
                    "parts": [{"text": q.strip()}]
                }
            })
            
    if not requests_payload:
         raise HTTPException(status_code=400, detail="queries list must contain valid strings")

    payload = {
        "requests": requests_payload
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if "embeddings" not in data:
                logger.error(f"Invalid response from Gemini API for batch: {data}")
                raise HTTPException(status_code=500, detail="Invalid response format from Gemini API")
                
            return {"embeddings": [e["values"] for e in data["embeddings"]]}
            
        except httpx.HTTPStatusError as e:
            error_data = e.response.text
            logger.error(f"Gemini API error (batch): {e.response.status_code} {e.response.reason_phrase} - {error_data}")
            raise HTTPException(status_code=502, detail=f"Gemini API error: {e.response.status_code} {error_data}")
        except httpx.RequestError as e:
            logger.error(f"Network error communicating with Gemini API: {str(e)}")
            raise HTTPException(status_code=503, detail="Network error communicating with Gemini API")
