import urllib.parse
import requests
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from app.models.chat import ChatRequest, TTSRequest, EndInterviewRequest, TranscribeRequest
from app.services import llm_service, tts_service, stt_service
from app.core.config import settings

router = APIRouter()

@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        # 1. Gọi LLM
        ai_text = await llm_service.generate_response(
            request.sessionId, request.message, request.isStart, request.topic
        )
        
        # 2. Xử lý stream audio từ ElevenLabs cho dạng PCM16
        voice_id = "pNInz6obpgDQGcFmaJgB"
        tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format=pcm_16000"
        
        tts_headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        
        tts_payload = {
            "text": ai_text,
            "model_id": "eleven_v3",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        def audio_stream_generator():
            try:
                # Sử dụng mode stream=True của requests
                with requests.post(tts_url, json=tts_payload, headers=tts_headers, stream=True) as tts_response:
                    tts_response.raise_for_status()
                    total = 0
                    for chunk in tts_response.iter_content(chunk_size=4096):
                        if chunk:
                            total += len(chunk)
                            yield chunk
                    print(f"[ElevenLabs] Streamed {total} bytes of pcm 16000 audio")
            except Exception as e:
                print(f"[ElevenLabs Streaming Error]: {e}")

        # Trả về StreamingResponse với headers chứa AI Text
        return StreamingResponse(
            audio_stream_generator(),
            media_type="application/octet-stream",
            headers={
                "X-AI-Response": urllib.parse.quote(ai_text),
                "Access-Control-Expose-Headers": "X-AI-Response",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tts")
async def tts(request: TTSRequest):
    return await tts_service.stream_audio_from_text(request.text)

@router.post("/transcribe")
async def transcribe(request: TranscribeRequest):
    try:
        text = await stt_service.transcribe_audio(request.audioData)
        return {"text": text}
    except Exception as e:
        status_code = 400 if "Audio too short" in str(e) else 500
        raise HTTPException(status_code=status_code, detail=str(e))

@router.post("/end")
async def end_interview(request: EndInterviewRequest):
    try:
        llm_service.clear_session(request.sessionId)
        return {"status": "success", "message": "Interview session ended"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
