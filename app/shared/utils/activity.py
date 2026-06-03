import logging

logger = logging.getLogger(__name__)


def log_activity(
    *,
    user_id: str,
    action: str,
    description: str,
    ip_address: str,
    metadata: dict | None = None,
) -> None:
    """Write a user activity entry to activity_logs.

    Resolves user_name / user_email / user_role from the profiles table so
    callers only need the user_id.  Failures are swallowed so they never
    break the main request flow.
    """
    from app.extensions import get_db

    try:
        db = get_db()

        prof_result = (
            db.table("profiles")
            .select("full_name, email, role")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        prof = (prof_result.data or [{}])[0]

        db.table("activity_logs").insert({
            "user_id":     user_id,
            "user_name":   prof.get("full_name", ""),
            "user_email":  prof.get("email", ""),
            "user_role":   prof.get("role", "ciudadano"),
            "action":      action,
            "description": description,
            "ip_address":  ip_address,
            "metadata":    metadata or {},
        }).execute()

    except Exception:
        logger.exception(
            "Activity log write failed — user=%s action=%s ip=%s",
            user_id, action, ip_address,
        )
