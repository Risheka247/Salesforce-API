import sys
import logging
from flask import Flask
from flask_restx import Api
from app.config import settings, validate_settings, setup_logging
from app.models.database import create_tables

logger = logging.getLogger(__name__)


def create_app():
    """
    Flask app factory with fail-fast startup validation.
    The service exits immediately if required config is missing.
    """
    setup_logging()

    # ── Fail-fast config validation ──────────────────────────────────────
    errors = validate_settings()
    if errors:
        logger.error("=" * 70)
        logger.error("[STARTUP FAILED] Configuration validation errors:")
        logger.error("=" * 70)
        for field, details in errors.items():
            logger.error(f"\n  [{field}]")
            logger.error(f"    Error: {details['error']}")
            logger.error(f"    Fix:   {details['fix']}")
        logger.error("=" * 70)
        logger.error("Fix the errors above and restart the service.")
        sys.exit(1)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.config["RESTX_MASK_SWAGGER"] = False

    # ── Register routes ──────────────────────────────────────────────────
    from app.routes import api
    api.init_app(app)

    # ── Create DB tables ─────────────────────────────────────────────────
    with app.app_context():
        create_tables()

    logger.info(f"BD Salesforce Service started — env={settings.ENVIRONMENT} port={settings.PORT}")
    return app
