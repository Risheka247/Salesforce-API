"""Tests for the health check endpoint."""


def test_health_returns_200(client):
    """Health endpoint should return 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_returns_healthy_status(client):
    """Health endpoint should return status: healthy."""
    response = client.get("/api/health")
    data = response.get_json()
    assert data["status"] == "healthy"


def test_health_returns_service_name(client):
    """Health endpoint should return the correct service name."""
    response = client.get("/api/health")
    data = response.get_json()
    assert data["service"] == "black-diamond-salesforce-service"


def test_health_returns_version(client):
    """Health endpoint should return version info."""
    response = client.get("/api/health")
    data = response.get_json()
    assert "version" in data
    assert data["version"] == "1.0.0"


def test_health_returns_timestamp(client):
    """Health endpoint should return a timestamp."""
    response = client.get("/api/health")
    data = response.get_json()
    assert "timestamp" in data


def test_health_returns_environment(client):
    """Health endpoint should return the environment."""
    response = client.get("/api/health")
    data = response.get_json()
    assert "environment" in data


def test_health_no_auth_required(client):
    """Health endpoint should work without any auth headers."""
    response = client.get("/api/health")
    assert response.status_code != 401
    assert response.status_code != 403
