import logging
import re
from datetime import date

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter
from app.shared.middleware.auth import require_admin, require_auth, optional_api_key
from app.shared.utils.email import send_foundation_approved, send_foundation_rejected
from app.shared.utils.activity import log_activity
from app.shared.utils.logger import audit_log
from . import service

logger = logging.getLogger(__name__)

foundations_bp = Blueprint("foundations", __name__, url_prefix="/foundations")


_DATE_RE  = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_TIME_RE  = re.compile(r'^\d{2}:\d{2}$')


@foundations_bp.post("/me/availability")
@limiter.limit("30 per minute")
@require_auth
def set_availability():
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403

    body = request.get_json(silent=True) or {}
    days = body.get("days")
    if not isinstance(days, list):
        return jsonify({"error": "days must be a list"}), 400

    validated = []
    for entry in days:
        d = (entry.get("available_date") or "").strip()
        st = (entry.get("start_time") or "").strip()
        et = (entry.get("end_time") or "").strip()
        if not (_DATE_RE.match(d) and _TIME_RE.match(st) and _TIME_RE.match(et)):
            return jsonify({"error": f"Invalid entry: {entry}"}), 400
        if st >= et:
            return jsonify({"error": f"start_time must be before end_time for {d}"}), 400
        validated.append({"available_date": d, "start_time": st, "end_time": et})

    try:
        service.set_availability(foundation_id=g.user_id, days=validated)
        return jsonify({"message": "Availability updated"}), 200
    except Exception:
        logger.exception("Error setting availability for foundation %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.get("/<foundation_id>/availability")
@limiter.limit("60 per minute")
@optional_api_key
def get_availability(foundation_id):
    from_date = request.args.get("from_date", date.today().isoformat())
    if not _DATE_RE.match(from_date):
        return jsonify({"error": "Invalid from_date format"}), 400
    try:
        slots = service.get_availability(foundation_id=foundation_id, from_date=from_date)
        return jsonify(slots), 200
    except Exception:
        logger.exception("Error fetching availability for foundation %s", foundation_id)
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.get("/me/pets")
@limiter.limit("30 per minute")
@require_auth
def my_pets():
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403
    try:
        pets = service.get_my_pets(foundation_id=g.user_id)
        return jsonify(pets), 200
    except Exception:
        logger.exception("Error fetching pets for foundation %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.get("/me/adoptions")
@limiter.limit("30 per minute")
@require_auth
def my_adoptions():
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403
    try:
        adoptions = service.get_my_adoptions(foundation_id=g.user_id)
        return jsonify(adoptions), 200
    except Exception:
        logger.exception("Error fetching adoptions for foundation %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.get("")
@limiter.limit("60 per minute")
@optional_api_key
def list_foundations():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid page parameter"}), 400

    params = {
        "city": request.args.get("city"),
        "page": page,
    }

    try:
        result = service.list_foundations(params)
        return jsonify(result), 200
    except Exception:
        logger.exception("Error listing foundations")
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.get("/<foundation_id>")
@limiter.limit("60 per minute")
@optional_api_key
def get_foundation(foundation_id):
    try:
        foundation = service.get_foundation_by_id_public(foundation_id)
        if not foundation:
            return jsonify({"error": "Foundation not found"}), 404
        return jsonify(foundation), 200
    except Exception:
        logger.exception("Error fetching foundation %s", foundation_id)
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.get("/pending")
@limiter.limit("10 per minute")
@require_admin
def get_pending():
    try:
        data = service.get_pending_foundations()
        return jsonify({"data": data}), 200
    except Exception:
        logger.exception("Error fetching pending foundations")
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.post("/<uuid:foundation_id>/approve")
@limiter.limit("10 per minute")
@require_admin
def approve(foundation_id):
    fid = str(foundation_id)

    try:
        foundation = service.get_foundation_with_profile(fid)
        if not foundation:
            return jsonify({"error": "Foundation not found"}), 404

        updated = service.approve_foundation(fid, g.user_id)
        if not updated:
            return jsonify({"error": "Foundation already reviewed or not found"}), 409

        profile = foundation.get("profiles") or {}
        email = profile.get("email")
        org_name = foundation.get("org_name", "")

        if email:
            try:
                send_foundation_approved(email, org_name)
            except Exception:
                # Email failure must not roll back a successful DB update
                logger.exception("Failed to send approval email to %s (foundation=%s)", email, fid)

        audit_log(
            admin_id=g.user_id,
            action="foundation_approved",
            target_id=fid,
            ip_address=request.remote_addr or "unknown",
            metadata={"org_name": org_name},
        )
        log_activity(
            user_id=g.user_id,
            action="foundation_approved",
            description=f"Fundación '{org_name}' aprobada",
            ip_address=request.remote_addr or "unknown",
            metadata={"foundation_id": fid, "org_name": org_name},
        )

        return jsonify({"message": "Foundation approved successfully"}), 200

    except Exception:
        logger.exception("Error approving foundation %s", fid)
        return jsonify({"error": "Internal server error"}), 500


@foundations_bp.post("/<uuid:foundation_id>/reject")
@limiter.limit("10 per minute")
@require_admin
def reject(foundation_id):
    fid = str(foundation_id)

    body = request.get_json(silent=True) or {}
    reason: str = (body.get("rejection_reason") or "").strip()

    if not reason:
        return jsonify({"error": "rejection_reason is required"}), 400
    if len(reason) > 1000:
        return jsonify({"error": "rejection_reason must be 1000 characters or fewer"}), 400

    try:
        foundation = service.get_foundation_with_profile(fid)
        if not foundation:
            return jsonify({"error": "Foundation not found"}), 404

        updated = service.reject_foundation(fid, g.user_id, reason)
        if not updated:
            return jsonify({"error": "Foundation already reviewed or not found"}), 409

        profile = foundation.get("profiles") or {}
        email = profile.get("email")
        org_name = foundation.get("org_name", "")

        if email:
            try:
                send_foundation_rejected(email, org_name, reason)
            except Exception:
                logger.exception("Failed to send rejection email to %s (foundation=%s)", email, fid)

        audit_log(
            admin_id=g.user_id,
            action="foundation_rejected",
            target_id=fid,
            ip_address=request.remote_addr or "unknown",
            metadata={"org_name": org_name, "reason": reason},
        )
        log_activity(
            user_id=g.user_id,
            action="foundation_rejected",
            description=f"Fundación '{org_name}' rechazada",
            ip_address=request.remote_addr or "unknown",
            metadata={"foundation_id": fid, "org_name": org_name, "reason": reason},
        )

        return jsonify({"message": "Foundation rejected successfully"}), 200

    except Exception:
        logger.exception("Error rejecting foundation %s", fid)
        return jsonify({"error": "Internal server error"}), 500
