"""
Database models for the Academic Integrity Review application.
Uses Flask-SQLAlchemy with SQLite for development; swap to PostgreSQL for production.
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Submission(db.Model):
    """Stores an uploaded student assignment submission."""
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(200), nullable=False)
    student_id = db.Column(db.String(100), nullable=False)
    course_code = db.Column(db.String(100), nullable=False)
    assignment_title = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)  # pdf | docx | txt
    word_count = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(
        db.String(30), default="pending"
    )  # pending | processing | complete | error

    # Relationships
    analysis = db.relationship(
        "AnalysisReport", back_populates="submission", uselist=False,
        cascade="all, delete-orphan"
    )
    flags = db.relationship(
        "Flag", back_populates="submission", cascade="all, delete-orphan"
    )
    instructor_feedback = db.relationship(
        "InstructorFeedback", back_populates="submission", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "student_name": self.student_name,
            "student_id": self.student_id,
            "course_code": self.course_code,
            "assignment_title": self.assignment_title,
            "word_count": self.word_count,
            "submitted_at": self.submitted_at.isoformat(),
            "status": self.status,
        }


class AnalysisReport(db.Model):
    """Stores the complete analysis result for a submission."""
    __tablename__ = "analysis_reports"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer, db.ForeignKey("submissions.id"), nullable=False, unique=True
    )
    overall_risk = db.Column(db.String(20), default="unknown")  # low | medium | high
    similarity_score = db.Column(db.Float, default=0.0)
    citation_score = db.Column(db.Float, default=0.0)
    style_score = db.Column(db.Float, default=0.0)
    ai_summary = db.Column(db.Text, default="")
    watsonx_raw_response = db.Column(db.Text, default="")
    analysed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    submission = db.relationship("Submission", back_populates="analysis")

    def to_dict(self):
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "overall_risk": self.overall_risk,
            "similarity_score": round(self.similarity_score, 3),
            "citation_score": round(self.citation_score, 3),
            "style_score": round(self.style_score, 3),
            "ai_summary": self.ai_summary,
            "analysed_at": self.analysed_at.isoformat(),
        }


class Flag(db.Model):
    """A single passage or element flagged during analysis."""
    __tablename__ = "flags"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer, db.ForeignKey("submissions.id"), nullable=False
    )
    flag_type = db.Column(
        db.String(50), nullable=False
    )  # similarity | citation | style | ai_pattern
    severity = db.Column(db.String(20), default="medium")  # low | medium | high
    passage = db.Column(db.Text, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    confidence = db.Column(db.Float, default=0.0)
    start_char = db.Column(db.Integer, default=0)
    end_char = db.Column(db.Integer, default=0)
    reviewed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    submission = db.relationship("Submission", back_populates="flags")

    def to_dict(self):
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "flag_type": self.flag_type,
            "severity": self.severity,
            "passage": self.passage,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "reviewed": self.reviewed,
        }


class InstructorFeedback(db.Model):
    """Instructor decisions and notes on a flagged submission."""
    __tablename__ = "instructor_feedback"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer, db.ForeignKey("submissions.id"), nullable=False
    )
    instructor_name = db.Column(db.String(200), nullable=False)
    decision = db.Column(
        db.String(50), nullable=False
    )  # cleared | under_review | referred
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    submission = db.relationship("Submission", back_populates="instructor_feedback")

    def to_dict(self):
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "instructor_name": self.instructor_name,
            "decision": self.decision,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }
