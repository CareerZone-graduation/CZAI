import json
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

from app.core.config import settings

router = APIRouter()

# Initialize OpenAI Client pointing to GitHub Models
client = None
if settings.LLM_API_KEY:
    client = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY
    )

class EnhanceJobRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None

ENHANCE_JOB_PROMPT = """Bạn là chuyên gia tuyển dụng chuyên nghiệp. Nhiệm vụ của bạn là VIẾT LẠI và MỞ RỘNG nội dung tin tuyển dụng từ các ghi chú ngắn gọn hoặc nội dung sơ khai thành văn bản chuyên nghiệp, chi tiết theo phong cách của các trang tuyển dụng hàng đầu như LinkedIn, Indeed, TopCV.

⚠️ QUAN TRỌNG: Input có thể là:
- Ghi chú tắt (VD: "1 năm kn", "có bằng ĐH", "biết React")
- Câu văn ngắn gọn
- Danh sách đơn giản
➡️ Bạn phải VIẾT LẠI thành văn bản đầy đủ, chuyên nghiệp, chi tiết

YÊU CẦU CHI TIẾT:

1. TIÊU ĐỀ (title):
   - Viết lại thành tiêu đề hấp dẫn, chuyên nghiệp
   - Thêm cấp bậc nếu phù hợp (Junior/Senior/Lead)
   - Giữ ngắn gọn, súc tích
   - VD: "dev react" → "Lập Trình Viên React (Junior/Middle)"

2. MÔ TẢ CÔNG VIỆC (description):
   - Viết lại từ ghi chú thành đoạn văn đầy đủ
   - Mở đầu bằng giới thiệu ngắn về vị trí
   - Liệt kê 5-8 trách nhiệm chính, mỗi mục một dòng với bullet points (-)
   - Mô tả cụ thể, chi tiết công việc hàng ngày
   - Làm rõ mục tiêu và kết quả mong đợi
   - Tối thiểu 150-200 từ
   - VD: "code web" → "- Phát triển và bảo trì các ứng dụng web sử dụng công nghệ hiện đại\n- Tham gia vào quá trình phân tích yêu cầu và thiết kế hệ thống..."

3. YÊU CẦU CÔNG VIỆC (requirements):
   - Viết lại từ ghi chú tắt thành câu văn đầy đủ
   - Chia thành "Yêu cầu bắt buộc" và "Yêu cầu ưu tiên" (nếu phù hợp)
   - Liệt kê 6-10 yêu cầu cụ thể với bullet points (-)
   - Bao gồm: kỹ năng kỹ thuật, kỹ năng mềm, kinh nghiệm, bằng cấp
   - Mô tả chi tiết từng yêu cầu
   - Tối thiểu 120-150 từ
   - VD:
     * "1 năm kn" → "- Có ít nhất 1 năm kinh nghiệm làm việc trong lĩnh vực tương tự"
     * "có bằng ĐH" → "- Tốt nghiệp Đại học chuyên ngành Công nghệ thông tin, Khoa học máy tính hoặc các ngành liên quan"
     * "biết React" → "- Thành thạo ReactJS và các thư viện liên quan (Redux, React Router, Hooks)"

4. QUYỀN LỢI (benefits):
   - Viết lại từ ghi chú thành câu văn hấp dẫn
   - Chia thành các nhóm: Lương thưởng, Phúc lợi, Phát triển, Môi trường
   - Liệt kê 8-12 quyền lợi cụ thể với bullet points (-)
   - Mô tả chi tiết, hấp dẫn
   - Tối thiểu 120-150 từ
   - VD: "lương cao" → "- Mức lương cạnh tranh, xứng đáng với năng lực và kinh nghiệm"

PHONG CÁCH:
- Chuyên nghiệp, thân thiện, thu hút
- Sử dụng ngôn ngữ tích cực, rõ ràng
- Viết câu văn đầy đủ, không để dạng ghi chú
- Cụ thể, có số liệu nếu có thể
- Dùng tiếng Việt chuẩn, dễ hiểu

LƯU Ý QUAN TRỌNG:
- VIẾT LẠI và MỞ RỘNG từ ghi chú ngắn thành văn bản đầy đủ
- Giữ nguyên ý nghĩa gốc, chỉ làm rõ và chuyên nghiệp hóa
- Tuyệt đối KHÔNG bịa thông tin không có trong input
- Có thể thay đổi từ ngữ cho hay hơn nếu cần

ĐỊNH DẠNG OUTPUT:
Bạn PHẢI trả về nội dung theo định dạng XML với các thẻ đánh dấu rõ ràng:

<TITLE>
[Nội dung tiêu đề ở đây]
</TITLE>

<DESCRIPTION>
[Nội dung mô tả công việc ở đây]
</DESCRIPTION>

<REQUIREMENTS>
[Nội dung yêu cầu công việc ở đây]
</REQUIREMENTS>

<BENEFITS>
[Nội dung quyền lợi ở đây]
</BENEFITS>

KHÔNG thêm code blocks, hoặc giải thích ngoài các thẻ XML.
>>> ĐẶC BIỆT LƯU Ý: VÌ GIAO DIỆN KHÔNG HỖ TRỢ MARKDOWN NÊN BẠN PHẢI DÙNG VĂN BẢN THUẦN TÚY (PLAIN TEXT). <<
- KHÔNG dùng dấu ** để in đậm (vd: không viết **Yêu cầu**)
- KHÔNG dùng chữ in nghiêng (*text*)
- KHÔNG dùng ký hiệu # cho tiêu đề
- CHỈ DÙNG viết hoa (vd: YÊU CẦU) để làm nổi bật nếu cần
- CHỈ DÙNG dấu gạch ngang (-) cho danh sách ngang cấp."""

async def stream_enhance_job(job_data: dict):
    """Stream job enhancement with field markers"""
    try:
        # Build user message with job data
        user_message = f"""Input: {json.dumps(job_data, ensure_ascii=False)}

Hãy viết lại theo định dạng XML đã yêu cầu. Không được trả về nội dung giống input."""

        # Call LLM with streaming
        stream = await client.chat.completions.create(
            model="gemini-2.5-flash-lite",
            messages=[
                {"role": "system", "content": ENHANCE_JOB_PROMPT},
                {"role": "user", "content": user_message}
            ],
            stream=True,
            temperature=1.0,
            max_tokens=3000,
            timeout=90.0
        )

        # State for parsing XML markers
        current_field = None
        field_buffer = ""
        field_order = ["title", "description", "requirements", "benefits"]
        field_map = {
            "TITLE": "title",
            "DESCRIPTION": "description",
            "REQUIREMENTS": "requirements",
            "BENEFITS": "benefits"
        }

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if not delta.content:
                continue

            content = delta.content
            field_buffer += content

            # Check for opening tags
            for tag, field in field_map.items():
                open_tag = f"<{tag}>"
                if open_tag in field_buffer and current_field is None:
                    # Found opening tag
                    current_field = field
                    field_buffer = field_buffer.split(open_tag, 1)[1]

                    # Emit field_start event
                    yield f"event: field_start\n"
                    yield f"data: {json.dumps({'field': field})}\n\n"
                    break

            # Check for closing tags
            if current_field:
                close_tag = f"</{field_map[current_field.upper()].upper()}>"
                if close_tag in field_buffer:
                    # Found closing tag - extract content
                    field_content = field_buffer.split(close_tag)[0].strip()

                    # Emit field_complete event
                    yield f"event: field_complete\n"
                    yield f"data: {json.dumps({'field': current_field, 'content': field_content})}\n\n"

                    # Reset for next field
                    field_buffer = field_buffer.split(close_tag, 1)[1] if close_tag in field_buffer else ""
                    current_field = None
                else:
                    # Still within field - emit delta
                    # Buffer chars if we suspect a closing tag is forming to prevent glitchy text
                    if "<" not in field_buffer[-15:]:
                        yield f"event: field_delta\n"
                        yield f"data: {json.dumps({'field': current_field, 'delta': content})}\n\n"

        # Emit done event
        yield f"event: done\n"
        yield f"data: {{}}\n\n"

    except Exception as e:
        # Emit error event
        error_msg = str(e)
        yield f"event: error\n"
        yield f"data: {json.dumps({'error': error_msg})}\n\n"

@router.post("/stream")
async def enhance_job_stream(
    request: EnhanceJobRequest,
    x_internal_api_key: str = Header(None)
):
    """
    Stream job enhancement with real-time field updates.

    Emits SSE events:
    - field_start: {"field": "title"}
    - field_delta: {"field": "title", "delta": "L"}
    - field_complete: {"field": "title", "content": "..."}
    - error: {"error": "..."}
    - done: {}
    """
    # Validate internal API key
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not client:
        raise HTTPException(status_code=503, detail="LLM service not configured")

    # Validate at least one field provided
    job_data = request.model_dump(exclude_none=True)
    if not job_data:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    return StreamingResponse(
        stream_enhance_job(job_data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
