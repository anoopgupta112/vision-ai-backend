import unittest
from unittest.mock import MagicMock, patch

import app as app_module


AUTH_USER = {
    "_id": "user-1",
    "email": "person@example.com",
    "is_active": True,
    "is_admin": False,
}


class SavedSearchRoutesTestCase(unittest.TestCase):
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

    def test_create_saved_search_validates_required_fields(self):
        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/saved-searches",
                json={"keyword": "", "location": "Mumbai", "limit": 10},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Keyword is required"})

    @patch("app.projects.lead_gen.saved_searches.routes.pipeline.create_saved_search")
    @patch("app.projects.lead_gen.saved_searches.routes.model.to_response")
    def test_create_saved_search_accepts_query_from_lead_gen_workflow(self, to_response, create_saved_search):
        create_saved_search.return_value = {"_id": "saved-2"}
        to_response.return_value = {
            "id": "saved-2",
            "name": "plumbers in mumbai",
            "query": "plumbers in mumbai",
            "limit": 20,
            "query_preview": "plumbers in mumbai",
        }

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/saved-searches",
                json={"query": "plumbers in mumbai", "limit": 20},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["saved_search"]["query"], "plumbers in mumbai")
        create_saved_search.assert_called_once_with(
            "user-1",
            "plumbers in mumbai",
            20,
            name=None,
            keyword=None,
            location=None,
        )

    @patch("app.projects.lead_gen.saved_searches.routes.pipeline.create_saved_search")
    @patch("app.projects.lead_gen.saved_searches.routes.model.to_response")
    def test_create_saved_search_returns_serialized_response(self, to_response, create_saved_search):
        create_saved_search.return_value = {"_id": "saved-1"}
        to_response.return_value = {
            "id": "saved-1",
            "name": "Plumbers in Mumbai",
            "query": "Plumbers in Mumbai",
            "keyword": "Plumbers",
            "location": "Mumbai",
            "limit": 10,
            "query_preview": "Plumbers in Mumbai",
        }

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/saved-searches",
                json={"keyword": "Plumbers", "location": "Mumbai", "limit": 10},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["saved_search"]["id"], "saved-1")
        create_saved_search.assert_called_once_with(
            "user-1",
            "Plumbers in Mumbai",
            10,
            name=None,
            keyword="Plumbers",
            location="Mumbai",
        )

    @patch("app.projects.lead_gen.saved_searches.routes.pipeline.list_saved_searches")
    @patch("app.projects.lead_gen.saved_searches.routes.model.to_response")
    def test_list_saved_searches_returns_user_items(self, to_response, list_saved_searches):
        list_saved_searches.return_value = [{"_id": "saved-1"}]
        to_response.return_value = {
            "id": "saved-1",
            "name": "Plumbers in Mumbai",
            "query": "Plumbers in Mumbai",
            "keyword": "Plumbers",
            "location": "Mumbai",
            "limit": 10,
            "query_preview": "Plumbers in Mumbai",
        }

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.get(
                "/api/lead_gen/saved-searches?limit=5",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        list_saved_searches.assert_called_once_with("user-1", limit=5)

    @patch("app.projects.lead_gen.saved_searches.routes.pipeline.delete_saved_search")
    def test_delete_saved_search_returns_success_message(self, delete_saved_search):
        delete_saved_search.return_value = {"message": "Saved search deleted"}

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.delete(
                "/api/lead_gen/saved-searches/saved-1",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"message": "Saved search deleted"})
        delete_saved_search.assert_called_once_with("saved-1", "user-1")

    @patch("app.projects.lead_gen.saved_searches.routes.pipeline.delete_saved_search")
    def test_delete_saved_search_returns_not_found_error(self, delete_saved_search):
        from app.core.exceptions import NotFoundError

        delete_saved_search.side_effect = NotFoundError("Saved search not found")

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.delete(
                "/api/lead_gen/saved-searches/missing-search",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Saved search not found"})
        delete_saved_search.assert_called_once_with("missing-search", "user-1")


class SavedSearchModelTestCase(unittest.TestCase):
    def test_delete_saved_search_raises_when_nothing_was_removed(self):
        from app.core.exceptions import NotFoundError
        from app.projects.lead_gen.saved_searches import pipeline

        mock_result = MagicMock()
        mock_result.deleted_count = 0

        with patch("app.projects.lead_gen.saved_searches.pipeline.model.delete_for_user", return_value=mock_result):
            with self.assertRaises(NotFoundError):
                pipeline.delete_saved_search("saved-1", "user-1")


if __name__ == "__main__":
    unittest.main()
