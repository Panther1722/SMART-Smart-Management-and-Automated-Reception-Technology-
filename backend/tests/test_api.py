def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "llm" in data
    assert "email" in data


def test_session_start_and_chat(client):
    start = client.post(
        "/api/session/start",
        json={"email": "guest@example.com"},
    )
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    chat = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "Hi, my name is Alex Smith. I need a room for 2 guests.",
        },
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["session_id"] == session_id
    assert body["reply"]


def test_booking_requests_requires_api_key(client):
    response = client.get("/api/booking-requests")
    assert response.status_code == 401


def test_booking_requests_with_api_key(client, admin_headers):
    client.post("/api/session/start", json={"email": "guest@example.com"})
    response = client.get("/api/booking-requests", headers=admin_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_validation_error_format(client):
    response = client.post("/api/session/start", json={"email": "bad"})
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "validation_error"
