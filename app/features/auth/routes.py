import logging

from flask import Blueprint, g, jsonify

from app.extensions import limiter
from app.shared.middleware.auth import require_auth
from . import service

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.get("/me")
@limiter.limit("60 per minute")
@require_auth
def me():
    try:
        profile = service.get_profile(g.user_id)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify(profile), 200
    except Exception:
        logger.exception("Error fetching profile for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500
