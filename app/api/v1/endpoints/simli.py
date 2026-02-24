import os
import requests
from fastapi import APIRouter, HTTPException
from app.models.chat import SimliSessionRequest
from app.core.config import settings

router = APIRouter()

@router.post("/get-session-token")
def get_session_token(req: SimliSessionRequest):
    api_key = settings.SIMLI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="SIMLI_API_KEY is not set in .env")

    url = "https://api.simli.ai/compose/token"
    headers = {
        "Content-Type": "application/json",
        "x-simli-api-key": api_key
    }
    # Important: MUST request pcm16 audio input format to use the raw PCM streaming byte trick from Elevenlabs
    payload = {
        "faceId": req.faceId,
        "handleSilence": True,
        "maxSessionLength": req.maxSessionLength,
        "maxIdleTime": 300,
        "audioInputFormat": "pcm16",
        "model": "artalk"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, "response") and e.response is not None and hasattr(e.response, "text"):
            error_msg += f". Response: {e.response.text}"
        raise HTTPException(status_code=500, detail=error_msg)

@router.get("/get-ice-servers")
def get_ice_servers():
    api_key = settings.SIMLI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="SIMLI_API_KEY is not set in .env")
    
    url = "https://api.simli.ai/compose/ice"
    headers = {"x-simli-api-key": api_key}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, "response") and e.response is not None and hasattr(e.response, "text"):
            error_msg += f". Response: {e.response.text}"
        raise HTTPException(status_code=500, detail=error_msg)
