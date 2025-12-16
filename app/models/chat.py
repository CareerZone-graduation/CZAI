from pydantic import BaseModel

class ChatRequest(BaseModel):
    sessionId: str
    message: str = ""
    isStart: bool = False

class TTSRequest(BaseModel):
    text: str

class EndInterviewRequest(BaseModel):
    sessionId: str

class TranscribeRequest(BaseModel):
    audioData: str
