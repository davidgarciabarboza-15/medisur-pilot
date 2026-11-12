# ---- Etapa 1: instalar dependencias (aquí queda todo lo de compilación) ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Etapa 2: imagen final, sin herramientas de compilación ----
FROM python:3.12-slim
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE} \
    PYTHONUNBUFFERED=1

# Usuario sin privilegios
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /srv
COPY --from=builder /install /usr/local
COPY app ./app

USER 10001
EXPOSE 8080

# 1 solo worker con varios hilos: las métricas viven en memoria del proceso,
# con varios workers /metrics devolvería datos distintos en cada petición.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--access-logfile", "-", "app.main:app"]