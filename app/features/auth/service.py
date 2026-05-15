import hashlib
import random
import secrets
import string
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from app.extensions import get_db

BACKUP_CODES_COUNT = 10
BACKUP_CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # sin 0/O/1/l/I


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _generate_code() -> str:
    segments = ["".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(segments)

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


def get_verified_mfa_factor(user_id: str) -> dict | None:
    """Return the first verified TOTP factor for a user, or None."""
    url = current_app.config["SUPABASE_URL"]
    key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}", "apikey": key}

    resp = requests.get(
        f"{url}/auth/v1/admin/users/{user_id}/factors",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()

    for factor in resp.json():
        if factor.get("status") == "verified" and factor.get("factor_type") == "totp":
            return {"id": factor["id"]}
    return None


def delete_pending_mfa_factors(user_id: str) -> int:
    """Delete all unverified TOTP factors for a user via the Supabase Admin API.
    Returns the count of deleted factors."""
    url = current_app.config["SUPABASE_URL"]
    key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}", "apikey": key}

    resp = requests.get(
        f"{url}/auth/v1/admin/users/{user_id}/factors",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()

    deleted = 0
    for factor in resp.json():
        if factor.get("status") != "verified":
            requests.delete(
                f"{url}/auth/v1/admin/users/{user_id}/factors/{factor['id']}",
                headers=headers,
                timeout=10,
            ).raise_for_status()
            deleted += 1

    return deleted


def generate_backup_codes(user_id: str) -> list[str]:
    db = get_db()
    db.table("backup_codes").delete().eq("user_id", user_id).execute()

    plain_codes = [_generate_code() for _ in range(BACKUP_CODES_COUNT)]
    rows = [{"user_id": user_id, "code_hash": _hash_code(c)} for c in plain_codes]
    db.table("backup_codes").insert(rows).execute()
    return plain_codes


def get_backup_codes_status(user_id: str) -> dict:
    db = get_db()
    result = (
        db.table("backup_codes")
        .select("id, used_at")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data or []
    total = len(rows)
    remaining = sum(1 for r in rows if r["used_at"] is None)
    return {"total": total, "remaining": remaining}


def verify_backup_code(user_id: str, code: str) -> bool:
    db = get_db()
    code_hash = _hash_code(code.strip().lower())
    result = (
        db.table("backup_codes")
        .select("id, used_at")
        .eq("user_id", user_id)
        .eq("code_hash", code_hash)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return False

    entry = rows[0]
    if entry["used_at"] is not None:
        return False

    db.table("backup_codes").update({"used_at": _now().isoformat()}).eq("id", entry["id"]).execute()
    return True


def generate_access_key(user_id: str) -> str:
    db = get_db()
    plain_key = secrets.token_hex(32)
    db.table("access_keys").upsert(
        {
            "user_id": user_id,
            "key_hash": _hash_code(plain_key),
            "created_at": _now().isoformat(),
            "last_used_at": None,
        },
        on_conflict="user_id",
    ).execute()
    return plain_key


def get_access_key_status(user_id: str) -> dict:
    db = get_db()
    result = db.table("access_keys").select("created_at").eq("user_id", user_id).execute()
    rows = result.data or []
    if not rows:
        return {"has_key": False, "created_at": None}
    return {"has_key": True, "created_at": rows[0]["created_at"]}


def revoke_access_key(user_id: str) -> None:
    db = get_db()
    db.table("access_keys").delete().eq("user_id", user_id).execute()


def login_with_access_key(user_id: str, plain_key: str) -> dict | None:
    db = get_db()
    key_hash = _hash_code(plain_key.strip())

    result = db.table("access_keys").select("id, key_hash").eq("user_id", user_id).execute()
    rows = result.data or []
    if not rows or rows[0]["key_hash"] != key_hash:
        return None

    db.table("access_keys").update({"last_used_at": _now().isoformat()}).eq("id", rows[0]["id"]).execute()

    profile_result = db.table("profiles").select("email").eq("id", user_id).execute()
    profile_rows = profile_result.data or []
    if not profile_rows:
        return None
    email = profile_rows[0]["email"]

    url = current_app.config["SUPABASE_URL"]
    svc_key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {
        "Authorization": f"Bearer {svc_key}",
        "apikey": svc_key,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{url}/auth/v1/admin/generate_link",
        headers=headers,
        json={"type": "magiclink", "email": email},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"hashed_token": data["hashed_token"]}


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
