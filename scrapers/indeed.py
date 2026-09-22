"""
Indeed India scraper — discovery only.
Uses server-rendered search results with fallback selectors, salary, and experience parsing.
"""
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://in.indeed.com/jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://in.indeed.com/",
}


def search_indeed(keyword: str, city: str, pages: int = 1):
    """Returns a list of dicts: title, company, location, job_url, salary_text, exp_min_years, exp_max_years."""
    results = []
    location_query = f"{city}, India" if city.lower() != "remote" else "Remote"

    for p in range(pages):
        start = p * 10
        params = {"q": keyword, "l": location_query, "start": start}
        try:
            resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"[indeed] status {resp.status_code} for '{keyword}'")
                break
        except Exception as e:
            print(f"[indeed] request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|jobCard|result"))
        if not cards:
            cards = soup.find_all("div", attrs={"data-jk": True})

        for card in cards:
            job_key = card.get("data-jk")
            title_el = card.find(["h2", "a"], class_=re.compile(r"jobTitle|jcs-JobTitle"))
            company_el = card.find(["span", "div"], class_=re.compile(r"companyName|css-1h7ux9g|company_location"))
            location_el = card.find(["div", "span"], class_=re.compile(r"companyLocation|locationsContainer"))
            salary_el = card.find(["div", "span"], class_=re.compile(r"salary-snippet|salaryOnly|metadata"))

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else city
            salary_text = salary_el.get_text(strip=True) if salary_el else ""

            if not job_key:
                link = card.find("a", href=True)
                if link and "/rc/clk" in link["href"] or "/viewjob" in link.get("href", ""):
                    m = re.search(r"jk=([a-f0-9]+)", link["href"])
                    if m:
                        job_key = m.group(1)

            job_url = f"https://in.indeed.com/viewjob?jk={job_key}" if job_key else None

            results.append({
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "source": "indeed",
                "salary_text": salary_text,
                "exp_min_years": None,
                "exp_max_years": None,
                "description": "",
            })

    return results
