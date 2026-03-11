from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "CareerZoneAI Backend"
    # API KEYS
    ELEVENLABS_API_KEY: str
    ASSEMBLYAI_API_KEY: str
    SIMLI_API_KEY: str
    GEMINI_API_KEY: str
    INTERNAL_API_KEY: str = "careerzone_internal_secret_key"
    # LLM Configuration
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    # MongoDB
    MONGO_URI: str = ""
    MONGO_DB_NAME: str = "careerzone"
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "*"
    ]

    # ── Collections ──────────────────────────────────────────────────────────
    JOBS_COLLECTION: str = "jobs"
    CANDIDATES_COLLECTION: str = "candidateprofiles"
    INTERACTIONS_COLLECTION: str = "interactions"

    # ── Recommendation model ─────────────────────────────────────────────────
    MODEL_DIR: str = "./models"
    RETRAIN_HOUR: int = 2
    RETRAIN_MINUTE: int = 0
    PARTIAL_UPDATE_INTERVAL_MINUTES: int = 30
    INTERACTION_DAYS: int = 50

    # LightFM hyper-parameters
    MODEL_NO_COMPONENTS: int = 64
    MODEL_EPOCHS: int = 30
    MODEL_PARTIAL_EPOCHS: int = 5
    MODEL_LEARNING_RATE: float = 0.05
    MODEL_LOSS: str = "warp"
    MODEL_NUM_THREADS: int = 4
    TOP_N: int = 20

    # Interaction weights
    WEIGHT_VIEW: float = 1.0
    WEIGHT_SAVE: float = 2.5
    WEIGHT_APPLY: float = 5.0

    @property
    def model_path(self) -> Path:
        return Path(self.MODEL_DIR)

    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra fields in .env


settings = Settings()
