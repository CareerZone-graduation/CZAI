from google import genai
from app.core.config import settings

# Initialize Gemini Client
client = genai.Client(api_key=settings.GEMINI_API_KEY)

INTERVIEWER_PROMPT = """Bạn là CareerZoneAI, một AI phỏng vấn viên chuyên nghiệp, thân thiện và hỗ trợ ứng viên.

QUY TẮC:
1. Trả lời NGẮN GỌN (1-2 câu), tự nhiên như đang nói chuyện
2. Đặt câu hỏi rõ ràng, cụ thể
3. Lắng nghe và phản hồi dựa trên câu trả lời của ứng viên
4. Thể hiện sự quan tâm và khuyến khích ứng viên
5. Sử dụng tiếng Việt tự nhiên, có thể thêm từ ngữ thân thiện, hoặc các hiệu ứng giọng nói, ví dụ: [haha]...
6. Quan trọng: tuyệt đối không được quá 15 từ trong mỗi câu hỏi hoặc phản hồi.
LUỒNG PHỎNG VẤN:
1. Chào hỏi và giới thiệu bản thân
2. Hỏi về background và kinh nghiệm
3. Hỏi về kỹ năng chuyên môn
4. Hỏi về dự án đã làm
5. Hỏi về mục tiêu nghề nghiệp
6. Kết thúc và cảm ơn

Hãy bắt đầu phỏng vấn một cách tự nhiên!"""

# Lưu trữ session trong bộ nhớ (Tương tự Map trong JS)
# Trong production nên dùng Redis
interview_sessions = {}

async def generate_response(session_id: str, message: str, is_start: bool = False):
    if session_id not in interview_sessions:
        interview_sessions[session_id] = []
    
    history = interview_sessions[session_id]
    
    if is_start:
        prompt = f"{INTERVIEWER_PROMPT}\n\nHãy bắt đầu cuộc phỏng vấn với lời chào... Thêm [haha] ở đầu để thêm sinh động"
    else:
        # Convert history objects to string format if needed, assuming they are dicts
        history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
        prompt = f"{INTERVIEWER_PROMPT}\n\nLịch sử hội thoại:\n{history_text}\n\nỨng viên: {message}\n\nPhỏng vấn viên (trả lời ngắn gọn 1-2 câu):"
    
    response = await client.aio.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt
    )
    ai_text = response.text
    
    if not is_start:
        history.append({"role": "Ứng viên", "content": message})
    history.append({"role": "Phỏng vấn viên", "content": ai_text})
    
    return ai_text

def clear_session(session_id: str):
    if session_id in interview_sessions:
        del interview_sessions[session_id]
