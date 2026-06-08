import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """All service configuration loaded from environment variables."""

    # Flask
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret")
    PORT: int = int(os.getenv("PORT", 5710))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")

    # Database
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_NAME: str = os.getenv("DB_NAME", "salesforce_dev")
    DB_USER: str = os.getenv("DB_USER", "dev_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "dev_pass")
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "public")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # Salesforce
    SF_CONSUMER_KEY: str = os.getenv("SF_CONSUMER_KEY", "")
    SF_PRIVATE_KEY_PEM: str = os.getenv("SF_PRIVATE_KEY_PEM", "")
    SF_USERNAME: str = os.getenv("SF_USERNAME", "")
    SF_LOGIN_URL: str = os.getenv("SF_LOGIN_URL", "https://test.salesforce.com")
    SF_API_VERSION: str = os.getenv("SF_API_VERSION", "v59.0")
    SF_BULK_PAGE_SIZE: int = int(os.getenv("SF_BULK_PAGE_SIZE", 50000))
    SF_MAX_JOB_TIMEOUT_HOURS: int = int(os.getenv("SF_MAX_JOB_TIMEOUT_HOURS", 2))

    # Scan settings
    MAX_CONCURRENT_SCANS: int = int(os.getenv("MAX_CONCURRENT_SCANS", 2))
    SCAN_TIMEOUT_HOURS: int = int(os.getenv("SCAN_TIMEOUT_HOURS", 2))
    CLEANUP_DAYS: int = int(os.getenv("CLEANUP_DAYS", 7))

    # HMAC
    HMAC_ENABLED: bool = os.getenv("HMAC_ENABLED", "false").lower() == "true"
    HMAC_SECRET_KEY_CORE: str = os.getenv("HMAC_SECRET_KEY_CORE", "")
    HMAC_SECRET_KEY_ENGINEER: str = os.getenv("HMAC_SECRET_KEY_ENGINEER", "")
    HMAC_SIGNATURE_MAX_AGE: int = int(os.getenv("HMAC_SIGNATURE_MAX_AGE", 300))

    # MinIO
    MINIO_ENABLED: bool = os.getenv("MINIO_ENABLED", "false").lower() == "true"
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "salesforce-dev")

    # Kafka
    KAFKA_ENABLED: bool = os.getenv("KAFKA_ENABLED", "false").lower() == "true"
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_CONSUMER_GROUP_ID: str = os.getenv("KAFKA_CONSUMER_GROUP_ID", "sf-service-dev")
    KAFKA_SF_CONTACTS_TOPIC: str = os.getenv("KAFKA_SF_CONTACTS_TOPIC", "sf.contacts.dev")
    KAFKA_SF_ACCOUNTS_TOPIC: str = os.getenv("KAFKA_SF_ACCOUNTS_TOPIC", "sf.accounts.dev")
    KAFKA_SF_OPPORTUNITIES_TOPIC: str = os.getenv("KAFKA_SF_OPPORTUNITIES_TOPIC", "sf.opportunities.dev")
    KAFKA_SF_LEADS_TOPIC: str = os.getenv("KAFKA_SF_LEADS_TOPIC", "sf.leads.dev")
    KAFKA_SF_ACTIVITIES_TOPIC: str = os.getenv("KAFKA_SF_ACTIVITIES_TOPIC", "sf.activities.dev")
    KAFKA_SF_USERS_TOPIC: str = os.getenv("KAFKA_SF_USERS_TOPIC", "sf.users.dev")
    KAFKA_SF_CAMPAIGNS_TOPIC: str = os.getenv("KAFKA_SF_CAMPAIGNS_TOPIC", "sf.campaigns.dev")

    # PII
    PII_MASKING_ENABLED: bool = os.getenv("PII_MASKING_ENABLED", "false").lower() == "true"

    # CORS
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")


settings = Settings()


def validate_settings() -> dict:
    """
    Validates all required settings at startup.
    Returns dict of errors — empty dict means all good.
    """
    errors = {}

    # In staging/prod, require real Salesforce credentials
    if settings.ENVIRONMENT in ("stage", "prod"):
        if not settings.SF_CONSUMER_KEY:
            errors["SF_CONSUMER_KEY"] = {
                "error": "Missing Salesforce Consumer Key",
                "fix": "Set SF_CONSUMER_KEY in Vault or environment"
            }
        if not settings.SF_PRIVATE_KEY_PEM:
            errors["SF_PRIVATE_KEY_PEM"] = {
                "error": "Missing Salesforce RSA private key",
                "fix": "Set SF_PRIVATE_KEY_PEM in Vault"
            }
        if not settings.SF_USERNAME:
            errors["SF_USERNAME"] = {
                "error": "Missing Salesforce username",
                "fix": "Set SF_USERNAME in Vault"
            }
        if settings.FLASK_DEBUG:
            errors["FLASK_DEBUG"] = {
                "error": "FLASK_DEBUG must be False in staging/prod",
                "fix": "Set FLASK_DEBUG=False"
            }
        if settings.HMAC_ENABLED and not settings.HMAC_SECRET_KEY_CORE:
            errors["HMAC_SECRET_KEY_CORE"] = {
                "error": "HMAC enabled but no core key set",
                "fix": "Set HMAC_SECRET_KEY_CORE in Vault"
            }

    return errors


def setup_logging():
    """Configure logging based on settings."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.DEBUG),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
