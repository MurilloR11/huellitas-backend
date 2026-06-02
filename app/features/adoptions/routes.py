import logging

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter
from app.shared.middleware.auth import require_auth
from . import service

logger = logging.getLogger(__name__)

adoptions_bp = Blueprint("adoptions", __name__, url_prefix="/adoptions")


_ALLOWED_FORM_KEYS = {
    "phone", "city", "housing_type", "ownership",
    "outdoor_space", "residents", "children", "current_pets", "prev_pets",
}


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

    raw_form = body.get("form_data")
    form_data = None
    if isinstance(raw_form, dict):
        form_data = {k: str(v)[:200] for k, v in raw_form.items() if k in _ALLOWED_FORM_KEYS}

    try:
        adoption = service.create_adoption(
            adopter_id=g.user_id,
            pet_id=pet_id,
            message=message,
            form_data=form_data,
        )
        if adoption is None:
            return jsonify({"error": "Pet not found or not available"}), 404
        return jsonify(adoption), 201
    except Exception:
        logger.exception("Error creating adoption request")
        return jsonify({"error": "Internal server error"}), 500


_ALLOWED_DOC_TYPES = {"doc_id", "doc_address", "doc_landlord"}
_ALLOWED_DOC_MIME = {"application/pdf", "image/jpeg", "image/png", "image/webp"}

_VALID_STATUSES = {"pending", "reviewing", "approved", "rejected", "completed"}


@adoptions_bp.post("/<int:adoption_id>/documents")
@limiter.limit("20 per hour")
@require_auth
def upload_document(adoption_id):
    doc_type = request.form.get("doc_type", "").strip()
    if doc_type not in _ALLOWED_DOC_TYPES:
        return jsonify({"error": f"doc_type must be one of: {', '.join(sorted(_ALLOWED_DOC_TYPES))}"}), 400

    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400

    f = request.files["file"]
    if f.content_type not in _ALLOWED_DOC_MIME:
        return jsonify({"error": "Only PDF, JPG, PNG, or WebP files are allowed"}), 400

    data = f.read()
    if len(data) > 5 * 1024 * 1024:
        return jsonify({"error": "File too large (max 5 MB)"}), 400

    try:
        url = service.upload_adoption_document(
            adoption_id=adoption_id,
            adopter_id=g.user_id,
            doc_type=doc_type,
            file_bytes=data,
            mime=f.content_type,
        )
        if url is None:
            return jsonify({"error": "Adoption not found or access denied"}), 404
        return jsonify({"url": url}), 201
    except Exception:
        logger.exception("Error uploading document for adoption %s", adoption_id)
        return jsonify({"error": "Internal server error"}), 500


@adoptions_bp.get("/by-code/<tracking_code>")
@limiter.limit("60 per minute")
@require_auth
def get_by_tracking_code(tracking_code):
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403

    try:
        result = service.get_adoption_by_tracking_code(
            tracking_code.upper().strip(),
            foundation_id=g.user_id,
        )
        if result is None:
            return jsonify({"error": "Código no encontrado o no pertenece a tu fundación"}), 404
        return jsonify(result), 200
    except Exception:
        logger.exception("Error looking up tracking code %s", tracking_code)
        return jsonify({"error": "Internal server error"}), 500


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
