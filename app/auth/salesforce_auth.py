import time
import logging
import requests
from threading import Lock

logger = logging.getLogger(__name__)


class SalesforceTokenManager:
    """
    Manages OAuth 2.0 JWT Bearer tokens with automatic refresh.
    Tokens expire after ~2 hours; refresh happens 5 minutes before expiry.
    """

    def __init__(self, consumer_key: str, private_key_pem: str,
                 username: str, login_url: str):
        self._consumer_key = consumer_key
        self._private_key_pem = private_key_pem
        self._username = username
        self._login_url = login_url
        self._access_token = None
        self._instance_url = None
        self._expires_at = 0
        self._lock = Lock()

    def get_token(self) -> tuple:
        """Returns (access_token, instance_url), refreshing if within 5 min of expiry."""
        with self._lock:
            if time.time() > (self._expires_at - 300):
                self._refresh()
        return self._access_token, self._instance_url

    def _refresh(self):
        """Exchange JWT for a new access token."""
        try:
            import jwt as pyjwt
        except ImportError:
            raise ImportError("PyJWT is required. Run: pip install PyJWT cryptography")

        now = int(time.time())
        claim = {
            "iss": self._consumer_key,
            "sub": self._username,
            "aud": self._login_url,
            "exp": now + 180,
        }

        # Sign JWT with RSA private key
        signed_jwt = pyjwt.encode(claim, self._private_key_pem, algorithm="RS256")

        # Exchange for access token
        resp = requests.post(
            f"{self._login_url}/services/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
            },
            timeout=30,
        )

        if not resp.ok:
            raise ConnectionError(
                f"Salesforce OAuth failed: {resp.status_code} — {resp.text}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        self._instance_url = data["instance_url"]
        self._expires_at = now + 7200   # tokens last ~2 hours
        logger.info(f"Salesforce token refreshed. Instance: {self._instance_url}")

    @property
    def is_connected(self) -> bool:
        return self._access_token is not None and time.time() < self._expires_at


class MockTokenManager:
    """
    Mock token manager for development when no Salesforce credentials are configured.
    Simulates the same interface as SalesforceTokenManager.
    """

    def get_token(self) -> tuple:
        return "mock_access_token", "https://mock-org.salesforce.com"

    @property
    def is_connected(self) -> bool:
        return True


def create_token_manager():
    """
    Factory — returns real or mock token manager based on config.
    """
    from app.config import settings

    if settings.SF_CONSUMER_KEY and settings.SF_USERNAME and settings.SF_PRIVATE_KEY_PEM:
        logger.info("Using real Salesforce JWT Bearer token manager")
        return SalesforceTokenManager(
            consumer_key=settings.SF_CONSUMER_KEY,
            private_key_pem=settings.SF_PRIVATE_KEY_PEM,
            username=settings.SF_USERNAME,
            login_url=settings.SF_LOGIN_URL,
        )
    else:
        logger.warning("Salesforce credentials not configured — using mock token manager")
        return MockTokenManager()
