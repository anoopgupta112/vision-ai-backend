import io
import openpyxl
from app.core import excel_styler


def test_create_styled_excel_basic():
    sample_rows = [
        {
            "name": "Sarah Connor",
            "email": "sarah@techcorp.io",
            "fit_score": "96%",
            "status": "Shortlisted",
            "resume_url": "https://drive.google.com/file/d/123/view",
            "github": "https://github.com/sconnor",
        },
        {
            "name": "Alex Murphy",
            "email": "alex@cyber.net",
            "fit_score": "65%",
            "status": "Moderate",
            "resume_url": "https://drive.google.com/file/d/456/view",
            "github": "https://github.com/murphy",
        },
        {
            "name": "John Doe",
            "email": "john@legacy.com",
            "fit_score": "35%",
            "status": "Rejected",
            "resume_url": "https://drive.google.com/file/d/789/view",
            "github": "",
        },
    ]

    excel_bytes = excel_styler.create_styled_excel(
        rows=sample_rows,
        title="Senior Full Stack Engineer — Candidate Evaluation",
        sheet_name="Candidates",
        subtitle="Generated: Sep 05, 2026 • 3 Candidates Evaluated",
    )

    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # Load with openpyxl to verify workbook integrity and structure
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb["Candidates"]

    # Verify Title Banner in row 1
    assert "SENIOR FULL STACK ENGINEER" in ws.cell(row=1, column=1).value

    # Verify Column Headers in row 4
    headers = [ws.cell(row=4, column=col).value for col in range(1, 7)]
    assert "Name" in headers
    assert "Fit Score" in headers
    assert "Resume Url" in headers

    # Verify Data Rows starting at row 5
    assert ws.cell(row=5, column=1).value == "Sarah Connor"
    assert "🟢" in ws.cell(row=5, column=3).value  # High score badge
    assert "=HYPERLINK(" in ws.cell(row=5, column=5).value  # Formatted hyperlink

    # Verify Moderate & Low score badges
    assert "🟡" in ws.cell(row=6, column=3).value
    assert "🔴" in ws.cell(row=7, column=3).value

    # Verify Frozen Panes and AutoFilter
    assert ws.freeze_panes == "A5"
    assert ws.auto_filter.ref is not None


def test_create_styled_excel_empty():
    excel_bytes = excel_styler.create_styled_excel(rows=[], title="Empty Report")
    assert isinstance(excel_bytes, bytes)
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == "No records found."
