"""
Indeed India scraper — discovery only. Indeed serves mostly server-rendered
HTML for the base search page. Selectors below are current as of writing
but Indeed changes markup periodically — if results come back empty, open
indeed.co.in search results in a browser, inspect a job card, and update
the class names here.
"""
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://in.indeed.com/jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def search_indeed(keyword: str, city: str, start: int = 0):
    params = {"q": keyword, "l": city, "start": start}
    results = []
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[indeed] request failed: {e}")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.find_all("div", class_="job_seen_beacon")
    for card in cards:
        title_el = card.find("h2", class_="jobTitle")
        company_el = card.find("span", class_="companyName")
        location_el = card.find("div", class_="companyLocation")
        link_el = card.find("a", href=True)
        if not title_el:
            continue
        job_key = card.get("data-jk")
        results.append({
            "title": title_el.get_text(strip=True),
            "company": company_el.get_text(strip=True) if company_el else "Unknown",
            "location": location_el.get_text(strip=True) if location_el else city,
            "job_url": f"https://in.indeed.com/viewjob?jk={job_key}" if job_key else None,
            "source": "indeed",
        })
    return results
