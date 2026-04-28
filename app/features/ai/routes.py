import logging

from flask import Blueprint, jsonify, request

from app.extensions import limiter
from . import service

logger = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")


@ai_bp.post("/chat")
@limiter.limit("20 per minute")
def chat():
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")

    if not messages or not isinstance(messages, list):
        return jsonify({"error": "messages array is required"}), 400
    if len(messages) > 50:
        return jsonify({"error": "Too many messages"}), 400

    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant"):
            return jsonify({"error": "Each message must have role 'user' or 'assistant'"}), 400
        if not isinstance(msg.get("content"), str) or not msg["content"].strip():
            return jsonify({"error": "Each message must have non-empty content"}), 400

    try:
        reply = service.chat(messages)
        return jsonify({"response": reply}), 200
    except Exception:
        logger.exception("Error calling Ollama")
        return jsonify({"error": "AI service unavailable"}), 503
