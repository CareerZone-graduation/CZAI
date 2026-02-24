import os
import urllib.parse
from openai import OpenAI
from app.core.config import settings

# Initialize OpenAI Client pointing to GitHub Models
client = None
if settings.GITHUB_TOKEN:
    client = OpenAI(
        base_url="https://models.github.ai/inference",
        api_key=settings.GITHUB_TOKEN
    )

def get_interviewer_prompt(topic: str = None) -> str:
    """Generate interviewer prompt based on topic"""
    
    # Base prompt
    base_prompt = """Bạn là CareerZoneAI, một AI phỏng vấn viên chuyên nghiệp, thân thiện và hỗ trợ ứng viên.

QUY TẮC:
1. Trả lời NGẮN GỌN (1-2 câu), tự nhiên như đang nói chuyện
2. Không dùng markdown, emoji, hoặc ký tự đặc biệt.
3. Khi muốn thể hiện cảm xúc, dùng tag tiếng Anh: [hihi], [haha],[laughs], [sighs], [chuckles], [gasps].
4. Đặt câu hỏi rõ ràng, cụ thể
5. Lắng nghe và phản hồi dựa trên câu trả lời của ứng viên
6. Trả lời bằng tiếng Việt."""
    
    # Topic-specific content
    if topic and topic.strip():
        topic_content = f"""

CHỦ ĐỀ PHỎNG VẤN: {topic}

LUỒNG PHỎNG VẤN (tập trung vào chủ đề "{topic}"):
1. Chào hỏi và giới thiệu bản thân, hãy cười và đề cập đến chủ đề phỏng vấn
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

# Lưu trữ session trong bộ nhớ (Tương tự Map trong JS)
interview_sessions = {}
# Lưu trữ topic cho mỗi session
interview_topics = {}

async def generate_response(session_id: str, message: str, is_start: bool = False, topic: str = None):
    if not client:
        raise ValueError("GitHub Token for LLM is not set!")
        
    if session_id not in interview_sessions:
        interview_sessions[session_id] = []
    
    # Save topic for this session if provided
    if is_start and topic:
        interview_topics[session_id] = topic
    
    # Get the topic for this session
    session_topic = interview_topics.get(session_id, None)
    current_prompt = get_interviewer_prompt(session_topic)
    
    history = interview_sessions[session_id]
    
    if len(history) == 0:
        history.append({"role": "system", "content": current_prompt})
    
    if is_start:
        topic_text = f" về chủ đề \"{session_topic}\"" if session_topic else ""
        prompt = f"Hãy bắt đầu cuộc phỏng vấn{topic_text} với lời chào... Thêm [haha] ở đầu để thêm sinh động"
    else:
        prompt = message
        
    history.append({"role": "user", "content": prompt})
    
    # Make sync call to OpenAI wrapper
    response = client.chat.completions.create(
        messages=history,
        temperature=1,
        top_p=1,
        model="gpt-4o"
    )
    
    ai_text = response.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": ai_text})
    
    print(f"[AI] User: {prompt}")
    print(f"[AI] AI: {ai_text}")
    
    return ai_text

def clear_session(session_id: str):
    if session_id in interview_sessions:
        del interview_sessions[session_id]
    if session_id in interview_topics:
        del interview_topics[session_id]
