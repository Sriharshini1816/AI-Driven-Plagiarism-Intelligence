"""
Academic Integrity Review — Flask Application Entry Point
Provides REST API + HTML UI for submission management, analysis, and instructor review.

AGENT_INSTRUCTIONS:
  All thresholds, policy text, privacy modes, and report formats are controlled
  via environment variables (see .env.template). No code changes are needed for
  institutional customisation — modify .env and restart.

  DISCLAIMER: This system provides RECOMMENDATIONS only. All final academic
  misconduct decisions MUST be made by qualified human instructors.
"""
import os
import uuid
import threading
import logging
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    abort,
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# ── App factory ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///academic_integrity.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))

UPLOAD_FOLDER = Path(__file__).parent / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Database init ────────────────────────────────────────────────────────────

from models import db, Submission, AnalysisReport, Flag, InstructorFeedback  # noqa: E402

db.init_app(app)

with app.app_context():
    db.create_all()

# ── Helpers ──────────────────────────────────────────────────────────────────

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_file_type(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower()


def _run_analysis_async(submission_id: int) -> None:
    """Start analysis in a background thread (avoids blocking the HTTP response)."""
    with app.app_context():
        from modules.analyser import run_analysis
        run_analysis(submission_id)


# ── Routes — Pages ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Upload / home page."""
    policy_text = os.getenv(
        "INTEGRITY_POLICY_TEXT",
        "By submitting this assignment you confirm the work is your own and complies "
        "with the institution's academic integrity policy.",
    )
    return render_template("index.html", policy_text=policy_text)


@app.route("/dashboard")
def dashboard():
    """Instructor dashboard — list of all submissions with risk indicators."""
    submissions = (
        Submission.query.order_by(Submission.submitted_at.desc()).all()
    )
    stats = {
        "total": len(submissions),
        "pending": sum(1 for s in submissions if s.status == "pending"),
        "processing": sum(1 for s in submissions if s.status == "processing"),
        "complete": sum(1 for s in submissions if s.status == "complete"),
        "high_risk": 0,
        "medium_risk": 0,
        "low_risk": 0,
    }
    for s in submissions:
        if s.analysis:
            stats[f"{s.analysis.overall_risk}_risk"] = stats.get(f"{s.analysis.overall_risk}_risk", 0) + 1
    return render_template("dashboard.html", submissions=submissions, stats=stats)


@app.route("/review/<int:submission_id>")
def review(submission_id: int):
    """Detailed review page for a single submission."""
    submission = Submission.query.get_or_404(submission_id)
    report = submission.analysis
    flags = (
        Flag.query.filter_by(submission_id=submission_id)
        .order_by(Flag.severity.desc(), Flag.confidence.desc())
        .all()
    )
    feedback_list = (
        InstructorFeedback.query.filter_by(submission_id=submission_id)
        .order_by(InstructorFeedback.created_at.desc())
        .all()
    )
    flag_counts = {
        "similarity": sum(1 for f in flags if f.flag_type == "similarity"),
        "citation": sum(1 for f in flags if f.flag_type == "citation"),
        "style": sum(1 for f in flags if f.flag_type == "style"),
        "ai_pattern": sum(1 for f in flags if f.flag_type == "ai_pattern"),
    }
    return render_template(
        "review.html",
        submission=submission,
        report=report,
        flags=flags,
        feedback_list=feedback_list,
        flag_counts=flag_counts,
        report_format=os.getenv("REPORT_FORMAT", "detailed"),
        privacy_mode=os.getenv("PRIVACY_MODE", "full"),
    )


# ── Routes — API ─────────────────────────────────────────────────────────────

@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Accepts a multipart form upload and queues analysis."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 415

    student_name = request.form.get("student_name", "").strip()
    student_id = request.form.get("student_id", "").strip()
    course_code = request.form.get("course_code", "").strip()
    assignment_title = request.form.get("assignment_title", "").strip()

    for field, value in [("student_name", student_name), ("student_id", student_id),
                          ("course_code", course_code), ("assignment_title", assignment_title)]:
        if not value:
            return jsonify({"error": f"Field '{field}' is required"}), 400

    original_filename = secure_filename(file.filename)
    file_type = _get_file_type(original_filename)
    unique_name = f"{uuid.uuid4().hex}_{original_filename}"
    save_path = UPLOAD_FOLDER / unique_name
    file.save(str(save_path))

    submission = Submission(
        student_name=student_name,
        student_id=student_id,
        course_code=course_code,
        assignment_title=assignment_title,
        filename=str(save_path),
        original_filename=original_filename,
        file_type=file_type,
    )
    db.session.add(submission)
    db.session.commit()

    # Kick off analysis asynchronously
    thread = threading.Thread(
        target=_run_analysis_async,
        args=(submission.id,),
        daemon=True,
    )
    thread.start()

    return jsonify(
        {
            "message": "Submission received. Analysis in progress.",
            "submission_id": submission.id,
            "redirect": url_for("review", submission_id=submission.id),
        }
    ), 202


@app.route("/api/submission/<int:submission_id>/status")
def api_status(submission_id: int):
    """Polling endpoint for analysis status."""
    submission = Submission.query.get_or_404(submission_id)
    data = submission.to_dict()
    if submission.analysis:
        data["analysis"] = submission.analysis.to_dict()
        data["flag_count"] = Flag.query.filter_by(submission_id=submission_id).count()
    return jsonify(data)


@app.route("/api/submission/<int:submission_id>/flags")
def api_flags(submission_id: int):
    """Return all flags for a submission as JSON."""
    flags = Flag.query.filter_by(submission_id=submission_id).all()
    return jsonify([f.to_dict() for f in flags])


@app.route("/api/submission/<int:submission_id>/flag/<int:flag_id>/review", methods=["POST"])
def api_mark_reviewed(submission_id: int, flag_id: int):
    """Mark a specific flag as reviewed by an instructor."""
    flag = Flag.query.filter_by(id=flag_id, submission_id=submission_id).first_or_404()
    flag.reviewed = True
    db.session.commit()
    return jsonify({"success": True, "flag_id": flag_id})


@app.route("/api/submission/<int:submission_id>/feedback", methods=["POST"])
def api_add_feedback(submission_id: int):
    """Add instructor feedback/decision for a submission."""
    Submission.query.get_or_404(submission_id)
    data = request.get_json(force=True)

    instructor_name = (data.get("instructor_name") or "").strip()
    decision = (data.get("decision") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not instructor_name or decision not in ("cleared", "under_review", "referred"):
        return jsonify(
            {"error": "instructor_name and a valid decision (cleared|under_review|referred) are required"}
        ), 400

    feedback = InstructorFeedback(
        submission_id=submission_id,
        instructor_name=instructor_name,
        decision=decision,
        notes=notes,
    )
    db.session.add(feedback)
    db.session.commit()
    return jsonify(feedback.to_dict()), 201


@app.route("/api/submissions")
def api_list_submissions():
    """List all submissions with optional course_code filter."""
    course = request.args.get("course_code")
    query = Submission.query.order_by(Submission.submitted_at.desc())
    if course:
        query = query.filter_by(course_code=course)
    submissions = query.limit(100).all()
    results = []
    for s in submissions:
        d = s.to_dict()
        if s.analysis:
            d["overall_risk"] = s.analysis.overall_risk
        results.append(d)
    return jsonify(results)


@app.route("/api/submission/<int:submission_id>", methods=["DELETE"])
def api_delete_submission(submission_id: int):
    """Delete a submission and all related data (GDPR / privacy compliance)."""
    submission = Submission.query.get_or_404(submission_id)
    # Remove uploaded file
    try:
        Path(submission.filename).unlink(missing_ok=True)
    except Exception:
        pass
    db.session.delete(submission)
    db.session.commit()
    return jsonify({"success": True, "deleted_id": submission_id})


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum size is 16 MB."}), 413


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
