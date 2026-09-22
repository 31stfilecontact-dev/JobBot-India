"""
Auto-apply to jobs hosted on Lever (jobs.lever.co).
Supports direct HTTP form submission with Playwright browser fallback.
"""
import os
import requests
from bs4 import BeautifulSoup
from autofill.browser_engine import run_playwright_apply


def apply_lever(job_url: str, profile: dict, resume_path: str, dry_run: bool = False, job_context: dict = None):
    """
    Apply to a Lever job posting.
    Returns: (success: bool, note: str, screenshot_file: str, unanswered_fields: list)
    """
    job_context = job_context or {}
    apply_url = job_url if job_url.rstrip("/").endswith("/apply") else job_url.rstrip("/") + "/apply"

    if dry_run:
        return run_playwright_apply(apply_url, profile, resume_path, "lever", dry_run=True, job_context=job_context)

    # First attempt: Direct HTTP submission
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

    try:
        resp = session.get(apply_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            form = soup.find("form")
            if form:
                action = form.get("action") or apply_url
                form_data = {
                    "name": profile.get("full_name", ""),
                    "email": profile.get("email", ""),
                    "phone": profile.get("phone", ""),
                    "urls[LinkedIn]": profile.get("linkedin_url", ""),
                    "comments": profile.get("cover_letter_template", ""),
                }
                files = {}
                if resume_path and os.path.exists(resume_path):
                    files["resume"] = open(resume_path, "rb")

                try:
                    submit_resp = session.post(action, data=form_data, files=files, headers=headers, timeout=20)
                    if files:
                        files["resume"].close()
                    if submit_resp.status_code in (200, 302):
                        return True, "Application submitted directly via Lever.", "", []
                except Exception:
                    if files and "resume" in files and not files["resume"].closed:
                        files["resume"].close()
    except Exception:
        pass

    # Fallback to Playwright
    return run_playwright_apply(apply_url, profile, resume_path, "lever", dry_run=False, job_context=job_context)
