import logging

logger = logging.getLogger(__name__)


def audit_log(
    *,
    admin_id: str,
    action: str,
    target_id: str,
    ip_address: str,
    metadata: dict | None = None,
) -> None:
    """Write a structured audit entry to the audit_logs table.

    Failures are logged locally and swallowed so they never break the main flow.
    """
    from app.extensions import get_db

    record = {
        "admin_id": admin_id,
        "action": action,
        "target_id": target_id,
        "target_type": "foundation",
        "ip_address": ip_address,
        "metadata": metadata or {},
    }

    try:
        get_db().table("audit_logs").insert(record).execute()
    except Exception:
        logger.exception(
            "Audit log write failed — admin=%s action=%s target=%s ip=%s",
            admin_id,
            action,
            target_id,
            ip_address,
        )
