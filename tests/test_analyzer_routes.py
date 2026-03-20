import unittest
from io import BytesIO
from unittest.mock import patch

import app as app_module


AUTH_HEADERS = {"Authorization": "Bearer valid-token"}


class AnalyzerRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

        self.decode_token_patcher = patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"})
        self.find_user_patcher = patch(
            "app.auth.models.find_user_by_id",
            return_value={"_id": "user-1", "email": "person@example.com", "is_active": True, "is_admin": False},
        )
        self.decode_token_patcher.start()
        self.find_user_patcher.start()

    def tearDown(self):
        self.find_user_patcher.stop()
        self.decode_token_patcher.stop()
        self.create_indexes_patcher.stop()

    def test_meta_returns_templates_and_provider(self):
        response = self.client.get("/api/analyzer/meta", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("provider", payload)
        self.assertTrue(payload["templates"])
        self.assertTrue(payload["fields"])

    def test_github_questions_requires_urls(self):
        with patch(
            "app.projects.analyzer.api.routes.generate_questions_from_github",
            return_value={"questions": [], "summary": "No code found."},
        ) as generate_questions:
            response = self.client.post("/api/analyzer/v1/github_questions", json={"github_urls": [], "num_questions": 10}, headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"questions": [], "summary": "No code found."})
        generate_questions.assert_called_once_with([], 10)

    @patch("app.projects.analyzer.api.routes.storage.create_form")
    @patch("app.projects.analyzer.api.routes.storage.list_forms")
    def test_create_form_uses_template_fields(self, list_forms, create_form):
        list_forms.return_value = [
            {
                "id": "form-1",
                "form_id": "abcd1234",
                "name": "Hiring Intake",
                "fields": [{"name": "resume", "label": "Resume", "data_type": "file"}],
                "submission_count": 0,
            }
        ]

        response = self.client.post(
            "/api/analyzer/forms",
            json={"name": "Hiring Intake", "template_name": "HR"},
            headers=AUTH_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        create_form.assert_called_once()
        self.assertEqual(response.get_json()["form"]["name"], "Hiring Intake")

    @patch("app.projects.analyzer.api.routes.process_uploaded_pdfs", return_value=[{"pdf_path": "resume.pdf", "match_report": {}, "github_questions": [], "links": []}])
    def test_resume_match_returns_results(self, process_uploaded_pdfs):
        response = self.client.post(
            "/api/analyzer/v1/match_from_pdfs",
            data={
                "jd": "Python developer with Flask experience",
                "pdf_files": (BytesIO(b"fake pdf"), "resume.pdf"),
            },
            headers=AUTH_HEADERS,
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"matches": [{"file_name": "resume.pdf", "pdf_path": "resume.pdf", "match_report": {}, "question_sets": [], "github_questions": [], "links": [], "resume_text": ""}]})
        process_uploaded_pdfs.assert_called_once()


if __name__ == "__main__":
    unittest.main()
