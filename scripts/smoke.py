"""Teste ponta a ponta contra o Compose ou port-forward do gateway.
Usa dados didaticos novos por execucao; nao apaga volumes ou registros.
"""
import json
import os
import urllib.error
import urllib.request
from uuid import uuid4

BASE = os.getenv("BASE_URL", "http://localhost:8080")


def call(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as result:
        return json.load(result)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    before = call("/stock")[0]["quantity"]
    check(before >= 1, "Necessario ao menos 1 CAMISETA para o teste")
    order = {"order_id": str(uuid4()), "sku": "CAMISETA", "quantity": 1}
    first = call("/orders", order)
    check(first["status"] == "CONFIRMED", f"Pedido nao confirmado: {first}")
    check(call(f'/orders/{order["order_id"]}')["status"] == "CONFIRMED", "Consulta divergente")
    check(call("/orders", order)["status"] == "CONFIRMED", "Idempotencia falhou")
    check(call("/stock")[0]["quantity"] == before - 1, "Reserva duplicada")
    declined = {**order, "order_id": str(uuid4()), "simulate_decline": True}
    # Se so havia uma unidade, a reserva acima esgotou o estoque; precisa de >=2.
    if before >= 2:
        check(call("/orders", declined)["status"] == "REJECTED_PAYMENT", "Recusa nao tratada")
        check(call("/stock")[0]["quantity"] == before - 1, "Compensacao nao devolveu estoque")
    missing = {**order, "order_id": str(uuid4()), "sku": "INEXISTENTE"}
    check(call("/orders", missing)["status"] == "REJECTED_STOCK", "Falta de estoque nao tratada")
    try:
        call("/orders", {**order, "order_id": str(uuid4()), "quantity": 0})
        raise RuntimeError("Entrada invalida foi aceita")
    except urllib.error.HTTPError as error:
        check(error.code == 422, "Esperado HTTP 422")
    print(json.dumps({"result": "PASS", "order_id": order["order_id"],
                      "stock_before": before, "stock_after": before - 1,
                      "decline_test": "PASS" if before >= 2 else "SKIPPED_NO_STOCK"}))


if __name__ == "__main__":
    main()
