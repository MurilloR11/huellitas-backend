import uuid as _uuid

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


_CODE_PREFIX = "HLL-"


def get_pet_by_code(code: str) -> dict | None:
    """Look up a pet by its adoption code (e.g. HLL-00042)."""
    upper = code.strip().upper()
    if not upper.startswith(_CODE_PREFIX):
        return None
    numeric = upper[len(_CODE_PREFIX):]
    if not numeric.isdigit():
        return None
    return get_pet_by_id(int(numeric))


def create_pet(*, foundation_id: str, data: dict) -> dict | None:
    db = get_db()
    check = (
        db.table("foundations")
        .select("id")
        .eq("id", foundation_id)
        .eq("status", "approved")
        .execute()
    )
    if not (check.data or []):
        return None

    result = (
        db.table("pets")
        .insert({
            "name": data["name"],
            "species": data["species"],
            "breed": data.get("breed") or None,
            "age_months": int(data["age_months"]),
            "gender": data["gender"],
            "size": data["size"],
            "description": (data.get("description") or "").strip(),
            "photos": data.get("photos") or [],
            "status": "available",
            "foundation_id": foundation_id,
            "city": data["city"],
            "vaccinated": bool(data.get("vaccinated", False)),
            "sterilized": bool(data.get("sterilized", False)),
            "dewormed": bool(data.get("dewormed", False)),
            "microchipped": bool(data.get("microchipped", False)),
            "health_notes": (data.get("health_notes") or "").strip() or None,
        })
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    return get_pet_by_id(rows[0]["id"])


_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def upload_pet_photo(*, pet_id: int, foundation_id: str, file_bytes: bytes, mime: str) -> str | None:
    db = get_db()
    row = (
        db.table("pets")
        .select("foundation_id, photos")
        .eq("id", pet_id)
        .execute()
    )
    if not row.data or row.data[0]["foundation_id"] != foundation_id:
        return None

    ext = _EXT_MAP.get(mime, ".jpg")
    path = f"{foundation_id}/{pet_id}/{_uuid.uuid4()}{ext}"

    db.storage.from_("pet-photos").upload(path, file_bytes, {"content-type": mime})
    url = db.storage.from_("pet-photos").get_public_url(path)

    current = list(row.data[0]["photos"] or [])
    current.append(url)
    db.table("pets").update({"photos": current}).eq("id", pet_id).execute()

    return url


def _format_pet(row: dict) -> dict:
    foundation = row.pop("foundations", None) or {}
    pet_id = row.get("id")
    return {
        "id": pet_id,
        "adoption_code": f"{_CODE_PREFIX}{pet_id:05d}" if pet_id is not None else None,
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
