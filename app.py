import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from models import db, Job, Profile, TrackedCompany
from scrapers.naukri import search_naukri
from scrapers.linkedin import search_linkedin
from scrapers.indeed import search_indeed
from scrapers.career_page import find_career_page, extract_email
from autofill.greenhouse import apply_greenhouse
from autofill.lever import apply_lever
from autofill.emailer import send_application_email
from scrapers.company_portal import (
    fetch_greenhouse_jobs,
    fetch_lever_jobs,
    fetch_generic_career_page_jobs,
    parse_experience_range,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "jobbot.db")
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
app.logger.setLevel(logging.INFO)
db.init_app(app)


def ensure_sqlite_schema():
    """Add addon columns without deleting existing SQLite data."""
    additions = {
        "job": {
            "role_category": "VARCHAR(100)",
            "exp_min_years": "FLOAT",
            "exp_max_years": "FLOAT",
        },
        "profile": {
            "exp_filter_min": "FLOAT DEFAULT 0",
            "exp_filter_max": "FLOAT DEFAULT 99",
            "role_filter": "VARCHAR(200) DEFAULT ''",
        },
    }
    inspector = db.session.connection()
    for table_name, columns in additions.items():
        existing = {
            row[1] for row in inspector.exec_driver_sql(f"PRAGMA table_info({table_name})")
        }
        for column_name, column_type in columns.items():
            if column_name not in existing:
                inspector.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )
    db.session.commit()


with app.app_context():
    db.create_all()
    ensure_sqlite_schema()
    if not Profile.query.first():
        db.session.add(Profile())
        db.session.commit()


def get_profile():
    return Profile.query.first()


def _parse_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def run_search(keywords, cities, sources=None):
    """Run the configured scrapers and persist only newly discovered jobs."""
    sources = sources or ["naukri", "linkedin", "indeed"]
    results_summary = {"jobs_found": 0, "jobs_added": 0}

    for keyword in keywords:
        for city in cities:
            results = []
            if "naukri" in sources:
                results += search_naukri(keyword, city)
            if "linkedin" in sources:
                results += search_linkedin(keyword, city)
            if "indeed" in sources:
                results += search_indeed(keyword, city)

            results_summary["jobs_found"] += len(results)
            for result in results:
                if not result.get("job_url"):
                    continue
                exists = Job.query.filter_by(job_url=result["job_url"]).first()
                if exists:
                    continue
                job = Job(
                    title=result.get("title", "Unknown"),
                    company=result.get("company", "Unknown"),
                    location=result.get("location", city),
                    source=result.get("source"),
                    job_url=result.get("job_url"),
                    status="new",
                )
                db.session.add(job)
                results_summary["jobs_added"] += 1

    db.session.commit()
    return results_summary


def run_auto_apply():
    """Apply the existing batch logic to every currently new job."""
    jobs = Job.query.filter_by(status="new").all()
    results = {"applied": 0, "failed": 0}
    for job in jobs:
        ok = _attempt_apply(job)
        results["applied" if ok else "failed"] += 1
    db.session.commit()
    return results


def run_scheduled_automation():
    """Run the daily profile-driven search, then apply to new results."""
    with app.app_context():
        profile = get_profile()
        keywords = _parse_csv(profile.keywords)
        cities = _parse_csv(profile.preferred_cities)
        search_results = run_search(keywords, cities)
        apply_results = run_auto_apply()
        app.logger.info(
            "[scheduled] run complete | jobs_found=%d jobs_added=%d applied=%d failed=%d",
            search_results["jobs_found"],
            search_results["jobs_added"],
            apply_results["applied"],
            apply_results["failed"],
        )


def start_scheduler():
    """Start one daily scheduler in the same process as the Flask app."""
    india_timezone = ZoneInfo("Asia/Kolkata")
    scheduler = BackgroundScheduler(timezone=india_timezone)
    scheduler.add_job(
        run_scheduled_automation,
        trigger=CronTrigger(hour=9, minute=0, timezone=india_timezone),
        id="daily-job-search-and-apply",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.logger.info("Scheduled auto-search/auto-apply for 09:00 Asia/Kolkata daily.")
    return scheduler


# ---------- Dashboard ----------

@app.route("/")
def index():
    status_filter = request.args.get("status", "new")
    role_filter = request.args.get("role", "").strip()
    exp_min = request.args.get("exp_min", type=float)
    exp_max = request.args.get("exp_max", type=float)

    query = Job.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    if role_filter:
        query = query.filter(Job.title.ilike(f"%{role_filter}%"))

    jobs = query.order_by(Job.discovered_at.desc()).all()

    # Experience ranges can be partial, so apply this part in Python.
    if exp_min is not None or exp_max is not None:
        def in_range(job):
            if job.exp_min_years is None and job.exp_max_years is None:
                return True
            lo = job.exp_min_years if job.exp_min_years is not None else 0
            hi = job.exp_max_years if job.exp_max_years is not None else 99
            want_lo = exp_min if exp_min is not None else 0
            want_hi = exp_max if exp_max is not None else 99
            return lo <= want_hi and hi >= want_lo

        jobs = [job for job in jobs if in_range(job)]

    counts = {
        "new": Job.query.filter_by(status="new").count(),
        "applied": Job.query.filter_by(status="applied").count(),
        "failed": Job.query.filter_by(status="failed").count(),
        "skipped": Job.query.filter_by(status="skipped").count(),
    }
    return render_template(
        "index.html",
        jobs=jobs,
        counts=counts,
        status_filter=status_filter,
        role_filter=role_filter,
        exp_min=exp_min,
        exp_max=exp_max,
        profile=get_profile(),
    )


# ---------- Search ----------

@app.route("/search", methods=["POST"])
def search():
    profile = get_profile()
    keywords = _parse_csv(request.form.get("keywords", profile.keywords))
    cities = _parse_csv(request.form.get("cities", profile.preferred_cities))
    sources = request.form.getlist("sources") or ["naukri", "linkedin", "indeed"]
    results = run_search(keywords, cities, sources)
    flash(f"Search complete — {results['jobs_added']} new jobs added.")
    return redirect(url_for("index"))


# ---------- Manual apply (single job) ----------

@app.route("/apply/<int:job_id>", methods=["POST"])
def apply_single(job_id):
    job = Job.query.get_or_404(job_id)
    _attempt_apply(job)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/skip/<int:job_id>", methods=["POST"])
def skip(job_id):
    job = Job.query.get_or_404(job_id)
    job.status = "skipped"
    db.session.commit()
    return redirect(url_for("index"))


# ---------- Auto-apply (batch) ----------

@app.route("/auto_apply", methods=["POST"])
def auto_apply():
    results = run_auto_apply()
    flash(f"Auto-apply run finished — {results['applied']} applied, {results['failed']} failed/need manual review.")
    return redirect(url_for("index"))


# ---------- Company portal tracking ----------

@app.route("/portals", methods=["GET"])
def portals():
    companies = TrackedCompany.query.order_by(TrackedCompany.added_at.desc()).all()
    return render_template("portals.html", companies=companies)


@app.route("/portals/add", methods=["POST"])
def portals_add():
    name = request.form.get("display_name", "").strip()
    ats_type = request.form.get("ats_type", "generic")
    board_token = request.form.get("board_token", "").strip()
    career_url = request.form.get("career_url", "").strip()

    if not name:
        flash("Company name is required.")
        return redirect(url_for("portals"))

    company = TrackedCompany(
        display_name=name,
        ats_type=ats_type,
        board_token=board_token or None,
        career_url=career_url or None,
    )
    db.session.add(company)
    db.session.commit()
    flash(f"Added {name} to tracked companies.")
    return redirect(url_for("portals"))


@app.route("/portals/<int:company_id>/delete", methods=["POST"])
def portals_delete(company_id):
    company = TrackedCompany.query.get_or_404(company_id)
    db.session.delete(company)
    db.session.commit()
    return redirect(url_for("portals"))


@app.route("/portals/search", methods=["POST"])
def portals_search():
    companies = TrackedCompany.query.all()
    added = 0
    for company in companies:
        if company.ats_type == "greenhouse" and company.board_token:
            results = fetch_greenhouse_jobs(company.board_token)
        elif company.ats_type == "lever" and company.board_token:
            results = fetch_lever_jobs(company.board_token)
        elif company.career_url:
            results = fetch_generic_career_page_jobs(company.career_url, company.display_name)
        else:
            continue

        for result in results:
            if not result.get("job_url"):
                continue
            if Job.query.filter_by(job_url=result["job_url"]).first():
                continue
            exp_min_years, exp_max_years = parse_experience_range(
                result.get("raw_content", "")
            )
            db.session.add(
                Job(
                    title=result.get("title", "Unknown"),
                    company=company.display_name,
                    location=result.get("location", ""),
                    source="company_portal",
                    job_url=result["job_url"],
                    career_page_url=result["job_url"],
                    ats_type=result.get("ats_type"),
                    exp_min_years=exp_min_years,
                    exp_max_years=exp_max_years,
                    status="new",
                )
            )
            added += 1
    db.session.commit()
    flash(f"Company portal search complete — {added} new jobs added.")
    return redirect(url_for("index"))


def _attempt_apply(job: Job) -> bool:
    """Detects the career page / ATS, then tries the right apply method.
    Mutates `job` in place; caller commits."""
    profile = get_profile()
    resume_path = os.path.join(UPLOAD_DIR, profile.resume_filename) if profile.resume_filename else None

    if not job.career_page_url or not job.ats_type:
        career_url, ats_type = find_career_page(job.company, job.job_url)
        job.career_page_url = career_url or job.job_url
        job.ats_type = ats_type

    ok, note = False, "no automated apply method available — apply manually"

    if job.ats_type == "greenhouse":
        ok, note = apply_greenhouse(job.career_page_url, profile.to_dict(), resume_path)
        job.apply_method = "ats_greenhouse"
    elif job.ats_type == "lever":
        ok, note = apply_lever(job.career_page_url, profile.to_dict(), resume_path)
        job.apply_method = "ats_lever"
    else:
        # fallback: try to find an HR email on the career page and email the application
        hr_email = job.hr_email or extract_email(job.career_page_url)
        if hr_email:
            job.hr_email = hr_email
            ok, note = send_application_email(hr_email, job.title, job.company, profile.to_dict(), resume_path)
            job.apply_method = "email"
        else:
            note = "no ATS form and no HR email found — apply manually"

    job.status = "applied" if ok else "failed"
    job.notes = note
    if ok:
        job.applied_at = datetime.utcnow()
    return ok


# ---------- Applied report ----------

@app.route("/report")
def report():
    jobs = Job.query.filter(Job.status.in_(["applied", "failed"])).order_by(Job.applied_at.desc()).all()
    return render_template("report.html", jobs=jobs)


# ---------- Profile / editable data ----------

@app.route("/profile", methods=["GET", "POST"])
def profile_page():
    profile = get_profile()
    if request.method == "POST":
        for field in ["full_name", "email", "phone", "current_company", "current_ctc",
                      "expected_ctc", "linkedin_url", "portfolio_url", "cover_letter_template",
                      "keywords", "preferred_cities"]:
            setattr(profile, field, request.form.get(field, ""))
        profile.total_experience_years = float(request.form.get("total_experience_years") or 0)
        profile.notice_period_days = int(request.form.get("notice_period_days") or 0)
        profile.min_experience = float(request.form.get("min_experience") or 0)

        resume = request.files.get("resume")
        if resume and resume.filename:
            filename = secure_filename(resume.filename)
            resume.save(os.path.join(UPLOAD_DIR, filename))
            profile.resume_filename = filename

        db.session.commit()
        flash("Profile updated.")
        return redirect(url_for("profile_page"))

    return render_template("profile.html", profile=profile)


if __name__ == "__main__":
    scheduler = start_scheduler()
    try:
        app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 5000)),
            debug=True,
            use_reloader=False,
        )
    finally:
        scheduler.shutdown(wait=False)
