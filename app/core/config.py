from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "CareerZoneAI Backend"
    # API KEYS
    ELEVENLABS_API_KEY: str 
    ASSEMBLYAI_API_KEY: str
    GITHUB_TOKEN: str
    SIMLI_API_KEY: str
    GEMINI_API_KEY: str
    INTERNAL_API_KEY: str = "careerzone_internal_secret_key"
    # MongoDB
    MONGO_URI: str = ""
    # CLOUDINARY
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "*"
    ]
    class Config:
        env_file = ".env"
        extra = "ignore" # Allow extra fields in .env

settings = Settings()

