"""
Naukri.com scraper — discovery only (no auto-apply here).
Uses Naukri's public search JSON endpoint. Naukri changes this occasionally;
if it stops returning results, check browser devtools > Network tab on
naukri.com search results page for the current endpoint/headers.
"""
import requests

SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "appid": "109",
    "systemid": "Naukri",
    "Accept": "application/json",
}


def search_naukri(keyword: str, city: str, pages: int = 1):
    """Returns a list of dicts: title, company, location, job_url."""
    results = []
    for page in range(1, pages + 1):
        params = {
            "noOfResults": 20,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": keyword,
            "location": city,
            "pageNo": page,
        }
        try:
            resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[naukri] request failed: {e}")
            continue

        for job in data.get("jobDetails", []):
            results.append({
                "title": job.get("title"),
                "company": job.get("companyName"),
                "location": job.get("placeholders", [{}])[0].get("label", city) if job.get("placeholders") else city,
                "job_url": "https://www.naukri.com/job-listings-" + job.get("jdURL", "").lstrip("/") if job.get("jdURL") else None,
                "source": "naukri",
            })
    return results
