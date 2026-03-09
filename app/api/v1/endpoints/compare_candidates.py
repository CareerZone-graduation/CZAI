import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

from app.core.config import settings

router = APIRouter()

# Initialize OpenAI Client
client = None
if settings.LLM_API_KEY:
    client = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY
    )

COMPARE_SYSTEM_PROMPT = """Bạn là chuyên gia tuyển dụng AI của CareerZone. Nhiệm vụ: phân tích và so sánh các ứng viên cho một vị trí tuyển dụng cụ thể.

## Quy tắc
1. Trả lời bằng tiếng Việt, sử dụng Markdown.
2. Phân tích KHÁCH QUAN dựa trên dữ liệu thực tế được cung cấp.
3. Nếu ứng viên thiếu thông tin, ghi rõ "Thiếu dữ liệu" thay vì suy đoán.

## Output BẮT BUỘC gồm 2 phần:

### PHẦN 1: JSON SCORES (đầu tiên)
Bắt đầu bằng dòng: ```json
Sau đó là JSON object với format:
{
  "candidates": [
    {
      "name": "Tên ứng viên",
      "applicationId": "ID",
      "scores": {
        "skills": 75,
        "experience": 60,
        "education": 85,
        "jobFit": 70,
        "salary": 90
      },
      "totalScore": 76,
      "reasoning": {
        "skills": "Lý do ngắn gọn",
        "experience": "Lý do ngắn gọn",
        "education": "Lý do ngắn gọn",
        "jobFit": "Lý do ngắn gọn",
        "salary": "Lý do ngắn gọn"
      }
    }
  ]
}
```
Kết thúc JSON bằng dòng: ```

**Hướng dẫn chấm điểm (0-100):**
- **skills**: Đánh giá kỹ năng phù hợp với JD (có đủ kỹ năng yêu cầu? level như thế nào?)
- **experience**: Số năm kinh nghiệm liên quan (0-2 năm: 0-30, 2-5 năm: 30-70, 5+ năm: 70-100)
- **education**: Bằng cấp phù hợp (Trung cấp: 40, Cao đẳng: 50, Cử nhân: 70, Thạc sĩ: 85, Tiến sĩ: 100) + GPA bonus
- **jobFit**: Mức độ phù hợp tổng thể với JD (xem xét tất cả yếu tố)
- **salary**: So sánh với budget (càng thấp càng tốt, trong khoảng hợp lý: 70-100, cao hơn: 30-60)
- **totalScore**: Trung bình 5 điểm trên

### PHẦN 2: PHÂN TÍCH MARKDOWN (sau JSON)
Sau khi kết thúc JSON, viết phân tích chi tiết theo cấu trúc:

### 📊 Tổng quan so sánh
Bảng markdown so sánh nhanh các tiêu chí chính: Kỹ năng phù hợp, Kinh nghiệm, Học vấn, Mức lương, Điểm nổi bật.

### 🔍 Phân tích chi tiết từng ứng viên
Cho mỗi ứng viên:
- **Điểm mạnh** liên quan đến JD
- **Điểm yếu / thiếu sót** so với yêu cầu
- **Mức độ phù hợp** (Cao / Trung bình / Thấp) kèm lý do

### 🏆 Xếp hạng & Gợi ý
1. Xếp hạng ứng viên từ phù hợp nhất đến ít phù hợp nhất
2. Gợi ý cụ thể: nên ưu tiên ai và tại sao
3. Lưu ý hoặc rủi ro cần xác minh thêm (nếu có)"""


class CandidateData(BaseModel):
    name: str
    applicationId: str
    status: Optional[str] = None
    coverLetter: Optional[str] = None
    appliedAt: Optional[str] = None
    notes: Optional[str] = None
    cvText: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None

class JobData(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[str] = None
    type: Optional[str] = None
    workType: Optional[str] = None
    minSalary: Optional[str] = None
    maxSalary: Optional[str] = None
    category: Optional[str] = None
    location: Optional[Dict[str, Any]] = None

class CompareRequest(BaseModel):
    candidates: List[CandidateData]
    job: JobData
    stream: Optional[bool] = True


async def verify_internal_secret(x_internal_secret: str = Header(None)):
    return x_internal_secret


def format_candidate_for_prompt(c: CandidateData) -> str:
    """Format a single candidate's data into a readable prompt section."""
    parts = [f"### Ứng viên: {c.name}"]
    parts.append(f"- Application ID: {c.applicationId}")
    if c.status:
        parts.append(f"- Trạng thái hiện tại: {c.status}")
    if c.appliedAt:
        parts.append(f"- Ngày ứng tuyển: {c.appliedAt}")
    if c.coverLetter:
        parts.append(f"- Thư xin việc: {c.coverLetter[:500]}")
    if c.notes:
        parts.append(f"- Ghi chú recruiter: {c.notes}")

    profile = c.profile or {}

    if profile.get("bio"):
        parts.append(f"- Giới thiệu: {profile['bio']}")

    # Skills
    skills = profile.get("skills", [])
    if skills:
        skill_strs = [f"{s.get('name', '')} ({s.get('level', '')})" for s in skills if s.get('name')]
        parts.append(f"- Kỹ năng: {', '.join(skill_strs)}")

    # Experience
    exps = profile.get("experiences", [])
    if exps:
        exp_strs = []
        for e in exps:
            duration = f"{e.get('startDate', '?')} - {e.get('endDate', 'Hiện tại')}"
            exp_strs.append(f"  • {e.get('position', 'N/A')} tại {e.get('company', 'N/A')} ({duration})")
            if e.get('description'):
                exp_strs.append(f"    {e['description'][:200]}")
        parts.append("- Kinh nghiệm:\n" + "\n".join(exp_strs))

    # Education
    edus = profile.get("educations", [])
    if edus:
        edu_strs = []
        for e in edus:
            edu_strs.append(f"  • {e.get('degree', 'N/A')} - {e.get('major', 'N/A')} tại {e.get('school', 'N/A')}")
            if e.get('gpa'):
                edu_strs.append(f"    GPA: {e['gpa']}")
        parts.append("- Học vấn:\n" + "\n".join(edu_strs))

    # Certificates
    certs = profile.get("certificates", [])
    if certs:
        cert_strs = [f"  • {c.get('name', '')} ({c.get('issuer', '')})" for c in certs]
        parts.append("- Chứng chỉ:\n" + "\n".join(cert_strs))

    # Projects
    projects = profile.get("projects", [])
    if projects:
        proj_strs = []
        for p in projects:
            tech = ", ".join(p.get("technologies", []))
            proj_strs.append(f"  • {p.get('name', 'N/A')}: {p.get('description', '')[:150]} [{tech}]")
        parts.append("- Dự án:\n" + "\n".join(proj_strs))

    # Expected salary
    salary = profile.get("expectedSalary", {})
    if salary and salary.get("min"):
        parts.append(f"- Mức lương mong muốn: {salary.get('min', 'N/A')} - {salary.get('max', 'N/A')} {salary.get('currency', 'VND')}")

    # Work preferences
    prefs = profile.get("workPreferences", {})
    if prefs:
        if prefs.get("workTypes"):
            parts.append(f"- Hình thức làm việc mong muốn: {', '.join(prefs['workTypes'])}")
        if prefs.get("experienceLevel"):
            parts.append(f"- Cấp bậc mong muốn: {', '.join(prefs['experienceLevel']) if isinstance(prefs['experienceLevel'], list) else prefs['experienceLevel']}")

    # CV text content
    if c.cvText:
        cv_preview = c.cvText[:3000]
        parts.append(f"- Nội dung CV:\n{cv_preview}")

    return "\n".join(parts)


def format_job_for_prompt(job: JobData) -> str:
    """Format job data into a readable prompt section."""
    parts = ["## Thông tin vị trí tuyển dụng"]
    if job.title:
        parts.append(f"- Vị trí: {job.title}")
    if job.category:
        parts.append(f"- Ngành: {job.category}")
    if job.experience:
        parts.append(f"- Yêu cầu kinh nghiệm: {job.experience}")
    if job.type:
        parts.append(f"- Loại hình: {job.type}")
    if job.workType:
        parts.append(f"- Hình thức: {job.workType}")
    if job.minSalary or job.maxSalary:
        parts.append(f"- Mức lương: {job.minSalary or 'N/A'} - {job.maxSalary or 'N/A'} VND")
    if job.location:
        loc_parts = [job.location.get("province", ""), job.location.get("district", "")]
        parts.append(f"- Địa điểm: {', '.join(filter(None, loc_parts))}")
    if job.skills:
        parts.append(f"- Kỹ năng yêu cầu: {', '.join(job.skills)}")
    if job.description:
        parts.append(f"- Mô tả:\n{job.description[:2000]}")
    if job.requirements:
        parts.append(f"- Yêu cầu:\n{job.requirements[:1500]}")
    return "\n".join(parts)


@router.post("/compare-candidates")
async def compare_candidates(
    request: CompareRequest,
    secret: str = Depends(verify_internal_secret)
):
    if not client:
        raise HTTPException(status_code=500, detail="LLM client not configured")

    if len(request.candidates) < 2:
        raise HTTPException(status_code=400, detail="Cần ít nhất 2 ứng viên để so sánh")

    # Build user message with structured data
    job_section = format_job_for_prompt(request.job)
    candidate_sections = "\n\n".join(
        format_candidate_for_prompt(c) for c in request.candidates
    )

    user_message = f"""{job_section}

## Danh sách ứng viên cần so sánh ({len(request.candidates)} người)

{candidate_sections}

---
Hãy phân tích, so sánh và xếp hạng các ứng viên trên cho vị trí "{request.job.title or 'N/A'}". Đưa ra gợi ý cụ thể cho nhà tuyển dụng."""

    messages = [
        {"role": "system", "content": COMPARE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]

    print(f"[COMPARE] Comparing {len(request.candidates)} candidates for job: {request.job.title}")

    async def stream_generator():
        try:
            stream = await client.chat.completions.create(
                # model=settings.LLM_MODEL,
                model="gemini-2.5-flash-lite",
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                print(chunk)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    data = json.dumps({"delta": delta.content}, ensure_ascii=False)
                    yield f"event: text_delta\ndata: {data}\n\n"

            yield f"event: done\ndata: {{}}\n\n"

        except Exception as e:
            print(f"[COMPARE] Error: {e}")
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
