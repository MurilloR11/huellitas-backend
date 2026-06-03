import logging
import threading

from flask import g, request

logger = logging.getLogger(__name__)


def log_api_call(response):
    """after_request hook: log every X-API-Key authenticated request asynchronously."""
    key_id  = getattr(g, 'api_key_id', None)
    user_id = getattr(g, 'user_id', None)
    if not key_id or not user_id:
        return response

    method      = request.method
    path        = request.path[:500]
    status_code = response.status_code

    threading.Thread(
        target=_insert,
        args=(key_id, user_id, method, path, status_code),
        daemon=True,
    ).start()

    return response


def _insert(key_id: str, user_id: str, method: str, path: str, status_code: int) -> None:
    try:
        from datetime import datetime, timezone
        from app.extensions import get_db
        get_db().table("api_call_logs").insert({
            "key_id":      key_id,
            "user_id":     user_id,
            "method":      method,
            "path":        path,
            "status_code": status_code,
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        logger.warning("Failed to log API call for key_id=%s", key_id, exc_info=True)
