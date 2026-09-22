"""
Cutshort.io Scraper
Searches Cutshort tech & startup job listings in India.
"""
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def search_cutshort(keyword: str, city: str, pages: int = 1):
    """Returns list of job postings from Cutshort."""
    results = []
    kw_encoded = urllib.parse.quote_plus(keyword)
    loc_encoded = urllib.parse.quote_plus(city)
    url = f"https://cutshort.io/jobs?search={kw_encoded}&locations={loc_encoded}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
    except Exception as e:
        print(f"[cutshort] request failed: {e}")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.find_all("div", class_=re.compile(r"job-card|JobCard|sc-"))
    if not cards:
        cards = soup.find_all("a", href=re.compile(r"/job/"))

    for card in cards:
        if card.name == "a" and "/job/" in card.get("href", ""):
            title_text = card.get_text(strip=True)
            href = card["href"]
            job_url = href if href.startswith("http") else f"https://cutshort.io{href}"
            results.append({
                "title": title_text,
                "company": "Tech Company (Cutshort)",
                "location": city,
                "job_url": job_url,
                "source": "cutshort",
                "salary_text": "",
                "exp_min_years": None,
                "exp_max_years": None,
                "description": "",
            })
            continue

        title_el = card.find(["h2", "h3", "div"], class_=re.compile(r"title|heading"))
        company_el = card.find(["div", "span"], class_=re.compile(r"company|company-name"))
        link_el = card.find("a", href=True)

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else "Startup"
        job_url = None
        if link_el:
            href = link_el["href"]
            job_url = href if href.startswith("http") else f"https://cutshort.io{href}"

        results.append({
            "title": title,
            "company": company,
            "location": city,
            "job_url": job_url,
            "source": "cutshort",
            "salary_text": "",
            "exp_min_years": None,
            "exp_max_years": None,
            "description": "",
        })

    return results
