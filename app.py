import json
import os
import re
import uuid
from datetime import datetime, timezone

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from exam_generator import generate_exam_pdf
from omr_grader import grade_sheet


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXAMS_DIR = os.path.join(DATA_DIR, "exams")
RESULTS_DIR = os.path.join(DATA_DIR, "results")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
for directory in (EXAMS_DIR, RESULTS_DIR, UPLOADS_DIR):
    os.makedirs(directory, exist_ok=True)

ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
EXAM_ID_PATTERN = re.compile(r"^[A-Z0-9]{8}$")

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "local-development-secret")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024


def is_valid_exam_id(exam_id):
    return bool(EXAM_ID_PATTERN.fullmatch(exam_id or ""))


def load_exam(exam_id):
    if not is_valid_exam_id(exam_id):
        return None
    path = os.path.join(EXAMS_DIR, f"{exam_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None


def save_json(directory, identifier, payload):
    path = os.path.join(directory, f"{identifier}.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return path


def list_exams():
    exams = []
    for filename in os.listdir(EXAMS_DIR):
        if filename.endswith(".json"):
            exam = load_exam(filename[:-5])
            if exam:
                exams.append(exam)
    return sorted(exams, key=lambda item: item.get("created_at", ""), reverse=True)


def list_results():
    results = []
    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith(".json"):
            path = os.path.join(RESULTS_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    results.append(json.load(stream))
            except (OSError, json.JSONDecodeError):
                continue
    return sorted(results, key=lambda item: item.get("created_at", ""), reverse=True)


def allowed_upload(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS
    )


@app.context_processor
def inject_navigation_counts():
    return {"exam_count": len(list_exams())}


@app.errorhandler(413)
def file_too_large(_error):
    flash("حجم الصورة كبير. الحد الأقصى المسموح به هو 12 ميجابايت.")
    return redirect(url_for("grade_exam"))


@app.route("/")
def index():
    return render_template(
        "index.html",
        exams=list_exams(),
        results=list_results()[:8],
    )


@app.route("/create", methods=["GET", "POST"])
def create_exam():
    if request.method == "GET":
        return render_template("create_exam.html")

    subject = request.form.get("subject", "").strip()
    school = request.form.get("school", "").strip()
    class_name = request.form.get("class_name", "").strip()
    semester = request.form.get("semester", "").strip()
    academic_year = request.form.get("academic_year", "").strip()
    try:
        question_count = int(request.form.get("question_count", 24))
    except (TypeError, ValueError):
        question_count = 0

    if not subject or not school or not class_name:
        flash("أدخلي اسم المدرسة والمادة والصف.")
        return redirect(url_for("create_exam"))
    if question_count < 4 or question_count > 40 or question_count % 4:
        flash("عدد الأسئلة يجب أن يكون من 4 إلى 40 ومن مضاعفات 4.")
        return redirect(url_for("create_exam"))

    questions = []
    for number in range(1, question_count + 1):
        text = request.form.get(f"question_{number}", "").strip()
        options = [
            request.form.get(f"q{number}_{letter}", "").strip()
            for letter in ("a", "b", "c", "d")
        ]
        correct = request.form.get(f"correct_{number}", "A").upper()
        if not text or any(not option for option in options) or correct not in "ABCD":
            flash(f"أكملي نص السؤال والاختيارات للسؤال رقم {number}.")
            return redirect(url_for("create_exam"))
        questions.append(
            {
                "number": number,
                "text": text,
                "options": options,
                "correct": correct,
            }
        )

    exam_id = uuid.uuid4().hex[:8].upper()
    exam = {
        "id": exam_id,
        "school": school,
        "subject": subject,
        "class_name": class_name,
        "semester": semester,
        "academic_year": academic_year,
        "question_count": question_count,
        "total_grade": question_count // 4,
        "options": ["A", "B", "C", "D"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }
    save_json(EXAMS_DIR, exam_id, exam)
    generate_exam_pdf(exam, os.path.join(EXAMS_DIR, f"{exam_id}.pdf"))
    return redirect(url_for("exam_created", exam_id=exam_id))


@app.route("/exam/<exam_id>")
def exam_created(exam_id):
    exam = load_exam(exam_id)
    if not exam:
        return render_template("not_found.html", message="الامتحان غير موجود"), 404
    return render_template("exam_created.html", exam=exam)


@app.route("/download/<exam_id>")
def download_exam(exam_id):
    exam = load_exam(exam_id)
    pdf_path = os.path.join(EXAMS_DIR, f"{exam_id}.pdf")
    if not exam or not os.path.isfile(pdf_path):
        return render_template("not_found.html", message="ملف الامتحان غير موجود"), 404
    return send_file(pdf_path, as_attachment=True, download_name=f"exam_{exam_id}.pdf")


@app.route("/grade", methods=["GET", "POST"])
def grade_exam():
    if request.method == "GET":
        return render_template("grade.html", exams=list_exams())

    exam_id = request.form.get("exam_id", "")
    exam = load_exam(exam_id)
    image = request.files.get("answer_sheet")
    if not exam:
        flash("اختاري امتحانًا صحيحًا.")
        return redirect(url_for("grade_exam"))
    if image is None or not image.filename:
        flash("اختاري صورة ورقة الطالب.")
        return redirect(url_for("grade_exam"))
    if not allowed_upload(image.filename):
        flash("نوع الملف غير مدعوم. استخدمي JPG أو PNG أو WEBP.")
        return redirect(url_for("grade_exam"))

    extension = secure_filename(image.filename).rsplit(".", 1)[-1].lower()
    upload_id = uuid.uuid4().hex
    image_path = os.path.join(UPLOADS_DIR, f"{upload_id}.{extension}")
    image.save(image_path)

    result = grade_sheet(image_path, exam)
    result_id = uuid.uuid4().hex[:10].upper()
    result.update(
        {
            "result_id": result_id,
            "exam_id": exam_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_json(RESULTS_DIR, result_id, result)
    return render_template("result.html", result=result, exam=exam)


@app.route("/result/<result_id>")
def result_detail(result_id):
    if not re.fullmatch(r"[A-Z0-9]{10}", result_id or ""):
        return render_template("not_found.html", message="النتيجة غير موجودة"), 404
    path = os.path.join(RESULTS_DIR, f"{result_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as stream:
            result = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return render_template("not_found.html", message="النتيجة غير موجودة"), 404
    exam = load_exam(result.get("exam_id"))
    if not exam:
        return render_template("not_found.html", message="الامتحان المرتبط غير موجود"), 404
    return render_template("result.html", result=result, exam=exam)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "smart-exam-grader"})


@app.route("/favicon.ico")
def favicon():
    return "", 204


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )