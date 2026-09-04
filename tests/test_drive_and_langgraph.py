import unittest
import io
from unittest.mock import patch, MagicMock
from app import create_app

AUTH_HEADERS = {"Authorization": "Bearer test-token"}

class DriveVaultAndLangGraphTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch("app.create_indexes")
        self.create_indexes_patcher.start()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        self.decode_token_patcher = patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"})
        self.find_user_patcher = patch(
            "app.auth.models.find_user_by_id",
            return_value={"_id": "user-1", "email": "recruiter@example.com", "is_active": True, "is_admin": False},
        )
        self.decode_token_patcher.start()
        self.find_user_patcher.start()

    def tearDown(self):
        self.find_user_patcher.stop()
        self.decode_token_patcher.stop()
        self.create_indexes_patcher.stop()

    @patch("app.projects.analyzer.api.routes._get_owned_form")
    @patch("app.projects.analyzer.services.google_drive.ensure_vault_form_structure")
    @patch("app.projects.analyzer.services.google_drive.share_folder_with_email")
    @patch("app.projects.analyzer.services.storage._forms_collection")
    def test_share_form_drive_endpoint(self, mock_forms_col, mock_share, mock_vault, mock_get_form):
        mock_get_form.return_value = {
            "form_id": "form-123",
            "name": "Backend Engineer Hiring",
            "shared_emails": [],
        }
        mock_vault.return_value = {
            "root_id": "root-1",
            "form_folder_id": "form-folder-1",
            "resumes_folder_id": "resumes-folder-1",
            "folder_url": "https://drive.google.com/drive/folders/form-folder-1",
        }
        mock_share.return_value = {
            "success": True,
            "email": "hiring@company.com",
            "permission_id": "perm-123",
            "folder_id": "form-folder-1",
            "folder_link": "https://drive.google.com/drive/folders/form-folder-1",
        }
        mock_collection = MagicMock()
        mock_forms_col.return_value = mock_collection

        response = self.client.post(
            "/api/analyzer/forms/form-123/share-drive",
            json={"email": "hiring@company.com"},
            headers=AUTH_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["email"], "hiring@company.com")
        self.assertIn("hiring@company.com", data["shared_emails"])
        mock_collection.update_one.assert_called_once()

    @patch("app.projects.analyzer.api.routes._get_owned_form")
    def test_get_form_drive_info_endpoint(self, mock_get_form):
        mock_get_form.return_value = {
            "form_id": "form-123",
            "name": "Backend Engineer Hiring",
            "vault_folder_id": "form-folder-1",
            "vault_folder_url": "https://drive.google.com/drive/folders/form-folder-1",
            "shared_emails": ["team@company.com"],
        }

        response = self.client.get("/api/analyzer/forms/form-123/drive-info", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["folder_id"], "form-folder-1")
        self.assertEqual(data["shared_emails"], ["team@company.com"])

    def test_extract_text_from_pdf_stream_in_memory(self):
        from app.projects.analyzer.services.ocr_engine import extract_text_from_pdf
        import fitz

        # Create a tiny 1-page PDF in memory
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Alice Smith - Senior Python Engineer")
        pdf_bytes = doc.write()
        doc.close()

        text, links = extract_text_from_pdf(pdf_bytes)
        self.assertIn("Alice Smith", text)
        self.assertIn("Senior Python Engineer", text)

    def test_langgraph_workflow_runs_with_mocked_state(self):
        from app.projects.analyzer.services.analysis_graph import run_candidate_analysis

        with patch("app.projects.analyzer.services.analysis_graph.extract_text_from_pdf") as mock_extract, \
             patch("app.projects.analyzer.services.analysis_graph.evaluate_resume_against_jd") as mock_match, \
             patch("app.projects.analyzer.services.analysis_graph.generate_questions_from_jd") as mock_jd_q:
            
            mock_extract.return_value = ("Senior Python Developer resume", [])
            mock_match.return_value = {
                "percent_match": 92,
                "positive": [{"description": "Strong Python knowledge", "keywords": ["Python"]}],
                "negative": [],
                "description": "Outstanding match for the role",
            }
            mock_jd_q.return_value = {
                "questions": ["How do you design scalable APIs?"],
                "summary": "Backend scalability",
            }

            result = run_candidate_analysis(b"%PDF-1.4...", "Python Developer", "alice_resume.pdf")

            self.assertEqual(result["file_name"], "alice_resume.pdf")
            self.assertEqual(result["match_report"]["percent_match"], 92)
            self.assertTrue(len(result["question_sets"]) > 0)


if __name__ == "__main__":
    unittest.main()
