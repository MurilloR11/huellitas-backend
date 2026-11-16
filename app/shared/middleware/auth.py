import hashlib
import logging
import time
from functools import wraps

import jwt
from flask import g, jsonify, request, current_app

logger = logging.getLogger(__name__)

# In-memory role cache — avoids a DB round-trip on every authenticated request.
# TTL of 60 s is short enough to pick up role changes quickly.
_ROLE_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 60.0


def _get_cached_role(user_id: str) -> str | None:
    entry = _ROLE_CACHE.get(user_id)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    return None


def _set_cached_role(user_id: str, role: str) -> None:
    _ROLE_CACHE[user_id] = (role, time.monotonic() + _CACHE_TTL)


# ---------------------------------------------------------------------------
# Modo demo: cuentas públicas de solo lectura
# ---------------------------------------------------------------------------
_DEMO_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Escrituras inofensivas permitidas a las cuentas demo (registro de login/logout).
_DEMO_ALLOWED_WRITES = {("POST", "/auth/activity")}


def _demo_user_ids() -> set[str]:
    raw = current_app.config.get("DEMO_USER_IDS") or ""
    return {uid.strip() for uid in raw.split(",") if uid.strip()}


def is_demo_user(user_id: str | None) -> bool:
    return bool(user_id) and user_id in _demo_user_ids()


def _demo_write_blocked(user_id: str):
    """Marca g.is_demo y devuelve un 403 si una cuenta demo intenta escribir."""
    if not is_demo_user(user_id):
        return None
    g.is_demo = True
    if request.method in _DEMO_SAFE_METHODS:
        return None
    if (request.method, request.path.rstrip("/")) in _DEMO_ALLOWED_WRITES:
        return None
    return jsonify({
        "error": "Modo demo: esta cuenta es de solo lectura",
        "demo": True,
    }), 403


def _extract_bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip() or None
    return None


def _extract_api_key() -> str | None:
    return request.headers.get("X-API-Key", "").strip() or None


def _load_user_from_api_key(plain_key: str) -> tuple[dict | None, tuple | None]:
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

    try:
        from app.extensions import get_db
        db = get_db()
        result = (
            db.table("access_keys")
            .select("id, user_id")
            .eq("key_hash", key_hash)
            .eq("active", True)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("DB error while validating API key")
        return None, (jsonify({"error": "Authentication failed"}), 401)

    rows = result.data or []
    if not rows:
        return None, (jsonify({"error": "Invalid API key"}), 401)

    row = rows[0]
    user_id: str = row["user_id"]
    key_id: str = row["id"]

    try:
        from datetime import datetime, timezone
        from app.extensions import get_db as _get_db
        _get_db().table("access_keys").update(
            {"last_used_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", key_id).execute()
    except Exception:
        logger.warning("Failed to update last_used_at for key %s", key_id)

    cached = _get_cached_role(user_id)
    if cached is not None:
        return {"user_id": user_id, "role": cached, "key_id": key_id}, None

    try:
        from app.extensions import get_db as _get_db2
        role_result = _get_db2().table("profiles").select("role").eq("id", user_id).execute()
        role_rows = role_result.data or []
        if not role_rows:
            return None, (jsonify({"error": "User not found"}), 401)
        role = role_rows[0].get("role")
        _set_cached_role(user_id, role)
        return {"user_id": user_id, "role": role, "key_id": key_id}, None
    except Exception:
        logger.exception("DB error loading role for user %s", user_id)
        return None, (jsonify({"error": "Authentication failed"}), 401)


def _decode_token(token: str) -> dict:
    """Verify and decode a Supabase JWT.

    Production: uses JWKS (supports ES256 / RS256 — whatever Supabase signs with).
    Testing:    falls back to HS256 with SUPABASE_JWT_SECRET to avoid network calls.
    """
    from app.extensions import get_jwks_client

    jwks = get_jwks_client()
    if jwks is not None:
        try:
            signing_key = jwks.get_signing_key_from_jwt(token)
        except Exception as exc:
            # Network error, key not in JWKS, algorithm mismatch, etc.
            raise jwt.InvalidTokenError(f"JWKS lookup failed: {exc}") from exc
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )

    # Test path: HS256 with symmetric secret
    return jwt.decode(
        token,
        current_app.config["SUPABASE_JWT_SECRET"],
        algorithms=["HS256"],
        audience="authenticated",
        options={"require": ["sub", "exp"]},
    )


def _load_user(token: str) -> tuple[dict | None, tuple | None]:
    """Decode JWT and load the user profile from DB.

    Returns (user_info, None) on success or (None, error_response) on failure.
    """
    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        return None, (jsonify({"error": "Token expired"}), 401)
    except jwt.InvalidTokenError:
        return None, (jsonify({"error": "Invalid token"}), 401)

    user_id: str | None = payload.get("sub")
    if not user_id:
        return None, (jsonify({"error": "Invalid token"}), 401)

    cached = _get_cached_role(user_id)
    if cached is not None:
        return {"user_id": user_id, "role": cached}, None

    try:
        from app.extensions import get_db
        result = (
            get_db()
            .table("profiles")
            .select("role")
            .eq("id", user_id)
            .execute()
        )
    except Exception:
        logger.exception("DB error while loading user_id=%s", user_id)
        return None, (jsonify({"error": "Authentication failed"}), 401)

    rows = result.data or []
    if not rows:
        # Profile missing — the Supabase trigger may have failed at sign-up.
        # Auto-create it from JWT claims so the user isn't permanently locked out.
        try:
            from app.extensions import get_db as _get_db
            meta = payload.get("user_metadata") or {}
            role_raw = meta.get("role", "ciudadano")
            # Mirror the trigger: prevent self-assignment of admin role.
            if role_raw not in ("ciudadano", "fundacion", "developer"):
                role_raw = "ciudadano"
            _get_db().table("profiles").insert({
                "id": user_id,
                "email": payload.get("email") or meta.get("email", ""),
                "full_name": meta.get("full_name", ""),
                "role": role_raw,
            }).execute()
            rows = [{"role": role_raw}]
            logger.warning("Auto-created missing profile for user_id=%s role=%s", user_id, role_raw)
        except Exception:
            logger.exception("Failed to auto-create profile for user_id=%s", user_id)
            return None, (jsonify({"error": "User not found"}), 401)

    role = rows[0].get("role")
    _set_cached_role(user_id, role)
    return {"user_id": user_id, "role": role}, None


def optional_api_key(f):
    """If X-API-Key is present and valid, populate g.api_key_id / g.user_id / g.user_role.
    Never blocks the request — public endpoints stay public.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = _extract_api_key()
        if api_key:
            user, err = _load_user_from_api_key(api_key)
            if user and not err:
                g.user_id   = user["user_id"]
                g.user_role = user["role"]
                g.api_key_id = user.get("key_id")
        return f(*args, **kwargs)
    return decorated


def require_auth(f):
    """Verify auth via X-API-Key header or Supabase JWT Bearer token.

    Sets g.user_id and g.user_role on success.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = _extract_api_key()
        if api_key:
            user, err = _load_user_from_api_key(api_key)
        else:
            token = _extract_bearer_token()
            if not token:
                return jsonify({"error": "Authentication required"}), 401
            user, err = _load_user(token)

        if err:
            return err

        blocked = _demo_write_blocked(user["user_id"])
        if blocked:
            return blocked

        g.user_id = user["user_id"]
        g.user_role = user["role"]
        if api_key:
            g.api_key_id = user.get("key_id")
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    """Verify the Supabase JWT and confirm role == 'admin' in the profiles table."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({"error": "Authentication required"}), 401

        user, err = _load_user(token)
        if err:
            return err

        if user["role"] != "admin":
            return jsonify({"error": "Forbidden"}), 403

        blocked = _demo_write_blocked(user["user_id"])
        if blocked:
            return blocked

        g.user_id = user["user_id"]
        g.user_role = user["role"]
        return f(*args, **kwargs)

    return decorated
