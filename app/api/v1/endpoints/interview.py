from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models.chat import ChatRequest, TTSRequest, EndInterviewRequest, TranscribeRequest
from app.services import llm_service, tts_service, stt_service

router = APIRouter()

@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        response = await llm_service.generate_response(
            request.sessionId, request.message, request.isStart, request.topic
        )
        return {"response": response}
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
