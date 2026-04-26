from app.extensions import get_db

_ADOPTION_SELECT = (
    "id, pet_id, adopter_id, foundation_id, status, message, created_at, updated_at, "
    "pets(name, photos)"
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


def get_my_adoptions(*, adopter_id: str) -> list[dict]:
    result = (
        get_db()
        .table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("adopter_id", adopter_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_format_adoption_from_row(r) for r in (result.data or [])]


def get_adoption_by_id(adoption_id: int, *, requester_id: str) -> dict | None:
    result = (
        get_db()
        .table("adoption_requests")
        .select(_ADOPTION_SELECT)
        .eq("id", adoption_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    row = rows[0]
    # Only the adopter can view their own request
    if row.get("adopter_id") != requester_id:
        return None

    return _format_adoption_from_row(row)


def _format_adoption_from_row(row: dict) -> dict:
    pet = row.pop("pets", None) or {}
    photos = pet.get("photos") or []
    return _format_adoption(
        row,
        pet_name=pet.get("name", ""),
        pet_photo=photos[0] if photos else None,
    )


def _format_adoption(row: dict, *, pet_name: str, pet_photo: str | None) -> dict:
    return {
        "id": row.get("id"),
        "pet_id": row.get("pet_id"),
        "pet_name": pet_name,
        "pet_photo": pet_photo,
        "adopter_id": row.get("adopter_id"),
        "foundation_id": row.get("foundation_id"),
        "status": row.get("status"),
        "message": row.get("message"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
