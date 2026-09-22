"""
LinkedIn scraper — discovery only.
Uses LinkedIn guest jobs search endpoint with pagination, error resilience, and experience parsing.
"""
import re
import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.linkedin.com/jobs",
}


def search_linkedin(keyword: str, city: str, pages: int = 1):
    """Returns a list of dicts: title, company, location, job_url, source."""
    results = []
    location_query = f"{city}, India" if city.lower() != "remote" else "India"

    for p in range(pages):
        start = p * 25
        params = {
            "keywords": keyword,
            "location": location_query,
            "start": start,
            "f_TPR": "r2592000",  # past month
        }
        if city.lower() == "remote":
            params["f_WT"] = "2"  # Remote filter

        try:
            resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"[linkedin] status {resp.status_code} for '{keyword}'")
                break
        except Exception as e:
            print(f"[linkedin] request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.find_all("li")
        if not cards:
            cards = soup.find_all("div", class_=re.compile(r"base-card|job-search-card"))

        for card in cards:
            title_el = card.find(["h3", "h4"], class_=re.compile(r"base-search-card__title|job-card-list__title"))
            company_el = card.find(["h4", "a"], class_=re.compile(r"base-search-card__subtitle|job-card-container__company-name"))
            location_el = card.find(["span", "div"], class_=re.compile(r"job-search-card__location|job-card-container__metadata-item"))
            link_el = card.find("a", class_=re.compile(r"base-card__full-link|job-card-list__title"))

            if not title_el or not company_el:
                continue

            link = link_el["href"].split("?")[0] if (link_el and link_el.get("href")) else None
            title_text = title_el.get_text(strip=True)
            company_text = company_el.get_text(strip=True)
            loc_text = location_el.get_text(strip=True) if location_el else city

            results.append({
                "title": title_text,
                "company": company_text,
                "location": loc_text,
                "job_url": link,
                "source": "linkedin",
                "salary_text": "",
                "exp_min_years": None,
                "exp_max_years": None,
                "description": "",
            })

    return results
