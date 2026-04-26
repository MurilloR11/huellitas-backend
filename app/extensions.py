from supabase import create_client, Client
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from jwt import PyJWKClient

limiter = Limiter(key_func=get_remote_address)

_supabase: Client | None = None
_jwks_client: PyJWKClient | None = None


def init_extensions(app) -> None:
    global _supabase, _jwks_client
    _supabase = create_client(
        app.config["SUPABASE_URL"],
        app.config["SUPABASE_SERVICE_ROLE_KEY"],
    )
    if not app.config.get("SUPABASE_USE_JWKS") == False:
        _jwks_client = PyJWKClient(
            f"{app.config['SUPABASE_URL']}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    limiter.init_app(app)
    CORS(
        app,
        origins=[app.config.get("FRONTEND_URL", "http://localhost:5173")],
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        supports_credentials=True,
    )


def get_jwks_client() -> PyJWKClient | None:
    return _jwks_client


def get_db() -> Client:
    if _supabase is None:
        raise RuntimeError("Supabase client not initialised. Call init_extensions first.")
    return _supabase
