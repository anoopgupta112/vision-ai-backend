import io
import os
import unittest
import openpyxl
from datetime import datetime
from app.core import excel_styler


class TestExcelStyler(unittest.TestCase):
    def test_create_styled_excel_basic(self):
        sample_rows = [
            {
                "name": "Sarah Connor",
                "email": "sarah@techcorp.io",
                "fit_score": "96%",
                "status": "Shortlisted",
                "resume_url": "https://drive.google.com/file/d/123/view",
                "github": "https://github.com/sconnor",
                "submitted_at": "2026-09-07T12:00:00Z",
                "salary_expectation": 140000,
            },
            {
                "name": "Alex Murphy",
                "email": "alex@cyber.net",
                "fit_score": "65%",
                "status": "Moderate",
                "resume_url": "https://drive.google.com/file/d/456/view",
                "github": "https://github.com/murphy",
                "submitted_at": "2026-09-07T14:30:00Z",
                "salary_expectation": 120000,
            },
            {
                "name": "John Doe",
                "email": "john@legacy.com",
                "fit_score": "35%",
                "status": "Rejected",
                "resume_url": "https://drive.google.com/file/d/789/view",
                "github": "",
                "submitted_at": "2026-09-07T16:15:00Z",
                "salary_expectation": 95000,
            },
        ]

        excel_bytes = excel_styler.create_styled_excel(
            rows=sample_rows,
            title="Senior Full Stack Engineer — Candidate Evaluation",
            sheet_name="Candidates",
            subtitle="Generated: Sep 05, 2026 • 3 Candidates Evaluated",
        )

        self.assertIsInstance(excel_bytes, bytes)
        self.assertGreater(len(excel_bytes), 0)

        # Load with openpyxl to verify workbook integrity and structure
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        self.assertEqual(len(wb.worksheets), 2)
        
        # Verify Sheet 1: Executive Dashboard
        ws_dash = wb.worksheets[0]
        self.assertTrue(ws_dash.views.sheetView[0].showGridLines)
        self.assertIn("SENIOR FULL STACK ENGINEER", ws_dash.cell(row=1, column=1).value)

        # Verify Sheet 2: Master Roster
        ws = [s for s in wb.worksheets if "Candidates" in s.title][0]
        self.assertTrue(ws.views.sheetView[0].showGridLines)

        # Verify Title Banner in row 1
        self.assertIn("SENIOR FULL STACK ENGINEER", ws.cell(row=1, column=1).value)

        # Verify Column Headers in row 4
        headers = [ws.cell(row=4, column=col).value for col in range(1, 9)]
        self.assertIn("Name", headers)
        self.assertIn("Fit Score", headers)
        self.assertIn("Resume Url", headers)
        self.assertIn("Submitted At", headers)

        # Verify Data Rows starting at row 5
        self.assertEqual(ws.cell(row=5, column=1).value, "Sarah Connor")
        self.assertIn("🟢", ws.cell(row=5, column=3).value)  # High score badge
        self.assertIn("=HYPERLINK(", ws.cell(row=5, column=5).value)  # Formatted hyperlink
        self.assertEqual(ws.cell(row=5, column=8).value, 140000)
        self.assertEqual(ws.cell(row=5, column=8).number_format, "#,##0")
        self.assertIsInstance(ws.cell(row=5, column=7).value, datetime)
        self.assertEqual(ws.cell(row=5, column=7).number_format, "yyyy-mm-dd hh:mm")

        # Verify Moderate & Low score badges
        self.assertIn("🟡", ws.cell(row=6, column=3).value)
        self.assertIn("🔴", ws.cell(row=7, column=3).value)

        # Verify Frozen Panes, AutoFilter, and bounded column width for hyperlink column
        self.assertEqual(ws.freeze_panes, "A5")
        self.assertIsNotNone(ws.auto_filter.ref)

        # Column E (Resume Url) width should be bounded appropriately (~18 to 25), not 50+
        resume_col_width = ws.column_dimensions["E"].width
        self.assertGreaterEqual(resume_col_width, 12)
        self.assertLessEqual(resume_col_width, 30)

        # Save test artifact file for verification
        export_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../exports"))
        os.makedirs(export_dir, exist_ok=True)
        artifact_path = os.path.join(export_dir, "test_export_verification.xlsx")
        excel_styler.save_styled_excel(
            rows=sample_rows,
            file_path=artifact_path,
            title="Senior Full Stack Engineer — Candidate Evaluation",
            sheet_name="Candidates",
        )
        self.assertTrue(os.path.exists(artifact_path))

    def test_create_styled_excel_generic_dataset(self):
        sample_rows = [
            {"company": "Acme Corp", "email": "info@acme.com", "phone": "555-0199", "website": "https://acme.com"},
            {"company": "Beta LLC", "email": "contact@beta.io", "phone": "555-0244", "website": "https://beta.io"},
        ]
        excel_bytes = excel_styler.create_styled_excel(
            rows=sample_rows,
            title="B2B Leads Report",
            sheet_name="Leads",
        )
        self.assertIsInstance(excel_bytes, bytes)
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        self.assertEqual(len(wb.worksheets), 2)
        ws_dash = wb.worksheets[0]
        self.assertIn("TOTAL RECORDS", ws_dash.cell(row=4, column=2).value)

    def test_create_styled_excel_unparseable_scores_and_none(self):
        sample_rows = [
            {"name": "Invalid Score User", "fit_score": "N/A", "email": "invalid@test.com"},
            {"name": "Valid Score User", "fit_score": 0.95, "email": "valid@test.com"},
            {"name": "None Score User", "fit_score": None, "email": "none@test.com"},
        ]
        excel_bytes = excel_styler.create_styled_excel(
            rows=sample_rows,
            title="Score Edge Case Report",
        )
        self.assertIsInstance(excel_bytes, bytes)
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        self.assertEqual(len(wb.worksheets), 2)
        ws_master = wb.worksheets[1]
        self.assertEqual(ws_master.cell(row=5, column=1).value, "Invalid Score User")

    def test_create_styled_excel_without_analytics_sheet(self):
        sample_rows = [{"item": "Widget A", "count": 10}]
        excel_bytes = excel_styler.create_styled_excel(
            rows=sample_rows,
            title="Single Sheet Report",
            include_analytics_sheet=False,
        )
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        self.assertEqual(len(wb.worksheets), 1)
        self.assertIn("Widget A", wb.worksheets[0].cell(row=5, column=1).value)


if __name__ == "__main__":
    unittest.main()

