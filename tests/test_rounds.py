from datetime import datetime, timezone, timedelta

def test_get_current_round(client):
    # Create and start a round first
    res = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-admin-token"},
        json={
            "round_number": 3,
            "name": "Active Round"
        }
    )
    round_id = res.json()["id"]
    client.post(
        f"/api/admin/rounds/{round_id}/start",
        headers={"Authorization": "Bearer mock-admin-token"}
    )
    
    # Fetch as user
    response = client.get(
        "/api/rounds/current",
        headers={"Authorization": "Bearer mock-user-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACTIVE"
    assert "target" in data
    # Ensure sensitive info is NOT exposed
    assert "reference_prompt" not in data.get("target", {})
    assert "seed" not in data.get("target", {})

def test_get_current_round_not_found(client, db):
    # End all rounds for this test
    # (Simplified for testing, assuming the above tests ran sequentially)
    # We will just fetch it, it might return the previous active one if we didn't end it
    # Let's end all of them
    while True:
        round_res = client.get("/api/rounds/current", headers={"Authorization": "Bearer mock-user-token"})
        if round_res.status_code == 200:
            r_id = round_res.json()["id"]
            client.post(
                f"/api/admin/rounds/{r_id}/end",
                headers={"Authorization": "Bearer mock-admin-token"}
            )
        else:
            break
    
    response = client.get(
        "/api/rounds/current",
        headers={"Authorization": "Bearer mock-user-token"}
    )
    assert response.status_code == 404
