"""
Given a company name (or an Indeed/Naukri/LinkedIn job listing URL), try to
find the company's careers page and identify which ATS (Applicant Tracking
System) it uses, so the autofill module knows how to submit an application.

Strategy:
1. If the job_url itself is already an ATS URL (boards.greenhouse.io,
   jobs.lever.co, myworkdayjobs.com, etc.) — use it directly.
2. Otherwise, try a DuckDuckGo HTML search for "<company> careers" and take
   the first plausible result. (DuckDuckGo's HTML endpoint doesn't require
   an API key, unlike Google.)
3. Inspect the resulting page for ATS fingerprints.
"""
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

ATS_PATTERNS = {
    "greenhouse": r"boards\.greenhouse\.io|greenhouse\.io/embed",
    "lever": r"jobs\.lever\.co",
    "workday": r"myworkdayjobs\.com",
    "smartrecruiters": r"smartrecruiters\.com",
    "zoho_recruit": r"zohorecruit\.com|recruit\.zoho\.com",
}


def detect_ats_from_url(url: str):
    if not url:
        return None
    for ats, pattern in ATS_PATTERNS.items():
        if re.search(pattern, url):
            return ats
    return None


def find_career_page(company: str, job_url: str = None):
    """Returns (career_page_url, ats_type) best-effort."""
    # 1. Job URL might already be an ATS link
    ats = detect_ats_from_url(job_url)
    if ats:
        return job_url, ats

    # 2. Search DuckDuckGo for "<company> careers"
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": f"{company} careers page"},
            headers=HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "lxml")
        first_link = soup.find("a", class_="result__a")
        if first_link and first_link.get("href"):
            candidate_url = first_link["href"]
            ats = detect_ats_from_url(candidate_url)
            if not ats:
                # fetch the page and check its body for ATS fingerprints
                try:
                    page = requests.get(candidate_url, headers=HEADERS, timeout=15)
                    ats = detect_ats_from_url(page.text)
                except Exception:
                    ats = None
            return candidate_url, ats
    except Exception as e:
        print(f"[career_page] search failed for {company}: {e}")

    return None, None


def extract_email(url: str):
    """Best-effort scrape of a careers/contact page for an HR-looking email."""
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resp.text)
        hr_like = [e for e in emails if any(k in e.lower() for k in ("hr", "career", "job", "recruit", "talent"))]
        return hr_like[0] if hr_like else (emails[0] if emails else None)
    except Exception:
        return None
