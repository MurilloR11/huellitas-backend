import logging

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter
from app.shared.middleware.auth import require_admin
from app.shared.utils.email import send_foundation_approved, send_foundation_rejected
from app.shared.utils.logger import audit_log
from . import service

logger = logging.getLogger(__name__)

foundations_bp = Blueprint("foundations", __name__, url_prefix="/foundations")


@foundations_bp.get("")
@limiter.limit("60 per minute")
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

        return jsonify({"message": "Foundation rejected successfully"}), 200

    except Exception:
        logger.exception("Error rejecting foundation %s", fid)
        return jsonify({"error": "Internal server error"}), 500
