import os
import textwrap

import arabic_reshaper
import qrcode
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from omr_layout import question_layout


PAGE_WIDTH, PAGE_HEIGHT = A4
LETTERS = ("أ", "ب", "ج", "د")
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ar(text):
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(str(text)))


def register_fonts():
    for name, path in (("Arabic", FONT_PATH), ("ArabicBold", BOLD_FONT_PATH)):
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass


def font_name(bold=False):
    available = set(pdfmetrics.getRegisteredFontNames())
    if bold and "ArabicBold" in available:
        return "ArabicBold"
    if "Arabic" in available:
        return "Arabic"
    return "Helvetica-Bold" if bold else "Helvetica"


def draw_corner_markers(pdf):
    size = 7 * mm
    margin = 8 * mm
    positions = (
        (margin, PAGE_HEIGHT - margin - size),
        (PAGE_WIDTH - margin - size, PAGE_HEIGHT - margin - size),
        (margin, margin),
        (PAGE_WIDTH - margin - size, margin),
    )
    pdf.setFillColorRGB(0, 0, 0)
    for x, y in positions:
        pdf.rect(x, y, size, size, fill=1, stroke=0)


def draw_header(pdf, exam):
    bold = font_name(True)
    regular = font_name()
    pdf.setFillColorRGB(0.08, 0.22, 0.35)
    pdf.setFont(bold, 16)
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 18 * mm, ar("ورقة إجابة"))
    pdf.setFont(regular, 9)
    pdf.drawCentredString(
        PAGE_WIDTH / 2,
        PAGE_HEIGHT - 25 * mm,
        ar("نظام الاختبارات والتصحيح الآلي"),
    )

    pdf.setFillColorRGB(0.12, 0.15, 0.2)
    pdf.setFont(bold, 9)
    right_x = PAGE_WIDTH - 18 * mm
    left_x = 18 * mm
    lines_right = (
        f"المدرسة: {exam.get('school', '')}",
        f"المادة: {exam.get('subject', '')}",
        f"الصف: {exam.get('class_name', '')}",
    )
    lines_left = (
        f"الفصل: {exam.get('semester', '')}",
        f"العام: {exam.get('academic_year', '')}",
        f"الدرجة الكلية: {exam.get('total_grade', '')}",
    )
    for index, value in enumerate(lines_right):
        pdf.drawRightString(right_x, PAGE_HEIGHT - (37 + index * 7) * mm, ar(value))
    for index, value in enumerate(lines_left):
        pdf.drawString(left_x, PAGE_HEIGHT - (37 + index * 7) * mm, ar(value))

    pdf.setFont(regular, 9)
    pdf.drawRightString(
        right_x,
        PAGE_HEIGHT - 61 * mm,
        ar("اسم الطالب: ........................................................"),
    )
    pdf.drawString(
        left_x,
        PAGE_HEIGHT - 61 * mm,
        ar("رقم الجلوس: ........................"),
    )
    pdf.setStrokeColorRGB(0.82, 0.86, 0.9)
    pdf.line(18 * mm, PAGE_HEIGHT - 66 * mm, PAGE_WIDTH - 18 * mm, PAGE_HEIGHT - 66 * mm)
    pdf.setFillColorRGB(0.25, 0.3, 0.38)
    pdf.setFont(bold, 8)
    pdf.drawCentredString(
        PAGE_WIDTH / 2,
        PAGE_HEIGHT - 73 * mm,
        ar("ظلّل دائرة واحدة فقط لكل سؤال بالقلم الداكن، ولا تضع علامة خارج الدوائر."),
    )


def draw_qr(pdf, exam, output_path):
    qr_path = f"{output_path}.qr.png"
    qr = qrcode.make(exam["id"])
    qr.save(qr_path)
    try:
        pdf.drawImage(
            qr_path,
            PAGE_WIDTH / 2 - 10 * mm,
            PAGE_HEIGHT - 59 * mm,
            width=20 * mm,
            height=20 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
    finally:
        try:
            os.remove(qr_path)
        except OSError:
            pass


def short_text(value, limit):
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def draw_question(pdf, question, layout_item, exam_count):
    bold = font_name(True)
    regular = font_name()
    column_left = layout_item["column_left"] * PAGE_WIDTH
    column_right = layout_item["column_right"] * PAGE_WIDTH
    text_y = PAGE_HEIGHT * (1 - layout_item["text_y"])
    bubble_y = PAGE_HEIGHT * (1 - layout_item["bubbles"][0][1])
    column_width = column_right - column_left
    row_top = PAGE_HEIGHT * (1 - layout_item["row_top"])
    row_bottom = PAGE_HEIGHT * (1 - layout_item["row_bottom"])
    card_height = row_top - row_bottom

    # Draw each question as a table cell: the question occupies the upper
    # part and the answer bubbles occupy the lower part.
    pdf.setFillColorRGB(0.985, 0.99, 0.997)
    pdf.setStrokeColorRGB(0.78, 0.84, 0.9)
    pdf.setLineWidth(0.7)
    pdf.roundRect(
        column_left,
        row_bottom,
        column_width,
        card_height,
        5,
        fill=1,
        stroke=1,
    )
    divider_y = PAGE_HEIGHT * (
        1 - (layout_item["text_y"] + (layout_item["bubbles"][0][1] - layout_item["text_y"]) * 0.58)
    )
    pdf.setStrokeColorRGB(0.86, 0.89, 0.93)
    pdf.line(column_left + 5, divider_y, column_right - 5, divider_y)

    pdf.setFillColorRGB(0.08, 0.1, 0.14)
    pdf.setFont(bold, 7.6 if exam_count <= 24 else 6.7)
    question_text = short_text(question.get("text", ""), 52 if exam_count <= 24 else 31)
    pdf.drawRightString(
        column_right,
        text_y,
        ar(f"س{question['number']}. {question_text}"),
    )

    pdf.setLineWidth(0.65)
    pdf.setStrokeColorRGB(0.25, 0.3, 0.35)
    radius = 3.5 if exam_count <= 24 else 3
    for option, (bubble_x, _) in enumerate(layout_item["bubbles"]):
        x = bubble_x * PAGE_WIDTH
        pdf.circle(x, bubble_y, radius, fill=0, stroke=1)
        pdf.setFont(bold, 6.2 if exam_count <= 24 else 5.2)
        pdf.drawCentredString(x, bubble_y - 2, LETTERS[option])
        cell_right = column_right - column_width * (0.04 + option * 0.24)
        pdf.setFont(regular, 5.8 if exam_count <= 24 else 4.8)
        pdf.drawRightString(
            min(cell_right, column_right),
            bubble_y + 6,
            ar(short_text(question["options"][option], 14 if exam_count <= 24 else 9)),
        )


def generate_exam_pdf(exam, output_path):
    """Generate one printable A4 answer sheet aligned with the OMR grader."""
    register_fonts()
    pdf = canvas.Canvas(output_path, pagesize=A4)
    draw_corner_markers(pdf)
    draw_header(pdf, exam)
    draw_qr(pdf, exam, output_path)

    layout = question_layout(exam["question_count"])
    for question, layout_item in zip(exam["questions"], layout):
        draw_question(pdf, question, layout_item, exam["question_count"])

    pdf.setFillColorRGB(0.25, 0.3, 0.38)
    pdf.setFont(font_name(), 7)
    pdf.drawCentredString(
        PAGE_WIDTH / 2,
        11 * mm,
        ar(f"رمز الامتحان: {exam['id']}  |  احتفظ بالورقة مستوية وواضحة عند التصوير"),
    )
    pdf.save()