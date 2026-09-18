from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["groq"] == "mock"
    assert body["telegram"] == "disabled"
    assert body["google_sheets"] == "disabled"
