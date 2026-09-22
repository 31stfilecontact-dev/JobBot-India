"""
Auto-apply to jobs hosted on Greenhouse (boards.greenhouse.io).
Supports direct HTTP multipart form submission with automatic Playwright browser fallback for JS-heavy boards.
"""
import requests
from bs4 import BeautifulSoup
from autofill.browser_engine import run_playwright_apply


def apply_greenhouse(job_url: str, profile: dict, resume_path: str, dry_run: bool = False, job_context: dict = None):
    """
    Apply to a Greenhouse job board.
    Returns: (success: bool, note: str, screenshot_file: str)
    """
    job_context = job_context or {}

    if dry_run:
        return run_playwright_apply(job_url, profile, resume_path, "greenhouse", dry_run=True, job_context=job_context)

    # First attempt: Fast direct HTTP form submission
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

    try:
        resp = session.get(job_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            form = soup.find("form", id="application_form") or soup.find("form")
            if form:
                action = form.get("action") or job_url
                if not action.startswith("http"):
                    action = requests.compat.urljoin(job_url, action)

                form_data = {}
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        form_data[name] = inp.get("value", "")

                full_name = profile.get("full_name", "")
                fname = full_name.split()[0] if full_name else ""
                lname = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else full_name

                field_map = {
                    "job_application[first_name]": fname,
                    "job_application[last_name]": lname,
                    "job_application[email]": profile.get("email", ""),
                    "job_application[phone]": profile.get("phone", ""),
                    "job_application[urls][LinkedIn]": profile.get("linkedin_url", ""),
                }
                for k, v in field_map.items():
                    if v:
                        form_data[k] = v

                files = {}
                if resume_path and os.path.exists(resume_path):
                    files["job_application[resume]"] = open(resume_path, "rb")

                try:
                    submit_resp = session.post(action, data=form_data, files=files, headers=headers, timeout=20)
                    if files:
                        files["job_application[resume]"].close()
                    if submit_resp.status_code in (200, 302) and "error" not in submit_resp.text.lower()[:1500]:
                        return True, "Application submitted directly via Greenhouse API.", ""
                except Exception:
                    if files and "job_application[resume]" in files and not files["job_application[resume]"].closed:
                        files["job_application[resume]"].close()
    except Exception:
        pass

    # Fallback to Playwright automation if direct HTTP encountered custom questions/JS
    return run_playwright_apply(job_url, profile, resume_path, "greenhouse", dry_run=False, job_context=job_context)
