"""
Naukri.com scraper — discovery only.
Uses enhanced browser-like headers, multi-page retrieval, salary, and experience parsing.
"""
import re
import requests

SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "appid": "109",
    "systemid": "Naukri",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.naukri.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def search_naukri(keyword: str, city: str, pages: int = 1):
    """Returns a list of dicts: title, company, location, job_url, salary_text, exp_min_years, exp_max_years."""
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
            if resp.status_code != 200:
                print(f"[naukri] non-200 response ({resp.status_code}) for '{keyword}' in '{city}'")
                break
            data = resp.json()
        except Exception as e:
            print(f"[naukri] request failed for page {page}: {e}")
            break

        jobs_list = data.get("jobDetails") or data.get("jobs") or []
        for job in jobs_list:
            title = job.get("title")
            company = job.get("companyName")
            if not title or not company:
                continue

            placeholders = job.get("placeholders", [])
            loc_label = city
            exp_text = ""
            salary_text = ""

            for ph in placeholders:
                ph_type = ph.get("type", "")
                if ph_type == "location":
                    loc_label = ph.get("label", city)
                elif ph_type == "experience":
                    exp_text = ph.get("label", "")
                elif ph_type == "salary":
                    salary_text = ph.get("label", "")

            exp_min, exp_max = None, None
            if exp_text:
                m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:Yrs|yrs|years)", exp_text)
                if m:
                    exp_min, exp_max = float(m.group(1)), float(m.group(2))
                else:
                    m1 = re.search(r"(\d+)\+?\s*(?:Yrs|yrs|years)", exp_text)
                    if m1:
                        exp_min = float(m1.group(1))

            jd_url = job.get("jdURL", "").lstrip("/")
            job_url = f"https://www.naukri.com/job-listings-{jd_url}" if jd_url else None
            if not job_url and job.get("jobId"):
                job_url = f"https://www.naukri.com/job-listings-{job.get('jobId')}"

            results.append({
                "title": title.strip(),
                "company": company.strip(),
                "location": loc_label.strip(),
                "job_url": job_url,
                "source": "naukri",
                "salary_text": salary_text,
                "exp_min_years": exp_min,
                "exp_max_years": exp_max,
                "description": job.get("jobDescription", ""),
            })

    return results
