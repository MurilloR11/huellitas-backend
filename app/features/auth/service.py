import random
import secrets
from datetime import datetime, timedelta, timezone

from app.extensions import get_db

OTP_TTL_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_and_send_otp(email: str) -> bool:
    db = get_db()
    result = db.table("profiles").select("id").eq("email", email).execute()
    if not (result.data or []):
        return False

    otp = f"{random.randint(0, 9999):04d}"
    expires_at = (_now() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()

    db.table("otp_store").upsert({
        "email": email,
        "otp": otp,
        "expires_at": expires_at,
        "verified_token": None,
    }).execute()

    from app.shared.utils.email import send_password_reset_otp
    send_password_reset_otp(email, otp)
    return True


def verify_otp(email: str, otp: str) -> str | None:
    db = get_db()
    result = db.table("otp_store").select("*").eq("email", email).execute()
    rows = result.data or []
    if not rows:
        return None

    entry = rows[0]
    expires_at = datetime.fromisoformat(entry["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if _now() > expires_at:
        db.table("otp_store").delete().eq("email", email).execute()
        return None
    if entry["otp"] != otp:
        return None

    reset_token = secrets.token_urlsafe(32)
    db.table("otp_store").update({
        "verified_token": reset_token,
        "otp": None,
    }).eq("email", email).execute()
    return reset_token


def reset_password(email: str, reset_token: str, new_password: str) -> bool:
    db = get_db()
    result = db.table("otp_store").select("*").eq("email", email).execute()
    rows = result.data or []
    if not rows:
        return False

    entry = rows[0]
    if entry.get("verified_token") != reset_token:
        return False

    expires_at = datetime.fromisoformat(entry["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if _now() > expires_at:
        db.table("otp_store").delete().eq("email", email).execute()
        return False

    result = db.table("profiles").select("id").eq("email", email).execute()
    rows = result.data or []
    if not rows:
        return False

    user_id = rows[0]["id"]
    db.auth.admin.update_user_by_id(user_id, {"password": new_password})
    db.table("otp_store").delete().eq("email", email).execute()
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
