"""
Auto-apply to jobs hosted on Lever (jobs.lever.co).
Lever job postings have an /apply URL with a plain HTML form, similar
approach to the Greenhouse module.
"""
import requests
from bs4 import BeautifulSoup


def apply_lever(job_url: str, profile: dict, resume_path: str):
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    apply_url = job_url if job_url.rstrip("/").endswith("/apply") else job_url.rstrip("/") + "/apply"

    try:
        resp = session.get(apply_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return False, f"could not load apply page: {e}"

    soup = BeautifulSoup(resp.text, "lxml")
    form = soup.find("form")
    if not form:
        return False, "no application form found"

    action = form.get("action") or apply_url

    form_data = {
        "name": profile.get("full_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "urls[LinkedIn]": profile.get("linkedin_url", ""),
        "comments": profile.get("cover_letter_template", ""),
    }

    files = {}
    if resume_path:
        files["resume"] = open(resume_path, "rb")

    try:
        submit_resp = session.post(action, data=form_data, files=files, headers=headers, timeout=20)
        if files:
            files["resume"].close()
        if submit_resp.status_code in (200, 302):
            return True, "submitted"
        return False, f"unexpected status code {submit_resp.status_code}"
    except Exception as e:
        return False, f"submission failed: {e}"
