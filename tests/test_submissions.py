def test_create_submission(client):
    # Setup round
    res = client.post(
        "/api/admin/rounds",
        headers={"Authorization": "Bearer mock-admin-token"},
        json={
            "round_number": 6,
            "name": "Sub Round",
            "attempt_limit": 2
        }
    )
    round_id = res.json()["id"]
    client.post(f"/api/admin/rounds/{round_id}/start", headers={"Authorization": "Bearer mock-admin-token"})
    
    # Generate
    gen_res = client.post(
        "/api/generations",
        headers={"Authorization": "Bearer mock-user-token"},
        json={"round_id": round_id, "prompt": "Submission test"}
    )
    gen_id = gen_res.json()["id"]
    
    # Submit
    sub_res = client.post(
        "/api/submissions",
        headers={"Authorization": "Bearer mock-user-token"},
        json={"generation_id": gen_id}
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["generation_id"] == gen_id
    
    # Try submit again (should fail with 409)
    sub_res_2 = client.post(
        "/api/submissions",
        headers={"Authorization": "Bearer mock-user-token"},
        json={"generation_id": gen_id}
    )
    assert sub_res_2.status_code == 409
