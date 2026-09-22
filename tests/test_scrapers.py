"""
Unit tests for Job Discovery Scrapers.
Tests payload handling, response parsing, salary & experience parsing using mocked responses.
"""
from unittest.mock import patch, MagicMock
from scrapers.naukri import search_naukri
from scrapers.linkedin import search_linkedin
from scrapers.indeed import search_indeed
from scrapers.google_jobs import search_google_jobs
from scrapers.foundit import search_foundit
from scrapers.shine import search_shine
from scrapers.career_page import detect_ats_from_url, extract_email
from scrapers.company_portal import fetch_greenhouse_jobs, fetch_lever_jobs, fetch_ashby_jobs, parse_experience_range


def test_detect_ats_from_url():
    assert detect_ats_from_url("https://boards.greenhouse.io/stripe/jobs/12345") == "greenhouse"
    assert detect_ats_from_url("https://jobs.lever.co/netflix/67890") == "lever"
    assert detect_ats_from_url("https://company.myworkdayjobs.com/careers/job/123") == "workday"
    assert detect_ats_from_url("https://jobs.smartrecruiters.com/org/456") == "smartrecruiters"
    assert detect_ats_from_url("https://jobs.ashbyhq.com/openai/789") == "ashby"
    assert detect_ats_from_url("https://example.com/about") is None


def test_parse_experience_range():
    min_exp, max_exp = parse_experience_range("Requires 3 - 5 years of Python experience.")
    assert min_exp == 3.0
    assert max_exp == 5.0

    min_exp, max_exp = parse_experience_range("Minimum 5+ yrs in distributed systems.")
    assert min_exp == 5.0
    assert max_exp is None


@patch("requests.get")
def test_search_naukri_mocked(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobDetails": [
            {
                "title": "Senior Python Developer",
                "companyName": "TechCorp India",
                "placeholders": [
                    {"type": "location", "label": "Bengaluru"},
                    {"type": "experience", "label": "3-7 Yrs"},
                    {"type": "salary", "label": "15-25 Lacs PA"},
                ],
                "jdURL": "senior-python-dev-12345",
                "jobDescription": "Looking for senior python engineer...",
            }
        ]
    }
    mock_get.return_value = mock_resp

    results = search_naukri("Python Developer", "Bengaluru", pages=1)
    assert len(results) == 1
    assert results[0]["title"] == "Senior Python Developer"
    assert results[0]["company"] == "TechCorp India"
    assert results[0]["location"] == "Bengaluru"
    assert results[0]["exp_min_years"] == 3.0
    assert results[0]["exp_max_years"] == 7.0
    assert "naukri.com" in results[0]["job_url"]


@patch("requests.get")
def test_search_linkedin_mocked(mock_get):
    html_sample = """
    <ul>
        <li>
            <div class="base-search-card">
                <h3 class="base-search-card__title">Backend Lead</h3>
                <h4 class="base-search-card__subtitle">Startup India</h4>
                <span class="job-search-card__location">Hyderabad, Telangana</span>
                <a class="base-card__full-link" href="https://in.linkedin.com/jobs/view/999999?refId=123"></a>
            </div>
        </li>
    </ul>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_sample
    mock_get.return_value = mock_resp

    results = search_linkedin("Backend Lead", "Hyderabad", pages=1)
    assert len(results) == 1
    assert results[0]["title"] == "Backend Lead"
    assert results[0]["company"] == "Startup India"
    assert "https://in.linkedin.com/jobs/view/999999" in results[0]["job_url"]


@patch("requests.get")
def test_search_indeed_mocked(mock_get):
    html_sample = """
    <div>
        <div class="job_seen_beacon" data-jk="indeed123">
            <h2 class="jobTitle">Full Stack Engineer</h2>
            <span class="companyName">Innovate Ltd</span>
            <div class="companyLocation">Pune, Maharashtra</div>
            <div class="salary-snippet">₹12,00,000 - ₹18,00,000 a year</div>
        </div>
    </div>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_sample
    mock_get.return_value = mock_resp

    results = search_indeed("Full Stack", "Pune", pages=1)
    assert len(results) == 1
    assert results[0]["title"] == "Full Stack Engineer"
    assert results[0]["company"] == "Innovate Ltd"
    assert "indeed.com/viewjob?jk=indeed123" in results[0]["job_url"]


@patch("requests.get")
def test_fetch_ashby_jobs_mocked(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Founding Engineer",
                "location": "Remote, India",
                "jobUrl": "https://jobs.ashbyhq.com/myco/abc-123",
                "descriptionHtml": "<p>Minimum 4 years experience required.</p>",
            }
        ]
    }
    mock_get.return_value = mock_resp

    results = fetch_ashby_jobs("myco")
    assert len(results) == 1
    assert results[0]["title"] == "Founding Engineer"
    assert results[0]["ats_type"] == "ashby"
