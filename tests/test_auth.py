"""Tests for authentication — HMAC and Salesforce token manager."""
from app.auth.salesforce_auth import MockTokenManager, SalesforceTokenManager


def test_mock_token_manager_returns_token():
    """Mock token manager should always return a token."""
    manager = MockTokenManager()
    token, instance_url = manager.get_token()
    assert token is not None
    assert instance_url is not None


def test_mock_token_manager_is_connected():
    """Mock token manager should always be connected."""
    manager = MockTokenManager()
    assert manager.is_connected is True


def test_mock_token_manager_returns_instance_url():
    """Mock token manager should return a valid instance URL."""
    manager = MockTokenManager()
    _, instance_url = manager.get_token()
    assert instance_url.startswith("https://")


def test_salesforce_token_manager_requires_credentials():
    """SalesforceTokenManager should be instantiable with credentials."""
    manager = SalesforceTokenManager(
        consumer_key="test_key",
        private_key_pem="test_pem",
        username="user@example.com",
        login_url="https://test.salesforce.com"
    )
    assert manager is not None
    assert manager.is_connected is False  # not connected until token refreshed


def test_key_verify_endpoint_returns_200(client):
    """Key verify endpoint should return 200 (HMAC disabled in dev)."""
    response = client.get("/api/key/verify")
    assert response.status_code == 200


def test_key_verify_returns_success(client):
    """Key verify endpoint should return success true."""
    response = client.get("/api/key/verify")
    data = response.get_json()
    assert data["success"] is True
