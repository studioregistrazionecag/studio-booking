from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "dev"
    SECRET_KEY: str
    JWT_EXPIRES_MIN: int = 1440

    # DB
    DB_URL: str

    # Gmail / Calendar (possono essere None in dev: in quel caso si logga soltanto)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REFRESH_TOKEN: str | None = None
    EMAIL_FROM: str | None = None
    GOOGLE_CALENDAR_ID: str | None = None

    # Link pubblico per email/reset (ES: http://127.0.0.1:8000)
    # NB: lo usiamo per costruire i link del reset password -> /frontend/auth/reset.html
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    # --- NEON API (card statistiche) ---
    NEON_API_KEY: str | None = None
    NEON_PROJECT_ID: str | None = None

    # === NEW === Manutenzione
    MAINTENANCE_MODE: bool = False  # se true, / e /login → pagina offline

    # Email manager (opzionale): CSV/; o newline. Se vuoto -> fallback ai manager nel DB.
    MANAGER_EMAILS: str | None = None


settings = Settings()