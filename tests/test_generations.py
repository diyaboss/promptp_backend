def test_create_generation(client):
    # Setup round and start
    res = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-admin-token"},
        json={
            "round_number": 4,
            "name": "Gen Round"
        }
    )
    round_id = res.json()["id"]
    client.post(
        f"/api/admin/rounds/{round_id}/start",
        headers={"Authorization": "Bearer mock-admin-token"}
    )
    
    # Generate
    gen_res = client.post(
        "/api/generations",
        headers={"Authorization": "Bearer mock-user-token"},
        json={
            "round_id": round_id,
            "prompt": "A beautiful sunset"
        }
    )
    
    assert gen_res.status_code == 200
    data = gen_res.json()
    assert data["prompt"] == "A beautiful sunset"
    assert data["status"] == "COMPLETE"
    assert "image_path" in data

def test_attempt_limit(client):
    # Setup round with limit 1
    res = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-admin-token"},
        json={
            "round_number": 5,
            "name": "Limit Round",
            "attempt_limit": 1
        }
    )
    round_id = res.json()["id"]
    client.post(
        f"/api/admin/rounds/{round_id}/start",
        headers={"Authorization": "Bearer mock-admin-token"}
    )
    
    # First attempt
    client.post(
        "/api/generations",
        headers={"Authorization": "Bearer mock-user-token"},
        json={"round_id": round_id, "prompt": "First"}
    )
    
    # Second attempt (should fail)
    gen_res = client.post(
        "/api/generations",
        headers={"Authorization": "Bearer mock-user-token"},
        json={"round_id": round_id, "prompt": "Second"}
    )
    assert gen_res.status_code == 429

def test_get_generations(client):
    res = client.get(
        "/api/generations",
        headers={"Authorization": "Bearer mock-user-token"}
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)
