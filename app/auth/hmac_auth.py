import hmac
import hashlib
import time
import logging
from functools import wraps
from flask import request, jsonify
from app.config import settings

logger = logging.getLogger(__name__)


def verify_hmac_signature(secret_key: str, request) -> bool:
    """Verify HMAC-SHA256 signature on incoming request."""
    signature = request.headers.get("X-HMAC-Signature")
    timestamp = request.headers.get("X-HMAC-Timestamp")

    if not signature or not timestamp:
        return False

    # Check timestamp freshness
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > settings.HMAC_SIGNATURE_MAX_AGE:
            logger.warning("HMAC signature expired")
            return False
    except ValueError:
        return False

    # Rebuild expected signature
    body = request.get_data(as_text=True) or ""
    message = f"{request.method}\n{request.path}\n{timestamp}\n{body}"
    expected = hmac.new(
        secret_key.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def require_hmac(key_type: str = "core"):
    """
    Decorator to protect endpoints with HMAC authentication.
    key_type: 'core' for core-service calls, 'engineer' for admin ops
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not settings.HMAC_ENABLED:
                # HMAC disabled in dev — allow all
                return f(*args, **kwargs)

            secret = (
                settings.HMAC_SECRET_KEY_ENGINEER
                if key_type == "engineer"
                else settings.HMAC_SECRET_KEY_CORE
            )

            if not verify_hmac_signature(secret, request):
                logger.warning(f"HMAC verification failed for {request.path}")
                return jsonify({"error": "Unauthorized — invalid HMAC signature"}), 401

            return f(*args, **kwargs)
        return decorated
    return decorator
