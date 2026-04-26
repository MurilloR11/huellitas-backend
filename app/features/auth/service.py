from app.extensions import get_db


def get_profile(user_id: str) -> dict | None:
    result = (
        get_db()
        .table("profiles")
        .select("id, email, full_name, role, status, avatar_url")
        .eq("id", user_id)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None
