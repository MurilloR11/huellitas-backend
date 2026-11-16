import os
from dotenv import load_dotenv

load_dotenv()

_REQUIRED = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "SENDGRID_API_KEY",
)


class Config:
    # Use get() so the class can be imported without env vars present.
    # create_app() calls validate_config() to enforce required vars at startup.
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_JWT_SECRET: str = os.environ.get("SUPABASE_JWT_SECRET", "")
    SENDGRID_API_KEY: str = os.environ.get("SENDGRID_API_KEY", "")
    EMAIL_FROM: str = os.environ.get("EMAIL_FROM", "Huellitas <noreply@huellitas.app>")
    FRONTEND_URL: str = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    CORS_ORIGINS: list = [
        o.strip().rstrip("/")
        for o in os.environ.get(
            "CORS_ORIGINS",
            os.environ.get("FRONTEND_URL", "http://localhost:5173")
            + ",http://localhost:5173,http://localhost:3000",
        ).split(",")
        if o.strip()
    ]
    RATELIMIT_STORAGE_URI: str = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    # IDs (UUID) de las cuentas de demo públicas, separados por coma.
    # Estas cuentas solo pueden leer: cualquier escritura responde 403.
    DEMO_USER_IDS: str = os.environ.get("DEMO_USER_IDS", "")
    TESTING: bool = False

    @classmethod
    def validate(cls) -> None:
        missing = [k for k in _REQUIRED if not getattr(cls, k, None)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


class TestConfig(Config):
    TESTING = True
    SUPABASE_USE_JWKS = False   # use HS256 + secret in tests, no network call
    SUPABASE_URL = "https://test.supabase.co"
    SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key"
    SUPABASE_JWT_SECRET = "test-jwt-secret-that-is-long-enough-for-hs256"
    EMAIL_API_KEY = "test-email-key"
    RATELIMIT_STORAGE_URI = "memory://"
