import os
import json
import logging
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.utils import secure_filename

from models import db, Job, Profile, TrackedCompany, AuditLog
from scrapers.naukri import search_naukri
from scrapers.linkedin import search_linkedin
from scrapers.indeed import search_indeed
from scrapers.google_jobs import search_google_jobs
from scrapers.foundit import search_foundit
from scrapers.shine import search_shine
from scrapers.cutshort import search_cutshort
from scrapers.instahyre import search_instahyre
from scrapers.career_page import find_career_page, extract_email
from scrapers.company_portal import (
    fetch_greenhouse_jobs,
    fetch_lever_jobs,
    fetch_ashby_jobs,
    fetch_generic_career_page_jobs,
    parse_experience_range,
)

from autofill.greenhouse import apply_greenhouse
from autofill.lever import apply_lever
from autofill.workday import apply_workday
from autofill.smartrecruiters import apply_smartrecruiters
from autofill.ashby import apply_ashby
from autofill.emailer import send_application_email

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "artifacts", "screenshots")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "jobbot.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"timeout": 30, "check_same_thread": False}
}
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
app.logger.setLevel(logging.INFO)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable SQLite WAL mode and busy timeout to avoid 'database is locked' errors."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


db.init_app(app)


def ensure_sqlite_schema():
    """Add new columns to existing SQLite database without dropping data."""
    additions = {
        "job": {
            "role_category": "VARCHAR(100)",
            "exp_min_years": "FLOAT",
            "exp_max_years": "FLOAT",
            "salary_text": "VARCHAR(200)",
            "description": "TEXT",
            "last_attempted_at": "DATETIME",
            "screenshot_file": "VARCHAR(300)",
        },
        "profile": {
            "current_city": "VARCHAR(100) DEFAULT ''",
            "current_title": "VARCHAR(200) DEFAULT ''",
            "work_authorization": "VARCHAR(100) DEFAULT 'Authorized to work in India'",
            "gender": "VARCHAR(50) DEFAULT ''",
            "github_url": "VARCHAR(300) DEFAULT ''",
            "custom_answers_json": "TEXT DEFAULT '{}'",
            "exp_filter_min": "FLOAT DEFAULT 0",
            "exp_filter_max": "FLOAT DEFAULT 99",
            "role_filter": "VARCHAR(200) DEFAULT ''",
            "dry_run_mode_enabled": "BOOLEAN DEFAULT 0",
        },
    }
    with app.app_context():
        inspector = db.session.connection()
        for table_name, columns in additions.items():
            try:
                existing = {
                    row[1] for row in inspector.exec_driver_sql(f"PRAGMA table_info({table_name})")
                }
                for column_name, column_type in columns.items():
                    if column_name not in existing:
                        inspector.exec_driver_sql(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        )
            except Exception as e:
                app.logger.warning(f"Schema update check for {table_name}: {e}")
        db.session.commit()


with app.app_context():
    db.create_all()
    ensure_sqlite_schema()
    if not Profile.query.first():
        db.session.add(Profile(
            full_name="Candidate Name",
            email="candidate@example.com",
            phone="+91 9876543210",
            current_city="Bengaluru",
            keywords="Software Engineer, Python Developer, Backend Engineer",
            preferred_cities="Bengaluru, Hyderabad, Pune, Remote",
        ))
        db.session.commit()


def get_profile() -> Profile:
    p = Profile.query.first()
    if not p:
        p = Profile()
        db.session.add(p)
        db.session.commit()
    return p


def _parse_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def run_search(keywords, cities, sources=None, pages: int = 1):
    """Run all selected scrapers with in-memory deduplication and bulk persistence."""
    sources = sources or ["naukri", "linkedin", "indeed", "google_jobs"]
    results_summary = {"jobs_found": 0, "jobs_added": 0}

    # Pre-fetch existing URLs and (title, company) keys into memory to prevent premature query autoflushes & lock contention
    existing_urls = {u[0] for u in db.session.query(Job.job_url).all() if u[0]}
    existing_titles = {
        (t[0].strip().lower(), t[1].strip().lower()) 
        for t in db.session.query(Job.title, Job.company).all() 
        if t[0] and t[1]
    }

    seen_urls_in_batch = set(existing_urls)
    seen_titles_in_batch = set(existing_titles)
    new_job_objects = []

    for keyword in keywords:
        for city in cities:
            results = []
            if "naukri" in sources:
                results += search_naukri(keyword, city, pages=pages)
            if "linkedin" in sources:
                results += search_linkedin(keyword, city, pages=pages)
            if "indeed" in sources:
                results += search_indeed(keyword, city, pages=pages)
            if "google_jobs" in sources:
                results += search_google_jobs(keyword, city, pages=pages)
            if "foundit" in sources:
                results += search_foundit(keyword, city, pages=pages)
            if "shine" in sources:
                results += search_shine(keyword, city, pages=pages)
            if "cutshort" in sources:
                results += search_cutshort(keyword, city, pages=pages)
            if "instahyre" in sources:
                results += search_instahyre(keyword, city, pages=pages)

            results_summary["jobs_found"] += len(results)

            for result in results:
                job_url = result.get("job_url")
                if not job_url:
                    continue

                title = (result.get("title") or "Unknown").strip()
                company = (result.get("company") or "Unknown").strip()
                title_key = (title.lower(), company.lower())

                if job_url in seen_urls_in_batch or title_key in seen_titles_in_batch:
                    continue

                seen_urls_in_batch.add(job_url)
                seen_titles_in_batch.add(title_key)

                job = Job(
                    title=title,
                    company=company,
                    location=result.get("location", city),
                    source=result.get("source", "web"),
                    job_url=job_url,
                    salary_text=result.get("salary_text", ""),
                    exp_min_years=result.get("exp_min_years"),
                    exp_max_years=result.get("exp_max_years"),
                    description=result.get("description", ""),
                    status="new",
                )
                new_job_objects.append(job)
                results_summary["jobs_added"] += 1

    if new_job_objects:
        db.session.add_all(new_job_objects)
        db.session.commit()

    return results_summary


def _attempt_apply(job: Job, dry_run: bool = False) -> bool:
    """
    Identifies the ATS / career page and applies using browser automation, direct API, or email.
    Records audit log and updates Job record.
    """
    profile = get_profile()
    profile_dict = profile.to_dict()
    resume_path = os.path.join(UPLOAD_DIR, profile.resume_filename) if profile.resume_filename else None

    # Resolve Career page & ATS if not already set
    if not job.career_page_url or not job.ats_type:
        career_url, ats_type = find_career_page(job.company, job.job_url)
        job.career_page_url = career_url or job.job_url
        job.ats_type = ats_type or "unknown"

    ok = False
    note = "No automated apply method available."
    screenshot_file = ""
    apply_method = f"ats_{job.ats_type}" if job.ats_type != "unknown" else "manual"

    job_ctx = {"title": job.title, "company": job.company, "job_url": job.job_url}

    if job.ats_type == "greenhouse":
        ok, note, screenshot_file = apply_greenhouse(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_greenhouse"
    elif job.ats_type == "lever":
        ok, note, screenshot_file = apply_lever(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_lever"
    elif job.ats_type == "workday":
        ok, note, screenshot_file = apply_workday(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_workday"
    elif job.ats_type == "smartrecruiters":
        ok, note, screenshot_file = apply_smartrecruiters(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_smartrecruiters"
    elif job.ats_type == "ashby":
        ok, note, screenshot_file = apply_ashby(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_ashby"
    else:
        # Email fallback
        hr_email = job.hr_email or extract_email(job.career_page_url)
        if hr_email:
            job.hr_email = hr_email
            ok, note, screenshot_file = send_application_email(hr_email, job.title, job.company, profile_dict, resume_path, dry_run=dry_run)
            apply_method = "email"
        else:
            note = "No ATS form detected and no HR email found on career page."
            apply_method = "manual_required"

    # Update job status
    job.apply_method = apply_method
    job.last_attempted_at = datetime.utcnow()
    job.notes = note
    if screenshot_file:
        job.screenshot_file = screenshot_file

    if dry_run:
        job.status = "dry_run" if ok else "failed"
    else:
        job.status = "applied" if ok else "failed"
        if ok:
            job.applied_at = datetime.utcnow()

    # Record Audit Log
    audit = AuditLog(
        job_id=job.id,
        job_title=job.title,
        company=job.company,
        apply_method=apply_method,
        is_dry_run=dry_run,
        status="success" if ok else "failed",
        message=note,
        screenshot_file=screenshot_file,
    )
    db.session.add(audit)
    return ok


def run_auto_apply(dry_run: bool = False):
    """Batch apply/dry-run on all new jobs."""
    jobs = Job.query.filter_by(status="new").all()
    results = {"applied": 0, "failed": 0, "dry_run": 0}
    for job in jobs:
        ok = _attempt_apply(job, dry_run=dry_run)
        if dry_run:
            results["dry_run" if ok else "failed"] += 1
        else:
            results["applied" if ok else "failed"] += 1
    db.session.commit()
    return results


def run_scheduled_automation():
    """Daily scheduled automated discovery and application."""
    with app.app_context():
        profile = get_profile()
        keywords = _parse_csv(profile.keywords)
        cities = _parse_csv(profile.preferred_cities)
        search_res = run_search(keywords, cities)
        apply_res = run_auto_apply(dry_run=profile.dry_run_mode_enabled)
        app.logger.info(
            "[scheduled] Complete: found=%d, added=%d, applied=%d, failed=%d",
            search_res["jobs_found"], search_res["jobs_added"], apply_res.get("applied", 0), apply_res.get("failed", 0)
        )


def start_scheduler():
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
    return scheduler


# ---------- Routes ----------

@app.route("/")
def index():
    status_filter = request.args.get("status", "new")
    role_filter = request.args.get("role", "").strip()
    source_filter = request.args.get("source", "").strip()
    exp_min = request.args.get("exp_min", type=float)
    exp_max = request.args.get("exp_max", type=float)

    query = Job.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    if role_filter:
        query = query.filter(Job.title.ilike(f"%{role_filter}%"))
    if source_filter:
        query = query.filter_by(source=source_filter)

    jobs = query.order_by(Job.discovered_at.desc()).all()

    # Experience range filtering
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
        "dry_run": Job.query.filter_by(status="dry_run").count(),
        "failed": Job.query.filter_by(status="failed").count(),
        "skipped": Job.query.filter_by(status="skipped").count(),
        "all": Job.query.count(),
    }

    return render_template(
        "index.html",
        jobs=jobs,
        counts=counts,
        status_filter=status_filter,
        role_filter=role_filter,
        source_filter=source_filter,
        exp_min=exp_min,
        exp_max=exp_max,
        profile=get_profile(),
    )


@app.route("/search", methods=["POST"])
def search():
    profile = get_profile()
    keywords = _parse_csv(request.form.get("keywords", profile.keywords))
    cities = _parse_csv(request.form.get("cities", profile.preferred_cities))
    sources = request.form.getlist("sources") or ["naukri", "linkedin", "indeed", "google_jobs"]
    pages = int(request.form.get("pages", 1))

    results = run_search(keywords, cities, sources, pages=pages)
    flash(f"Search complete: Found {results['jobs_found']} jobs, added {results['jobs_added']} new jobs.")
    return redirect(url_for("index"))


@app.route("/apply/<int:job_id>", methods=["POST"])
def apply_single(job_id):
    job = Job.query.get_or_404(job_id)
    _attempt_apply(job, dry_run=False)
    db.session.commit()
    flash(f"Apply completed for '{job.title}' at {job.company}: {job.notes}")
    return redirect(url_for("index"))


@app.route("/dry_run/<int:job_id>", methods=["POST"])
def dry_run_single(job_id):
    job = Job.query.get_or_404(job_id)
    _attempt_apply(job, dry_run=True)
    db.session.commit()
    flash(f"Dry-run executed for '{job.title}' at {job.company}: {job.notes}")
    return redirect(url_for("index"))


@app.route("/skip/<int:job_id>", methods=["POST"])
def skip(job_id):
    job = Job.query.get_or_404(job_id)
    job.status = "skipped"
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/auto_apply", methods=["POST"])
def auto_apply():
    mode = request.form.get("mode", "apply")
    dry_run = (mode == "dry_run")
    results = run_auto_apply(dry_run=dry_run)
    if dry_run:
        flash(f"Auto-Apply Dry Run finished — {results['dry_run']} simulated, {results['failed']} failed.")
    else:
        flash(f"Auto-apply run finished — {results['applied']} applied, {results['failed']} failed.")
    return redirect(url_for("index"))


@app.route("/report")
def report():
    jobs = Job.query.filter(Job.status.in_(["applied", "failed", "dry_run"])).order_by(Job.last_attempted_at.desc()).all()
    return render_template("report.html", jobs=jobs)


@app.route("/audit")
def audit():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template("audit.html", logs=logs)


@app.route("/screenshots/<path:filename>")
def get_screenshot(filename):
    return send_from_directory(SCREENSHOTS_DIR, filename)


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
    flash(f"Added {name} to tracked company portals.")
    return redirect(url_for("portals"))


@app.route("/portals/<int:company_id>/delete", methods=["POST"])
def portals_delete(company_id):
    company = TrackedCompany.query.get_or_404(company_id)
    db.session.delete(company)
    db.session.commit()
    flash("Company portal removed.")
    return redirect(url_for("portals"))


@app.route("/portals/search", methods=["POST"])
def portals_search():
    companies = TrackedCompany.query.all()
    added = 0
    existing_urls = {u[0] for u in db.session.query(Job.job_url).all() if u[0]}
    new_jobs = []

    for company in companies:
        if company.ats_type == "greenhouse" and company.board_token:
            results = fetch_greenhouse_jobs(company.board_token)
        elif company.ats_type == "lever" and company.board_token:
            results = fetch_lever_jobs(company.board_token)
        elif company.ats_type == "ashby" and company.board_token:
            results = fetch_ashby_jobs(company.board_token)
        elif company.career_url:
            results = fetch_generic_career_page_jobs(company.career_url, company.display_name)
        else:
            continue

        for result in results:
            url = result.get("job_url")
            if not url or url in existing_urls:
                continue
            existing_urls.add(url)
            exp_min, exp_max = parse_experience_range(result.get("raw_content", ""))
            new_jobs.append(
                Job(
                    title=result.get("title", "Unknown"),
                    company=company.display_name,
                    location=result.get("location", ""),
                    source="company_portal",
                    job_url=url,
                    career_page_url=url,
                    ats_type=result.get("ats_type", "unknown"),
                    exp_min_years=exp_min,
                    exp_max_years=exp_max,
                    status="new",
                )
            )
            added += 1

    if new_jobs:
        db.session.add_all(new_jobs)
        db.session.commit()

    flash(f"Company portal search complete — {added} new jobs added.")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
def profile_page():
    profile = get_profile()
    if request.method == "POST":
        for field in [
            "full_name", "email", "phone", "current_city", "current_company", "current_title",
            "current_ctc", "expected_ctc", "work_authorization", "gender",
            "linkedin_url", "github_url", "portfolio_url", "cover_letter_template",
            "keywords", "preferred_cities", "smtp_email"
        ]:
            if field in request.form:
                setattr(profile, field, request.form.get(field, "").strip())

        profile.total_experience_years = float(request.form.get("total_experience_years") or 0)
        profile.notice_period_days = int(request.form.get("notice_period_days") or 0)
        profile.min_experience = float(request.form.get("min_experience") or 0)
        profile.dry_run_mode_enabled = bool(request.form.get("dry_run_mode_enabled"))

        # Parse Custom Q&A key-values
        custom_keys = request.form.getlist("custom_key")
        custom_values = request.form.getlist("custom_val")
        custom_dict = {}
        for k, v in zip(custom_keys, custom_values):
            if k.strip():
                custom_dict[k.strip()] = v.strip()
        profile.set_custom_answers(custom_dict)

        resume = request.files.get("resume")
        if resume and resume.filename:
            filename = secure_filename(resume.filename)
            resume.save(os.path.join(UPLOAD_DIR, filename))
            profile.resume_filename = filename

        db.session.commit()
        flash("Profile and auto-apply settings updated successfully.")
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
