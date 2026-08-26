import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from models import db, Job, Profile
from scrapers.naukri import search_naukri
from scrapers.linkedin import search_linkedin
from scrapers.indeed import search_indeed
from scrapers.career_page import find_career_page, extract_email
from autofill.greenhouse import apply_greenhouse
from autofill.lever import apply_lever
from autofill.emailer import send_application_email

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "jobbot.db")
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
app.logger.setLevel(logging.INFO)
db.init_app(app)

with app.app_context():
    db.create_all()
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
    query = Job.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    jobs = query.order_by(Job.discovered_at.desc()).all()
    counts = {
        "new": Job.query.filter_by(status="new").count(),
        "applied": Job.query.filter_by(status="applied").count(),
        "failed": Job.query.filter_by(status="failed").count(),
        "skipped": Job.query.filter_by(status="skipped").count(),
    }
    return render_template("index.html", jobs=jobs, counts=counts, status_filter=status_filter, profile=get_profile())


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
