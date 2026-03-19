import unittest
from datetime import datetime
from unittest.mock import patch

import app as app_module


AUTH_USER = {
    "_id": "user-1",
    "email": "person@example.com",
    "is_active": True,
    "is_admin": False,
}


class PaymentRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()
        self.auth_headers = {"Authorization": "Bearer valid-token"}

    def tearDown(self):
        self.create_indexes_patcher.stop()

    def _auth_patches(self):
        return (
            patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"}),
            patch("app.auth.models.find_user_by_id", return_value=AUTH_USER),
        )

    def test_export_history_requires_authentication(self):
        response = self.client.get("/api/payments/history/export")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Authorization required"})

    @patch("app.payments.routes.model.get_user_transactions")
    def test_export_history_returns_csv_for_authenticated_user(self, get_user_transactions):
        get_user_transactions.return_value = [
            {
                "_id": "txn-1",
                "razorpay_order_id": "order_123",
                "razorpay_payment_id": "pay_123",
                "package_id": "starter",
                "amount": 9900,
                "credits": 100,
                "status": "success",
                "created_at": datetime(2026, 3, 1, 10, 30, 0),
                "updated_at": datetime(2026, 3, 1, 10, 35, 0),
            }
        ]

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.get(
                "/api/payments/history/export",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn(
            "attachment; filename=payment_history.csv",
            response.headers["Content-Disposition"],
        )
        csv_text = response.get_data(as_text=True)
        self.assertIn(
            "Order ID,Payment ID,Package ID,Amount,Currency,Credits Purchased,Payment Status,Created At,Updated At",
            csv_text,
        )
        self.assertIn(
            "order_123,pay_123,starter,9900,INR,100,success,2026-03-01T10:30:00,2026-03-01T10:35:00",
            csv_text,
        )
        get_user_transactions.assert_called_once_with("user-1", 10000)


if __name__ == "__main__":
    unittest.main()
