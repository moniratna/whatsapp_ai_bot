from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    OPENWA_BASE_URL: str
    OPENWA_API_KEY: str
    OPENWA_SESSION_ID: str

    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str
    BEDROCK_BASE_URL: str
    AWS_BEARER_TOKEN_BEDROCK: str
    BEDROCK_TIMEOUT_SECONDS: float = 45.0

    CRM_WEBHOOK_URL: str = ""
    CRM_API_KEY: str = ""
    DASHBOARD_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
