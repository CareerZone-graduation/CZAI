import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends
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

COPILOT_SYSTEM_PROMPT = """Bạn là CareerZone Copilot — trợ lý AI thông minh của nền tảng tuyển dụng CareerZone.

## Vai trò
- Hỗ trợ ứng viên tìm việc, theo dõi đơn ứng tuyển, chuẩn bị phỏng vấn
- Hỗ trợ nhà tuyển dụng quản lý tin tuyển dụng, sàng lọc ứng viên, lên lịch phỏng vấn
- Trả lời câu hỏi về chính sách, tính năng của CareerZone

## Quy tắc hoạt động
1. LUÔN sử dụng Tool Calling khi cần dữ liệu thực từ hệ thống. KHÔNG BAO GIỜ bịa dữ liệu.
2. Trả lời bằng tiếng Việt kèm định dạng markdown phù hợp để dễ đọc trừ khi user dùng ngôn ngữ khác.
3. Giao diện frontend sẽ TỰ ĐỘNG vẽ giao diện thẻ (UI cards) từ dữ liệu bạn query qua công cụ (tools) đối với danh sách việc làm/ tin tuyển dụng/phỏng vấn. DO ĐÓ, bạn TUYỆT ĐỐI KHÔNG sinh ra bảng (markdown table) hoặc liệt kê chi tiết từng công việc bằng text trong câu trả lời. Chỉ cần cung cấp một câu giới thiệu ngắn gọn (Ví dụ: "Dưới đây là danh sách công việc phù hợp:").
4. Khi giải đáp về **chính sách (thanh toán, ứng tuyển, bảo mật), quy định, hướng dẫn phỏng vấn, lỗi tài khoản hoặc hướng dẫn sử dụng hệ thống**, bạn PHẢI LUÔN gọi tool `search_knowledge_base` để lấy thông tin chính xác nhất từ CareerZone. Không tự đoán.

## Hỗ trợ tìm kiếm thông minh (Tool `search_jobs`)
- Khi người dùng tìm việc (VD: "việc làm java fresher cao đẳng"), bạn cần trích xuất TOÀN BỘ các từ khóa quan trọng vào tham số `query`, ngoại trừ các từ khóa không liên quan đến việc tuyển dụng hoặc đó là bộ lọc đã có trong filter (district, province, district, category, type, workType, experience, minSalary, maxSalary, skills, limit) 
## Hướng dẫn theo Trigger
- **summarize_job**: Khi trigger là 'summarize_job', nhiệm vụ chính của bạn là tóm tắt tin tuyển dụng. Hãy trình bày bằng **Markdown** với các **gạch đầu dòng ngắn gọn**, súc tích. Sử dụng **chữ đậm** cho các tiêu đề mục (Vị trí, Lương, v.v.). Tập trung vào: **Vị trí**, **Mức lương**, **Địa điểm**, **Yêu cầu cốt lõi** và **Quyền lợi nổi bật**. Tránh viết đoạn văn dài.

## Thông tin user hiện tại
- User ID: {user_id}
- Vai trò: {role}
- Trang hiện tại: {current_page}
- Trigger: {trigger}

## Context UI (Dữ liệu đang có trên giao diện)
{additional_context}"""

class Message(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
class UserContext(BaseModel):
    userId: Optional[str] = None
    role: Optional[str] = None
    profileSummary: Optional[str] = None
    currentPage: Optional[str] = None
    trigger: Optional[str] = None
    additionalContext: Optional[str] = None

class CopilotRequest(BaseModel):
    messages: List[Message]
    stream: Optional[bool] = True
    user_context: Optional[UserContext] = None
    ui_context: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None

def build_messages(messages: List[Message], system_prompt: str, tool_results: Optional[List[Dict[str, Any]]] = None, max_messages: int = 10) -> List[Dict[str, Any]]:
    """
    Xây dựng danh sách messages gửi tới model, áp dụng cơ chế 'Sliding window'
    chỉ lấy max_messages gần nhất từ MongoDB session.
    """
    api_messages = [{"role": "system", "content": system_prompt}]
    
    # Sliding window: lấy `max_messages` tin nhắn gần nhất
    history = messages[-max_messages:] if len(messages) > max_messages else messages
    
    for m in history:
        if m.role == "system":
            continue
        msg_dict = {"role": m.role}
        if m.content is not None:
            msg_dict["content"] = m.content
        if m.tool_calls is not None:
            msg_dict["tool_calls"] = m.tool_calls
        if m.tool_call_id is not None:
            msg_dict["tool_call_id"] = m.tool_call_id
        api_messages.append(msg_dict)
        
    if tool_results:
        for t_res in tool_results:
            api_messages.append({
                "role": "tool",
                "tool_call_id": t_res.get("tool_call_id"),
                "content": json.dumps(t_res.get("result", {}), ensure_ascii=False)
            })
            
    return api_messages

async def verify_internal_secret(x_internal_secret: str = Header(None)):
    # if not x_internal_secret or x_internal_secret != settings.INTERNAL_API_KEY:
    #     raise HTTPException(status_code=403, detail="Forbidden: Invalid internal secret")
    return x_internal_secret

@router.post("/invoke")
async def invoke_copilot(
    request: CopilotRequest,
    secret: str = Depends(verify_internal_secret)
):
    print(f"========== COPILOT INVOKE START ==========")
    print(f"[DEBUG] User Context: {request.user_context}")
    print(f"[DEBUG] Has provided tools: {bool(request.tools)}")
    print(f"[DEBUG] Has tool results: {bool(request.tool_results)}")
    
    if not client:
        raise HTTPException(status_code=500, detail="OpenAI client not configured")
        
    # Assemble System Prompt
    user_ctx = request.user_context or UserContext()
    ui_ctx = request.ui_context or {}
    
    ui_context_str = json.dumps(ui_ctx, ensure_ascii=False) if ui_ctx else "None"
    
    system_prompt_content = COPILOT_SYSTEM_PROMPT.format(
        user_id=user_ctx.userId or "Unknown",
        role=user_ctx.role or "Unknown",
        current_page=ui_ctx.get("currentPage", "Unknown"),
        trigger=ui_ctx.get("trigger", "None"),
        additional_context=ui_context_str
    )
    
    api_messages = build_messages(
        messages=request.messages,
        system_prompt=system_prompt_content,
        tool_results=request.tool_results,
        max_messages=10
    )
    print(f"[DEBUG] Assembled API Messages ({len(api_messages)} msgs)")
    for msg in api_messages:
        role = msg.get("role")
        content = msg.get("content", "")
        print(f"  - Role: {role} | Content Sample: {str(content)[:60]}...")

    async def stream_generator():
        try:
            from .copilot_tools import copilot_tools
            
            kwargs = {
                "model": settings.LLM_MODEL,
                "messages": api_messages,
                "stream": True,
                "temperature": 0.7,
                "tools": request.tools if request.tools else copilot_tools
            }
            
            print(f"[DEBUG] Calling OpenAI API ...")
            print(f"[DEBUG] Available tools for LLM: {[t['function']['name'] for t in kwargs['tools'] if 'function' in t] if kwargs.get('tools') else []}")
            
            stream = await client.chat.completions.create(**kwargs)
            
            tool_calls_accumulator = {}
            
            async for chunk in stream:
                if getattr(chunk, "choices", None) is None or len(chunk.choices) == 0:
                    continue
                delta = chunk.choices[0].delta
                
                if delta.content is not None:
                    data = json.dumps({"delta": delta.content}, ensure_ascii=False)
                    yield f"event: text_delta\ndata: {data}\n\n"
                    
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {
                                "id": tc_chunk.id,
                                "function": tc_chunk.function.name if tc_chunk.function else "",
                                "arguments": tc_chunk.function.arguments if tc_chunk.function and tc_chunk.function.arguments else ""
                            }
                        else:
                            if tc_chunk.function and tc_chunk.function.arguments:
                                tool_calls_accumulator[idx]["arguments"] += tc_chunk.function.arguments

            for idx, tc in tool_calls_accumulator.items():
                tc_data = json.dumps(tc, ensure_ascii=False)
                print(f"[DEBUG] LLM decided to use tool: {tc['function']} with args: {tc['arguments']}")
                yield f"event: tool_call\ndata: {tc_data}\n\n"
                
            print(f"========== COPILOT INVOKE END ==========\n")
            yield f"event: done\ndata: {{}}\n\n"
            
        except Exception as e:
            print(e)
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
