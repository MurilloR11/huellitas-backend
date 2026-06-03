import logging
from datetime import date, datetime, timezone

from app.extensions import get_db

logger = logging.getLogger(__name__)

_FOUNDATION_SELECT = (
    "id, org_name, municipio, phone, status, "
    "profiles!foundations_id_fkey(email, created_at)"
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
        "contact_email": profile.get("email", ""),
        "contact_phone": row.get("phone"),
        "active_pets_count": active_count,
        "adopted_pets_count": adopted_count,
        "created_at": profile.get("created_at"),
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


def get_my_pets(*, foundation_id: str) -> list[dict]:
    _PET_SELECT = (
        "id, name, species, breed, age_months, gender, size, description, "
        "photos, status, foundation_id, city, created_at, "
        "vaccinated, sterilized, dewormed, microchipped, health_notes, "
        "foundations(org_name)"
    )
    result = (
        get_db()
        .table("pets")
        .select(_PET_SELECT)
        .eq("foundation_id", foundation_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_format_pet(r) for r in (result.data or [])]


def _format_pet(row: dict) -> dict:
    foundation = row.pop("foundations", None) or {}
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "species": row.get("species"),
        "breed": row.get("breed"),
        "age_months": row.get("age_months"),
        "gender": row.get("gender"),
        "size": row.get("size"),
        "description": row.get("description"),
        "photos": row.get("photos") or [],
        "status": row.get("status"),
        "foundation_id": row.get("foundation_id"),
        "foundation_name": foundation.get("org_name", ""),
        "city": row.get("city"),
        "created_at": row.get("created_at"),
        "clinical_record": {
            "vaccinated": bool(row.get("vaccinated", False)),
            "sterilized": bool(row.get("sterilized", False)),
            "dewormed": bool(row.get("dewormed", False)),
            "microchipped": bool(row.get("microchipped", False)),
            "health_notes": row.get("health_notes"),
        },
    }


_FOUNDATION_ADOPTION_SELECT = (
    "id, pet_id, adopter_id, foundation_id, status, message, form_data, created_at, updated_at, "
    "pets(name, photos), "
    "profiles!adoption_requests_adopter_id_fkey(full_name, email)"
)


def get_my_adoptions(*, foundation_id: str) -> list[dict]:
    result = (
        get_db()
        .table("adoption_requests")
        .select(_FOUNDATION_ADOPTION_SELECT)
        .eq("foundation_id", foundation_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_format_foundation_adoption(r) for r in (result.data or [])]


def _format_foundation_adoption(row: dict) -> dict:
    pet = row.pop("pets", None) or {}
    adopter = row.pop("profiles", None) or {}
    photos = pet.get("photos") or []
    return {
        "id": row.get("id"),
        "pet_id": row.get("pet_id"),
        "pet_name": pet.get("name", ""),
        "pet_photo": photos[0] if photos else None,
        "adopter_id": row.get("adopter_id"),
        "adopter_name": adopter.get("full_name", ""),
        "adopter_email": adopter.get("email", ""),
        "foundation_id": row.get("foundation_id"),
        "status": row.get("status"),
        "message": row.get("message", ""),
        "form_data": row.get("form_data"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ── Availability ──────────────────────────────────────────────────────────────

def set_availability(*, foundation_id: str, days: list[dict]) -> None:
    db = get_db()
    db.table("foundation_availability") \
      .delete() \
      .eq("foundation_id", foundation_id) \
      .gte("available_date", date.today().isoformat()) \
      .execute()
    if days:
        db.table("foundation_availability").insert([
            {
                "foundation_id": foundation_id,
                "available_date": d["available_date"],
                "start_time": d["start_time"],
                "end_time": d["end_time"],
            }
            for d in days
        ]).execute()


def get_availability(*, foundation_id: str, from_date: str) -> list[dict]:
    result = (
        get_db()
        .table("foundation_availability")
        .select("available_date, start_time, end_time")
        .eq("foundation_id", foundation_id)
        .gte("available_date", from_date)
        .order("available_date")
        .execute()
    )
    return result.data or []


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
