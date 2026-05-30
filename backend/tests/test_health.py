from fastapi.testclient import TestClient

from src.main import app


def test_root_returns_200():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from FastAPI"}
