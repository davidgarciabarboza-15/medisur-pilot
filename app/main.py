import os
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Toda la configuración viene de variables de entorno.
APP_VERSION = os.getenv("APP_VERSION", "dev")
GIT_SHA = os.getenv("GIT_SHA", "unknown")
BUILD_DATE = os.getenv("BUILD_DATE", "unknown")
POD_NAME = os.getenv("POD_NAME", "local")
READY_DELAY_SECONDS = float(os.getenv("READY_DELAY_SECONDS", "0"))
START_TIME = time.time()

# Se agrega la etiqueta "pod" para que cada réplica tenga su propia serie
# en Prometheus aunque se consulte a través del Service.
REQUESTS = Counter(
    "http_requests_total",
    "Total de peticiones HTTP",
    ["pod", "method", "endpoint", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Duración de las peticiones HTTP en segundos",
    ["pod", "method", "endpoint"],
)
BUILD_INFO = Gauge("app_build_info", "Versión desplegada", ["version", "commit"])
BUILD_INFO.labels(version=APP_VERSION, commit=GIT_SHA).set(1)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("APP_SECRET_KEY", "")
ITEMS = []


@app.before_request
def start_timer():
    g.start = time.perf_counter()


@app.after_request
def record_metrics(response):
    endpoint = request.url_rule.rule if request.url_rule else "unmatched"
    elapsed = time.perf_counter() - g.get("start", time.perf_counter())
    REQUESTS.labels(POD_NAME, request.method, endpoint, str(response.status_code)).inc()
    LATENCY.labels(POD_NAME, request.method, endpoint).observe(elapsed)
    return response


@app.get("/health")
def health():
    return jsonify(status="ok"), 200


@app.get("/ready")
def ready():
    if time.time() - START_TIME >= READY_DELAY_SECONDS:
        return jsonify(status="ready"), 200
    return jsonify(status="starting"), 503


@app.get("/version")
def version():
    return jsonify(version=APP_VERSION, commit=GIT_SHA, build_date=BUILD_DATE)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.get("/api/items")
def list_items():
    return jsonify(ITEMS)


@app.post("/api/items")
def create_item():
    data = request.get_json(silent=True)
    if not data or not str(data.get("name", "")).strip():
        return jsonify(error="El campo 'name' es obligatorio"), 400
    item = {"id": len(ITEMS) + 1, "name": str(data["name"]).strip()}
    ITEMS.append(item)
    return jsonify(item), 201


@app.get("/api/fail")
def fail():
    # Endpoint de apoyo para la demo: genera errores 5xx visibles en Grafana.
    return jsonify(error="fallo simulado"), 500