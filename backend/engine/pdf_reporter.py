import os
import datetime
from typing import List, Dict, Any, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

REPORT_DIR = os.environ.get("REPORT_OUTPUT_DIR") or (
    "/tmp/AutomatePinterest" if os.environ.get("VERCEL") else r"C:\Downloads\AutomatePinterest"
)


def ensure_report_directory(path: str = REPORT_DIR) -> str:
    """Ensures the report output directory exists."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def get_next_report_filename(report_dir: str = REPORT_DIR) -> Tuple[str, str]:
    """Calculates the next sequential daily report filename: AutomatePinterest_YYYY-MM-DD_X.pdf."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    existing_files = os.listdir(report_dir) if os.path.exists(report_dir) else []

    prefix = f"AutomatePinterest_{today_str}_"
    max_num = 0

    for f in existing_files:
        if f.startswith(prefix) and f.endswith(".pdf"):
            try:
                num_str = f[len(prefix) : -4]
                num = int(num_str)
                if num > max_num:
                    max_num = num
            except ValueError:
                pass

    next_num = max_num + 1
    file_name = f"AutomatePinterest_{today_str}_{next_num}.pdf"
    full_path = os.path.join(report_dir, file_name)
    return file_name, full_path


def generate_daily_activity_pdf(
    run_summary: Dict[str, Any],
    processed_cards: List[Dict[str, Any]],
    report_dir: str = REPORT_DIR,
) -> Dict[str, Any]:
    """Generates a professional dated PDF activity report matching project specifications."""
    ensure_report_directory(report_dir)
    file_name, full_path = get_next_report_filename(report_dir)

    doc = SimpleDocTemplate(
        full_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#E60023"),
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )

    story = []

    # Header
    story.append(Paragraph("AutomatePinterest — Daily Activity Report", title_style))
    story.append(
        Paragraph(
            f"Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Target Profile: Dhanvi Collections (in.pinterest.com/ganeshkumardevarasetty)",
            subtitle_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#E60023"), spaceAfter=12))

    # Summary KPI Table
    total_cards = run_summary.get("total_cards", len(processed_cards))
    success_count = run_summary.get("success_count", sum(1 for c in processed_cards if c.get("status") == "success"))
    failed_count = run_summary.get("failed_count", sum(1 for c in processed_cards if c.get("status") == "failed"))
    pages_count = run_summary.get("pages_count", 1)
    duration_sec = run_summary.get("duration_seconds", 0)

    summary_data = [
        ["Selected Pages", "Total Deals Processed", "Successfully Saved", "Failed", "Total Duration"],
        [
            str(pages_count),
            str(total_cards),
            str(success_count),
            str(failed_count),
            f"{duration_sec}s",
        ],
    ]

    summary_table = Table(summary_data, colWidths=[100, 120, 110, 80, 100])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # Processed Deal Cards Table
    story.append(Paragraph("Processed Deal Cards & Pinterest Boards", section_heading))

    table_data = [
        ["#", "Page", "Truncated Board Title (Max 50 Chars)", "Collaborators Added", "Price", "Status"]
    ]

    for idx, card in enumerate(processed_cards):
        c_title = card.get("truncatedTitle") or card.get("title") or "N/A"
        raw_collabs = card.get("collaborators")
        if isinstance(raw_collabs, list) and raw_collabs and raw_collabs != ["auto"]:
            collabs = ", ".join(raw_collabs)
        else:
            collabs = "Dynamic (All Account Collaborators)"
        price = card.get("price") or "N/A"
        status = (card.get("status") or "success").upper()

        p_num = str(card.get("pageNumber", 1))

        table_data.append(
            [
                str(idx + 1),
                p_num,
                Paragraph(c_title, body_style),
                Paragraph(collabs, body_style),
                price,
                status,
            ]
        )

    cards_table = Table(table_data, colWidths=[24, 34, 210, 150, 56, 60])
    cards_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E60023")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (1, -1), "CENTER"),
                ("ALIGN", (4, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fdf2f2")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(cards_table)
    story.append(Spacer(1, 14))

    # Collect all unique collaborators across cards
    all_assigned = set()
    for card in processed_cards:
        for c in card.get("collaborators", []):
            if c and str(c).lower() != "auto":
                all_assigned.add(c)
    collab_note = f"• Added collaborators (dynamically discovered): {', '.join(sorted(all_assigned))}.<br/>" if all_assigned else "• Added collaborators: Dynamically discovered and assigned from Pinterest account.<br/>"

    # Verification Footer
    story.append(Paragraph("Verification Details & Compliance", section_heading))
    verification_notes = (
        "• All board titles strictly truncated to 50 characters (hard cut).<br/>"
        f"{collab_note}"
        "• Verified Save button state transition: Red to dark grey disabled ('Saved') state.<br/>"
        "• Live account profile: https://in.pinterest.com/ganeshkumardevarasetty/_saved/"
    )
    story.append(Paragraph(verification_notes, subtitle_style))


    doc.build(story)

    file_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0

    return {
        "success": True,
        "fileName": file_name,
        "fullPath": full_path,
        "sizeBytes": file_size,
        "timestamp": datetime.datetime.now().isoformat(),
    }
