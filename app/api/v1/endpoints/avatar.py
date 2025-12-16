from fastapi import APIRouter, HTTPException
from app.models.did import SDPRequest, ICERequest, SpeakRequest, CloseStreamRequest
from app.services import did_service, llm_service, tts_service, cloudinary_service # Import cloudinary ở đây luôn
import re
import time

router = APIRouter()

@router.get("/credentials") # Matches /api/did/credentials if routed correctly
async def get_credentials():
    try:
        return await did_service.create_stream()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sdp")
async def submit_sdp(request: SDPRequest):
    try:
        answer = {
            "type": request.sdpType,
            "sdp": request.sdpSdp
        }
        return await did_service.submit_sdp(request.streamId, request.sessionId, answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ice")
async def submit_ice(request: ICERequest):
    try:
        return await did_service.submit_ice(
            request.streamId, 
            request.sessionId, 
            request.candidate, 
            request.sdpMid, 
            request.sdpMLineIndex
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/speak")
async def speak(request: SpeakRequest):
    try:
        # LOGIC QUAN TRỌNG: Luôn biến Text thành Audio trước khi gọi D-ID
        print(f"Processing speak request for session {request.sessionId}")

        # 1. Generate Audio bằng ElevenLabs (Backend-side)
        # Sử dụng giọng và setting chuẩn trong tts_service
        audio_bytes = await tts_service.generate_audio(request.text)
        
        # 2. Upload lên Cloudinary để lấy Public URL
        # Tạo tên file an toàn
        safe_session_id = re.sub(r'[^a-zA-Z0-9_-]', '', request.sessionId)[:30]
        timestamp = int(time.time())
        public_id = f"{safe_session_id}_{timestamp}"
        
        audio_url = await cloudinary_service.upload_audio_bytes(audio_bytes, public_id=public_id)
        print(f"Audio generated & uploaded: {audio_url}")
        
        # 3. Gọi D-ID với audio_url (Không bao giờ gửi text trực tiếp nữa)
        data = await did_service.speak(
            stream_id=request.streamId, 
            session_id=request.sessionId, 
            audio_url=audio_url # Chỉ truyền tham số này
        )
        return data

    except Exception as e:
        print(f"Error in speak: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/close")
async def close_stream(request: CloseStreamRequest):
    try:
        # 1. Gọi D-ID để đóng kết nối WebRTC
        did_result = await did_service.delete_stream(request.streamId, request.sessionId)
        
        # 2. (Tùy chọn) Xóa lịch sử hội thoại của session này trong llm_service
        # Để lần sau chat không bị nhớ nhầm nội dung cũ
        if hasattr(llm_service, 'clear_session'):
             llm_service.clear_session(request.sessionId)
             
        return did_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
