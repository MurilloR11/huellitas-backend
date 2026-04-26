import logging
from datetime import datetime, timezone

from app.extensions import get_db

logger = logging.getLogger(__name__)

_FOUNDATION_SELECT = (
    "id, org_name, municipio, phone, description, logo, instagram, status, created_at, "
    "profiles!foundations_id_fkey(email)"
)


# ── Public endpoints ───────────────────────────────────────────────────────────

def list_foundations(params: dict) -> dict:
    page = params.get("page", 1)
    per_page = 20
    offset = (page - 1) * per_page

    db = get_db()
    q = (
        db.table("foundations")
        .select(_FOUNDATION_SELECT, count="exact")
        .eq("status", "approved")
    )

    if params.get("city"):
        q = q.ilike("municipio", f"%{params['city']}%")

    result = q.range(offset, offset + per_page - 1).execute()

    foundations = []
    for row in (result.data or []):
        fid = row.get("id")
        active = (
            db.table("pets").select("id", count="exact")
            .eq("foundation_id", fid).eq("status", "available").execute()
        )
        adopted = (
            db.table("pets").select("id", count="exact")
            .eq("foundation_id", fid).eq("status", "adopted").execute()
        )
        foundations.append(_format_foundation(row, active.count or 0, adopted.count or 0))

    return {
        "data": foundations,
        "total": result.count or 0,
        "page": page,
        "per_page": per_page,
    }


def get_foundation_by_id_public(foundation_id: str) -> dict | None:
    db = get_db()
    result = (
        db.table("foundations")
        .select(_FOUNDATION_SELECT)
        .eq("id", foundation_id)
        .eq("status", "approved")
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    row = rows[0]
    fid = row.get("id")
    active = (
        db.table("pets").select("id", count="exact")
        .eq("foundation_id", fid).eq("status", "available").execute()
    )
    adopted = (
        db.table("pets").select("id", count="exact")
        .eq("foundation_id", fid).eq("status", "adopted").execute()
    )
    return _format_foundation(row, active.count or 0, adopted.count or 0)


def _format_foundation(row: dict, active_count: int, adopted_count: int) -> dict:
    profile = (row.pop("profiles", None) or {})
    return {
        "id": row.get("id"),
        "name": row.get("org_name", ""),
        "city": row.get("municipio", ""),
        "description": row.get("description", ""),
        "logo": row.get("logo"),
        "contact_email": profile.get("email", ""),
        "contact_phone": row.get("phone"),
        "instagram": row.get("instagram"),
        "active_pets_count": active_count,
        "adopted_pets_count": adopted_count,
        "created_at": row.get("created_at"),
    }


# ── Admin endpoints ────────────────────────────────────────────────────────────

def get_pending_foundations() -> list[dict]:
    result = (
        get_db()
        .table("foundations")
        .select("id, org_name, municipio, phone, status, profiles!foundations_id_fkey(email, full_name)")
        .eq("status", "pending")
        .execute()
    )
    return result.data or []


def get_foundation_with_profile(foundation_id: str) -> dict | None:
    result = (
        get_db()
        .table("foundations")
        .select("id, org_name, municipio, phone, status, profiles!foundations_id_fkey(email, full_name)")
        .eq("id", foundation_id)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def approve_foundation(foundation_id: str, admin_id: str) -> dict | None:
    """Set status to 'approved'. Returns the updated row, or None if not found / already reviewed."""
    now = datetime.now(timezone.utc).isoformat()
    result = (
        get_db()
        .table("foundations")
        .update(
            {
                "status": "approved",
                "reviewed_by": admin_id,
                "reviewed_at": now,
            }
        )
        .eq("id", foundation_id)
        .eq("status", "pending")   # idempotency guard
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def reject_foundation(
    foundation_id: str,
    admin_id: str,
    reason: str,
) -> dict | None:
    """Set status to 'rejected'. Returns the updated row, or None if not found / already reviewed."""
    now = datetime.now(timezone.utc).isoformat()
    result = (
        get_db()
        .table("foundations")
        .update(
            {
                "status": "rejected",
                "rejection_reason": reason,
                "reviewed_by": admin_id,
                "reviewed_at": now,
            }
        )
        .eq("id", foundation_id)
        .eq("status", "pending")   # idempotency guard
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None
