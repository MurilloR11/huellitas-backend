from app.extensions import get_db


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
