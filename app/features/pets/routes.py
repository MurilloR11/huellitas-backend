import logging

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter
from app.shared.middleware.auth import require_auth, optional_api_key
from app.shared.utils.activity import log_activity
from . import service

logger = logging.getLogger(__name__)

pets_bp = Blueprint("pets", __name__, url_prefix="/pets")


@pets_bp.post("")
@limiter.limit("20 per hour")
@require_auth
def create_pet():
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403

    body = request.get_json(silent=True) or {}

    for field in ("name", "species", "age_months", "gender", "size", "city"):
        if not body.get(field) and body.get(field) != 0:
            return jsonify({"error": f"{field} is required"}), 400

    try:
        age = int(body["age_months"])
        if age < 0 or age > 360:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "age_months must be an integer 0-360"}), 400

    if body["species"] not in {"dog", "cat", "rabbit", "other"}:
        return jsonify({"error": "Invalid species"}), 400
    if body["gender"] not in {"male", "female"}:
        return jsonify({"error": "Invalid gender"}), 400
    if body["size"] not in {"small", "medium", "large"}:
        return jsonify({"error": "Invalid size"}), 400

    try:
        pet = service.create_pet(foundation_id=g.user_id, data=body)
        if pet is None:
            return jsonify({"error": "Foundation not found or not approved"}), 403
        log_activity(
            user_id=g.user_id,
            action="pet_published",
            description=f"Mascota '{body.get('name', '')}' publicada",
            ip_address=request.remote_addr or "unknown",
            metadata={"pet_id": pet.get("id"), "species": body.get("species")},
        )
        return jsonify(pet), 201
    except Exception:
        logger.exception("Error creating pet")
        return jsonify({"error": "Internal server error"}), 500


@pets_bp.post("/<int:pet_id>/photos")
@limiter.limit("30 per hour")
@require_auth
def upload_photo(pet_id: int):
    if g.user_role != "fundacion":
        return jsonify({"error": "Forbidden"}), 403

    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400

    f = request.files["file"]
    if not f.content_type or not f.content_type.startswith("image/"):
        return jsonify({"error": "Only images are allowed"}), 400

    data = f.read()
    if len(data) > 5 * 1024 * 1024:
        return jsonify({"error": "File too large (max 5 MB)"}), 400

    try:
        url = service.upload_pet_photo(
            pet_id=pet_id,
            foundation_id=g.user_id,
            file_bytes=data,
            mime=f.content_type,
        )
        if url is None:
            return jsonify({"error": "Pet not found or access denied"}), 404
        return jsonify({"url": url}), 201
    except Exception:
        logger.exception("Error uploading photo for pet %s", pet_id)
        return jsonify({"error": "Internal server error"}), 500


@pets_bp.get("")
@limiter.limit("60 per minute")
@optional_api_key
def list_pets():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid pagination parameters"}), 400

    filters = {
        "species": request.args.get("species"),
        "city": request.args.get("city"),
        "size": request.args.get("size"),
        "status": request.args.get("status"),
        "q": request.args.get("q"),
        "page": page,
        "per_page": per_page,
    }

    try:
        result = service.list_pets(filters)
        return jsonify(result), 200
    except Exception:
        logger.exception("Error listing pets")
        return jsonify({"error": "Internal server error"}), 500


@pets_bp.get("/by-code/<string:code>")
@limiter.limit("60 per minute")
@optional_api_key
def get_pet_by_code(code: str):
    try:
        pet = service.get_pet_by_code(code)
        if not pet:
            return jsonify({"error": "Pet not found"}), 404
        return jsonify(pet), 200
    except Exception:
        logger.exception("Error fetching pet by code %s", code)
        return jsonify({"error": "Internal server error"}), 500


@pets_bp.get("/<int:pet_id>")
@limiter.limit("60 per minute")
@optional_api_key
def get_pet(pet_id):
    try:
        pet = service.get_pet_by_id(pet_id)
        if not pet:
            return jsonify({"error": "Pet not found"}), 404
        return jsonify(pet), 200
    except Exception:
        logger.exception("Error fetching pet %s", pet_id)
        return jsonify({"error": "Internal server error"}), 500
