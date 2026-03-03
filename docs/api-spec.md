# CareerZoneAI — API Specification

> **Base URL:** `http://localhost:8000/api/v1`  
> **Version:** 1.0 | **Date:** 2026-03-02

---

## Quy ước chung

- **camelCase** cho tất cả JSON field (tương thích với JS frontend)
- **Auth header:** `X-Internal-Secret: <INTERNAL_API_KEY>` cho các endpoint internal
- **Error format:**
  ```json
  { "detail": "<error message>" }
  ```
- **Content-Type:** `application/json` (trừ `/chat` → `application/octet-stream`)

---

## 1. Interview — AI phỏng vấn

### `POST /chat`

Gửi message của user → trả về stream PCM16 audio + AI text trong header.

**Request body:**
```json
{
  "sessionId": "uuid-string",
  "message": "Tôi có 3 năm kinh nghiệm React",
  "isStart": false,
  "topic": "Frontend Development",
  "avatarType": "simli"
}
```

| Field       | Type    | Required | Mô tả                                         |
|-------------|---------|----------|-----------------------------------------------|
| `sessionId` | string  | ✓        | ID phiên phỏng vấn (UUID khuyến nghị)         |
| `message`   | string  | ✓        | Tin nhắn của user (rỗng khi `isStart=true`)   |
| `isStart`   | boolean |          | `true` để bắt đầu phiên mới (default: false)  |
| `topic`     | string  |          | Chủ đề phỏng vấn (vd: "Python Backend")       |
| `avatarType`| string  |          | `"simli"` hoặc `"live2d"` → chọn voice ElevenLabs |

**Response:**
- `Content-Type: application/octet-stream`
- Streaming PCM16 audio bytes (16000 Hz, 16-bit)
- Header `X-AI-Response: <URL-encoded AI text>`

**Errors:**
| Code | Khi nào                  |
|------|--------------------------|
| 500  | LLM/TTS lỗi              |

---

### `POST /tts`

Chuyển text thành audio MP3.

**Request body:**
```json
{ "text": "Xin chào, tôi là CareerZoneAI" }
```

**Response:** `StreamingResponse` — MP3 audio stream

---

### `POST /transcribe`

Transcribe audio base64 → text (tiếng Việt).

**Request body:**
```json
{ "audioData": "<base64-encoded audio bytes>" }
```

**Response:**
```json
{ "text": "Tôi có 3 năm kinh nghiệm lập trình" }
```

**Errors:**
| Code | Khi nào                               |
|------|---------------------------------------|
| 400  | Audio quá ngắn (< 5000 bytes decoded) |
| 500  | AssemblyAI lỗi / timeout              |

---

### `POST /end`

Kết thúc phiên phỏng vấn — xóa session khỏi in-memory store.

**Request body:**
```json
{ "sessionId": "uuid-string" }
```

**Response:**
```json
{ "status": "success", "message": "Interview session ended" }
```

---

## 2. Simli — AI Avatar

### `POST /simli/get-session-token`

Lấy session token từ Simli AI để khởi tạo WebRTC avatar.

**Request body:**
```json
{
  "faceId": "simli-face-id",
  "maxSessionLength": 3600
}
```

**Response:** Simli session token object (passthrough từ Simli API)

---

### `GET /simli/get-ice-servers`

Lấy danh sách ICE servers cho WebRTC.

**Response:** Simli ICE servers object (passthrough từ Simli API)

---

## 3. Embeddings

> ⚠️ Yêu cầu header: `X-Internal-Secret`

### `POST /embeddings/query-embedding`

Tạo vector embedding từ text sử dụng Gemini API.

**Request body:**
```json
{
  "query": "Lập trình viên Python có kinh nghiệm AI",
  "model": "models/gemini-embedding-001"
}
```

| Field   | Type   | Required | Mô tả                              |
|---------|--------|----------|------------------------------------|
| `query` | string | ✓        | Text cần embed                     |
| `model` | string |          | Gemini model (default: `gemini-embedding-001`) |

**Response:**
```json
{
  "embedding": [0.0123, -0.0456, ...]
}
```

**Errors:**
| Code | Khi nào                       |
|------|-------------------------------|
| 400  | `query` rỗng                  |
| 403  | `X-Internal-Secret` sai       |
| 502  | Gemini API lỗi                |
| 503  | Network error                 |

---

### `POST /embeddings/similar-jobs`

Tìm jobs tương tự bằng MongoDB Atlas `$vectorSearch`.

**Request body:**
```json
{
  "job_id": "67a1b2c3d4e5f6789abcdef0",
  "limit": 6
}
```

| Field    | Type   | Required | Mô tả                              |
|----------|--------|----------|------------------------------------|
| `job_id` | string | ✓        | MongoDB ObjectId của job nguồn     |
| `limit`  | int    |          | Số kết quả (1–20, default: 6)      |

**Response:**
```json
{
  "success": true,
  "data": [
    { "job_id": "...", "similarity_score": 0.9234 },
    { "job_id": "...", "similarity_score": 0.8901 }
  ]
}
```

**Errors:**
| Code | Khi nào                          |
|------|----------------------------------|
| 400  | `job_id` không phải MongoDB ObjectId |
| 401  | `X-Internal-Secret` sai          |
| 404  | Job không tồn tại hoặc không có embedding |

---

## 4. Recommendations

> ⚠️ Yêu cầu header: `X-Internal-Secret`

### `POST /interactions`

Ghi nhận tương tác của user với job.

**Request body:**
```json
{
  "userId": "user-mongodb-id",
  "jobId": "job-mongodb-id",
  "type": "VIEW"
}
```

| Field    | Type   | Values                     | Mô tả          |
|----------|--------|----------------------------|----------------|
| `userId` | string | MongoDB ObjectId           | ID của user    |
| `jobId`  | string | MongoDB ObjectId           | ID của job     |
| `type`   | enum   | `VIEW` / `SAVE` / `APPLY`  | Loại tương tác |

**Weights:**
- `VIEW` → `1.0`
- `SAVE` → `2.5`
- `APPLY` → `5.0`

**Response:**
```json
{ "status": "ok" }
```

---

### `GET /recommendations/{user_id}`

Lấy danh sách gợi ý việc làm cá nhân hóa cho user.

**Path params:**
- `user_id` — MongoDB ObjectId của user

**Response:**
```json
{
  "userId": "user-id",
  "recommendations": [
    { "jobId": "job-id-1", "score": 0.9234 },
    { "jobId": "job-id-2", "score": 0.8567 }
  ],
  "source": "model"
}
```

| `source`      | Ý nghĩa                                         |
|---------------|-------------------------------------------------|
| `"model"`     | User có interactions → model dự đoán            |
| `"cold_start"`| User mới, dùng job features từ profile          |
| `"popular"`   | Fallback: top popular jobs                      |

---

### `GET /recommendations/candidates/{job_id}`

Lấy danh sách gợi ý ứng viên phù hợp cho một công việc cụ thể. Kết hợp Vector Search (Retrieval), MaxSim Re-ranking và Rule-based Scoring.

Chi tiết về thuật toán và kiến trúc scoring, xem thêm tại: [candidate-recommendation-spec.md](./candidate-recommendation-spec.md)

**Path params:**
- `job_id` — MongoDB ObjectId của job cần tìm ứng viên

**Query params:**
- `page` (int, default: `1`) — Số trang
- `limit` (int, default: `10`) — Số lượng ứng viên trả về mỗi trang
- `minScore` (float, default: `0.5`) — Điểm chẩn chỉnh tối thiểu (0.0 - 1.0) để lọc ứng viên

**Response:**
```json
{
  "jobId": "67b9c1d...",
  "recommendations": [
    {
      "userId": "user-id-1",
      "candidateProfileId": "profile-id-1",
      "score": 0.85,
      "similarityPercentage": 85,
      "matchedSkills": ["React", "Node.js"],
      "experienceYears": 3,
      "matchReasons": [
        {
          "type": "ai_match",
          "value": "Phù hợp với mô tả công việc (AI đánh giá)",
          "weight": 35
        },
        {
          "type": "skill_match",
          "value": "Khớp 2 kỹ năng: React, Node.js",
          "weight": 16
        }
      ]
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 5,
    "totalItems": 45,
    "limit": 10,
    "hasNextPage": true,
    "hasPrevPage": false
  },
  "source": "vector_search_maxsim_rulebased"
}
```

---

### `POST /retrain`

Trigger full retrain toàn bộ model LightFM.

**Response:**
```json
{
  "status": "ok",
  "users": 1250,
  "jobs": 3400,
  "interactions": 18500,
  "duration_seconds": 12.4
}
```

---

### `POST /partial-update`

Trigger incremental update (`fit_partial`) với interactions mới nhất.

**Response:** tương tự retrain

---

### `GET /health`

Kiểm tra trạng thái model.

**Response:**
```json
{
  "status": "ready",
  "is_ready": true,
  "last_retrain_at": "2026-03-02T02:00:00Z",
  "last_partial_at": "2026-03-02T08:30:00Z",
  "active_jobs": 3400,
  "model_components": 64
}
```
