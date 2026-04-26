import logging

from flask import Blueprint, jsonify, request

from app.extensions import limiter
from . import service

logger = logging.getLogger(__name__)

pets_bp = Blueprint("pets", __name__, url_prefix="/pets")


@pets_bp.get("")
@limiter.limit("60 per minute")
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


@pets_bp.get("/<int:pet_id>")
@limiter.limit("60 per minute")
def get_pet(pet_id):
    try:
        pet = service.get_pet_by_id(pet_id)
        if not pet:
            return jsonify({"error": "Pet not found"}), 404
        return jsonify(pet), 200
    except Exception:
        logger.exception("Error fetching pet %s", pet_id)
        return jsonify({"error": "Internal server error"}), 500
