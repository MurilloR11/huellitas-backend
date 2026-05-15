import logging

from flask import Blueprint, g, jsonify, request

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


@auth_bp.get("/mfa/factor")
@limiter.limit("30 per minute")
@require_auth
def get_mfa_factor():
    try:
        factor = service.get_verified_mfa_factor(g.user_id)
        return jsonify({"id": factor["id"] if factor else None}), 200
    except Exception:
        logger.exception("Error fetching MFA factor for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.delete("/mfa/pending")
@limiter.limit("10 per minute")
@require_auth
def clear_pending_mfa():
    try:
        deleted = service.delete_pending_mfa_factors(g.user_id)
        return jsonify({"deleted": deleted}), 200
    except Exception:
        logger.exception("Error clearing pending MFA factors for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/backup-codes/generate")
@limiter.limit("5 per minute")
@require_auth
def generate_backup_codes():
    try:
        codes = service.generate_backup_codes(g.user_id)
        return jsonify({"codes": codes}), 201
    except Exception:
        logger.exception("Error generating backup codes for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/backup-codes/regenerate")
@limiter.limit("5 per minute")
@require_auth
def regenerate_backup_codes():
    try:
        codes = service.generate_backup_codes(g.user_id)
        return jsonify({"codes": codes}), 200
    except Exception:
        logger.exception("Error regenerating backup codes for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.get("/backup-codes/status")
@limiter.limit("30 per minute")
@require_auth
def backup_codes_status():
    try:
        status = service.get_backup_codes_status(g.user_id)
        return jsonify(status), 200
    except Exception:
        logger.exception("Error fetching backup codes status for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/backup-codes/verify")
@limiter.limit("10 per minute")
@require_auth
def verify_backup_code():
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()

    if not code:
        return jsonify({"error": "code is required"}), 400

    try:
        ok = service.verify_backup_code(g.user_id, code)
        if not ok:
            return jsonify({"error": "Código inválido o ya utilizado"}), 400
        return jsonify({"message": "Código válido"}), 200
    except Exception:
        logger.exception("Error verifying backup code for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/access-key/generate")
@limiter.limit("5 per hour")
@require_auth
def generate_access_key():
    try:
        plain_key = service.generate_access_key(g.user_id)
        return jsonify({"key": plain_key}), 201
    except Exception:
        logger.exception("Error generating access key for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.get("/access-key/status")
@limiter.limit("30 per minute")
@require_auth
def access_key_status():
    try:
        status = service.get_access_key_status(g.user_id)
        return jsonify(status), 200
    except Exception:
        logger.exception("Error fetching access key status for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.delete("/access-key")
@limiter.limit("10 per minute")
@require_auth
def revoke_access_key():
    try:
        service.revoke_access_key(g.user_id)
        return jsonify({"message": "Llave revocada"}), 200
    except Exception:
        logger.exception("Error revoking access key for user %s", g.user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/access-key/login")
@limiter.limit("5 per hour")
def login_with_access_key():
    body = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    plain_key = (body.get("key") or "").strip()

    if not user_id or not plain_key:
        return jsonify({"error": "user_id and key are required"}), 400

    try:
        result = service.login_with_access_key(user_id, plain_key)
        if not result:
            return jsonify({"error": "Llave inválida o no configurada"}), 401
        return jsonify(result), 200
    except Exception:
        logger.exception("Error logging in with access key for user %s", user_id)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/forgot-password")
@limiter.limit("5 per minute")
def forgot_password():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "email is required"}), 400

    try:
        found = service.generate_and_send_otp(email)
        # Always return 200 to avoid email enumeration
        if not found:
            logger.info("Forgot password requested for unknown email: %s", email)
        return jsonify({"message": "Si el correo existe, recibirás un código en breve"}), 200
    except Exception:
        logger.exception("Error sending OTP to %s", email)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/verify-otp")
@limiter.limit("10 per minute")
def verify_otp():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    otp = (body.get("otp") or "").strip()

    if not email or not otp:
        return jsonify({"error": "email and otp are required"}), 400

    try:
        reset_token = service.verify_otp(email, otp)
        if not reset_token:
            return jsonify({"error": "Código inválido o expirado"}), 400
        return jsonify({"reset_token": reset_token}), 200
    except Exception:
        logger.exception("Error verifying OTP for %s", email)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.post("/reset-password")
@limiter.limit("5 per minute")
def reset_password():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    reset_token = (body.get("reset_token") or "").strip()
    new_password = body.get("new_password") or ""

    if not email or not reset_token or not new_password:
        return jsonify({"error": "email, reset_token and new_password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "La contraseña debe tener al menos 8 caracteres"}), 400

    try:
        ok = service.reset_password(email, reset_token, new_password)
        if not ok:
            return jsonify({"error": "Token inválido o expirado"}), 400
        return jsonify({"message": "Contraseña actualizada exitosamente"}), 200
    except Exception:
        logger.exception("Error resetting password for %s", email)
        return jsonify({"error": "Internal server error"}), 500
