import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main


def response(code=200, payload=None):
    return httpx.Response(code, json=payload or {}, request=httpx.Request("POST", "http://test"))


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_live(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)

    def test_invalid_quantity_is_rejected_before_forward(self):
        with patch.object(main, "remote") as call:
            result = self.client.post("/orders", json={"order_id": str(uuid4()), "quantity": 0})
            self.assertEqual(result.status_code, 422)
            call.assert_not_called()

    def test_gateway_forwards_order(self):
        with patch.object(main, "remote", return_value=response(payload={"status": "CONFIRMED"})):
            result = self.client.post("/orders", json={"order_id": str(uuid4())})
            self.assertEqual(result.json()["status"], "CONFIRMED")

    def test_dependency_timeout_is_503(self):
        with patch.object(main, "remote", side_effect=httpx.ConnectTimeout("timeout")):
            result = self.client.get("/stock")
            self.assertEqual(result.status_code, 503)

    def test_log_keeps_incoming_trace_id(self):
        trace_id = "1234567890abcdef1234567890abcdef"
        with patch.object(main, "remote", return_value=response(payload=[])):
            with self.assertLogs("veloz", level="INFO") as logs:
                self.client.get("/stock", headers={"traceparent": f"00-{trace_id}-1234567890abcdef-01"})
        event = json.loads(logs.records[0].getMessage())
        self.assertEqual(event["trace_id"], trace_id)


class OrderWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.data = main.OrderInput(order_id=uuid4())
        self.db = patch.object(main, "connect")
        self.conn = self.db.start().return_value.__enter__.return_value
        self.conn.execute.return_value.fetchone.return_value = {"order_id": str(self.data.order_id)}
        self.status = patch.object(main, "set_status", side_effect=lambda oid, state: {"status": state})
        self.change = self.status.start()
        self.addCleanup(self.db.stop)
        self.addCleanup(self.status.stop)

    def test_approved_payment_confirms_order(self):
        with patch.object(main, "remote", side_effect=[response(), response(payload={"status": "APPROVED"})]):
            self.assertEqual(main.process_order(self.data)["status"], "CONFIRMED")

    def test_insufficient_stock_does_not_charge(self):
        with patch.object(main, "remote", return_value=response(409)) as remote:
            self.assertEqual(main.process_order(self.data)["status"], "REJECTED_STOCK")
            self.assertEqual(remote.call_count, 1)

    def test_declined_payment_compensates_reservation(self):
        with patch.object(main, "remote", side_effect=[response(), response(payload={"status": "DECLINED"}), response()]) as remote:
            self.assertEqual(main.process_order(self.data)["status"], "REJECTED_PAYMENT")
            self.assertEqual(remote.call_args.args[:2], ("estoque", "DELETE"))

    def test_uncertain_payment_requires_manual_review(self):
        with patch.object(main, "remote", side_effect=[response(), httpx.ReadTimeout("timeout")]) as remote:
            self.assertEqual(main.process_order(self.data)["status"], "MANUAL_REVIEW")
            self.assertEqual(remote.call_count, 2)

    def test_repeated_id_does_not_repeat_side_effects(self):
        self.conn.execute.return_value.fetchone.return_value = None
        existing = {"sku": "CAMISETA", "quantity": 1, "simulate_decline": False, "status": "CONFIRMED"}
        with patch.object(main, "get_order", return_value=existing), patch.object(main, "remote") as remote:
            self.assertEqual(main.process_order(self.data), existing)
            remote.assert_not_called()

    def test_repeated_id_with_other_payload_is_conflict(self):
        self.conn.execute.return_value.fetchone.return_value = None
        existing = {"sku": "CAMISETA", "quantity": 2, "simulate_decline": False}
        with patch.object(main, "get_order", return_value=existing):
            with self.assertRaises(HTTPException) as caught:
                main.process_order(self.data)
            self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
