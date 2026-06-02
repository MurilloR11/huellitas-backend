import logging

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter
from app.shared.middleware.auth import require_auth
from . import service

logger = logging.getLogger(__name__)

adoptions_bp = Blueprint("adoptions", __name__, url_prefix="/adoptions")


@adoptions_bp.post("")
@limiter.limit("5 per hour")
@require_auth
def create_adoption():
    body = request.get_json(silent=True) or {}
    pet_id = body.get("pet_id")
    message = (body.get("message") or "").strip()

    if not pet_id:
        return jsonify({"error": "pet_id is required"}), 400
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 1000:
        return jsonify({"error": "message must be 1000 characters or fewer"}), 400

    try:
        adoption = service.create_adoption(
            adopter_id=g.user_id,
            pet_id=pet_id,
            message=message,
        )
        if adoption is None:
            return jsonify({"error": "Pet not found or not available"}), 404
        return jsonify(adoption), 201
    except Exception:
        logger.exception("Error creating adoption request")
        return jsonify({"error": "Internal server error"}), 500


_VALID_STATUSES = {"pending", "reviewing", "approved", "rejected", "completed"}


@adoptions_bp.patch("/<int:adoption_id>/status")
@limiter.limit("30 per minute")
@require_auth
def update_adoption_status(adoption_id):
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403

    body = request.get_json(silent=True) or {}
    new_status = body.get("status")
    if not new_status or new_status not in _VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}"}), 400

    try:
        result = service.update_adoption_status(
            adoption_id, foundation_id=g.user_id, new_status=new_status
        )
        if result is None:
            return jsonify({"error": "Adoption request not found or not yours"}), 404
        return jsonify(result), 200
    except Exception:
        logger.exception("Error updating adoption %s", adoption_id)
        return jsonify({"error": "Internal server error"}), 500


@adoptions_bp.get("/mine")
@limiter.limit("30 per minute")
@require_auth
def my_adoptions():
    try:
        adoptions = service.get_my_adoptions(adopter_id=g.user_id)
        return jsonify(adoptions), 200
    except Exception:
        logger.exception("Error fetching adoptions for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@adoptions_bp.get("/<int:adoption_id>")
@limiter.limit("30 per minute")
@require_auth
def get_adoption(adoption_id):
    try:
        adoption = service.get_adoption_by_id(adoption_id, requester_id=g.user_id)
        if not adoption:
            return jsonify({"error": "Adoption request not found"}), 404
        return jsonify(adoption), 200
    except Exception:
        logger.exception("Error fetching adoption %s", adoption_id)
        return jsonify({"error": "Internal server error"}), 500


@adoptions_bp.post("/<int:adoption_id>/schedule")
@limiter.limit("10 per minute")
@require_auth
def schedule_visit(adoption_id):
    body = request.get_json(silent=True) or {}
    scheduled_at = (body.get("scheduled_at") or "").strip()
    if not scheduled_at:
        return jsonify({"error": "scheduled_at is required"}), 400

    try:
        result = service.schedule_visit(
            adoption_id=adoption_id,
            adopter_id=g.user_id,
            scheduled_at=scheduled_at,
        )
        if result is None:
            return jsonify({"error": "Adoption not found, not approved, or visit already scheduled"}), 409
        return jsonify(result), 201
    except Exception:
        logger.exception("Error scheduling visit for adoption %s", adoption_id)
        return jsonify({"error": "Internal server error"}), 500
