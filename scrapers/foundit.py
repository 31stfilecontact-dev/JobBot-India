"""
Foundit.in (formerly Monster India) Scraper
Searches Foundit India public job endpoints and pages.
"""
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.foundit.in/",
}


def search_foundit(keyword: str, city: str, pages: int = 1):
    """Returns list of job postings from Foundit India."""
    results = []
    location_query = city if city.lower() != "remote" else ""
    query = f"{keyword} {location_query}".strip()
    encoded = urllib.parse.quote_plus(query)

    url = f"https://www.foundit.in/srp/results?query={encoded}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
    except Exception as e:
        print(f"[foundit] request failed: {e}")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.find_all("div", class_=re.compile(r"srpResultCardContainer|cardContainer|jobCard"))
    if not cards:
        cards = soup.find_all("div", class_=re.compile(r"card"))

    for card in cards:
        title_el = card.find(["div", "h3", "a"], class_=re.compile(r"cardTitle|jobTitle|header"))
        company_el = card.find(["div", "span", "a"], class_=re.compile(r"companyName|company"))
        loc_el = card.find(["div", "span"], class_=re.compile(r"location|details"))
        exp_el = card.find(["div", "span"], class_=re.compile(r"experience|exp"))
        salary_el = card.find(["div", "span"], class_=re.compile(r"salary"))

        if not title_el or not company_el:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True)
        loc = loc_el.get_text(strip=True) if loc_el else city
        salary = salary_el.get_text(strip=True) if salary_el else ""
        exp_text = exp_el.get_text(strip=True) if exp_el else ""

        exp_min, exp_max = None, None
        if exp_text:
            m = re.search(r"(\d+)\s*-\s*(\d+)", exp_text)
            if m:
                exp_min, exp_max = float(m.group(1)), float(m.group(2))

        link_el = card.find("a", href=True)
        job_url = None
        if link_el:
            href = link_el["href"]
            job_url = href if href.startswith("http") else f"https://www.foundit.in{href}"

        results.append({
            "title": title,
            "company": company,
            "location": loc,
            "job_url": job_url,
            "source": "foundit",
            "salary_text": salary,
            "exp_min_years": exp_min,
            "exp_max_years": exp_max,
            "description": "",
        })

    return results
