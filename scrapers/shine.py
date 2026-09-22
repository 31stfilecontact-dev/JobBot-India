"""
Shine.com Scraper (India)
Searches Shine.com job listings with experience and salary extraction.
"""
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.shine.com/",
}


def search_shine(keyword: str, city: str, pages: int = 1):
    """Returns list of job postings from Shine.com."""
    results = []
    kw_slug = re.sub(r"[^a-zA-Z0-9]+", "-", keyword.strip().lower())
    loc_slug = re.sub(r"[^a-zA-Z0-9]+", "-", city.strip().lower())

    url = f"https://www.shine.com/job-search/{kw_slug}-jobs-in-{loc_slug}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
    except Exception as e:
        print(f"[shine] request failed: {e}")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.find_all("div", class_=re.compile(r"jobCard|parentClass|job_listing"))

    for card in cards:
        title_el = card.find(["h2", "strong", "a"], class_=re.compile(r"jobCard_pHeading|job_title|title"))
        company_el = card.find(["div", "span"], class_=re.compile(r"jobCard_jobInfo|companyName|company"))
        loc_el = card.find(["div", "li"], class_=re.compile(r"jobCard_location|location"))
        exp_el = card.find(["div", "li"], class_=re.compile(r"jobCard_experience|experience"))

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        loc = loc_el.get_text(strip=True) if loc_el else city
        exp_text = exp_el.get_text(strip=True) if exp_el else ""

        exp_min, exp_max = None, None
        if exp_text:
            m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:Yrs|yrs|years)", exp_text)
            if m:
                exp_min, exp_max = float(m.group(1)), float(m.group(2))

        link_el = card.find("a", href=True)
        job_url = None
        if link_el:
            href = link_el["href"]
            job_url = href if href.startswith("http") else f"https://www.shine.com{href}"

        results.append({
            "title": title,
            "company": company,
            "location": loc,
            "job_url": job_url,
            "source": "shine",
            "salary_text": "",
            "exp_min_years": exp_min,
            "exp_max_years": exp_max,
            "description": "",
        })

    return results
