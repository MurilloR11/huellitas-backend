from app.extensions import get_db

_TRACKING_PREFIX = "SOL-"

_ADOPTION_SELECT = (
    "id, pet_id, adopter_id, foundation_id, status, message, created_at, updated_at, "
    "pets(name, photos), foundations(org_name, municipio)"
)


def create_adoption(*, adopter_id: str, pet_id: int, message: str) -> dict | None:
    db = get_db()

    pet_result = (
        db.table("pets")
        .select("id, name, photos, status, foundation_id")
        .eq("id", pet_id)
        .eq("status", "available")
        .execute()
    )
    pet_rows = pet_result.data or []
    if not pet_rows:
        return None
    pet = pet_rows[0]

    result = (
        db.table("adoption_requests")
        .insert({
            "pet_id": pet_id,
            "adopter_id": adopter_id,
            "foundation_id": pet.get("foundation_id"),
            "message": message,
            "status": "pending",
        })
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    photos = pet.get("photos") or []
    return _format_adoption(
        rows[0],
        pet_name=pet.get("name", ""),
        pet_photo=photos[0] if photos else None,
    )


def _get_visit(db, adoption_id: int) -> dict | None:
    """Fetch the visit schedule for a single adoption (separate query, avoids PostgREST FK issues)."""
    result = (
        db.table("visit_schedules")
        .select("id, scheduled_at, location, status")
        .eq("adoption_request_id", adoption_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def get_my_adoptions(*, adopter_id: str) -> list[dict]:
    db = get_db()
    result = (
        db.table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("adopter_id", adopter_id)
        .order("created_at", desc=True)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return []

    # Batch-fetch visits to avoid N+1 queries
    adoption_ids = [r["id"] for r in rows if r.get("id") is not None]
    visits_map: dict = {}
    if adoption_ids:
        visits_result = (
            db.table("visit_schedules")
            .select("id, adoption_request_id, scheduled_at, location, status")
            .in_("adoption_request_id", adoption_ids)
            .execute()
        )
        for v in (visits_result.data or []):
            aid = v.get("adoption_request_id")
            if aid is not None and aid not in visits_map:
                visits_map[aid] = {
                    "id": v["id"],
                    "scheduled_at": v["scheduled_at"],
                    "location": v.get("location"),
                    "status": v["status"],
                }

    return [_format_adoption_from_row(r, visit=visits_map.get(r.get("id"))) for r in rows]


def get_adoption_by_id(adoption_id: int, *, requester_id: str) -> dict | None:
    db = get_db()
    result = (
        db.table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("id", adoption_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    visit = _get_visit(db, adoption_id)
    return _format_adoption_from_row(rows[0], visit=visit)


def update_adoption_status(adoption_id: int, *, foundation_id: str, new_status: str) -> dict | None:
    db = get_db()
    check = (
        db.table("adoption_requests")
        .select("id, foundation_id, pet_id")
        .eq("id", adoption_id)
        .execute()
    )
    rows = check.data or []
    if not rows or rows[0].get("foundation_id") != foundation_id:
        return None

    update_result = (
        db.table("adoption_requests")
        .update({"status": new_status})
        .eq("id", adoption_id)
        .execute()
    )
    if not (update_result.data or []):
        return None

    if new_status == "completed":
        pet_id = rows[0].get("pet_id")
        if pet_id:
            db.table("pets").update({"status": "adopted"}).eq("id", pet_id).execute()

    refetch = (
        db.table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("id", adoption_id)
        .execute()
    )
    refetch_rows = refetch.data or []
    if not refetch_rows:
        return None
    visit = _get_visit(db, adoption_id)
    return _format_adoption_from_row(refetch_rows[0], visit=visit)


def _format_adoption_from_row(row: dict, *, visit: dict | None = None) -> dict:
    pet = row.pop("pets", None) or {}
    foundation = row.pop("foundations", None) or {}
    photos = pet.get("photos") or []
    return _format_adoption(
        row,
        pet_name=pet.get("name", ""),
        pet_photo=photos[0] if photos else None,
        foundation_name=foundation.get("org_name", ""),
        foundation_address=foundation.get("municipio", ""),
        visit_schedule=visit,
    )


def _format_adoption(
    row: dict,
    *,
    pet_name: str,
    pet_photo: str | None,
    foundation_name: str = "",
    foundation_address: str = "",
    visit_schedule: dict | None = None,
) -> dict:
    adoption_id = row.get("id")
    return {
        "id": adoption_id,
        "tracking_code": f"{_TRACKING_PREFIX}{adoption_id:05d}" if adoption_id is not None else None,
        "pet_id": row.get("pet_id"),
        "pet_name": pet_name,
        "pet_photo": pet_photo,
        "adopter_id": row.get("adopter_id"),
        "foundation_id": row.get("foundation_id"),
        "foundation_name": foundation_name,
        "foundation_address": foundation_address,
        "status": row.get("status"),
        "message": row.get("message"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "visit_schedule": visit_schedule,
    }


def schedule_visit(*, adoption_id: int, adopter_id: str, scheduled_at: str) -> dict | None:
    db = get_db()

    adoption_result = (
        db.table("adoption_requests")
        .select("id, adopter_id, foundation_id, status")
        .eq("id", adoption_id)
        .execute()
    )
    rows = adoption_result.data or []
    if not rows:
        return None

    adoption = rows[0]
    if adoption.get("adopter_id") != adopter_id:
        return None
    if adoption.get("status") != "approved":
        return None

    existing = (
        db.table("visit_schedules")
        .select("id")
        .eq("adoption_request_id", adoption_id)
        .execute()
    )
    if existing.data:
        return None

    db.table("visit_schedules").insert({
        "adoption_request_id": adoption_id,
        "foundation_id": adoption["foundation_id"],
        "adopter_id": adopter_id,
        "scheduled_at": scheduled_at,
        "status": "confirmed",
    }).execute()

    refetch = (
        db.table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("id", adoption_id)
        .execute()
    )
    refetch_rows = refetch.data or []
    if not refetch_rows:
        return None
    visit = _get_visit(db, adoption_id)
    return _format_adoption_from_row(refetch_rows[0], visit=visit)
