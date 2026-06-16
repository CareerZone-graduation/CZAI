# CareerZoneAI — Data Models

> **Version:** 1.0 | **Date:** 2026-03-02

---

## 1. Request / Response Models (Pydantic)

### 1.1 Interview — `app/models/chat.py`

#### `ChatRequest`
```python
class ChatRequest(BaseModel):
    sessionId: str           # UUID định danh phiên phỏng vấn
    message: str = ""        # Tin nhắn của user (rỗng khi isStart=true)
    isStart: bool = False    # true để bắt đầu phiên mới
    topic: Optional[str]     # Chủ đề phỏng vấn (vd: "Python Backend")
    avatarType: Optional[str] = "live2d"  # "simli" | "live2d"
```

#### `TTSRequest`
```python
class TTSRequest(BaseModel):
    text: str  # Text cần chuyển thành giọng nói
```

#### `TranscribeRequest`
```python
class TranscribeRequest(BaseModel):
    audioData: str  # Base64-encoded audio bytes
```

#### `EndInterviewRequest`
```python
class EndInterviewRequest(BaseModel):
    sessionId: str  # UUID của phiên cần kết thúc
```

#### `SimliSessionRequest`
```python
class SimliSessionRequest(BaseModel):
    faceId: str                    # Face ID từ Simli AI
    maxSessionLength: int = 3600   # Thời gian tối đa (giây)
```

---

### 1.2 Embeddings — `app/models/embedding.py`

#### `QueryEmbeddingRequest`
```python
class QueryEmbeddingRequest(BaseModel):
    query: str                                         # Text cần embed
    model: Optional[str] = "models/gemini-embedding-001"  # Gemini model ID
```

---

### 1.3 Similar Jobs — `app/api/v1/endpoints/similar_jobs.py` (inline models)

#### `SimilarJobsRequest`
```python
class SimilarJobsRequest(BaseModel):
    job_id: str         # Source job MongoDB ObjectId
    limit: int = 6      # Số kết quả (1–20)
```

#### `SimilarJobResult`
```python
class SimilarJobResult(BaseModel):
    job_id: str
    similarity_score: float
```

#### `SimilarJobsResponse`
```python
class SimilarJobsResponse(BaseModel):
    success: bool = True
    data: list[SimilarJobResult]
```

---

### 1.4 Recommendations — `app/models/recommendation.py`

#### `InteractionType`
```python
class InteractionType(str, Enum):
    VIEW  = "VIEW"
    SAVE  = "SAVE"
    APPLY = "APPLY"
```

#### `InteractionRequest`
```python
class InteractionRequest(BaseModel):
    userId: str              # User MongoDB ObjectId
    jobId: str               # Job MongoDB ObjectId
    type: InteractionType    # Loại tương tác
```

#### `JobScore`
```python
class JobScore(BaseModel):
    jobId: str    # Job MongoDB ObjectId
    score: float  # LightFM prediction score (higher = more relevant)
```

#### `RecommendationResponse`
```python
class RecommendationResponse(BaseModel):
    userId: str
    recommendations: list[JobScore]
    source: str  # "model" | "cold_start" | "popular"
```

---

## 2. MongoDB Documents

### 2.1 `interactions` collection

```json
{
  "_id": ObjectId,
  "userId": "string (MongoDB ObjectId)",
  "jobId": "string (MongoDB ObjectId)",
  "type": "VIEW | SAVE | APPLY",
  "createdAt": ISODate
}
```

**Indexes:**
```
idx_user_job_type: { userId: 1, jobId: 1, type: 1 }
idx_created_at:    { createdAt: 1 }
```

---

### 2.2 `jobs` collection (read-only, managed by Node.js)

Các fields được dùng bởi AI service:

```json
{
  "_id": ObjectId,
  "title": "string",
  "status": "ACTIVE | ...",
  "category": "IT | ...",
  "type": "FULL_TIME | PART_TIME | CONTRACT | INTERNSHIP | ...",
  "workType": "ONSITE | REMOTE | HYBRID",
  "experience": "INTERN | FRESHER | JUNIOR | MID | SENIOR_LEVEL | LEAD | ...",
  "area": "NORTH | SOUTH | CENTRAL | ...",
  "skills": ["Python", "React", "..."],
  "location": {
    "province": "Hà Nội",
    "district": "..."
  },
  "minSalary": Decimal128,
  "maxSalary": Decimal128,
  "chunks": [
    {
      "text": "Job description chunk...",
      "embedding": [0.001, -0.023, ...]  // Gemini embedding vector (1536-dim)
    }
  ]
}
```

---

### 2.3 `candidateprofiles` collection (read-only, managed by Node.js)

Các fields được dùng bởi AI service:

```json
{
  "_id": ObjectId,
  "userId": "string (MongoDB ObjectId)",
  "isOnboarded": true,
  "skills": [
    { "name": "Python", "level": "ADVANCED" }
  ],
  "preferredCategories": ["IT", "Finance"],
  "preferredLocations": [
    { "province": "TP.HCM", "district": "..." }
  ],
  "workPreferences": {
    "workTypes": ["REMOTE", "HYBRID"],
    "contractTypes": ["FULL_TIME"],
    "experienceLevel": ["MID", "SENIOR_LEVEL"]
  }
}
```

---

## 3. Environment Variables

Tất cả env vars được load qua `app/core/config.py` (pydantic-settings):

### 3.1 Required

| Variable             | Mô tả                                |
|---------------------|--------------------------------------|
| `GITHUB_TOKEN`      | Token cho GitHub Models (GPT-4o)     |
| `ELEVENLABS_API_KEY`| ElevenLabs TTS API key               |
| `ASSEMBLYAI_API_KEY`| AssemblyAI STT API key               |
| `SIMLI_API_KEY`     | Simli AI avatar API key              |
| `GEMINI_API_KEY`    | Google Gemini embedding API key      |
| `MONGO_URI`         | MongoDB connection string            |

### 3.2 Optional (có default)

| Variable                         | Default              | Mô tả                               |
|---------------------------------|----------------------|-------------------------------------|
| `INTERNAL_API_KEY`              | `"careerzone_internal_secret_key"` | Secret cho internal endpoints |
| `MONGO_DB_NAME`                 | `"careerzone"`       | MongoDB database name               |
| `API_PREFIX`                    | `"/api/v1"`          | API prefix                          |
| `MODEL_DIR`                     | `"./models"`         | Thư mục lưu model                   |
| `RETRAIN_HOUR`                  | `2`                  | Giờ retrain hằng ngày               |
| `RETRAIN_MINUTE`                | `0`                  | Phút retrain hằng ngày              |
| `PARTIAL_UPDATE_INTERVAL_MINUTES` | `30`               | Chu kỳ partial update (phút)        |
| `INTERACTION_DAYS`              | `30`                 | Số ngày lấy interaction để train    |
| `MODEL_NO_COMPONENTS`           | `64`                 | LightFM latent factors              |
| `MODEL_EPOCHS`                  | `30`                 | Full training epochs                |
| `MODEL_PARTIAL_EPOCHS`          | `5`                  | Partial update epochs               |
| `MODEL_LEARNING_RATE`           | `0.05`               | Learning rate                       |
| `MODEL_LOSS`                    | `"warp"`             | Loss function (`warp` / `bpr`)      |
| `MODEL_NUM_THREADS`             | `4`                  | Training threads                    |
| `TOP_N`                         | `20`                 | Số gợi ý trả về                     |
| `WEIGHT_VIEW`                   | `1.0`                | Weight cho VIEW interaction         |
| `WEIGHT_SAVE`                   | `2.5`                | Weight cho SAVE interaction         |
| `WEIGHT_APPLY`                  | `5.0`                | Weight cho APPLY interaction        |
| `JOBS_COLLECTION`               | `"jobs"`             | Tên collection jobs                 |
| `CANDIDATES_COLLECTION`         | `"candidateprofiles"`| Tên collection candidates           |
| `INTERACTIONS_COLLECTION`       | `"interactions"`     | Tên collection interactions         |
| `BACKEND_CORS_ORIGINS`          | `["http://localhost:5173", ...]` | Allowed CORS origins  |

---

## 4. In-Memory State

| Variable                | Type                          | Module             | Mô tả                        |
|------------------------|-------------------------------|---------------------|------------------------------|
| `interview_sessions`   | `dict[sessionId, list[msg]]`  | `llm_service.py`   | Chat history per session     |
| `interview_topics`     | `dict[sessionId, str]`        | `llm_service.py`   | Topic per session            |
| `engine`               | `RecommendationEngine`        | `model_manager.py` | LightFM engine singleton     |
| `scheduler`            | `AsyncIOScheduler`            | `scheduler.py`     | APScheduler singleton        |
