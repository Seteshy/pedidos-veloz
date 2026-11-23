"""MVP didatico: uma imagem, quatro processos/servicos com responsabilidades distintas."""
import os
from uuid import UUID

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db import connect
from app.telemetry import setup

ROLE = os.getenv("SERVICE_ROLE", "gateway")
URLS = {name: os.getenv(f"{name.upper()}_URL", f"http://{name}:8000")
        for name in ("pedidos", "estoque", "pagamentos")}
app = FastAPI(title=f"Pedidos Veloz - {ROLE}", version="0.1.0")
setup(app, ROLE)


class OrderInput(BaseModel):
    order_id: UUID
    sku: str = Field(default="CAMISETA", pattern=r"^[A-Z0-9_-]{1,30}$")
    quantity: int = Field(default=1, ge=1, le=100)
    simulate_decline: bool = False


class Reservation(BaseModel):
    order_id: UUID
    sku: str = Field(pattern=r"^[A-Z0-9_-]{1,30}$")
    quantity: int = Field(ge=1, le=100)


class Payment(BaseModel):
    order_id: UUID
    simulate_decline: bool = False


def remote(service, method, path, payload=None):
    # Sem retry automatico de operacoes que alteram estado.
    with httpx.Client(timeout=5, trust_env=False) as client:
        return client.request(method, URLS[service] + path, json=payload)


def forward(service, method, path, payload=None):
    try:
        response = remote(service, method, path, payload)
        return JSONResponse(status_code=response.status_code, content=response.json())
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Servico temporariamente indisponivel") from None


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Banco temporariamente indisponivel"})


@app.get("/health/live")
def live():
    return {"status": "alive", "service": ROLE}


@app.get("/health/ready")
def ready():
    if ROLE != "gateway":
        with connect() as conn:
            conn.execute("SELECT 1")
    return {"status": "ready", "service": ROLE}


def get_order(order_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id=%s", (str(order_id),)).fetchone()
    if not row:
        raise HTTPException(404, "Pedido nao encontrado")
    return row


def set_status(order_id, status):
    with connect() as conn:
        conn.execute("UPDATE orders SET status=%s WHERE order_id=%s", (status, str(order_id)))
    return get_order(order_id)


def process_order(data):
    payload = data.model_dump(mode="json")
    with connect() as conn:
        created = conn.execute(
            "INSERT INTO orders(order_id,sku,quantity,simulate_decline,status) "
            "VALUES (%s,%s,%s,%s,'PENDING') ON CONFLICT DO NOTHING RETURNING order_id",
            (str(data.order_id), data.sku, data.quantity, data.simulate_decline),
        ).fetchone()
    if not created:
        existing = get_order(data.order_id)
        if any(existing[key] != payload[key] for key in ("sku", "quantity", "simulate_decline")):
            raise HTTPException(409, "ID ja utilizado com outros dados")
        # Nao reprocessa um pedido em andamento ou incerto.
        return existing
    try:
        reserve = remote("estoque", "POST", "/reservations",
                         {key: payload[key] for key in ("order_id", "sku", "quantity")})
        if reserve.status_code == 409:
            return set_status(data.order_id, "REJECTED_STOCK")
        reserve.raise_for_status()
        pay = remote("pagamentos", "POST", "/payments",
                     {key: payload[key] for key in ("order_id", "simulate_decline")})
        pay.raise_for_status()
        if pay.json()["status"] == "DECLINED":
            release = remote("estoque", "DELETE", f"/reservations/{data.order_id}")
            release.raise_for_status()
            return set_status(data.order_id, "REJECTED_PAYMENT")
        return set_status(data.order_id, "CONFIRMED")
    except (httpx.HTTPError, KeyError, ValueError):
        # Timeout pode ocorrer depois de um efeito remoto. Exige conciliacao.
        return set_status(data.order_id, "MANUAL_REVIEW")


if ROLE == "gateway":
    @app.get("/")
    def index():
        return {"project": "Pedidos Veloz", "docs": "/docs", "payment": "SIMULATED"}

    @app.post("/orders")
    def create_order(data: OrderInput):
        return forward("pedidos", "POST", "/orders", data.model_dump(mode="json"))

    @app.get("/orders/{order_id}")
    def read_order(order_id: UUID):
        return forward("pedidos", "GET", f"/orders/{order_id}")

    @app.get("/stock")
    def read_stock():
        return forward("estoque", "GET", "/stock")

elif ROLE == "pedidos":
    @app.post("/orders")
    def create_order(data: OrderInput):
        return process_order(data)

    @app.get("/orders/{order_id}")
    def read_order(order_id: UUID):
        return get_order(order_id)

elif ROLE == "estoque":
    @app.get("/stock")
    def read_stock():
        with connect() as conn:
            return conn.execute("SELECT sku,quantity FROM inventory ORDER BY sku").fetchall()

    @app.post("/reservations")
    def reserve(data: Reservation):
        with connect() as conn:
            # Advisory lock serializa chamadas com o mesmo ID entre replicas.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(data.order_id),))
            previous = conn.execute("SELECT * FROM reservations WHERE order_id=%s",
                                    (str(data.order_id),)).fetchone()
            if previous:
                if (previous["sku"], previous["quantity"]) != (data.sku, data.quantity):
                    raise HTTPException(409, "Reserva existente com outros dados")
                return previous
            changed = conn.execute(
                "UPDATE inventory SET quantity=quantity-%s WHERE sku=%s AND quantity>=%s RETURNING sku",
                (data.quantity, data.sku, data.quantity),
            ).fetchone()
            if not changed:
                raise HTTPException(409, "Estoque insuficiente ou produto inexistente")
            conn.execute("INSERT INTO reservations(order_id,sku,quantity) VALUES (%s,%s,%s)",
                         (str(data.order_id), data.sku, data.quantity))
        return {"status": "RESERVED"}

    @app.delete("/reservations/{order_id}")
    def release(order_id: UUID):
        with connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(order_id),))
            row = conn.execute("DELETE FROM reservations WHERE order_id=%s RETURNING sku,quantity",
                               (str(order_id),)).fetchone()
            if row:
                conn.execute("UPDATE inventory SET quantity=quantity+%s WHERE sku=%s",
                             (row["quantity"], row["sku"]))
        return {"status": "RELEASED"}

elif ROLE == "pagamentos":
    @app.post("/payments")
    def pay(data: Payment):
        status = "DECLINED" if data.simulate_decline else "APPROVED"
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO payments(order_id,status) VALUES (%s,%s) "
                "ON CONFLICT (order_id) DO UPDATE SET order_id=EXCLUDED.order_id RETURNING status",
                (str(data.order_id), status),
            ).fetchone()
        return {"status": row["status"], "provider": "SIMULATED"}
else:
    raise RuntimeError(f"SERVICE_ROLE invalido: {ROLE}")
