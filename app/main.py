from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(title=settings.PROJECT_NAME)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Đăng ký Router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Welcome to CareerZoneAI Python Backend"}

if __name__ == "__main__":
    import uvicorn
    # Should likely change port if running alongside Node.js, but replacing it means reusing 8000
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
