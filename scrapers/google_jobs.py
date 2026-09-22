"""
Google Jobs Scraper (India)
Queries Google Search / Google Jobs public index for matching postings.
"""
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def search_google_jobs(keyword: str, city: str, pages: int = 1):
    """
    Search Google for job postings matching the query in the given Indian city.
    Returns structured job listings.
    """
    results = []
    location_str = f"{city} India" if city.lower() != "remote" else "Remote India"
    query = f"{keyword} jobs {location_str}"
    
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}&ibp=htl;jobs"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
    except Exception as e:
        print(f"[google_jobs] request failed: {e}")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    
    # Extract job cards from Google Jobs structured widgets
    job_cards = soup.find_all("li", class_=re.compile(r"smnx|PwjeAc|iFjolb"))
    if not job_cards:
        job_cards = soup.find_all("div", attrs={"data-share-url": True}) or soup.find_all("div", class_=re.compile(r"g|card|MjjYud"))

    for card in job_cards:
        title_el = card.find(["div", "h2", "h3"], class_=re.compile(r"BjN20e|title|header|LC20lb"))
        company_el = card.find(["div", "span"], class_=re.compile(r"vNEEBe|company|sub-title"))
        loc_el = card.find(["div", "span"], class_=re.compile(r"Qk80nd|location"))
        
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        loc = loc_el.get_text(strip=True) if loc_el else city

        # Link extraction
        link_el = card.find("a", href=True)
        job_url = None
        if link_el:
            href = link_el["href"]
            if href.startswith("http"):
                job_url = href
            elif href.startswith("/url?q="):
                job_url = href.split("/url?q=")[1].split("&")[0]

        if not job_url:
            job_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(f'{company} {title} careers')}"

        results.append({
            "title": title,
            "company": company,
            "location": loc,
            "job_url": job_url,
            "source": "google_jobs",
            "salary_text": "",
            "exp_min_years": None,
            "exp_max_years": None,
            "description": "",
        })

    return results
