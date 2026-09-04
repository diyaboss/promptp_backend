from datetime import datetime, timezone, timedelta

def test_create_round_admin(client):
    response = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-admin-token"},
        json={
            "round_number": 1,
            "name": "Test Round",
            "start_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "end_time": (datetime.now(timezone.utc) + timedelta(minutes=55)).isoformat(),
            "attempt_limit": 5,
            "status": "DRAFT"
        }
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Test Round"
    assert "id" in response.json()

def test_create_round_unauthorized(client):
    response = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-user-token"},
        json={
            "round_number": 1,
            "name": "Test Round"
        }
    )
    assert response.status_code == 403

def test_start_round(client, db):
    # Setup round
    res = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-admin-token"},
        json={
            "round_number": 2,
            "name": "Test Start Round"
        }
    )
    round_id = res.json()["id"]
    
    start_res = client.post(
        f"/api/admin/rounds/{round_id}/start",
        headers={"Authorization": "Bearer mock-admin-token"}
    )
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "ACTIVE"
