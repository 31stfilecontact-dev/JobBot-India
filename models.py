from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    source = db.Column(db.String(50))          # naukri / linkedin / indeed / manual
    job_url = db.Column(db.String(1000))        # link to the job posting
    career_page_url = db.Column(db.String(1000))  # detected company career/ATS page
    ats_type = db.Column(db.String(50))         # greenhouse / lever / workday / unknown
    hr_email = db.Column(db.String(200))        # extracted email fallback

    role_category = db.Column(db.String(100))  # e.g. "Corporate Tax", "Direct Tax", "GST"
    exp_min_years = db.Column(db.Float)         # parsed from JD, best-effort
    exp_max_years = db.Column(db.Float)

    status = db.Column(db.String(30), default="new")
    # new -> discovered, applied -> applied, skipped -> user skipped, failed -> apply attempt failed

    apply_method = db.Column(db.String(50))     # ats_greenhouse / ats_lever / email / manual
    applied_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

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
            "applied_at": self.applied_at.strftime("%Y-%m-%d %H:%M") if self.applied_at else None,
            "notes": self.notes,
        }


class Profile(db.Model):
    """Single-row table holding the user's editable application data."""
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    current_company = db.Column(db.String(200), default="")
    total_experience_years = db.Column(db.Float, default=0)
    current_ctc = db.Column(db.String(50), default="")
    expected_ctc = db.Column(db.String(50), default="")
    notice_period_days = db.Column(db.Integer, default=0)
    linkedin_url = db.Column(db.String(300), default="")
    portfolio_url = db.Column(db.String(300), default="")
    cover_letter_template = db.Column(db.Text, default="")
    resume_filename = db.Column(db.String(300), default="")  # stored under /uploads

    # search preferences
    keywords = db.Column(db.String(500), default="")          # comma separated
    preferred_cities = db.Column(db.String(500), default="Hyderabad,Bengaluru,Mumbai,Pune,Delhi NCR")
    min_experience = db.Column(db.Float, default=0)

    # SMTP config for email auto-apply (stored, but recommend using env vars instead)
    smtp_email = db.Column(db.String(200), default="")

    exp_filter_min = db.Column(db.Float, default=0)
    exp_filter_max = db.Column(db.Float, default=99)
    role_filter = db.Column(db.String(200), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TrackedCompany(db.Model):
    """Company career portals the user wants to search directly."""
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(200), nullable=False)
    ats_type = db.Column(db.String(50))       # greenhouse / lever / generic
    board_token = db.Column(db.String(200))   # greenhouse/lever slug, if applicable
    career_url = db.Column(db.String(1000))   # generic careers page URL
    added_at = db.Column(db.DateTime, default=db.func.now())

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
