from app.extensions import get_db

# Clinical record fields are stored as columns on the pets table.
# The foundation name is joined from the foundations table via foreign key.
_PET_SELECT = (
    "id, name, species, breed, age_months, gender, size, description, "
    "photos, status, foundation_id, city, created_at, "
    "vaccinated, sterilized, dewormed, microchipped, health_notes, "
    "foundations(org_name)"
)


def list_pets(filters: dict) -> dict:
    page = filters["page"]
    per_page = filters["per_page"]
    offset = (page - 1) * per_page

    q = get_db().table("pets").select(_PET_SELECT, count="exact")

    if filters.get("species"):
        q = q.eq("species", filters["species"])
    if filters.get("city"):
        q = q.ilike("city", f"%{filters['city']}%")
    if filters.get("size"):
        q = q.eq("size", filters["size"])
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("q"):
        q = q.ilike("name", f"%{filters['q']}%")

    result = q.range(offset, offset + per_page - 1).execute()

    return {
        "data": [_format_pet(r) for r in (result.data or [])],
        "total": result.count or 0,
        "page": page,
        "per_page": per_page,
    }


def get_pet_by_id(pet_id: int) -> dict | None:
    result = (
        get_db()
        .table("pets")
        .select(_PET_SELECT)
        .eq("id", pet_id)
        .execute()
    )
    rows = result.data or []
    return _format_pet(rows[0]) if rows else None


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
