"""
Facebook Group Share Report & Excel Exporter
============================================
Generates live-proof export Excel (.xlsx) spreadsheets and ReportLab PDF
activity reports for Pinterest -> Facebook Group automations.
"""

import os
import sys
import datetime
from typing import List, Dict, Any, Tuple, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.environ.get("REPORT_OUTPUT_DIR") or (
    "/tmp/AutomatePinterest" if os.environ.get("VERCEL") else r"C:\Downloads\AutomatePinterest"
)


def ensure_report_dir(path: str = REPORT_DIR) -> str:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def get_next_filename(prefix: str, extension: str, report_dir: str = REPORT_DIR) -> Tuple[str, str]:
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    full_prefix = f"{prefix}_{today_str}_"
    existing_files = os.listdir(report_dir) if os.path.exists(report_dir) else []

    max_num = 0
    for f in existing_files:
        if f.startswith(full_prefix) and f.endswith(f".{extension}"):
            try:
                num_str = f[len(full_prefix) : -(len(extension) + 1)]
                num = int(num_str)
                if num > max_num:
                    max_num = num
            except ValueError:
                pass

    next_num = max_num + 1
    file_name = f"{prefix}_{today_str}_{next_num}.{extension}"
    full_path = os.path.join(report_dir, file_name)
    return file_name, full_path


def export_facebook_shares_excel(
    results: List[Dict[str, Any]],
    report_dir: str = REPORT_DIR,
) -> Dict[str, Any]:
    """
    Exports completed Facebook pin shares to a formatted Excel (.xlsx) spreadsheet.
    """
    ensure_report_dir(report_dir)
    file_name, full_path = get_next_filename("Facebook_Group_Share_Proof", "xlsx", report_dir)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FB Completed Pins"

    # Ensure grid lines are visible
    ws.views.sheetView[0].showGridLines = True

    # Header fonts and fills
    title_font = Font(name="Calibri", size=16, bold=True, color="1877F2")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="4B5563")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1877F2", end_color="1877F2", fill_type="solid")
    
    success_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    success_font = Font(name="Calibri", size=10, bold=True, color="166534")
    skipped_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    skipped_font = Font(name="Calibri", size=10, bold=True, color="92400E")
    failed_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    failed_font = Font(name="Calibri", size=10, bold=True, color="991B1B")

    thin_border = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )

    # Title Block
    ws["A1"] = "AutomatePinterest — Facebook Group Share Live Proof Report"
    ws["A1"].font = title_font
    ws["A2"] = (
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Source: Dhanvi Collections (in.pinterest.com/ganeshkumardevarasetty) | "
        f"Target: Worldnewzs -> Amazon Affiliate Group"
    )
    ws["A2"].font = subtitle_font

    headers = [
        "S.No",
        "Pin ID",
        "Product Title",
        "Pinterest URL",
        "Target Facebook Group",
        "Status",
        "Date & Time",
        "Post Text / Deal Copy",
        "Proof Screenshot Reference",
    ]

    # Write Headers at Row 4
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[4].height = 26

    # Populate Data Rows
    current_row = 5
    for idx, r in enumerate(results, 1):
        status_val = (r.get("status") or "success").upper()
        pin_id = str(r.get("pinId") or "")
        pin_url = r.get("pinUrl") or (f"https://in.pinterest.com/pin/{pin_id}/" if pin_id else "")
        title = r.get("title") or ""
        target = r.get("target") or "Worldnewzs -> Amazon Affiliate Group"
        timestamp = r.get("date") or r.get("timestamp") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        post_text = r.get("content") or r.get("text") or ""
        proof_img = r.get("screenshotPath") or (f"verified_fb_group_pin_{pin_id}.png" if pin_id else "")

        ws.cell(row=current_row, column=1, value=idx).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=current_row, column=2, value=pin_id).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=current_row, column=3, value=title).alignment = Alignment(horizontal="left", vertical="center")
        
        # Hyperlinked Pinterest URL
        url_cell = ws.cell(row=current_row, column=4, value=pin_url)
        url_cell.alignment = Alignment(horizontal="left", vertical="center")
        if pin_url.startswith("http"):
            url_cell.hyperlink = pin_url
            url_cell.font = Font(name="Calibri", size=10, color="1D4ED8", underline="single")

        ws.cell(row=current_row, column=5, value=target).alignment = Alignment(horizontal="left", vertical="center")
        
        # Status Pill
        status_cell = ws.cell(row=current_row, column=6, value=status_val)
        status_cell.alignment = Alignment(horizontal="center", vertical="center")
        if status_val == "SUCCESS":
            status_cell.fill = success_fill
            status_cell.font = success_font
        elif status_val == "SKIPPED":
            status_cell.fill = skipped_fill
            status_cell.font = skipped_font
        else:
            status_cell.fill = failed_fill
            status_cell.font = failed_font

        ws.cell(row=current_row, column=7, value=timestamp).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=current_row, column=8, value=post_text[:120]).alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=current_row, column=9, value=os.path.basename(proof_img)).alignment = Alignment(horizontal="left", vertical="center")

        for c_idx in range(1, 10):
            ws.cell(row=current_row, column=c_idx).border = thin_border

        ws.row_dimensions[current_row].height = 22
        current_row += 1

    # Auto-fit column widths
    column_widths = {1: 8, 2: 24, 3: 38, 4: 40, 5: 32, 6: 14, 7: 22, 8: 45, 9: 35}
    for col_idx, width in column_widths.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    wb.save(full_path)
    file_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0

    return {
        "success": True,
        "fileName": file_name,
        "fullPath": full_path,
        "sizeBytes": file_size,
        "totalRows": len(results),
        "timestamp": datetime.datetime.now().isoformat(),
    }


def generate_facebook_pdf_report(
    results: List[Dict[str, Any]],
    summary: Dict[str, Any],
    report_dir: str = REPORT_DIR,
) -> Dict[str, Any]:
    """
    Generates a high-quality ReportLab PDF activity report with proof screenshots.
    """
    ensure_report_dir(report_dir)
    file_name, full_path = get_next_filename("Facebook_Group_Share_Report", "pdf", report_dir)

    doc = SimpleDocTemplate(
        full_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "FBTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1877F2"),
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "FBSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
    )

    section_heading = ParagraphStyle(
        "FBSectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "FBBody",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )

    story = []

    # Header
    story.append(Paragraph("AutomatePinterest — Facebook Group Share Activity Report", title_style))
    story.append(
        Paragraph(
            f"Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Target: Worldnewzs → Amazon Affiliate Group | "
            f"Source Profile: Dhanvi Collections (in.pinterest.com/ganeshkumardevarasetty)",
            subtitle_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1877F2"), spaceAfter=10))

    # KPI Summary Table
    total_requested = summary.get("totalPins", len(results))
    success_cnt = summary.get("successCount", sum(1 for r in results if r.get("status") == "success"))
    skipped_cnt = summary.get("skippedCount", sum(1 for r in results if r.get("status") == "skipped"))
    failed_cnt = summary.get("failedCount", sum(1 for r in results if r.get("status") == "failed"))
    duration_sec = summary.get("durationSeconds", 0)

    summary_data = [
        ["Requested Pins", "Successfully Posted", "Skipped (Already on FB)", "Failed", "Duration"],
        [
            str(total_requested),
            str(success_cnt),
            str(skipped_cnt),
            str(failed_cnt),
            f"{duration_sec}s" if duration_sec else "N/A",
        ],
    ]

    summary_table = Table(summary_data, colWidths=[105, 115, 125, 85, 110])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Processed Pins Table
    story.append(Paragraph("Completed Pins & Live Facebook Group Proofs", section_heading))

    table_data = [
        ["#", "Pin ID", "Product Title", "Target Group", "Status"]
    ]

    for idx, r in enumerate(results, 1):
        pin_id = str(r.get("pinId") or "N/A")
        title = r.get("title") or "Pinterest Deal"
        target = "Amazon Affiliate Group"
        status = (r.get("status") or "success").upper()

        table_data.append(
            [
                str(idx),
                pin_id,
                Paragraph(title[:60], body_style),
                target,
                status,
            ]
        )

    pins_table = Table(table_data, colWidths=[25, 120, 235, 100, 60])
    pins_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1877F2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (1, -1), "CENTER"),
                ("ALIGN", (4, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF6FF")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(pins_table)
    story.append(Spacer(1, 14))

    # Embedded Proof Screenshots for Completed Pins (Up to 4 prominent proofs)
    screenshots_dir = os.path.join(PROJECT_ROOT, "state", "screenshots")
    proof_candidates = []
    for r in results:
        p_id = r.get("pinId")
        candidates = [
            r.get("screenshotPath"),
            os.path.join(screenshots_dir, f"verified_fb_group_pin_{p_id}.png") if p_id else None,
            os.path.join(screenshots_dir, f"verified_fb_page_pin_{p_id}.png") if p_id else None,
            os.path.join(PROJECT_ROOT, f"verified_fb_group_pin_{p_id}.png") if p_id else None,
            os.path.join(PROJECT_ROOT, f"fb_share_complete_pin_{p_id}.png") if p_id else None,
        ]
        for c in candidates:
            if c and os.path.exists(c):
                proof_candidates.append((p_id, r.get("title", ""), c))
                break

    if proof_candidates:
        story.append(Paragraph("Live Proof Screenshots (Facebook Group Feed)", section_heading))
        for p_id, p_title, img_path in proof_candidates[:4]:
            try:
                story.append(Paragraph(f"• Proof for Pin ID: {p_id} — {p_title[:55]}", body_style))
                story.append(Spacer(1, 4))
                rl_img = RLImage(img_path, width=480, height=180)
                story.append(rl_img)
                story.append(Spacer(1, 8))
            except Exception:
                pass

    doc.build(story)
    file_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0

    return {
        "success": True,
        "fileName": file_name,
        "fullPath": full_path,
        "sizeBytes": file_size,
        "timestamp": datetime.datetime.now().isoformat(),
    }
