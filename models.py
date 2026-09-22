import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    source = db.Column(db.String(50))          # naukri / linkedin / indeed / google_jobs / foundit / shine / cutshort / instahyre / company_portal
    job_url = db.Column(db.String(1000))        # link to the job posting
    career_page_url = db.Column(db.String(1000))  # detected company career/ATS page
    ats_type = db.Column(db.String(50))         # greenhouse / lever / workday / smartrecruiters / ashby / unknown
    hr_email = db.Column(db.String(200))        # extracted email fallback

    role_category = db.Column(db.String(100))
    exp_min_years = db.Column(db.Float)
    exp_max_years = db.Column(db.Float)
    salary_text = db.Column(db.String(200))
    description = db.Column(db.Text)

    status = db.Column(db.String(30), default="new")
    # new -> discovered, applied -> applied, dry_run -> tested dry run, skipped -> user skipped, failed -> apply attempt failed

    apply_method = db.Column(db.String(50))     # ats_greenhouse / ats_lever / ats_workday / ats_smartrecruiters / ats_ashby / email / manual
    applied_at = db.Column(db.DateTime)
    last_attempted_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    screenshot_file = db.Column(db.String(300))

    discovered_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "source": self.source,
            "job_url": self.job_url,
            "career_page_url": self.career_page_url,
            "ats_type": self.ats_type,
            "status": self.status,
            "apply_method": self.apply_method,
            "salary_text": self.salary_text,
            "applied_at": self.applied_at.strftime("%Y-%m-%d %H:%M") if self.applied_at else None,
            "notes": self.notes,
            "screenshot_file": self.screenshot_file,
        }


class Profile(db.Model):
    """Single-row table holding the user's editable application data."""
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    current_city = db.Column(db.String(100), default="")
    current_company = db.Column(db.String(200), default="")
    current_title = db.Column(db.String(200), default="")
    total_experience_years = db.Column(db.Float, default=0)
    current_ctc = db.Column(db.String(50), default="")
    expected_ctc = db.Column(db.String(50), default="")
    notice_period_days = db.Column(db.Integer, default=0)
    work_authorization = db.Column(db.String(100), default="Authorized to work in India")
    gender = db.Column(db.String(50), default="")
    linkedin_url = db.Column(db.String(300), default="")
    github_url = db.Column(db.String(300), default="")
    portfolio_url = db.Column(db.String(300), default="")
    cover_letter_template = db.Column(db.Text, default="")
    resume_filename = db.Column(db.String(300), default="")

    # Custom Q&A key-value answers JSON (e.g. why join us, relocation preference, etc.)
    custom_answers_json = db.Column(db.Text, default="{}")

    # Search preferences
    keywords = db.Column(db.String(500), default="Software Engineer, Python Developer, Full Stack Developer")
    preferred_cities = db.Column(db.String(500), default="Hyderabad,Bengaluru,Mumbai,Pune,Delhi NCR,Remote")
    min_experience = db.Column(db.Float, default=0)
    exp_filter_min = db.Column(db.Float, default=0)
    exp_filter_max = db.Column(db.Float, default=99)
    role_filter = db.Column(db.String(200), default="")

    # Settings
    dry_run_mode_enabled = db.Column(db.Boolean, default=False)
    smtp_email = db.Column(db.String(200), default="")

    def get_custom_answers(self):
        try:
            return json.loads(self.custom_answers_json or "{}")
        except Exception:
            return {}

    def set_custom_answers(self, data: dict):
        self.custom_answers_json = json.dumps(data or {})

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        d["custom_answers"] = self.get_custom_answers()
        return d


class TrackedCompany(db.Model):
    """Company career portals the user wants to search directly."""
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(200), nullable=False)
    ats_type = db.Column(db.String(50))       # greenhouse / lever / ashby / workday / generic
    board_token = db.Column(db.String(200))   # greenhouse/lever/ashby slug
    career_url = db.Column(db.String(1000))   # generic careers page URL
    added_at = db.Column(db.DateTime, default=db.func.now())

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class AuditLog(db.Model):
    """Detailed audit log for every application attempt (dry run or real)."""
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id", ondelete="CASCADE"), nullable=True)
    job_title = db.Column(db.String(300))
    company = db.Column(db.String(200))
    apply_method = db.Column(db.String(50))
    is_dry_run = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(30))         # success / failed / simulated
    message = db.Column(db.Text)
    screenshot_file = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship("Job", backref=db.backref("audit_logs", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "apply_method": self.apply_method,
            "is_dry_run": self.is_dry_run,
            "status": self.status,
            "message": self.message,
            "screenshot_file": self.screenshot_file,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
