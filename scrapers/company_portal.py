"""
Company Portal search — pulls open roles directly from a company's own
careers page, rather than from aggregators.

Greenhouse and Lever expose public JSON APIs per company. Other ATSes use a
best-effort HTML scrape of the supplied careers page.
"""
import re

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_greenhouse_jobs(board_token: str):
    """Fetch Greenhouse jobs for a board slug such as ``stripe``."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"[company_portal] greenhouse fetch failed for {board_token}: {exc}")
        return []

    return [
        {
            "title": job.get("title"),
            "company": board_token,
            "location": (job.get("location") or {}).get("name", ""),
            "job_url": job.get("absolute_url"),
            "source": "company_portal",
            "ats_type": "greenhouse",
            "raw_content": job.get("content", ""),
        }
        for job in data.get("jobs", [])
    ]


def fetch_lever_jobs(site_slug: str):
    """Fetch Lever jobs for a site slug such as ``netflix``."""
    url = f"https://api.lever.co/v0/postings/{site_slug}?mode=json"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"[company_portal] lever fetch failed for {site_slug}: {exc}")
        return []

    return [
        {
            "title": job.get("text"),
            "company": site_slug,
            "location": (job.get("categories") or {}).get("location", ""),
            "job_url": job.get("hostedUrl"),
            "source": "company_portal",
            "ats_type": "lever",
            "raw_content": job.get("descriptionPlain", ""),
        }
        for job in data
    ]


def fetch_generic_career_page_jobs(career_url: str, company_name: str):
    """Best-effort extraction of likely job links from a careers page."""
    try:
        response = requests.get(career_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        print(f"[company_portal] generic fetch failed for {career_url}: {exc}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        href = anchor["href"]
        if len(text) < 6 or len(text) > 120:
            continue
        if not re.search(r"job|career|position|req|opening", href, re.I) and not re.search(
            r"engineer|manager|analyst|associate|lead|executive|officer|consultant|specialist",
            text,
            re.I,
        ):
            continue
        full_url = (
            href if href.startswith("http") else requests.compat.urljoin(career_url, href)
        )
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        jobs.append(
            {
                "title": text,
                "company": company_name,
                "location": "",
                "job_url": full_url,
                "source": "company_portal",
                "ats_type": "unknown",
                "raw_content": "",
            }
        )
    return jobs[:30]


def parse_experience_range(text: str):
    """Extract a best-effort experience range in years from job text."""
    if not text:
        return None, None
    text = text.lower()

    match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*\+?\s*(?:years|yrs)", text)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = re.search(r"(\d+)\s*\+\s*(?:years|yrs)", text)
    if match:
        return float(match.group(1)), None

    match = re.search(r"minimum\s*(?:of\s*)?(\d+)\s*(?:years|yrs)", text)
    if match:
        return float(match.group(1)), None

    return None, None