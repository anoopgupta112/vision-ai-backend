import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import openpyxl
    from openpyxl.chart import BarChart, DoughnutChart, PieChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None


def is_openpyxl_available() -> bool:
    return openpyxl is not None


def _format_cell_link(url: str, column_name: str) -> str:
    """Formats URLs cleanly with intuitive labels."""
    col_lower = column_name.lower()
    if "resume" in col_lower or "pdf" in col_lower or "drive" in col_lower:
        label = "🔗 View Resume"
    elif "github" in col_lower or "repo" in col_lower:
        label = "🔗 GitHub Profile"
    elif "website" in col_lower or "site" in col_lower:
        label = "🔗 Visit Website"
    elif "linkedin" in col_lower:
        label = "🔗 LinkedIn"
    else:
        label = "🔗 Open Link"
    escaped_url = url.replace('"', '""')
    return f'=HYPERLINK("{escaped_url}", "{label}")'


def _parse_score(val: Any) -> Optional[float]:
    """Helper to safely extract float percentage (0..100) from string/number."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", val_str)
        if not cleaned:
            return None
        num = float(cleaned)
        if num <= 1.0 and "%" in val_str:
            num = num * 100.0
        return num
    except Exception:
        return None


def create_styled_excel(
    rows: List[Dict[str, Any]],
    title: str = "Candidate Intelligence Report",
    sheet_name: str = "All Candidates",
    subtitle: Optional[str] = None,
    headers: Optional[List[str]] = None,
    include_analytics_sheet: bool = True,
) -> bytes:
    """
    Generates a multi-sheet executive-grade Excel workbook with KPI cards,
    embedded native charts (BarChart, DoughnutChart), and styled data grids.
    """
    if not openpyxl:
        raise RuntimeError("openpyxl is required for styled Excel generation.")

    wb = openpyxl.Workbook()
    
    # -------------------------------------------------------------
    # STYLES DEFINITION (Linear Executive Theme)
    # -------------------------------------------------------------
    title_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")  # Slate 900
    title_font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")

    sub_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")    # Slate 800
    sub_font = Font(name="Segoe UI", size=9.5, italic=True, color="94A3B8")

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid") # Slate 800
    header_font = Font(name="Segoe UI", size=10.5, bold=True, color="FFFFFF")

    row_fill_a = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    row_fill_b = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")  # Slate 50

    card_header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    card_header_font = Font(name="Segoe UI", size=9, bold=True, color="94A3B8")
    
    card_body_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    card_val_emerald = Font(name="Segoe UI", size=18, bold=True, color="10B981")
    card_val_indigo = Font(name="Segoe UI", size=18, bold=True, color="60A5FA")
    card_val_violet = Font(name="Segoe UI", size=18, bold=True, color="C084FC")
    card_val_amber = Font(name="Segoe UI", size=18, bold=True, color="FBBF24")

    badge_high_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")  # Emerald 100
    badge_high_font = Font(name="Segoe UI", size=10, bold=True, color="166534")                # Emerald 800

    badge_med_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")    # Amber 100
    badge_med_font = Font(name="Segoe UI", size=10, bold=True, color="92400E")                  # Amber 800

    badge_low_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")    # Rose 100
    badge_low_font = Font(name="Segoe UI", size=10, bold=True, color="991B1B")                  # Rose 800

    link_font = Font(name="Segoe UI", size=10, color="2563EB", underline="single")
    regular_font = Font(name="Segoe UI", size=10, color="0F172A")

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    header_border = Border(
        left=Side(style="thin", color="334155"),
        right=Side(style="thin", color="334155"),
        top=Side(style="thin", color="334155"),
        bottom=Side(style="medium", color="0F172A"),
    )

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=False)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=False)
    align_right = Alignment(horizontal="right", vertical="center", wrap_text=False)

    if not rows:
        ws = wb.active
        ws.title = "Overview"
        ws.append(["No records found."])
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    # Determine headers
    if not headers:
        key_dict = {}
        for r in rows:
            for k in r.keys():
                key_dict[k] = None
        headers = list(key_dict.keys())

    # Calculate metrics
    scores = []
    score_col_name = None
    for h in headers:
        if any(k in h.lower() for k in ["score", "fit", "match", "rating", "percentage"]):
            score_col_name = h
            break

    high_count = 0
    med_count = 0
    low_count = 0
    total_count = len(rows)

    for r in rows:
        val = r.get(score_col_name) if score_col_name else None
        num = _parse_score(val)
        if num is not None:
            scores.append(num)
            if num >= 80:
                high_count += 1
            elif num >= 50:
                med_count += 1
            else:
                low_count += 1

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    if not scores:
        high_count = total_count
        med_count = 0
        low_count = 0

    now_str = datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")

    # =============================================================
    # SHEET 1: 📊 Executive Overview & Analytics Dashboard
    # =============================================================
    if include_analytics_sheet:
        ws_dash = wb.active
        ws_dash.title = "📊 Executive Dashboard"
        ws_dash.views.sheetView[0].showGridLines = True

        dash_cols = 14
        # 1. Header Banner
        ws_dash.row_dimensions[1].height = 38
        ws_dash.merge_cells(start_row=1, start_column=1, end_row=1, end_column=dash_cols)
        t_cell = ws_dash.cell(row=1, column=1, value=f"🚀 {title.upper()} — EXECUTIVE INTELLIGENCE")
        t_cell.font = title_font
        t_cell.fill = title_fill
        t_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        for c in range(2, dash_cols + 1):
            ws_dash.cell(row=1, column=c).fill = title_fill

        ws_dash.row_dimensions[2].height = 24
        ws_dash.merge_cells(start_row=2, start_column=1, end_row=2, end_column=dash_cols)
        s_cell = ws_dash.cell(row=2, column=1, value=f"  Generated on {now_str} • {total_count} Total Evaluated • AI Semantic Intelligence Engine")
        s_cell.font = sub_font
        s_cell.fill = sub_fill
        s_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        for c in range(2, dash_cols + 1):
            ws_dash.cell(row=2, column=c).fill = sub_fill

        # Row 3: Spacer
        ws_dash.row_dimensions[3].height = 10

        # 2. KPI Summary Cards (Rows 4-5)
        # Card 1: Total Candidates (Cols B-D)
        # Card 2: Top Fit Shortlist (Cols E-G)
        # Card 3: Avg Fit Score (Cols H-J)
        # Card 4: Qualified Share (Cols K-M)
        kpi_defs = [
            ("TOTAL EVALUATED", f"{total_count}", card_val_indigo, 2, 4),
            ("SHORTLISTED (≥80%)", f"{high_count}", card_val_emerald, 5, 7),
            ("AVERAGE FIT SCORE", f"{avg_score}%" if scores else "N/A", card_val_violet, 8, 10),
            ("TOP FIT RATIO", f"{round((high_count/max(total_count, 1))*100, 1)}%", card_val_amber, 11, 13),
        ]

        ws_dash.row_dimensions[4].height = 18
        ws_dash.row_dimensions[5].height = 32

        for label, val, font, sc, ec in kpi_defs:
            ws_dash.merge_cells(start_row=4, start_column=sc, end_row=4, end_column=ec)
            lbl_cell = ws_dash.cell(row=4, column=sc, value=label)
            lbl_cell.fill = card_header_fill
            lbl_cell.font = card_header_font
            lbl_cell.alignment = align_center

            ws_dash.merge_cells(start_row=5, start_column=sc, end_row=5, end_column=ec)
            val_cell = ws_dash.cell(row=5, column=sc, value=val)
            val_cell.fill = card_body_fill
            val_cell.font = font
            val_cell.alignment = align_center

            for r in [4, 5]:
                for c in range(sc, ec + 1):
                    ws_dash.cell(row=r, column=c).border = thin_border

        # 3. Chart Data Source (Hidden table on Col Z)
        ws_dash.cell(row=8, column=25, value="Category")
        ws_dash.cell(row=8, column=26, value="Count")
        ws_dash.cell(row=9, column=25, value="Top Fit (≥80%)")
        ws_dash.cell(row=9, column=26, value=high_count)
        ws_dash.cell(row=10, column=25, value="Moderate (50-79%)")
        ws_dash.cell(row=10, column=26, value=med_count)
        ws_dash.cell(row=11, column=25, value="Low Fit (<50%)")
        ws_dash.cell(row=11, column=26, value=low_count)

        # 4. Embedded Bar Chart
        bar_chart = BarChart()
        bar_chart.type = "col"
        bar_chart.style = 10
        bar_chart.title = "Candidate Fit Score Distribution"
        bar_chart.y_axis.title = "Candidates"
        bar_chart.x_axis.title = "Tier"
        data_ref = Reference(ws_dash, min_col=26, min_row=8, max_row=11)
        cats_ref = Reference(ws_dash, min_col=25, min_row=9, max_row=11)
        bar_chart.add_data(data_ref, titles_from_data=True)
        bar_chart.set_categories(cats_ref)
        bar_chart.width = 14
        bar_chart.height = 9.5
        bar_chart.legend = None
        ws_dash.add_chart(bar_chart, "B7")

        # 5. Embedded Doughnut / Pie Chart
        pie_chart = DoughnutChart()
        pie_chart.title = "Applicant Pool Breakdown"
        pie_chart.style = 2
        pie_chart.add_data(data_ref, titles_from_data=True)
        pie_chart.set_categories(cats_ref)
        pie_chart.width = 12
        pie_chart.height = 9.5
        ws_dash.add_chart(pie_chart, "I7")

        # 6. Top 5 Star Candidates Table (Row 24)
        top_start_row = 24
        ws_dash.row_dimensions[top_start_row].height = 28
        ws_dash.merge_cells(start_row=top_start_row, start_column=2, end_row=top_start_row, end_column=13)
        star_title = ws_dash.cell(row=top_start_row, column=2, value="⭐ TOP SHORTLISTED CANDIDATES")
        star_title.font = header_font
        star_title.fill = header_fill
        star_title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        for c in range(3, 14):
            ws_dash.cell(row=top_start_row, column=c).fill = header_fill

        # Sort top 5 rows
        sorted_rows = list(rows)
        if score_col_name:
            sorted_rows.sort(key=lambda r: _parse_score(r.get(score_col_name)) or 0, reverse=True)
        top_5 = sorted_rows[:5]

        # Top 5 headers (Col B to G)
        top_headers = ["Rank", "Candidate Name", "Email", "Fit Score", "Resume File", "GitHub / Link"]
        th_row = top_start_row + 1
        ws_dash.row_dimensions[th_row].height = 24
        for idx, th in enumerate(top_headers, start=2):
            cell = ws_dash.cell(row=th_row, column=idx, value=th)
            cell.font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
            cell.alignment = align_center if idx in [2, 5, 6, 7] else align_left
            cell.border = header_border

        curr_top_row = th_row + 1
        for rank_idx, r in enumerate(top_5, start=1):
            ws_dash.row_dimensions[curr_top_row].height = 22
            is_odd = (rank_idx % 2 == 1)
            b_fill = row_fill_b if is_odd else row_fill_a

            # Rank
            c_rank = ws_dash.cell(row=curr_top_row, column=2, value=f"#{rank_idx:02d}")
            c_rank.fill = b_fill
            c_rank.alignment = align_center
            c_rank.border = thin_border
            c_rank.font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")

            # Name
            name_val = r.get("name") or r.get("full_name") or "Candidate"
            c_name = ws_dash.cell(row=curr_top_row, column=3, value=str(name_val))
            c_name.fill = b_fill
            c_name.alignment = align_left
            c_name.border = thin_border
            c_name.font = regular_font

            # Email
            email_val = r.get("email") or ""
            c_email = ws_dash.cell(row=curr_top_row, column=4, value=str(email_val))
            c_email.fill = b_fill
            c_email.alignment = align_left
            c_email.border = thin_border
            c_email.font = regular_font

            # Score
            score_val = r.get(score_col_name, "") if score_col_name else "100%"
            s_num = _parse_score(score_val)
            c_score = ws_dash.cell(row=curr_top_row, column=5)
            c_score.border = thin_border
            c_score.alignment = align_center
            if s_num and s_num >= 80:
                c_score.value = f"🟢 {int(s_num)}%"
                c_score.fill = badge_high_fill
                c_score.font = badge_high_font
            elif s_num and s_num >= 50:
                c_score.value = f"🟡 {int(s_num)}%"
                c_score.fill = badge_med_fill
                c_score.font = badge_med_font
            else:
                c_score.value = f"{score_val}"
                c_score.fill = b_fill
                c_score.font = regular_font

            # Resume Link
            res_val = None
            for k, v in r.items():
                if any(x in k.lower() for x in ["resume", "pdf", "drive_url"]):
                    res_val = str(v)
                    break
            c_res = ws_dash.cell(row=curr_top_row, column=6)
            c_res.fill = b_fill
            c_res.border = thin_border
            if res_val and res_val.startswith("http"):
                c_res.value = _format_cell_link(res_val, "resume")
                c_res.font = link_font
                c_res.alignment = align_center
            else:
                c_res.value = "—"
                c_res.alignment = align_center

            # GitHub Link
            gh_val = None
            for k, v in r.items():
                if any(x in k.lower() for x in ["github", "repo", "website"]):
                    gh_val = str(v)
                    break
            c_gh = ws_dash.cell(row=curr_top_row, column=7)
            c_gh.fill = b_fill
            c_gh.border = thin_border
            if gh_val and gh_val.startswith("http"):
                c_gh.value = _format_cell_link(gh_val, "github")
                c_gh.font = link_font
                c_gh.alignment = align_center
            else:
                c_gh.value = "—"
                c_gh.alignment = align_center

            curr_top_row += 1

        # Auto-width dashboard columns
        for col_i in range(1, 15):
            col_ltr = get_column_letter(col_i)
            ws_dash.column_dimensions[col_ltr].width = 18

    # =============================================================
    # SHEET 2: 👥 Full Master Data Grid
    # =============================================================
    ws_data = wb.create_sheet(title=f"👥 {sheet_name[:26]}")
    ws_data.views.sheetView[0].showGridLines = True
    total_cols = max(len(headers), 1)

    # 1. Header Banner
    ws_data.row_dimensions[1].height = 36
    ws_data.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws_data.cell(row=1, column=1, value=f"🚀 {title.upper()} — MASTER ROSTER")
    title_cell.font = title_font
    title_cell.fill = title_fill
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    for col in range(2, total_cols + 1):
        ws_data.cell(row=1, column=col).fill = title_fill

    # Row 2: Subtitle
    ws_data.row_dimensions[2].height = 22
    ws_data.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    sub_cell = ws_data.cell(row=2, column=1, value=f"  Generated: {now_str} • {len(rows)} Total Records • Full Raw Dataset")
    sub_cell.font = sub_font
    sub_cell.fill = sub_fill
    sub_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    for col in range(2, total_cols + 1):
        ws_data.cell(row=2, column=col).fill = sub_fill

    # Row 3: Spacer Row
    ws_data.row_dimensions[3].height = 8

    # Row 4: Column Headers
    header_row_idx = 4
    ws_data.row_dimensions[header_row_idx].height = 28
    for col_idx, header_name in enumerate(headers, start=1):
        clean_header = header_name.replace("_", " ").title()
        cell = ws_data.cell(row=header_row_idx, column=col_idx, value=clean_header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align_center if any(k in header_name.lower() for k in ["score", "fit", "status", "link", "pdf", "date", "phone"]) else align_left
        cell.border = header_border

    # Data Rows
    current_row = 5
    for row_idx, data in enumerate(rows):
        ws_data.row_dimensions[current_row].height = 24
        is_odd = (row_idx % 2 == 1)
        base_fill = row_fill_b if is_odd else row_fill_a

        for col_idx, header_name in enumerate(headers, start=1):
            val = data.get(header_name, "")
            cell = ws_data.cell(row=current_row, column=col_idx)
            cell.border = thin_border
            cell.fill = base_fill

            if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                cell.value = _format_cell_link(val, header_name)
                cell.font = link_font
                cell.alignment = align_center
            else:
                h_lower = header_name.lower()
                val_str = str(val).strip() if val is not None else ""

                is_score_col = any(k in h_lower for k in ["score", "fit", "match", "rating", "percentage"])
                score_num = _parse_score(val_str) if is_score_col else None

                if score_num is not None:
                    if score_num >= 80:
                        cell.value = f"🟢 {val_str if '%' in val_str else f'{int(score_num)}%'}"
                        cell.fill = badge_high_fill
                        cell.font = badge_high_font
                    elif score_num >= 50:
                        cell.value = f"🟡 {val_str if '%' in val_str else f'{int(score_num)}%'}"
                        cell.fill = badge_med_fill
                        cell.font = badge_med_font
                    else:
                        cell.value = f"🔴 {val_str if '%' in val_str else f'{int(score_num)}%'}"
                        cell.fill = badge_low_fill
                        cell.font = badge_low_font
                    cell.alignment = align_center
                elif any(k in h_lower for k in ["status", "tier"]):
                    val_upper = val_str.upper()
                    if any(w in val_upper for w in ["HIGH", "PASS", "ACCEPTED", "SHORTLIST", "S-TIER", "A-TIER"]):
                        cell.value = f"🟢 {val_str}"
                        cell.fill = badge_high_fill
                        cell.font = badge_high_font
                    elif any(w in val_upper for w in ["MED", "MODERATE", "REVIEW", "PENDING", "B-TIER"]):
                        cell.value = f"🟡 {val_str}"
                        cell.fill = badge_med_fill
                        cell.font = badge_med_font
                    elif any(w in val_upper for w in ["LOW", "REJECT", "FAIL", "C-TIER"]):
                        cell.value = f"🔴 {val_str}"
                        cell.fill = badge_low_fill
                        cell.font = badge_low_font
                    else:
                        cell.value = val_str
                        cell.font = regular_font
                    cell.alignment = align_center
                else:
                    cell.value = val if val is not None else ""
                    cell.font = regular_font
                    cell.alignment = align_left if isinstance(val, str) else align_right

        current_row += 1

    # Auto-fit column widths
    for col_idx, header_name in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = len(header_name.replace("_", " ")) + 4

        for row in range(5, current_row):
            cell_val = str(ws_data.cell(row=row, column=col_idx).value or "")
            if cell_val.startswith("=HYPERLINK"):
                max_len = max(max_len, 18)
            else:
                max_len = max(max_len, len(cell_val) + 3)

        ws_data.column_dimensions[col_letter].width = min(max(max_len, 14), 50)

    # Enable AutoFilter and Freeze Panes on Master Sheet
    last_col_letter = get_column_letter(total_cols)
    last_row_idx = current_row - 1
    ws_data.auto_filter.ref = f"A{header_row_idx}:{last_col_letter}{last_row_idx}"
    ws_data.freeze_panes = f"A{header_row_idx + 1}"

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def save_styled_excel(
    rows: List[Dict[str, Any]],
    file_path: str,
    title: str = "Candidate Intelligence Report",
    sheet_name: str = "All Candidates",
    subtitle: Optional[str] = None,
    headers: Optional[List[str]] = None,
    include_analytics_sheet: bool = True,
) -> str:
    """Generates and writes multi-sheet styled Excel to a local file path."""
    excel_bytes = create_styled_excel(
        rows=rows,
        title=title,
        sheet_name=sheet_name,
        subtitle=subtitle,
        headers=headers,
        include_analytics_sheet=include_analytics_sheet,
    )
    with open(file_path, "wb") as f:
        f.write(excel_bytes)
    return file_path
