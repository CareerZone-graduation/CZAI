# CareerZoneAI Backend

Backend API cho CareerZoneAI - được xây dựng bằng FastAPI.

## 🚀 Tính năng

- API phỏng vấn với AI
- Text-to-Speech (ElevenLabs)
- Speech-to-Text (AssemblyAI)
- AI Avatar (D-ID)
- Lưu trữ media (Cloudinary)
- Gemini AI cho xử lý ngôn ngữ tự nhiên

## 📋 Yêu cầu

- Python 3.10 trở lên
- pip (Python package manager)

## 🛠️ Cài đặt

### 1. Clone repository

```bash
git clone https://github.com/your-username/CZAI.git
cd CZAI
```

### 2. Tạo Virtual Environment (venv)

**Windows (PowerShell):**
```powershell
# Tạo virtual environment
python -m venv venv

# Kích hoạt virtual environment
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
# Tạo virtual environment
python -m venv venv

# Kích hoạt virtual environment
venv\Scripts\activate.bat
```

**Linux/macOS:**
```bash
# Tạo virtual environment
python3 -m venv venv

# Kích hoạt virtual environment
source venv/bin/activate
```

> 💡 Khi virtual environment được kích hoạt, bạn sẽ thấy `(venv)` xuất hiện ở đầu dòng lệnh.

### 3. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 4. Cấu hình biến môi trường

Tạo file `.env` trong thư mục gốc của project:

```env
# ElevenLabs - Text to Speech
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=TX3LPaxmHKxFdv7VOQHJ

# AssemblyAI - Speech to Text
ASSEMBLYAI_API_KEY=your_assemblyai_api_key

# Google Gemini AI
GEMINI_API_KEY=your_gemini_api_key

# D-ID - AI Avatar
DID_API_KEY=your_did_api_key

# Cloudinary - Media Storage
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
```

## ▶️ Chạy ứng dụng

### Chạy với Uvicorn

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Ứng dụng sẽ chạy tại: `http://localhost:8000`

### Chạy với Docker

```bash
# Build image
docker build -t czai-backend .

# Chạy container
docker run -p 8000:8000 --env-file .env czai-backend
```

## 📚 API Documentation

Sau khi chạy ứng dụng, truy cập:

- **Swagger UI:** `http://localhost:3001/docs`
- **ReDoc:** `http://localhost:3001/redoc`

## 📁 Cấu trúc Project

```
CZAI/
├── app/
│   ├── __init__.py
│   ├── main.py              # Entry point của ứng dụng
│   ├── api/
│   │   └── v1/
│   │       ├── router.py    # API router chính
│   │       └── endpoints/   # Các endpoint API
│   │           ├── avatar.py
│   │           └── interview.py
│   ├── core/
│   │   └── config.py        # Cấu hình ứng dụng
│   ├── models/              # Pydantic models
│   │   ├── chat.py
│   │   └── did.py
│   └── services/            # Business logic
│       ├── cloudinary_service.py
│       ├── did_service.py
│       ├── llm_service.py
│       ├── stt_service.py
│       └── tts_service.py
├── static/                  # Static files
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🔧 Các lệnh hữu ích

### Tắt Virtual Environment

```bash
deactivate
```

### Cập nhật dependencies

```bash
pip install --upgrade -r requirements.txt
```

### Freeze dependencies hiện tại

```bash
pip freeze > requirements.txt
```

### Kiểm tra phiên bản Python trong venv

```bash
python --version
```

## 🐛 Xử lý lỗi thường gặp

### Lỗi khi kích hoạt venv trên Windows PowerShell

Nếu gặp lỗi về execution policy, chạy lệnh sau với quyền Administrator:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Lỗi thiếu module

```bash
pip install <tên_module>
```

### Lỗi port đã được sử dụng

Thay đổi port trong lệnh chạy:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📄 License

MIT License

## 👥 Đóng góp

Mọi đóng góp đều được hoan nghênh! Vui lòng tạo Pull Request hoặc Issue.
