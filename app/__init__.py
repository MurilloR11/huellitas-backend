import logging
import logging.config
from flask import Flask, jsonify

from app.config import Config
from app.extensions import init_extensions


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("TESTING"):
        config_class.validate()

    _configure_logging(app)
    init_extensions(app)

    from app.features.auth.routes import auth_bp
    from app.features.foundations.routes import foundations_bp
    from app.features.pets.routes import pets_bp
    from app.features.adoptions.routes import adoptions_bp
    from app.features.ai.routes import ai_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(foundations_bp)
    app.register_blueprint(pets_bp)
    app.register_blueprint(adoptions_bp)
    app.register_blueprint(ai_bp)

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(429)
    def rate_limit_exceeded(_e):
        return jsonify({"error": "Too many requests, please try again later"}), 429

    @app.errorhandler(500)
    def internal_error(_e):
        return jsonify({"error": "Internal server error"}), 500

    return app


def _configure_logging(app: Flask) -> None:
    log_level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Silence noisy third-party loggers in production
    if not app.config.get("DEBUG"):
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
