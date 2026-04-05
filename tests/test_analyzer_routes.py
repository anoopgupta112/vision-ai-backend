import unittest
from io import BytesIO
from unittest.mock import patch
import types
import sys

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

    def test_landing_page_renders(self):
        response = self.client.get("/api/analyzer", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertIn("DataExtractor", response.get_data(as_text=True))

    def test_form_builder_page_renders(self):
        response = self.client.get("/api/analyzer/form-builder", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Build your form", response.get_data(as_text=True))

    def test_github_questions_page_renders(self):
        response = self.client.get("/api/analyzer/github_questions", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertIn("GitHub Code Questions", response.get_data(as_text=True))

    @patch("app.projects.analyzer.api.routes.storage.get_form")
    def test_form_view_page_renders(self, get_form):
        get_form.return_value = {
            "form_id": "form123",
            "fields": [{"name": "resume", "label": "Resume", "data_type": "file", "accept": ["pdf"]}],
        }

        response = self.client.get("/api/analyzer/forms/form123/view")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Fill the Form", response.get_data(as_text=True))

    @patch("app.projects.analyzer.api.routes.storage.get_form")
    @patch("app.projects.analyzer.api.routes.storage.get_form_submissions")
    def test_analyze_pdfs_page_renders(self, get_form_submissions, get_form):
        get_form.return_value = {
            "form_id": "form123",
            "user_id": "user-1",
            "fields": [{"name": "resume", "label": "Resume", "data_type": "file", "accept": ["pdf"]}],
        }
        get_form_submissions.return_value = [
            {"id": "sub1", "resume": {"name": "resume.pdf", "path": "/tmp/resume.pdf"}}
        ]

        response = self.client.get("/api/analyzer/analyze_pdfs/form123", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Analyze PDFs", response.get_data(as_text=True))

    @patch("app.projects.analyzer.api.routes.storage.get_form")
    def test_form_submissions_rejects_non_owner(self, get_form):
        get_form.return_value = {
            "form_id": "form123",
            "user_id": "user-2",
            "fields": [{"name": "resume", "label": "Resume", "data_type": "file"}],
        }

        response = self.client.get("/api/analyzer/forms/form123/submissions", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Access denied"})

    @patch("app.projects.analyzer.api.routes.storage.get_form")
    def test_analyze_saved_pdfs_rejects_non_owner(self, get_form):
        get_form.return_value = {
            "form_id": "form123",
            "user_id": "user-2",
            "fields": [{"name": "resume", "label": "Resume", "data_type": "file"}],
        }

        response = self.client.post(
            "/api/analyzer/v1/analyze_from_excel/form123",
            data={"jd": "Python developer"},
            headers=AUTH_HEADERS,
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Access denied"})

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

    @patch("app.projects.analyzer.api.routes.credits_pipeline.deduct_credits")
    @patch("app.projects.analyzer.api.routes.credits_pipeline.get_user_balance", return_value=5)
    @patch("app.projects.analyzer.api.routes.process_uploaded_pdfs", return_value=[{"pdf_path": "resume.pdf", "match_report": {}, "github_questions": [], "links": []}])
    def test_resume_match_returns_results(self, process_uploaded_pdfs, get_user_balance, deduct_credits):
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
        get_user_balance.assert_called_once_with("user-1")
        deduct_credits.assert_called_once_with("user-1", 1, note="Analyzer usage: matched 1 uploaded PDF(s)")
        process_uploaded_pdfs.assert_called_once()

    def test_resume_match_deducts_credits_for_uploaded_pdfs(self):
        with patch(
            "app.projects.analyzer.api.routes.process_uploaded_pdfs",
            return_value=[
                {"pdf_path": "resume-1.pdf", "match_report": {}, "github_questions": [], "links": []},
                {"pdf_path": "resume-2.pdf", "match_report": {}, "github_questions": [], "links": []},
            ],
        ) as process_uploaded_pdfs, patch(
            "app.projects.analyzer.api.routes.credits_pipeline.get_user_balance",
            return_value=5,
        ) as get_user_balance, patch(
            "app.projects.analyzer.api.routes.credits_pipeline.deduct_credits"
        ) as deduct_credits:
            response = self.client.post(
                "/api/analyzer/v1/match_from_pdfs",
                data={
                    "jd": "Python developer with Flask experience",
                    "pdf_files": [
                        (BytesIO(b"fake pdf 1"), "resume-1.pdf"),
                        (BytesIO(b"fake pdf 2"), "resume-2.pdf"),
                    ],
                },
                headers=AUTH_HEADERS,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["matches"]), 2)
        get_user_balance.assert_called_once_with("user-1")
        deduct_credits.assert_called_once_with("user-1", 2, note="Analyzer usage: matched 2 uploaded PDF(s)")
        process_uploaded_pdfs.assert_called_once()

    def test_resume_match_returns_insufficient_credit_error_before_processing(self):
        with patch(
            "app.projects.analyzer.api.routes.process_uploaded_pdfs"
        ) as process_uploaded_pdfs, patch(
            "app.projects.analyzer.api.routes.credits_pipeline.get_user_balance",
            return_value=0,
        ) as get_user_balance, patch(
            "app.projects.analyzer.api.routes.credits_pipeline.deduct_credits"
        ) as deduct_credits:
            response = self.client.post(
                "/api/analyzer/v1/match_from_pdfs",
                data={
                    "jd": "Python developer with Flask experience",
                    "pdf_files": (BytesIO(b"fake pdf"), "resume.pdf"),
                },
                headers=AUTH_HEADERS,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Insufficient credits. You have 0, need 1"})
        get_user_balance.assert_called_once_with("user-1")
        deduct_credits.assert_not_called()
        process_uploaded_pdfs.assert_not_called()

    def test_form_analysis_deducts_credits_for_selected_pdfs(self):
        submission_docs = [
            {"_id": "sub-1", "data": {"resume": {"path": "/tmp/resume-1.pdf", "name": "resume-1.pdf"}}},
            {"_id": "sub-2", "data": {"resume": {"path": "/tmp/resume-2.pdf", "name": "resume-2.pdf"}}},
        ]

        with patch(
            "app.projects.analyzer.api.routes.storage.get_form",
            return_value={
                "form_id": "form123",
                "user_id": "user-1",
                "fields": [{"name": "resume", "label": "Resume", "data_type": "file"}],
            },
        ), patch(
            "app.projects.analyzer.api.routes.storage.get_submission_documents",
            return_value=submission_docs,
        ), patch(
            "app.projects.analyzer.api.routes.os.path.exists",
            return_value=True,
        ), patch(
            "app.projects.analyzer.api.routes.extract_text_from_pdf",
            return_value=("Resume text", []),
        ) as extract_text_from_pdf, patch(
            "app.projects.analyzer.api.routes.evaluate_resume_against_jd",
            return_value={"percent_match": 75},
        ), patch(
            "app.projects.analyzer.api.routes.generate_questions_from_jd",
            return_value={"questions": [], "summary": ""},
        ), patch(
            "app.projects.analyzer.api.routes.extract_experience_section",
            return_value="",
        ), patch(
            "app.projects.analyzer.api.routes.generate_questions_from_experience",
            return_value={},
        ), patch(
            "app.projects.analyzer.api.routes.extract_project_section",
            return_value="",
        ), patch(
            "app.projects.analyzer.api.routes.generate_questions_from_projects",
            return_value=[],
        ), patch(
            "app.projects.analyzer.api.routes.credits_pipeline.get_user_balance",
            return_value=10,
        ) as get_user_balance, patch(
            "app.projects.analyzer.api.routes.credits_pipeline.deduct_credits"
        ) as deduct_credits:
            response = self.client.post(
                "/api/analyzer/forms/form123/analyze",
                json={
                    "jd": "Python developer with Flask experience",
                    "selected_pdfs": ["resume-2.pdf"],
                },
                headers=AUTH_HEADERS,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["matches"]), 1)
        extract_text_from_pdf.assert_called_once_with("/tmp/resume-2.pdf")
        get_user_balance.assert_called_once_with("user-1")
        deduct_credits.assert_called_once_with(
            "user-1",
            1,
            note="Analyzer usage: analyzed 1 submission PDF(s) for form form123",
        )

    @patch.dict("os.environ", {"GEMINI_API_KEY_1": "k1"}, clear=False)
    def test_meta_prefers_gemini_when_any_gemini_key_exists(self):
        response = self.client.get("/api/analyzer/meta", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["provider"], "Gemini")

    def test_gemini_client_rotates_keys_until_success(self):
        from app.clients import gemini_client

        class FakeResponse:
            def __init__(self, text):
                self.text = text

        class FakeModel:
            def __init__(self, module, model_name=None, generation_config=None):
                self._module = module

            def generate_content(self, prompt):
                if self._module.current_key == "bad-key":
                    raise RuntimeError("quota exceeded")
                return FakeResponse("ok")

        fake_module = types.SimpleNamespace()
        fake_module.current_key = None

        def configure(api_key):
            fake_module.current_key = api_key

        def generative_model(model_name=None, generation_config=None):
            return FakeModel(fake_module, model_name=model_name, generation_config=generation_config)

        fake_module.configure = configure
        fake_module.GenerativeModel = generative_model

        with self.app.app_context(), \
            patch.dict("os.environ", {"GEMINI_API_KEY": "bad-key", "GEMINI_API_KEY_1": "good-key"}, clear=False), \
            patch.dict(sys.modules, {"google.generativeai": fake_module}):
            self.app.config["GEMINI_API_KEY"] = "bad-key"
            self.app.config["GEMINI_API_KEY_1"] = "good-key"
            result = gemini_client.complete_chat("hello")

        self.assertEqual(result, "ok")

    @patch("app.projects.analyzer.services.match_agent.complete_chat", side_effect=["not json", "still not json"])
    def test_match_agent_returns_fallback_report_when_model_output_is_not_json(self, complete_chat):
        from app.projects.analyzer.services.match_agent import evaluate_resume_against_jd

        report = evaluate_resume_against_jd("Python Flask developer", "Built Flask APIs")

        self.assertEqual(report["percent_match"], 0)
        self.assertEqual(report["description"], "Unable to analyze automatically right now. Please retry.")
        self.assertEqual(complete_chat.call_count, 2)

    def test_match_agent_extracts_fenced_json_response(self):
        from app.projects.analyzer.services.match_agent import extract_json_from_text

        report = extract_json_from_text(
            """Here is the analysis:
```json
{
  "percent_match": "78%",
  "positive": [{"description": "Strong Python background", "keywords": ["python", "flask"]}],
  "negative": [{"description": "Limited AWS exposure", "keywords": ["aws"]}],
  "description": "Good fit overall."
}
```"""
        )

        self.assertEqual(report["percent_match"], 78)
        self.assertEqual(report["positive"][0]["description"], "Strong Python background")
        self.assertEqual(report["negative"][0]["keywords"], ["aws"])

    def test_gemini_client_requests_json_for_json_prompts(self):
        from app.clients import gemini_client

        captured_configs = []

        class FakeResponse:
            text = '{"ok": true}'

        class FakeModel:
            def __init__(self, model_name=None, generation_config=None):
                captured_configs.append(generation_config or {})

            def generate_content(self, prompt):
                return FakeResponse()

        fake_module = types.SimpleNamespace(
            configure=lambda api_key: None,
            GenerativeModel=FakeModel,
        )

        with self.app.app_context(), \
            patch.dict("os.environ", {"GEMINI_API_KEY": "good-key"}, clear=False), \
            patch.dict(sys.modules, {"google.generativeai": fake_module}):
            self.app.config["GEMINI_API_KEY"] = "good-key"
            gemini_client.complete_chat("Respond ONLY with a JSON object using the schema: {}", max_tokens=100)

        self.assertTrue(captured_configs)
        self.assertEqual(captured_configs[0]["response_mime_type"], "application/json")


if __name__ == "__main__":
    unittest.main()
