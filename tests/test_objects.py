"""Tests for Salesforce objects and batch info endpoints."""
from unittest.mock import patch, MagicMock
from app.auth.salesforce_auth import MockTokenManager


def test_objects_returns_200(client):
    response = client.get("/api/objects")
    assert response.status_code == 200


def test_objects_returns_supported_objects(client):
    response = client.get("/api/objects")
    data = response.get_json()
    assert "supported_objects" in data
    assert len(data["supported_objects"]) > 0


def test_objects_contains_contact(client):
    response = client.get("/api/objects")
    names = [o["name"] for o in response.get_json()["supported_objects"]]
    assert "Contact" in names


def test_objects_contains_account(client):
    response = client.get("/api/objects")
    names = [o["name"] for o in response.get_json()["supported_objects"]]
    assert "Account" in names


def test_objects_contains_opportunity(client):
    response = client.get("/api/objects")
    names = [o["name"] for o in response.get_json()["supported_objects"]]
    assert "Opportunity" in names


def test_objects_contains_soql_template(client):
    response = client.get("/api/objects")
    for obj in response.get_json()["supported_objects"]:
        assert "SELECT" in obj["soql_template"].upper()


def test_objects_contains_incremental_support(client):
    response = client.get("/api/objects")
    for obj in response.get_json()["supported_objects"]:
        assert "supports_incremental" in obj


def test_batch_info_returns_200(client):
    """Batch info should return 200 with mock token manager."""
    with patch("app.auth.salesforce_auth.create_token_manager") as mock_factory:
        mock_factory.return_value = MockTokenManager()
        response = client.get("/api/batch/info")
    assert response.status_code == 200


def test_batch_info_returns_org_info(client):
    with patch("app.auth.salesforce_auth.create_token_manager") as mock_factory:
        mock_factory.return_value = MockTokenManager()
        data = client.get("/api/batch/info").get_json()
    assert "org" in data
    assert "instance_url" in data["org"]


def test_batch_info_returns_service_info(client):
    with patch("app.auth.salesforce_auth.create_token_manager") as mock_factory:
        mock_factory.return_value = MockTokenManager()
        data = client.get("/api/batch/info").get_json()
    assert "service" in data
    assert "max_concurrent_scans" in data["service"]
