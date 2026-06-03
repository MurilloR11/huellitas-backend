import hashlib
import secrets
from datetime import datetime, timezone

from app.extensions import get_db

MAX_KEYS_PER_USER = 5
_KEY_PREFIX = "hll_sk_"
_PREFIX_LENGTH = 16  # hll_sk_ (7) + 9 hex chars


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_key(plain_key: str) -> str:
    return hashlib.sha256(plain_key.encode()).hexdigest()


def list_keys(user_id: str) -> list[dict]:
    db = get_db()
    result = (
        db.table("access_keys")
        .select("id, name, prefix, created_at, last_used_at, active")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def create_key(user_id: str, name: str) -> dict:
    db = get_db()

    active_result = (
        db.table("access_keys")
        .select("id")
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if len(active_result.data or []) >= MAX_KEYS_PER_USER:
        raise ValueError(f"Máximo {MAX_KEYS_PER_USER} keys activas por usuario")

    raw = secrets.token_hex(32)
    plain_key = _KEY_PREFIX + raw
    prefix = plain_key[:_PREFIX_LENGTH]

    row = {
        "user_id": user_id,
        "name": name,
        "key_hash": _hash_key(plain_key),
        "prefix": prefix,
        "created_at": _now().isoformat(),
        "last_used_at": None,
        "active": True,
    }
    result = db.table("access_keys").insert(row).execute()
    inserted = result.data[0]

    return {
        "id": inserted["id"],
        "name": inserted["name"],
        "prefix": inserted["prefix"],
        "created_at": inserted["created_at"],
        "last_used_at": None,
        "active": True,
        "key": plain_key,
    }


def revoke_key(user_id: str, key_id: str) -> bool:
    db = get_db()
    check = (
        db.table("access_keys")
        .select("id")
        .eq("id", key_id)
        .eq("user_id", user_id)
        .eq("active", True)
        .execute()
    )
    if not check.data:
        return False
    db.table("access_keys").update({"active": False}).eq("id", key_id).execute()
    return True
