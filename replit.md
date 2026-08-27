# JobBot India

Flask app for finding India-focused jobs and tracking manual or supported
auto-apply attempts through employer career pages.

## Run & Operate

- Run with `python3 app.py`.
- The Replit workflow `JobBot India` serves the app on port 5000.
- Python dependencies are declared in `requirements.txt`.
- The app creates its local SQLite database (`jobbot.db`) and `uploads/`
  directory on first start.
- Optional email auto-apply configuration uses the `SMTP_USER`,
  `SMTP_PASS`, `SMTP_HOST`, and `SMTP_PORT` environment variables. Do not
  commit these values.

## Stack

- Python 3.12
- Flask 3
- Flask-SQLAlchemy with SQLite
- Requests, BeautifulSoup, and lxml for job discovery
- APScheduler for daily profile-driven automation

## Where things live

- `app.py` — Flask routes, persistence, scheduler, and orchestration
- `models.py` — SQLAlchemy models for the profile and jobs
- `scrapers/` — Naukri, LinkedIn, Indeed, and career-page discovery
- `autofill/` — Greenhouse, Lever, and email application handlers
- `templates/` — dashboard, profile, and report pages
- `static/style.css` — application styling
- `uploads/` — local resume uploads

## Architecture decisions

- SQLite is used for the local Replit app, keeping setup self-contained.
- Job discovery sources are used for finding listings; direct automated
  applications are routed through employer ATS pages or email instead of
  applying on LinkedIn or Naukri.
- The scheduler runs once daily at 09:00 in the `Asia/Kolkata` timezone.

## Product

- Search jobs by comma-separated keywords and cities.
- Review new jobs and open original listings.
- Save a profile and resume for supported application flows.
- Track applied, failed, and manually reviewable applications.

## User preferences

_No project-specific preferences recorded._

## Gotchas

- Fill in `Profile & Data` before searching or using auto-apply.
- Search pages may change their HTML structure, so scrapers can require
  selector updates when an upstream site changes.
- Workday, SmartRecruiters, and other JavaScript-heavy ATS forms are detected
  but require manual application in this version.

## Pointers

- See `README.md` for the supported auto-apply methods and legal/ethical
  boundaries.
