"""Tests for maintenance endpoints."""
import json


def test_cleanup_returns_200(client):
    """Cleanup endpoint should return 200."""
    response = client.post("/api/maintenance/cleanup")
    assert response.status_code == 200


def test_cleanup_returns_success(client):
    """Cleanup endpoint should return success true."""
    response = client.post("/api/maintenance/cleanup")
    data = response.get_json()
    assert data["success"] is True


def test_cleanup_returns_deleted_count(client):
    """Cleanup should return how many records were deleted."""
    response = client.post("/api/maintenance/cleanup")
    data = response.get_json()
    assert "deleted" in data
    assert isinstance(data["deleted"], int)


def test_cleanup_returns_message(client):
    """Cleanup should return a message."""
    response = client.post("/api/maintenance/cleanup")
    data = response.get_json()
    assert "message" in data
