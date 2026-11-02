import math
import unittest
from unittest.mock import MagicMock, patch

import app as app_module
from app.projects.vip_concierge.services.milvus_service import milvus_client
from app.projects.vip_concierge.services.presence_service import presence_service

AUTH_HEADERS = {"Authorization": "Bearer valid-vip-token"}


class VipConciergeRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

        self.decode_token_patcher = patch(
            "app.core.middleware.decode_token",
            return_value={"user_id": "user-vip-owner-1"},
        )
        self.find_user_patcher = patch(
            "app.auth.models.find_user_by_id",
            return_value={
                "_id": "user-vip-owner-1",
                "email": "boutique_owner@luxury.com",
                "is_active": True,
                "is_admin": False,
            },
        )
        self.decode_token_patcher.start()
        self.find_user_patcher.start()

    def tearDown(self):
        self.find_user_patcher.stop()
        self.decode_token_patcher.stop()
        self.create_indexes_patcher.stop()

    def test_health_check(self):
        resp = self.client.get("/api/vip-concierge/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("milvus_connected", data)

    @patch("app.projects.vip_concierge.api.routes.storage.create_customer")
    @patch("app.projects.vip_concierge.api.routes.storage.list_customers")
    def test_create_and_list_customers(self, mock_list, mock_create):
        mock_create.return_value = {
            "id": "cust-101",
            "name": "Rajesh Khanna",
            "tier": "Diamond VIP",
            "total_spent": 15400.0,
            "currency": "USD",
        }
        mock_list.return_value = [mock_create.return_value]

        # 1. Create
        payload = {
            "name": "Rajesh Khanna",
            "tier": "Diamond VIP",
            "total_spent": 15400.0,
            "notes": "Prefers single malt, size 42R",
        }
        res_create = self.client.post("/api/vip-concierge/customers", json=payload, headers=AUTH_HEADERS)
        self.assertEqual(res_create.status_code, 201)
        self.assertEqual(res_create.get_json()["customer"]["name"], "Rajesh Khanna")

        # 2. List
        res_list = self.client.get("/api/vip-concierge/customers", headers=AUTH_HEADERS)
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.get_json()["customers"]), 1)

    @patch("app.projects.vip_concierge.api.routes.storage.get_customer")
    @patch("app.projects.vip_concierge.api.routes.gemini_concierge_agent.generate_briefing")
    @patch("app.projects.vip_concierge.api.routes.storage.log_visit")
    def test_face_match_and_debounce_flow(self, mock_log_visit, mock_briefing, mock_get_customer):
        # Setup mock customer
        mock_customer = {
            "id": "cust-202",
            "user_id": "user-vip-owner-1",
            "name": "Lady Eleanor",
            "tier": "Platinum",
            "total_spent": 35000.0,
            "currency": "USD",
            "notes": "Prefers champagne, size 38",
            "purchases": [{"item": "Evening Gown", "price": 4500}],
        }
        mock_get_customer.return_value = mock_customer
        mock_briefing.return_value = {
            "headline": "VIP Lady Eleanor entered • Platinum Client ($35k LTV)",
            "greeting_approach": "Welcome back Lady Eleanor, delightful to see you.",
            "talking_point": "Compliment her style and show the newly arrived silk scarves.",
            "suggested_items": ["Embroidered Silk Shawl", "Diamond drop earrings"],
            "preferences_alert": "Offer chilled champagne immediately.",
        }
        mock_log_visit.return_value = {"id": "visit-001", "status": "new"}

        # Create deterministic 512-dim embedding
        raw_vec = [math.sin(i * 0.1) for i in range(512)]
        norm = math.sqrt(sum(x * x for x in raw_vec))
        norm_vec = [x / norm for x in raw_vec]

        # Insert vector directly into milvus_client (which uses fallback store when Milvus offline)
        milvus_client.insert_face_embedding(
            customer_id="cust-202",
            shop_id="default",
            embedding=norm_vec,
        )

        # Clear cooldown before test
        presence_service.reset_cooldown("cust-202")

        # Probe with same vector
        payload = {
            "embedding": norm_vec,
            "camera_id": "door_1",
            "shop_id": "default",
            "threshold": 0.70,
        }

        # First visit: Should MATCH and ALERT
        res1 = self.client.post("/api/vip-concierge/matches/search", json=payload, headers=AUTH_HEADERS)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertTrue(data1["matched"])
        self.assertEqual(data1["customer_id"], "cust-202")
        self.assertTrue(data1["alert_triggered"])
        self.assertIsNotNone(data1["dossier"])
        self.assertEqual(data1["dossier"]["headline"], "VIP Lady Eleanor entered • Platinum Client ($35k LTV)")

        # Second visit immediately after: Should MATCH but SUPPRESS alert (Debounce active)
        res2 = self.client.post("/api/vip-concierge/matches/search", json=payload, headers=AUTH_HEADERS)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2["matched"])
        self.assertFalse(data2["alert_triggered"])
        self.assertTrue(data2["cooldown_active"])

    def test_search_below_threshold(self):
        # Different non-matching vector
        non_matching_vec = [1.0 if i == 0 else 0.0 for i in range(512)]
        payload = {
            "embedding": non_matching_vec,
            "threshold": 0.85,
        }
        res = self.client.post("/api/vip-concierge/matches/search", json=payload, headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()["matched"])

    def test_matches_search_requires_auth(self):
        # Security test: Ensure unauthenticated requests are rejected with 401
        res = self.client.post("/api/vip-concierge/matches/search", json={"threshold": 0.5})
        self.assertEqual(res.status_code, 401)

    def test_events_stream_requires_auth(self):
        # Security test: Ensure unauthenticated SSE requests are rejected with 401
        res = self.client.get("/api/vip-concierge/events/stream")
        self.assertEqual(res.status_code, 401)

    @patch("app.projects.vip_concierge.api.routes.storage.list_recent_visits")
    @patch("app.projects.vip_concierge.api.routes.storage.list_customers")
    def test_stats_and_visits(self, mock_customers, mock_visits):
        mock_customers.return_value = [
            {"id": "c1", "total_spent": 10000, "visit_count": 5},
            {"id": "c2", "total_spent": 20000, "visit_count": 3},
        ]
        mock_visits.return_value = [
            {"id": "v1", "status": "new"},
            {"id": "v2", "status": "greeted"},
        ]

        res = self.client.get("/api/vip-concierge/stats", headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["total_vips"], 2)
        self.assertEqual(data["total_portfolio_spend"], 30000)
        self.assertEqual(data["recent_alerts_count"], 1)

    @patch("app.projects.vip_concierge.api.routes.storage.update_visit_status")
    def test_action_visit(self, mock_update_status):
        mock_update_status.return_value = True
        payload = {"status": "greeted", "staff_notes": "Offered sparkling water"}
        res = self.client.post("/api/vip-concierge/visits/visit-123/action", json=payload, headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        self.assertIn("greeted", res.get_json()["message"])

    @patch("app.projects.vip_concierge.api.routes.storage.upsert_shop")
    @patch("app.projects.vip_concierge.api.routes.storage.list_shops")
    def test_shop_crud(self, mock_list, mock_upsert):
        mock_upsert.return_value = {
            "shop_id": "shop_aurum_1",
            "name": "Aurum Diamonds",
            "industry": "jewelry",
            "is_active": True,
        }
        mock_list.return_value = [mock_upsert.return_value]

        # 1. Upsert Shop
        save_res = self.client.post("/api/vip-concierge/shops", json={
            "name": "Aurum Diamonds",
            "industry": "jewelry",
            "brand_tone": "Quiet luxury",
        }, headers=AUTH_HEADERS)
        self.assertEqual(save_res.status_code, 200)
        self.assertEqual(save_res.get_json()["shop"]["industry"], "jewelry")

        # 2. List Shops
        list_res = self.client.get("/api/vip-concierge/shops", headers=AUTH_HEADERS)
        self.assertEqual(list_res.status_code, 200)
        self.assertTrue(len(list_res.get_json()["shops"]) > 0)

    @patch("app.projects.vip_concierge.api.routes.shop_consultant_agent.consult")
    def test_shop_agent_chat(self, mock_consult):
        mock_consult.return_value = {
            "reply": "Welcome! Let us customize your jewelry boutique.",
            "proposed_config": {
                "name": "Aurum",
                "industry": "jewelry",
                "vip_tiers": [{"name": "Diamond", "min_spend": 50000, "perks": "Vault viewing"}],
                "client_attributes_schema": [{"key": "ring_size", "label": "Ring Size", "type": "text"}],
            },
            "quick_suggestions": ["Configure for Fine Jewelry", "Set VIP brackets"]
        }

        res = self.client.post("/api/vip-concierge/shops/agent/chat", json={
            "message": "We run a jewelry boutique in London."
        }, headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("jewelry boutique", data["reply"])
        self.assertEqual(data["proposed_config"]["industry"], "jewelry")

    def test_shop_agent_generate_preset(self):
        res = self.client.post("/api/vip-concierge/shops/agent/generate", json={
            "industry": "watches",
            "store_name": "Geneva Timepieces"
        }, headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        shop = res.get_json()["shop"]
        self.assertEqual(shop["industry"], "watches")
        self.assertEqual(shop["name"], "Geneva Timepieces")
        self.assertTrue(len(shop["client_attributes_schema"]) > 0)

    def test_get_shop_templates(self):
        res = self.client.get("/api/vip-concierge/shops/templates", headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("templates", data)
        self.assertTrue(len(data["templates"]) >= 5)
        industries = [t["industry"] for t in data["templates"]]
        self.assertIn("jewelry", industries)
        self.assertIn("clothing", industries)
        self.assertIn("watches", industries)

    def test_get_shop_agent_welcome(self):
        res = self.client.get("/api/vip-concierge/shops/agent/welcome", headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("welcome", data)
        self.assertIn("reply", data["welcome"])
        self.assertTrue(len(data["welcome"]["quick_suggestions"]) > 0)

    @patch("app.projects.vip_concierge.api.routes.discover_onvif_cameras")
    def test_discover_cctv_cameras(self, mock_discover):
        mock_discover.return_value = [{"ip": "192.168.1.120", "port": 80, "types": ["NetworkVideoTransmitter"]}]
        res = self.client.post("/api/vip-concierge/cameras/discover", json={"timeout": 1}, headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["cameras"][0]["ip"], "192.168.1.120")

    @patch("app.projects.vip_concierge.api.routes.test_rtsp_snapshot")
    def test_test_rtsp_stream(self, mock_test):
        mock_test.return_value = {"success": True, "width": 1920, "height": 1080, "preview_b64": "data:image/jpeg;base64,abc"}
        res = self.client.post("/api/vip-concierge/cameras/test-stream", json={
            "rtsp_url": "rtsp://admin:pass@192.168.1.50:554/stream"
        }, headers=AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["width"], 1920)

    @patch("app.projects.vip_concierge.api.routes.cctv_manager.start_camera_stream")
    @patch("app.projects.vip_concierge.api.routes.cctv_manager.stop_camera_stream")
    @patch("app.projects.vip_concierge.api.routes.storage.get_camera")
    def test_start_and_stop_camera_stream(self, mock_get_cam, mock_stop, mock_start):
        mock_get_cam.return_value = {
            "id": "cam_entrance_99",
            "name": "Entrance CCTV",
            "rtsp_url": "rtsp://admin:pass@192.168.1.50:554/live",
            "shop_id": "default",
        }
        mock_start.return_value = True
        mock_stop.return_value = True

        # Start stream
        start_res = self.client.post("/api/vip-concierge/cameras/cam_entrance_99/start-stream", headers=AUTH_HEADERS)
        self.assertEqual(start_res.status_code, 200)
        self.assertTrue(start_res.get_json()["active"])

        # Stop stream
        stop_res = self.client.post("/api/vip-concierge/cameras/cam_entrance_99/stop-stream", headers=AUTH_HEADERS)
        self.assertEqual(stop_res.status_code, 200)
        self.assertFalse(stop_res.get_json()["active"])


if __name__ == "__main__":
    unittest.main()
