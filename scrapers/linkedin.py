"""
LinkedIn scraper — discovery only. Uses LinkedIn's public "guest" jobs
search endpoint, which returns an HTML fragment without needing login.
LinkedIn rate-limits this fairly aggressively and explicitly disallows
automated access in its Terms of Service — keep volume low (this app only
uses it for search/discovery, never for automated "Easy Apply").
"""
import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def search_linkedin(keyword: str, city: str, start: int = 0):
    params = {
        "keywords": keyword,
        "location": f"{city}, India",
        "start": start,
    }
    results = []
    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[linkedin] request failed: {e}")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.find_all("li")
    for card in cards:
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("span", class_="job-search-card__location")
        link_el = card.find("a", class_="base-card__full-link")
        if not title_el or not company_el:
            continue
        results.append({
            "title": title_el.get_text(strip=True),
            "company": company_el.get_text(strip=True),
            "location": location_el.get_text(strip=True) if location_el else city,
            "job_url": link_el["href"].split("?")[0] if link_el else None,
            "source": "linkedin",
        })
    return results
