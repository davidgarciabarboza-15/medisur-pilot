import pytest

from app.main import ITEMS, app


@pytest.fixture
def client():
    ITEMS.clear()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_health_devuelve_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_ready_devuelve_200_cuando_ya_arranco(client):
    assert client.get("/ready").status_code == 200


def test_ready_devuelve_503_mientras_arranca(client, monkeypatch):
    monkeypatch.setattr("app.main.READY_DELAY_SECONDS", 9999)
    assert client.get("/ready").status_code == 503


def test_version_incluye_los_tres_campos(client):
    data = client.get("/version").get_json()
    assert set(data) == {"version", "commit", "build_date"}


def test_crear_y_listar_items(client):
    created = client.post("/api/items", json={"name": "Paracetamol"})
    assert created.status_code == 201
    assert created.get_json() == {"id": 1, "name": "Paracetamol"}
    assert client.get("/api/items").get_json() == [{"id": 1, "name": "Paracetamol"}]


def test_crear_item_sin_nombre_devuelve_400(client):
    response = client.post("/api/items", json={})
    assert response.status_code == 400
    assert "name" in response.get_json()["error"]


def test_metricas_cuentan_las_peticiones(client):
    client.get("/health")
    body = client.get("/metrics").get_data(as_text=True)
    assert "http_requests_total" in body
    assert 'endpoint="/health"' in body
    assert "http_request_duration_seconds_bucket" in body


def test_ruta_inexistente_devuelve_404(client):
    assert client.get("/no-existe").status_code == 404


def test_endpoint_de_fallo_simulado_devuelve_500(client):
    assert client.get("/api/fail").status_code == 500