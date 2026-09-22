"""
Given a company name (or a job listing URL), detect or search the company's careers page
and identify which ATS (Applicant Tracking System) it uses.

Supported ATS fingerprints:
- Greenhouse (boards.greenhouse.io, greenhouse.io/embed)
- Lever (jobs.lever.co)
- Workday (myworkdayjobs.com)
- SmartRecruiters (smartrecruiters.com, jobs.smartrecruiters.com)
- Ashby (jobs.ashbyhq.com, ashbyhq.com)
- Taleo (taleo.net)
- Zoho Recruit (zohorecruit.com, recruit.zoho.com)
"""
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

ATS_PATTERNS = {
    "greenhouse": r"boards\.greenhouse\.io|greenhouse\.io/embed|gh_jid=",
    "lever": r"jobs\.lever\.co",
    "workday": r"myworkdayjobs\.com|wd3\.myworkday\.com|wd5\.myworkday\.com",
    "smartrecruiters": r"smartrecruiters\.com|jobs\.smartrecruiters\.com",
    "ashby": r"jobs\.ashbyhq\.com|ashbyhq\.com",
    "zoho_recruit": r"zohorecruit\.com|recruit\.zoho\.com",
    "taleo": r"taleo\.net",
}


def detect_ats_from_url(url: str):
    """Detect ATS type from URL string or return None."""
    if not url:
        return None
    for ats, pattern in ATS_PATTERNS.items():
        if re.search(pattern, url, re.IGNORECASE):
            return ats
    return None


def detect_ats_from_html(html_text: str):
    """Detect ATS from embedded scripts, iframes, or signatures in HTML."""
    if not html_text:
        return None
    for ats, pattern in ATS_PATTERNS.items():
        if re.search(pattern, html_text, re.IGNORECASE):
            return ats
    return None


def find_career_page(company: str, job_url: str = None):
    """
    Returns (career_page_url, ats_type) best-effort.
    1. Checks if job_url itself is already an ATS link.
    2. Searches for <company> careers page on DuckDuckGo and Google fallback.
    """
    if job_url:
        ats = detect_ats_from_url(job_url)
        if ats:
            return job_url, ats

    # Search DuckDuckGo HTML endpoint
    search_queries = [
        f"{company} careers jobs",
        f"{company} apply job",
    ]

    for q in search_queries:
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": q},
                headers=HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                links = soup.find_all("a", class_="result__a")
                for link in links:
                    candidate_url = link.get("href")
                    if not candidate_url or "duckduckgo.com" in candidate_url:
                        continue

                    # Unquote DuckDuckGo redirect if needed
                    if "uddg=" in candidate_url:
                        m = re.search(r"uddg=([^&]+)", candidate_url)
                        if m:
                            candidate_url = urllib.parse.unquote(m.group(1))

                    ats = detect_ats_from_url(candidate_url)
                    if ats:
                        return candidate_url, ats

                    # If not obvious from URL, fetch page to inspect body
                    try:
                        page = requests.get(candidate_url, headers=HEADERS, timeout=8)
                        ats = detect_ats_from_html(page.text)
                        if ats:
                            return candidate_url, ats
                        return candidate_url, "generic"
                    except Exception:
                        pass
        except Exception as e:
            print(f"[career_page] search error for {company}: {e}")

    return job_url, "unknown"


def extract_email(url: str):
    """Scrape a careers/contact page for an HR/careers email."""
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resp.text)
        # Filter out common false positives
        valid_emails = [
            e for e in emails 
            if not e.endswith((".png", ".jpg", ".svg", ".webp"))
            and "example.com" not in e 
            and "w3.org" not in e
            and "sentry" not in e
        ]
        hr_like = [e for e in valid_emails if any(k in e.lower() for k in ("hr", "career", "job", "recruit", "talent", "hiring", "india"))]
        return hr_like[0] if hr_like else (valid_emails[0] if valid_emails else None)
    except Exception:
        return None
