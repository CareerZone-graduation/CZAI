from google import genai
from app.core.config import settings

# Initialize Gemini Client
client = genai.Client(api_key=settings.GEMINI_API_KEY)

def get_interviewer_prompt(topic: str = None) -> str:
    """Generate interviewer prompt based on topic"""
    
    # Base prompt
    base_prompt = """Bạn là CareerZoneAI, một AI phỏng vấn viên chuyên nghiệp, thân thiện và hỗ trợ ứng viên.

QUY TẮC:
1. Trả lời NGẮN GỌN (1-2 câu), tự nhiên như đang nói chuyện
2. Đặt câu hỏi rõ ràng, cụ thể
3. Lắng nghe và phản hồi dựa trên câu trả lời của ứng viên
4. Thể hiện sự quan tâm và khuyến khích ứng viên
5. Sử dụng tiếng Việt tự nhiên, có thể thêm từ ngữ thân thiện, hoặc các hiệu ứng giọng nói, ví dụ: [haha]...
6. Quan trọng: tuyệt đối không được quá 15 từ trong mỗi câu hỏi hoặc phản hồi."""
    
    # Topic-specific content
    if topic and topic.strip():
        topic_content = f"""

CHỦ ĐỀ PHỎNG VẤN: {topic}

LUỒNG PHỎNG VẤN (tập trung vào chủ đề "{topic}"):
1. Chào hỏi và giới thiệu bản thân, đề cập đến chủ đề phỏng vấn
2. Hỏi về kiến thức cơ bản liên quan đến {topic}
3. Hỏi về kinh nghiệm thực tế với {topic}
4. Hỏi về dự án/case study liên quan đến {topic}
5. Hỏi về cách xử lý vấn đề/thách thức trong {topic}
6. Kết thúc và cảm ơn

Lưu ý: Tất cả câu hỏi phải liên quan trực tiếp đến chủ đề "{topic}". Đặt câu hỏi chuyên sâu và phù hợp với lĩnh vực này.

Hãy bắt đầu phỏng vấn về chủ đề "{topic}" một cách tự nhiên!"""
    else:
        topic_content = """

LUỒNG PHỎNG VẤN:
1. Chào hỏi và giới thiệu bản thân
2. Hỏi về background và kinh nghiệm
3. Hỏi về kỹ năng chuyên môn
4. Hỏi về dự án đã làm
5. Hỏi về mục tiêu nghề nghiệp
6. Kết thúc và cảm ơn

Hãy bắt đầu phỏng vấn một cách tự nhiên!"""
    
    return base_prompt + topic_content

# Default prompt for backward compatibility
INTERVIEWER_PROMPT = get_interviewer_prompt()

# Lưu trữ session trong bộ nhớ (Tương tự Map trong JS)
# Trong production nên dùng Redis
interview_sessions = {}
# Lưu trữ topic cho mỗi session
interview_topics = {}

async def generate_response(session_id: str, message: str, is_start: bool = False, topic: str = None):
    if session_id not in interview_sessions:
        interview_sessions[session_id] = []
    
    # Save topic for this session if provided
    if is_start and topic:
        interview_topics[session_id] = topic
    
    # Get the topic for this session
    session_topic = interview_topics.get(session_id, None)
    current_prompt = get_interviewer_prompt(session_topic)
    
    history = interview_sessions[session_id]
    
    if is_start:
        topic_text = f" về chủ đề \"{session_topic}\"" if session_topic else ""
        prompt = f"{current_prompt}\n\nHãy bắt đầu cuộc phỏng vấn{topic_text} với lời chào... Thêm [haha] ở đầu để thêm sinh động"
    else:
        # Convert history objects to string format if needed, assuming they are dicts
        history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
        prompt = f"{current_prompt}\n\nLịch sử hội thoại:\n{history_text}\n\nỨng viên: {message}\n\nPhỏng vấn viên (trả lời ngắn gọn 1-2 câu):"
    
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
    if session_id in interview_topics:
        del interview_topics[session_id]
