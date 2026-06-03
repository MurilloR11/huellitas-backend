from datetime import date, datetime, timedelta, timezone

from app.extensions import get_db

_ADMIN_FOUNDATION_SELECT = (
    "id, org_name, municipio, status, "
    "profiles!foundations_id_fkey(email, created_at)"
)

_MONTHS_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def _last_6_months() -> list[tuple[int, int]]:
    """Return the last 6 (year, month) pairs in chronological order."""
    months = []
    year, month = date.today().year, date.today().month
    for _ in range(6):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months[::-1]


def get_stats() -> dict:
    db = get_db()

    available   = db.table("pets").select("id", count="exact").eq("status", "available").execute()
    in_process  = db.table("pets").select("id", count="exact").eq("status", "in_process").execute()
    adopted     = db.table("pets").select("id", count="exact").eq("status", "adopted").execute()
    dogs        = db.table("pets").select("id", count="exact").eq("species", "dog").execute()
    cats        = db.table("pets").select("id", count="exact").eq("species", "cat").execute()
    foundations = db.table("foundations").select("id", count="exact").eq("status", "approved").execute()

    av  = available.count  or 0
    ip  = in_process.count or 0
    ad  = adopted.count    or 0

    months = _last_6_months()
    # earliest month we care about: first entry
    cutoff = f"{months[0][0]:04d}-{months[0][1]:02d}-01"

    adoptions_result = (
        db.table("adoption_requests")
        .select("created_at")
        .eq("status", "completed")
        .gte("created_at", cutoff)
        .execute()
    )

    trend_map: dict[str, int] = {}
    for row in (adoptions_result.data or []):
        raw = row.get("created_at", "")
        if len(raw) >= 7:
            key = raw[:7]  # "YYYY-MM"
            trend_map[key] = trend_map.get(key, 0) + 1

    adoption_trend = [
        {
            "mes": _MONTHS_ES[m],
            "adopciones": trend_map.get(f"{y:04d}-{m:02d}", 0),
        }
        for y, m in months
    ]

    return {
        "available":      av,
        "in_process":     ip,
        "adopted":        ad,
        "total_pets":     av + ip + ad,
        "dogs":           dogs.count        or 0,
        "cats":           cats.count        or 0,
        "other":          max(0, av + ip + ad - (dogs.count or 0) - (cats.count or 0)),
        "foundations":    foundations.count or 0,
        "adoption_trend": adoption_trend,
    }


def list_admin_users(search: str) -> dict:
    db = get_db()

    q = db.table("profiles").select("id, full_name, email, role, created_at")
    if search:
        safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.or_(f"full_name.ilike.%{safe}%,email.ilike.%{safe}%")
    result = q.order("created_at", desc=True).execute()

    # Bulk fetch auth data — one call instead of N
    auth_map: dict[str, dict] = {}
    try:
        auth_users = db.auth.admin.list_users(page=1, per_page=1000)
        for au in (auth_users or []):
            auth_map[str(au.id)] = {
                "last_login": au.last_sign_in_at,
                "is_banned":  au.banned_until is not None,
            }
    except Exception:
        pass

    items = []
    for row in (result.data or []):
        uid  = row["id"]
        auth = auth_map.get(uid, {})
        items.append({
            "id":         uid,
            "name":       row.get("full_name", ""),
            "email":      row.get("email", ""),
            "role":       row.get("role", "ciudadano"),
            "created_at": row.get("created_at", ""),
            "last_login": auth.get("last_login"),
            "status":     "inactive" if auth.get("is_banned") else "active",
        })

    return {"data": items, "total": len(items)}


def toggle_user_ban(user_id: str, ban: bool) -> None:
    ban_duration = "876600h" if ban else "none"
    get_db().auth.admin.update_user_by_id(user_id, {"ban_duration": ban_duration})


def list_admin_pets() -> dict:
    db = get_db()
    result = (
        db.table("pets")
        .select(
            "id, name, species, breed, age_months, status, created_at, foundation_id, "
            "foundations(org_name)"
        )
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )

    items = []
    for row in (result.data or []):
        foundation = (row.pop("foundations", None) or {})
        pet_id = row["id"]
        items.append({
            "id":              pet_id,
            "code":            f"HLL-{pet_id:05d}",
            "name":            row.get("name", ""),
            "species":         row.get("species", "other"),
            "breed":           row.get("breed") or "",
            "age_months":      row.get("age_months"),
            "foundation_name": foundation.get("org_name", ""),
            "foundation_id":   str(row.get("foundation_id") or ""),
            "status":          row.get("status", "available"),
            "created_at":      row.get("created_at", ""),
        })

    return {"data": items, "total": len(items)}


def toggle_pet_status(pet_id: int, suspend: bool) -> None:
    new_status = "suspended" if suspend else "available"
    get_db().table("pets").update({"status": new_status}).eq("id", pet_id).execute()


def list_admin_adoptions() -> dict:
    db = get_db()
    result = (
        db.table("adoption_requests")
        .select(
            "id, adopter_id, status, created_at, updated_at, form_data, "
            "pets(id, name, species), foundations(org_name)"
        )
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = result.data or []

    # Batch-fetch adopter profiles
    adopter_ids = list({r["adopter_id"] for r in rows if r.get("adopter_id")})
    profiles_map: dict[str, dict] = {}
    if adopter_ids:
        prof_result = (
            db.table("profiles")
            .select("id, full_name, email")
            .in_("id", adopter_ids)
            .execute()
        )
        for p in (prof_result.data or []):
            profiles_map[p["id"]] = {
                "name":  p.get("full_name") or "",
                "email": p.get("email") or "",
            }

    # Batch-fetch visit schedules
    adoption_ids = [r["id"] for r in rows if r.get("id") is not None]
    visits_map: dict[int, str | None] = {}
    if adoption_ids:
        visits_result = (
            db.table("visit_schedules")
            .select("adoption_request_id, scheduled_at")
            .in_("adoption_request_id", adoption_ids)
            .execute()
        )
        for v in (visits_result.data or []):
            aid = v.get("adoption_request_id")
            if aid is not None and aid not in visits_map:
                visits_map[aid] = v.get("scheduled_at")

    items = []
    for row in rows:
        pet        = (row.pop("pets", None) or {})
        foundation = (row.pop("foundations", None) or {})
        form_data  = row.get("form_data") or {}
        profile    = profiles_map.get(row.get("adopter_id") or "", {})
        aid        = row["id"]
        pet_id     = pet.get("id")

        items.append({
            "id":              aid,
            "code":            f"SOL-{aid:05d}",
            "requester_name":  profile.get("name", ""),
            "requester_email": profile.get("email", ""),
            "requester_phone": form_data.get("phone", ""),
            "requester_city":  form_data.get("city", ""),
            "pet_id":          pet_id,
            "pet_code":        f"HLL-{pet_id:05d}" if pet_id is not None else "",
            "pet_name":        pet.get("name", ""),
            "pet_species":     pet.get("species", "other"),
            "foundation_name": foundation.get("org_name", ""),
            "requester_id":    row.get("adopter_id", ""),
            "status":          row.get("status", "pending"),
            "created_at":      row.get("created_at", ""),
            "updated_at":      row.get("updated_at"),
            "visit_at":        visits_map.get(aid),
        })

    return {"data": items, "total": len(items)}


def cancel_admin_adoption(adoption_id: int) -> None:
    get_db().table("adoption_requests").update({"status": "cancelled"}).eq("id", adoption_id).execute()


def list_activities(page: int, search: str, action: str, date_range: str) -> dict:
    db = get_db()
    per_page = 15
    offset = (page - 1) * per_page

    q = db.table("activity_logs").select("*", count="exact")

    if search:
        safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.or_(f"user_name.ilike.%{safe}%,user_email.ilike.%{safe}%")

    if action and action != "all":
        q = q.eq("action", action)

    if date_range and date_range != "all":
        now = datetime.now(timezone.utc)
        if date_range == "today":
            cutoff: datetime | None = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "week":
            cutoff = now - timedelta(days=7)
        elif date_range == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None
        if cutoff:
            q = q.gte("created_at", cutoff.isoformat())

    result = q.order("created_at", desc=True).range(offset, offset + per_page - 1).execute()

    items = [
        {
            "id":          row["id"],
            "user_id":     row.get("user_id", ""),
            "user_name":   row.get("user_name", ""),
            "user_email":  row.get("user_email", ""),
            "user_role":   row.get("user_role", "ciudadano"),
            "action":      row.get("action", ""),
            "description": row.get("description", ""),
            "metadata":    row.get("metadata") or {},
            "ip_address":  row.get("ip_address"),
            "created_at":  row.get("created_at", ""),
        }
        for row in (result.data or [])
    ]

    return {
        "data":     items,
        "total":    result.count or 0,
        "page":     page,
        "per_page": per_page,
    }


def list_admin_foundations(status: str, page: int) -> dict:
    db = get_db()
    per_page = 15
    offset = (page - 1) * per_page

    q = db.table("foundations").select(_ADMIN_FOUNDATION_SELECT, count="exact")

    if status != "all":
        q = q.eq("status", status)

    result = q.order("created_at", desc=True, foreign_table="profiles").range(offset, offset + per_page - 1).execute()

    items = []
    for row in (result.data or []):
        profile = (row.pop("profiles", None) or {})
        fid = row.get("id")
        row_status = row.get("status", "")

        active_count  = 0
        adopted_count = 0
        if row_status == "approved":
            a = db.table("pets").select("id", count="exact").eq("foundation_id", fid).eq("status", "available").execute()
            d = db.table("pets").select("id", count="exact").eq("foundation_id", fid).eq("status", "adopted").execute()
            active_count  = a.count or 0
            adopted_count = d.count or 0

        items.append({
            "id":                 fid,
            "name":               row.get("org_name", ""),
            "city":               row.get("municipio", ""),
            "contact_email":      profile.get("email", ""),
            "active_pets_count":  active_count,
            "adopted_pets_count": adopted_count,
            "created_at":         profile.get("created_at", ""),
            "status":             row_status,
        })

    return {
        "data":     items,
        "total":    result.count or 0,
        "page":     page,
        "per_page": per_page,
    }
