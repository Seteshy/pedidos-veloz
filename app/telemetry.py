import json
import logging
import os
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

REQUESTS = Counter("veloz_http_requests_total", "Requisicoes HTTP", ["service", "route", "status"])
LATENCY = Histogram("veloz_http_duration_seconds", "Duracao HTTP", ["service", "route"])
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("veloz")


def setup(app, role):
    provider = TracerProvider(resource=Resource.create({"service.name": role}))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def observe(request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            # Usa o template da rota, nunca o ID do pedido como label.
            route = getattr(request.scope.get("route"), "path", "unknown")
            if request.url.path not in ("/health/live", "/health/ready", "/metrics", "/metrics/"):
                elapsed = time.perf_counter() - start
                REQUESTS.labels(role, route, str(status)).inc()
                LATENCY.labels(role, route).observe(elapsed)
                span = trace.get_current_span().get_span_context()
                logger.info(json.dumps({"service": role, "route": route, "status": status,
                                        "duration_ms": round(elapsed * 1000, 2),
                                        "trace_id": format(span.trace_id, "032x")}))

    # Deve envolver o middleware de logs, mantendo o span ativo durante o registro.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready,metrics")
