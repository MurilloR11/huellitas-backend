import logging
from functools import wraps

import jwt
from flask import g, jsonify, request, current_app

logger = logging.getLogger(__name__)


def _extract_bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip() or None
    return None


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

    return {"user_id": user_id, "role": rows[0].get("role")}, None


def require_auth(f):
    """Verify the Supabase JWT. Any authenticated user is allowed.

    Sets g.user_id and g.user_role on success.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({"error": "Authentication required"}), 401

        user, err = _load_user(token)
        if err:
            return err

        g.user_id = user["user_id"]
        g.user_role = user["role"]
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

        g.user_id = user["user_id"]
        g.user_role = user["role"]
        return f(*args, **kwargs)

    return decorated
