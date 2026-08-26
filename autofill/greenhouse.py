"""
Auto-apply to jobs hosted on Greenhouse (boards.greenhouse.io).
Greenhouse job boards render a normal HTML <form> that posts to the same
URL — no JS execution needed, so this works with plain requests, which is
much lighter than running a browser on Replit's free tier.

NOTE: Every Greenhouse board customises required fields per employer
(some add custom screening questions). This module fills the fields it
recognises (name, email, phone, resume, LinkedIn, cover letter) and skips
unknown custom questions — those will cause the submission to fail
validation, in which case the job is marked "failed" with a note so you
can apply manually. This is expected behaviour, not a bug to "fix away".
"""
import requests
from bs4 import BeautifulSoup


def apply_greenhouse(job_url: str, profile: dict, resume_path: str):
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        resp = session.get(job_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return False, f"could not load job page: {e}"

    soup = BeautifulSoup(resp.text, "lxml")
    form = soup.find("form", id="application_form") or soup.find("form")
    if not form:
        return False, "no application form found on page"

    action = form.get("action") or job_url

    # Build form data from recognised hidden/text inputs, then overlay our profile
    form_data = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        form_data[name] = inp.get("value", "")

    field_map = {
        "job_application[first_name]": profile.get("full_name", "").split(" ")[0],
        "job_application[last_name]": " ".join(profile.get("full_name", "").split(" ")[1:]),
        "job_application[email]": profile.get("email", ""),
        "job_application[phone]": profile.get("phone", ""),
        "job_application[urls][LinkedIn]": profile.get("linkedin_url", ""),
    }
    for k, v in field_map.items():
        if v:
            form_data[k] = v

    files = {}
    if resume_path:
        files["job_application[resume]"] = open(resume_path, "rb")

    try:
        submit_resp = session.post(action, data=form_data, files=files, headers=headers, timeout=20)
        if files:
            files["job_application[resume]"].close()
        if submit_resp.status_code in (200, 302):
            # Greenhouse returns 200 with a "thank you" fragment on success,
            # or redirects — treat both as success, but flag if error text is present
            if "error" in submit_resp.text.lower()[:2000]:
                return False, "form submitted but page shows validation errors — check manually"
            return True, "submitted"
        return False, f"unexpected status code {submit_resp.status_code}"
    except Exception as e:
        return False, f"submission failed: {e}"
