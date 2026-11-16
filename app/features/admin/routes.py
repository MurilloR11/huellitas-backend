import json
import logging

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter
from app.shared.middleware.auth import require_admin
from app.shared.utils.activity import log_activity
from . import service

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

_VALID_STATUSES = {"approved", "pending", "rejected", "all"}
_VALID_ROLES   = {"ciudadano", "fundacion", "admin", "developer", "all"}
_VALID_USER_STATUSES = {"active", "inactive", "all"}
_VALID_ACTIVITY_ACTIONS = {
    "login", "logout",
    "adoption_request", "adoption_cancelled", "adoption_status_updated",
    "visit_scheduled",
    "profile_updated",
    "foundation_approved", "foundation_rejected",
    "pet_published", "pet_suspended", "pet_unsuspended",
    "user_banned", "user_unbanned",
    "all",
}
_VALID_DATE_RANGES = {"today", "week", "month", "all"}


def _mask_email(value: str) -> str:
    """ana.perez@gmail.com -> a***@gmail.com"""
    if not isinstance(value, str) or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _mask_emails(data):
    if isinstance(data, dict):
        return {
            k: _mask_email(v) if "email" in k.lower() and isinstance(v, str) else _mask_emails(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_emails(item) for item in data]
    return data


@admin_bp.after_request
def _hide_emails_for_demo(response):
    """La cuenta admin de demo no ve los correos reales de los usuarios."""
    if g.get("is_demo") and response.is_json:
        response.set_data(json.dumps(_mask_emails(response.get_json()), ensure_ascii=False))
    return response


@admin_bp.get("/stats")
@limiter.limit("30 per minute")
@require_admin
def get_stats():
    try:
        data = service.get_stats()
        return jsonify(data), 200
    except Exception:
        logger.exception("Error fetching admin stats")
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.get("/foundations")
@limiter.limit("30 per minute")
@require_admin
def list_foundations():
    status = request.args.get("status", "approved")
    if status not in _VALID_STATUSES:
        return jsonify({"error": "Invalid status parameter"}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid page parameter"}), 400

    try:
        data = service.list_admin_foundations(status=status, page=page)
        return jsonify(data), 200
    except Exception:
        logger.exception("Error listing admin foundations")
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.get("/users")
@limiter.limit("30 per minute")
@require_admin
def list_users():
    search = request.args.get("search", "").strip()[:100]
    try:
        data = service.list_admin_users(search=search)
        return jsonify(data), 200
    except Exception:
        logger.exception("Error listing admin users")
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.post("/users/<user_id>/ban")
@limiter.limit("20 per minute")
@require_admin
def ban_user(user_id: str):
    try:
        service.toggle_user_ban(user_id, ban=True)
        log_activity(
            user_id=g.user_id,
            action="user_banned",
            description="Cuenta de usuario bloqueada",
            ip_address=request.remote_addr or "unknown",
            metadata={"target_user_id": user_id},
        )
        return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Error banning user %s", user_id)
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.post("/users/<user_id>/unban")
@limiter.limit("20 per minute")
@require_admin
def unban_user(user_id: str):
    try:
        service.toggle_user_ban(user_id, ban=False)
        log_activity(
            user_id=g.user_id,
            action="user_unbanned",
            description="Cuenta de usuario desbloqueada",
            ip_address=request.remote_addr or "unknown",
            metadata={"target_user_id": user_id},
        )
        return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Error unbanning user %s", user_id)
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.get("/pets")
@limiter.limit("30 per minute")
@require_admin
def list_pets():
    try:
        data = service.list_admin_pets()
        return jsonify(data), 200
    except Exception:
        logger.exception("Error listing admin pets")
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.post("/pets/<int:pet_id>/suspend")
@limiter.limit("20 per minute")
@require_admin
def suspend_pet(pet_id: int):
    try:
        service.toggle_pet_status(pet_id, suspend=True)
        log_activity(
            user_id=g.user_id,
            action="pet_suspended",
            description=f"Mascota #{pet_id} suspendida",
            ip_address=request.remote_addr or "unknown",
            metadata={"pet_id": pet_id},
        )
        return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Error suspending pet %s", pet_id)
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.post("/pets/<int:pet_id>/unsuspend")
@limiter.limit("20 per minute")
@require_admin
def unsuspend_pet(pet_id: int):
    try:
        service.toggle_pet_status(pet_id, suspend=False)
        log_activity(
            user_id=g.user_id,
            action="pet_unsuspended",
            description=f"Mascota #{pet_id} reactivada",
            ip_address=request.remote_addr or "unknown",
            metadata={"pet_id": pet_id},
        )
        return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Error unsuspending pet %s", pet_id)
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.get("/adoptions")
@limiter.limit("30 per minute")
@require_admin
def list_adoptions():
    try:
        data = service.list_admin_adoptions()
        return jsonify(data), 200
    except Exception:
        logger.exception("Error listing admin adoptions")
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.post("/adoptions/<int:adoption_id>/cancel")
@limiter.limit("20 per minute")
@require_admin
def cancel_adoption(adoption_id: int):
    try:
        service.cancel_admin_adoption(adoption_id)
        log_activity(
            user_id=g.user_id,
            action="adoption_cancelled",
            description=f"Solicitud #{adoption_id} cancelada por administrador",
            ip_address=request.remote_addr or "unknown",
            metadata={"adoption_id": adoption_id},
        )
        return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Error cancelling adoption %s", adoption_id)
        return jsonify({"error": "Internal server error"}), 500


@admin_bp.get("/activities")
@limiter.limit("30 per minute")
@require_admin
def list_activities():
    search     = request.args.get("search", "").strip()[:100]
    action     = request.args.get("action", "all").strip()
    date_range = request.args.get("date_range", "all").strip()

    if action not in _VALID_ACTIVITY_ACTIONS:
        return jsonify({"error": "Invalid action parameter"}), 400
    if date_range not in _VALID_DATE_RANGES:
        return jsonify({"error": "Invalid date_range parameter"}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid page parameter"}), 400

    try:
        data = service.list_activities(
            page=page, search=search, action=action, date_range=date_range
        )
        return jsonify(data), 200
    except Exception:
        logger.exception("Error listing activities")
        return jsonify({"error": "Internal server error"}), 500
