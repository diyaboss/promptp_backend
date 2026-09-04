def test_auth_me_mock_user(client):
    response = client.get(
        "/api/me",
        headers={"Authorization": "Bearer mock-user-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "participant"
    assert data["email"] == "user@example.com"

def test_auth_me_mock_admin(client):
    response = client.get(
        "/api/me",
        headers={"Authorization": "Bearer mock-admin-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"

def test_auth_me_unauthorized(client):
    response = client.get(
        "/api/me",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
