import os
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.utils import secure_filename

from models import db, Job, Profile, TrackedCompany, AuditLog, ApplicationMemory
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

from autofill.ai_form_filler import learn_memory
from autofill.greenhouse import apply_greenhouse
from autofill.lever import apply_lever
from autofill.workday import apply_workday
from autofill.smartrecruiters import apply_smartrecruiters
from autofill.ashby import apply_ashby
from autofill.emailer import send_application_email
from autofill.linkedin_apply import apply_linkedin


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "artifacts", "screenshots")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "jobbot.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"timeout": 60, "check_same_thread": False}
}
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
app.logger.setLevel(logging.INFO)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable SQLite WAL mode and 60s busy timeout to avoid 'database is locked' errors."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.close()


db.init_app(app)


class TaskProgress:
    """Thread-safe background progress tracker for auto-apply and scraping."""
    def __init__(self):
        self._lock = threading.Lock()
        self.is_running = False
        self.task_type = ""
        self.total = 0
        self.current = 0
        self.success_count = 0
        self.fail_count = 0
        self.current_title = ""
        self.current_company = ""
        self.message = ""
        self.started_at = None

    def start(self, task_type: str, total: int, message: str = ""):
        with self._lock:
            self.is_running = True
            self.task_type = task_type
            self.total = total
            self.current = 0
            self.success_count = 0
            self.fail_count = 0
            self.current_title = ""
            self.current_company = ""
            self.message = message
            self.started_at = time.time()

    def update(self, current: int, title: str = "", company: str = "", success: bool = None, note: str = ""):
        with self._lock:
            self.current = current
            if title:
                self.current_title = title
            if company:
                self.current_company = company
            if success is True:
                self.success_count += 1
            elif success is False:
                self.fail_count += 1
            if note:
                self.message = note

    def finish(self, message: str = "Completed"):
        with self._lock:
            self.is_running = False
            self.current = self.total
            self.message = message

    def to_dict(self):
        with self._lock:
            pct = int((self.current / self.total * 100)) if self.total > 0 else 0
            return {
                "is_running": self.is_running,
                "task_type": self.task_type,
                "total": self.total,
                "current": self.current,
                "percent": min(100, pct),
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "current_title": self.current_title,
                "current_company": self.current_company,
                "message": self.message,
            }

progress_tracker = TaskProgress()



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
            "unanswered_fields_json": "TEXT DEFAULT '[]'",
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


try:
    with app.app_context():
        db.create_all()
        ensure_sqlite_schema()
        if not Profile.query.first():
            db.session.add(Profile(
                full_name="Aman Mehta",
                email="amanmehta080799@gmail.com",
                phone="+91 9876543210",
                current_city="Bengaluru",
                keywords="Software Engineer, Python Developer, Backend Engineer",
                preferred_cities="Bengaluru, Hyderabad, Pune, Remote",
                smtp_email="amanmehta080799@gmail.com",
            ))
            db.session.commit()
except Exception as e:
    app.logger.warning(f"DB startup init: {e}")



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
    Records audit log, captures unanswered fields, and updates Job record.
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
    unanswered_fields = []
    apply_method = f"ats_{job.ats_type}" if job.ats_type != "unknown" else "manual"

    job_ctx = {"title": job.title, "company": job.company, "job_url": job.job_url, "ats_type": job.ats_type}

    if job.ats_type == "greenhouse":
        ok, note, screenshot_file, unanswered_fields = apply_greenhouse(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_greenhouse"
    elif job.ats_type == "lever":
        ok, note, screenshot_file, unanswered_fields = apply_lever(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_lever"
    elif job.ats_type == "workday":
        ok, note, screenshot_file, unanswered_fields = apply_workday(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_workday"
    elif job.ats_type == "smartrecruiters":
        ok, note, screenshot_file, unanswered_fields = apply_smartrecruiters(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_smartrecruiters"
    elif job.ats_type == "ashby":
        ok, note, screenshot_file, unanswered_fields = apply_ashby(job.career_page_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx)
        apply_method = "ats_ashby"
    elif job.source == "linkedin" or (job.job_url and "linkedin.com" in job.job_url):
        ok, note, screenshot_file, unanswered_fields = apply_linkedin(
            job.job_url, profile_dict, resume_path, dry_run=dry_run, job_context=job_ctx
        )
        apply_method = "linkedin_auto"
    else:
        # Email fallback
        hr_email = job.hr_email or extract_email(job.career_page_url)
        if hr_email:
            job.hr_email = hr_email
            ok, note, screenshot_file, unanswered_fields = send_application_email(hr_email, job.title, job.company, profile_dict, resume_path, dry_run=dry_run)
            apply_method = "email"
        else:
            note = "No ATS form detected and no HR email found on career page."
            apply_method = "manual_required"


    # Update job record
    job.apply_method = apply_method
    job.last_attempted_at = datetime.utcnow()
    job.notes = note
    if screenshot_file:
        job.screenshot_file = screenshot_file
    if unanswered_fields:
        job.set_unanswered_fields(unanswered_fields)

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
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"[apply] Commit error for job {job.id}: {e}")
    return ok


def run_auto_apply(dry_run: bool = False, async_mode: bool = False):
    """Batch apply/dry-run on all new jobs with atomic commits and progress tracking."""
    def _worker():
        with app.app_context():
            job_ids = [j.id for j in Job.query.filter_by(status="new").all()]
            total = len(job_ids)
            progress_tracker.start(
                task_type="dry_run" if dry_run else "apply",
                total=total,
                message=f"Starting {'Dry-Run' if dry_run else 'Auto-Apply'} for {total} new jobs..."
            )
            results = {"applied": 0, "failed": 0, "dry_run": 0}
            for idx, j_id in enumerate(job_ids, 1):
                try:
                    job = db.session.get(Job, j_id)
                    if not job or job.status != "new":
                        continue
                    progress_tracker.update(idx - 1, title=job.title, company=job.company, note=f"Processing {job.title} at {job.company}...")
                    ok = _attempt_apply(job, dry_run=dry_run)
                    if dry_run:
                        results["dry_run" if ok else "failed"] += 1
                    else:
                        results["applied" if ok else "failed"] += 1
                    outcome_tag = "Simulated" if dry_run else "Applied"
                    progress_tracker.update(idx, title=job.title, company=job.company, success=ok, note=f"{outcome_tag} {idx}/{total}: {job.title}")
                except Exception as e:
                    app.logger.error(f"[auto_apply] Error on job {j_id}: {e}")
                    progress_tracker.update(idx, success=False, note=f"Error: {str(e)[:40]}")
            
            progress_tracker.finish(message=f"Completed {total} applications.")
            return results

    if async_mode and not app.config.get("TESTING"):
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return {"status": "started", "total": Job.query.filter_by(status="new").count()}
    else:
        _worker()
        return {"status": "started", "total": Job.query.filter_by(status="new").count()}




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


@app.route("/api/progress", methods=["GET"])
def api_progress():
    """Return JSON status of the background task and progress bar."""
    return jsonify(progress_tracker.to_dict())


@app.route("/apply/<int:job_id>", methods=["POST"])
def apply_single(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        abort(404)
    _attempt_apply(job, dry_run=False)
    flash(f"Apply finished for '{job.title}' at {job.company}: {job.notes}")
    return redirect(url_for("index"))


@app.route("/dry_run/<int:job_id>", methods=["POST"])
def dry_run_single(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        abort(404)
    _attempt_apply(job, dry_run=True)
    flash(f"Dry-run executed for '{job.title}' at {job.company}: {job.notes}")
    return redirect(url_for("index"))


@app.route("/skip/<int:job_id>", methods=["POST"])
def skip(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        abort(404)
    job.status = "skipped"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for("index"))


@app.route("/auto_apply", methods=["POST"])
def auto_apply():
    mode = request.form.get("mode") or (request.get_json(silent=True) or {}).get("mode", "apply")
    dry_run = (mode == "dry_run")
    is_async = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.form.get("async") == "1"
    )
    if is_async:
        run_auto_apply(dry_run=dry_run, async_mode=True)
        return jsonify({"status": "started", "dry_run": dry_run})
    else:
        run_auto_apply(dry_run=dry_run, async_mode=True)
        flash(f"{'Dry-run' if dry_run else 'Live auto-apply'} started in the background. Watch the progress bar below!")
        return redirect(url_for("index"))




# ---------- Resolve & Teach Memory ----------

@app.route("/job/<int:job_id>/resolve", methods=["POST"])
def resolve_and_teach(job_id):
    """
    Saves manually resolved screening answers directly into ApplicationMemory
    and immediately re-triggers an auto-apply/dry-run on the job.
    """
    job = Job.query.get_or_404(job_id)
    questions = request.form.getlist("question")
    answers = request.form.getlist("answer")
    scope = request.form.get("scope", "global") # global or company
    mode = request.form.get("mode", "dry_run" if job.status == "dry_run" else "apply")
    dry_run = (mode == "dry_run")

    target_company = job.company if scope == "company" else None
    learned_count = 0

    for q, a in zip(questions, answers):
        if q.strip() and a.strip():
            learn_memory(q.strip(), a.strip(), company=target_company, ats_type=job.ats_type)
            learned_count += 1

    # Clear unanswered fields since they are now resolved
    job.set_unanswered_fields([])
    db.session.commit()

    # Automatically re-attempt application with new memory
    ok = _attempt_apply(job, dry_run=dry_run)
    db.session.commit()

    if ok:
        action_str = "simulated dry-run" if dry_run else "submitted application"
        flash(f"Learned {learned_count} answer(s) into Memory Bank & successfully {action_str} for {job.company}!")
    else:
        flash(f"Learned {learned_count} answer(s) into Memory Bank. Attempt outcome: {job.notes}")

    return redirect(request.referrer or url_for("index"))



# ---------- Memory Bank Management ----------

@app.route("/memory", methods=["GET"])
def memory_page():
    q = request.args.get("q", "").strip()
    company_filter = request.args.get("company", "").strip()

    query = ApplicationMemory.query
    if q:
        query = query.filter(
            ApplicationMemory.question_pattern.ilike(f"%{q}%") | 
            ApplicationMemory.answer_value.ilike(f"%{q}%")
        )
    if company_filter == "global":
        query = query.filter(ApplicationMemory.company.is_(None))
    elif company_filter == "company":
        query = query.filter(ApplicationMemory.company.isnot(None))

    memories = query.order_by(ApplicationMemory.times_used.desc(), ApplicationMemory.created_at.desc()).all()
    stats = {
        "total": ApplicationMemory.query.count(),
        "global": ApplicationMemory.query.filter(ApplicationMemory.company.is_(None)).count(),
        "company": ApplicationMemory.query.filter(ApplicationMemory.company.isnot(None)).count(),
    }
    return render_template("memory.html", memories=memories, stats=stats, q=q, company_filter=company_filter)


@app.route("/memory/add", methods=["POST"])
def memory_add():
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()
    scope = request.form.get("scope", "global")
    company = request.form.get("company", "").strip() if scope == "company" else None
    ats_type = request.form.get("ats_type", "").strip() or None

    if question and answer:
        learn_memory(question, answer, company=company, ats_type=ats_type)
        flash("New Q&A pair successfully stored in Memory Bank.")
    else:
        flash("Question and Answer are required.")
    return redirect(url_for("memory_page"))


@app.route("/memory/<int:mem_id>/delete", methods=["POST"])
def memory_delete(mem_id):
    mem = ApplicationMemory.query.get_or_404(mem_id)
    db.session.delete(mem)
    db.session.commit()
    flash("Memory entry removed.")
    return redirect(url_for("memory_page"))


# ---------- Reports & Portals ----------

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
