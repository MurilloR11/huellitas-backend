from app.extensions import get_db

_TRACKING_PREFIX = "SOL-"
_SCHEDULING_PREFIX = "CIT-"

_ADOPTION_SELECT = (
    "id, pet_id, adopter_id, foundation_id, status, message, form_data, created_at, updated_at, "
    "pets(name, photos), foundations(org_name, municipio)"
)


def create_adoption(*, adopter_id: str, pet_id: int, message: str, form_data: dict | None = None) -> dict | None:
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

    insert_payload: dict = {
        "pet_id": pet_id,
        "adopter_id": adopter_id,
        "foundation_id": pet.get("foundation_id"),
        "message": message,
        "status": "pending",
    }
    if form_data:
        insert_payload["form_data"] = form_data

    result = (
        db.table("adoption_requests")
        .insert(insert_payload)
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

    adopter_ids = list({r.get("adopter_id") for r in rows if r.get("adopter_id") is not None})
    profiles_map: dict = {}
    if adopter_ids:
        profiles_result = (
            db.table("profiles")
            .select("id, full_name, email")
            .in_("id", adopter_ids)
            .execute()
        )
        for p in (profiles_result.data or []):
            profiles_map[p["id"]] = {"name": p.get("full_name") or "", "email": p.get("email") or ""}

    return [
        _format_adoption_from_row(
            r,
            visit=visits_map.get(r.get("id")),
            adopter_name=profiles_map.get(r.get("adopter_id"), {}).get("name", ""),
            adopter_email=profiles_map.get(r.get("adopter_id"), {}).get("email", ""),
        )
        for r in rows
    ]


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


def _format_adoption_from_row(
    row: dict,
    *,
    visit: dict | None = None,
    adopter_name: str = "",
    adopter_email: str = "",
) -> dict:
    pet = row.pop("pets", None) or {}
    foundation = row.pop("foundations", None) or {}
    photos = pet.get("photos") or []
    return _format_adoption(
        row,
        pet_name=pet.get("name", ""),
        pet_photo=photos[0] if photos else None,
        foundation_name=foundation.get("org_name", ""),
        foundation_address=foundation.get("municipio", ""),
        adopter_name=adopter_name,
        adopter_email=adopter_email,
        visit_schedule=visit,
    )


def _format_adoption(
    row: dict,
    *,
    pet_name: str,
    pet_photo: str | None,
    foundation_name: str = "",
    foundation_address: str = "",
    adopter_name: str = "",
    adopter_email: str = "",
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
        "adopter_name": adopter_name,
        "adopter_email": adopter_email,
        "foundation_id": row.get("foundation_id"),
        "foundation_name": foundation_name,
        "foundation_address": foundation_address,
        "status": row.get("status"),
        "message": row.get("message"),
        "form_data": row.get("form_data"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "visit_schedule": visit_schedule,
    }


def get_adoption_by_tracking_code(tracking_code: str, *, foundation_id: str) -> dict | None:
    upper = tracking_code.upper()
    if not upper.startswith(_SCHEDULING_PREFIX):
        return None
    try:
        adoption_id = int(upper[len(_SCHEDULING_PREFIX):])
    except ValueError:
        return None

    db = get_db()
    result = (
        db.table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("id", adoption_id)
        .eq("foundation_id", foundation_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    adopter_id = rows[0].get("adopter_id")
    adopter_name, adopter_email = "", ""
    if adopter_id:
        try:
            prof = db.table("profiles").select("full_name, email").eq("id", adopter_id).execute()
            prof_rows = prof.data or []
            if prof_rows:
                adopter_name = prof_rows[0].get("full_name") or ""
                adopter_email = prof_rows[0].get("email") or ""
        except Exception:
            pass

    visit = _get_visit(db, adoption_id)
    return _format_adoption_from_row(rows[0], visit=visit, adopter_name=adopter_name, adopter_email=adopter_email)


def upload_adoption_document(
    *,
    adoption_id: int,
    adopter_id: str,
    doc_type: str,
    file_bytes: bytes,
    mime: str,
) -> str | None:
    db = get_db()

    result = (
        db.table("adoption_requests")
        .select("id, adopter_id, form_data")
        .eq("id", adoption_id)
        .execute()
    )
    rows = result.data or []
    if not rows or rows[0].get("adopter_id") != adopter_id:
        return None

    current_form_data: dict = rows[0].get("form_data") or {}

    ext = mime.split("/")[-1].replace("jpeg", "jpg")
    path = f"{adopter_id}/{adoption_id}/{doc_type}.{ext}"

    try:
        db.storage.from_("adoption-documents").remove([path])
    except Exception:
        pass
    db.storage.from_("adoption-documents").upload(path, file_bytes, {"content-type": mime})
    url = db.storage.from_("adoption-documents").get_public_url(path)

    documents = dict(current_form_data.get("documents") or {})
    documents[doc_type] = url
    current_form_data["documents"] = documents

    db.table("adoption_requests").update({"form_data": current_form_data}).eq("id", adoption_id).execute()

    return url


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
