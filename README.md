# CareerZoneAI Backend

Backend AI cho nền tảng CareerZone, được xây dựng bằng **FastAPI (Python)**. Đây là microservice xử lý các tác vụ AI/ML, hoạt động song song với backend chính Node.js/Express.

## Tính năng

- **Phỏng vấn AI**: Vòng lặp LLM → TTS → stream PCM16 audio đến client
- **Text-to-Speech**: ElevenLabs streaming
- **Speech-to-Text**: AssemblyAI (hỗ trợ tiếng Việt)
- **Avatar AI**: Simli AI (WebRTC session tokens & ICE servers)
- **Embeddings & Tìm việc tương tự**: Google Gemini Embedding + MongoDB Atlas `$vectorSearch`
- **Hệ thống gợi ý việc làm**: LightFM hybrid collaborative filtering + content-based

## Yêu cầu

- Python 3.10+
- MongoDB (Atlas hoặc local)

## Cài đặt

### 1. Clone repository

```bash
git clone https://github.com/your-username/CZAI.git
cd CZAI
```

### 2. Tạo Virtual Environment

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 4. Cấu hình biến môi trường

Tạo file `.env` trong thư mục gốc:

```env
# API Keys
ASSEMBLYAI_API_KEY=
ELEVENLABS_API_KEY=
SIMLI_API_KEY=
GEMINI_API_KEY=
INTERNAL_API_KEY=

# LLM Configuration
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=

# MongoDB
MONGO_URI=
MONGO_DB_NAME=
```

## Chạy ứng dụng

### Uvicorn (development)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Ứng dụng sẽ chạy tại: `http://localhost:8000`

### Docker

```bash
# Build image
docker build -t czai-backend .

# Chạy container
docker run -p 8000:8000 --env-file .env czai-backend
```

## API Documentation

Sau khi chạy ứng dụng:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## Các endpoint chính

Tất cả endpoint có prefix `/api/v1`.

### Phỏng vấn AI

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/chat` | Chat phỏng vấn AI – trả về stream PCM16 audio + AI text trong header `X-AI-Response` |
| `POST` | `/tts` | Chuyển text thành audio |
| `POST` | `/transcribe` | Chuyển audio (base64) thành text |
| `POST` | `/end` | Kết thúc phiên phỏng vấn |

### Avatar Simli

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/simli/get-session-token` | Lấy session token từ Simli AI |
| `GET` | `/simli/get-ice-servers` | Lấy ICE servers cho WebRTC |

### Embeddings & Tìm việc tương tự

Được bảo vệ bằng header `X-Internal-Secret`.

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/embeddings/query-embedding` | Tạo text embedding qua Gemini API |
| `POST` | `/embeddings/similar-jobs` | Tìm việc làm tương tự qua `$vectorSearch` |

### Hệ thống gợi ý

Được bảo vệ bằng header `X-Internal-Secret`.

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/interactions` | Ghi nhận tương tác người dùng – job (`VIEW`/`SAVE`/`APPLY`) |
| `GET` | `/recommendations/{user_id}` | Lấy danh sách việc làm gợi ý cá nhân hóa |
| `POST` | `/retrain` | Kích hoạt train lại toàn bộ model |
| `POST` | `/partial-update` | Kích hoạt cập nhật tăng dần model |
| `GET` | `/health` | Kiểm tra trạng thái model |

## Hệ thống gợi ý việc làm (LightFM)

Model LightFM hybrid, kết hợp collaborative filtering và content-based filtering.

**Features dùng chung** cho cả user và job: `skill:python`, `province:ho_chi_minh`, `salary:10m_15m`, `category:IT`, `worktype:REMOTE`, v.v.

**Trọng số tương tác**: `VIEW=1.0`, `SAVE=2.5`, `APPLY=5.0`

**Lịch train tự động**:
- Train toàn bộ: mỗi ngày lúc 2:00 AM
- Cập nhật tăng dần: mỗi 30 phút

**Cold-start**: User mới được gợi ý dựa trên features từ hồ sơ; fallback về việc làm phổ biến nếu không có hồ sơ.

**Model artifacts** được lưu tại `./models/` (joblib), tự động rebuild khi khởi động nếu chưa có.

### Đánh giá model

```bash
# Đánh giá nhanh model hiện tại
python scripts/evaluate_model.py --mode current --k 10

# Đánh giá offline (train/test split)
python scripts/evaluate_model.py --mode split --ratio 0.2
```

Metrics: Precision@K, Recall@K, AUC, MRR, Hit Rate, Coverage.

## Cấu trúc Project

```
CZAI/
├── app/
│   ├── main.py                          # Entry point, lifespan (DB, model, scheduler)
│   ├── api/
│   │   └── v1/
│   │       ├── router.py                # Router tổng hợp
│   │       └── endpoints/
│   │           ├── interview.py         # Chat, TTS, STT, end session
│   │           ├── simli.py             # Avatar session
│   │           ├── embeddings.py        # Embeddings & similar jobs
│   │           └── recommendation.py   # Recommendations & interactions
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings (env vars)
│   │   └── database.py                  # Motor MongoDB client
│   ├── models/                          # Pydantic request/response schemas
│   ├── services/
│   │   ├── llm_service.py               # GitHub Models (gpt-4o)
│   │   ├── tts_service.py               # ElevenLabs TTS
│   │   ├── stt_service.py               # AssemblyAI STT
│   │   └── recommendation/
│   │       ├── model_manager.py         # RecommendationEngine singleton
│   │       ├── feature_engineering.py   # Shared feature namespace
│   │       ├── data_loader.py           # MongoDB queries
│   │       ├── scheduler.py             # APScheduler cron jobs
│   │       └── evaluator.py             # Offline evaluation metrics
│   └── utils/
│       └── text_utils.py                # Chuẩn hóa kỹ năng, tỉnh/thành, mức lương
├── scripts/
│   └── evaluate_model.py                # Script đánh giá model
├── models/                              # Model artifacts (gitignored)
├── Dockerfile
├── requirements.txt
└── README.md
```

## Các lệnh hữu ích

```bash
# Tắt virtual environment
deactivate

# Cập nhật dependencies
pip install --upgrade -r requirements.txt

# Freeze dependencies hiện tại
pip freeze > requirements.txt
```

## License

MIT License
