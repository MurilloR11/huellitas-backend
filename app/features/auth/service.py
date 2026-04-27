import random
import secrets
from datetime import datetime, timedelta, timezone

from app.extensions import get_db

# In-memory OTP store: { email: { otp, expires_at, verified_token } }
_otp_store: dict = {}

OTP_TTL_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_and_send_otp(email: str) -> bool:
    """Generate a 4-digit OTP, store it, and send the email. Returns False if email not found."""
    db = get_db()
    result = db.table("profiles").select("id").eq("email", email).execute()
    if not (result.data or []):
        return False

    otp = f"{random.randint(0, 9999):04d}"
    _otp_store[email] = {
        "otp": otp,
        "expires_at": _now() + timedelta(minutes=OTP_TTL_MINUTES),
        "verified_token": None,
    }

    from app.shared.utils.email import send_password_reset_otp
    send_password_reset_otp(email, otp)
    return True


def verify_otp(email: str, otp: str) -> str | None:
    """Verify OTP. Returns a one-time reset token on success, None on failure."""
    entry = _otp_store.get(email)
    if not entry:
        return None
    if _now() > entry["expires_at"]:
        _otp_store.pop(email, None)
        return None
    if entry["otp"] != otp:
        return None

    reset_token = secrets.token_urlsafe(32)
    entry["verified_token"] = reset_token
    entry["otp"] = None  # invalidate OTP after verification
    return reset_token


def reset_password(email: str, reset_token: str, new_password: str) -> bool:
    """Reset password using the token issued after OTP verification."""
    entry = _otp_store.get(email)
    if not entry or entry.get("verified_token") != reset_token:
        return False
    if _now() > entry["expires_at"]:
        _otp_store.pop(email, None)
        return False

    db = get_db()
    result = db.table("profiles").select("id").eq("email", email).execute()
    rows = result.data or []
    if not rows:
        return False

    user_id = rows[0]["id"]
    db.auth.admin.update_user_by_id(user_id, {"password": new_password})
    _otp_store.pop(email, None)
    return True


def get_profile(user_id: str) -> dict | None:
    db = get_db()

    result = (
        db.table("profiles")
        .select("id, email, full_name, role")
        .eq("id", user_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    profile = rows[0]

    # status solo existe para fundaciones, se lee desde la tabla foundations
    if profile.get("role") == "fundacion":
        found = (
            db.table("foundations")
            .select("status")
            .eq("id", user_id)
            .execute()
        )
        found_rows = found.data or []
        profile["status"] = found_rows[0].get("status") if found_rows else None
    else:
        profile["status"] = None

    return profile
