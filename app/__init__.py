import logging
import logging.config
import os
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.extensions import init_extensions

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.2 if os.environ.get("FLASK_DEBUG") != "true" else 1.0,
    environment="development" if os.environ.get("FLASK_DEBUG") == "true" else "production",
)


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.from_object(config_class)

    if not app.config.get("TESTING"):
        config_class.validate()

    _configure_logging(app)
    init_extensions(app)

    from app.shared.middleware.call_logger import log_api_call
    app.after_request(log_api_call)

    from app.features.auth.routes import auth_bp
    from app.features.foundations.routes import foundations_bp
    from app.features.pets.routes import pets_bp
    from app.features.adoptions.routes import adoptions_bp
    from app.features.ai.routes import ai_bp
    from app.features.admin.routes import admin_bp
    from app.features.developer.routes import developer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(foundations_bp)
    app.register_blueprint(pets_bp)
    app.register_blueprint(adoptions_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(developer_bp)

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
