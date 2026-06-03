from collections import defaultdict
from datetime import datetime, timezone, timedelta

from flask import Blueprint, g, jsonify, request

from app.extensions import limiter, get_db
from app.shared.middleware.auth import require_auth
from app.features.developer import service

developer_bp = Blueprint("developer", __name__, url_prefix="/developer")


@developer_bp.route("/keys", methods=["GET"])
@limiter.limit("30/minute")
@require_auth
def list_keys():
    return jsonify({"data": service.list_keys(g.user_id)})


@developer_bp.route("/keys", methods=["POST"])
@limiter.limit("10/hour")
@require_auth
def create_key():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "El nombre es requerido"}), 400
    if len(name) > 50:
        return jsonify({"error": "El nombre no puede superar los 50 caracteres"}), 400

    try:
        key = service.create_key(g.user_id, name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422

    return jsonify(key), 201


@developer_bp.route("/keys/<key_id>", methods=["DELETE"])
@limiter.limit("20/minute")
@require_auth
def revoke_key(key_id: str):
    ok = service.revoke_key(g.user_id, key_id)
    if not ok:
        return jsonify({"error": "Key no encontrada"}), 404
    return jsonify({"ok": True})


@developer_bp.route("/stats", methods=["GET"])
@limiter.limit("30/minute")
@require_auth
def get_stats():
    user_id = g.user_id
    db      = get_db()
    since   = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # Last 7 days of logs with key name
    result = (
        db.table("api_call_logs")
        .select("id, method, path, status_code, created_at, access_keys!api_call_logs_key_id_fkey(name)")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(5000)
        .execute()
    )
    logs = result.data or []

    # All-time total
    total_result = (
        db.table("api_call_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total_all_time = total_result.count or 0

    # Aggregate
    daily_map    = defaultdict(lambda: {"calls": 0, "errors": 0})
    errors_by_code = {"404": 0, "429": 0, "5xx": 0}
    recent_errors  = []

    for log in logs:
        day  = log["created_at"][:10]
        code = log["status_code"]
        daily_map[day]["calls"] += 1
        if code >= 400:
            daily_map[day]["errors"] += 1
            if code == 404:
                errors_by_code["404"] += 1
            elif code == 429:
                errors_by_code["429"] += 1
            elif code >= 500:
                errors_by_code["5xx"] += 1
            if len(recent_errors) < 20:
                recent_errors.append({
                    "id":         log["id"],
                    "status":     code,
                    "method":     log["method"],
                    "path":       log["path"],
                    "key_name":   (log.get("access_keys") or {}).get("name", ""),
                    "created_at": log["created_at"],
                })

    # Build 7-day list oldest → newest
    today = datetime.now(timezone.utc).date()
    daily = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        daily.append({
            "date":   d,
            "calls":  daily_map[d]["calls"],
            "errors": daily_map[d]["errors"],
        })

    return jsonify({
        "daily":           daily,
        "total_calls_7d":  sum(d["calls"]  for d in daily),
        "total_calls_all": total_all_time,
        "total_errors_7d": sum(d["errors"] for d in daily),
        "errors_by_code":  errors_by_code,
        "recent_errors":   recent_errors,
    }), 200
