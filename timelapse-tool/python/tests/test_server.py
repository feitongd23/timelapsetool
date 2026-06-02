from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_echoes_ping():
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data == {"type": "pong"}
