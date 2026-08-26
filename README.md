# JobBot India — Job Search & Auto-Apply

A Flask app that searches Naukri, LinkedIn, and Indeed for jobs (India-focused,
editable city preferences), lets you manually apply or auto-apply, and
auto-detects each company's careers page / ATS so it can submit applications
using your saved profile + resume.

## How auto-apply actually works (read this first)

- **Discovery** (finding jobs) works across Naukri, LinkedIn, and Indeed.
- **Auto-apply** only works reliably where a real ATS form exists:
  - ✅ **Greenhouse** (`boards.greenhouse.io`) — auto-filled directly
  - ✅ **Lever** (`jobs.lever.co`) — auto-filled directly
  - ✅ **Email fallback** — if no ATS is detected but an HR/careers email is
    found on the company's site, the bot emails your resume + cover letter
  - ⚠️ **Workday, SmartRecruiters, and custom company ATSes** are detected
    but not auto-filled in this version (they're JS-heavy and need a real
    browser — see "Extending" below). These jobs land in the "failed" tab
    with a note so you can apply manually.
- LinkedIn and Naukri **do not allow automated applications** in their Terms
  of Service — this app never attempts to auto-apply on those platforms
  directly. It only uses them to *find* jobs, then applies through the
  employer's own ATS or email.

## Setup on Replit

1. Create a new Replit → Python template (or import this folder as a GitHub repo).
2. Upload all these files, preserving the folder structure (`scrapers/`, `autofill/`, `templates/`, `static/`).
3. Replit auto-installs from `requirements.txt` on first run — if not, run:
   ```
   pip install -r requirements.txt
   ```
4. Set Secrets (padlock icon in Replit sidebar) if you want email auto-apply:
   - `SMTP_USER` — your Gmail address
   - `SMTP_PASS` — a Gmail **App Password** (myaccount.google.com/apppasswords), not your normal password
   - `SMTP_HOST` / `SMTP_PORT` — optional, defaults to Gmail
5. Click **Run**. Open the webview URL.
6. Go to **Profile & Data** first — fill in your details and upload your resume PDF.
7. Go to **Dashboard** → enter keywords/cities → **Search Now**.
8. Review jobs, click **Apply** individually, or **Run Auto-Apply on All New Jobs**.
9. Check the **Applied Report** tab anytime to see what's been submitted, by what method, and any failures needing manual follow-up.

## Hosting on a free tier after building

Replit's free "Always On" is limited, so for a bot that should keep running:
- **Render.com free web service** — connect your GitHub repo, set the same environment secrets, use `gunicorn app:app` as the start command (add `gunicorn` to requirements.txt).
- **Fly.io free allowance** — good for small always-on apps via a Dockerfile.
- **PythonAnywhere free tier** — easiest for a Flask app with SQLite, no Docker needed.
- Note: free tiers usually **sleep on inactivity**. For a background auto-apply job to run daily as a real "bot" rather than only when you click the button, add a scheduler (see below) plus an uptime pinger (e.g. UptimeRobot free) hitting your `/` route every few minutes to keep it awake — or move the scheduled job to a GitHub Actions cron workflow that calls your `/auto_apply` endpoint on a schedule instead of relying on the web dyno staying awake.

## Extending

- **Workday/other ATS auto-fill**: these render forms via JavaScript, so plain `requests` won't work — you'd add a Selenium-based module (`pip install selenium webdriver-manager`) that opens a headless Chrome, fills fields, and submits. Heavier on Replit's free CPU/RAM, so test carefully.
- **Scheduled auto-search**: add `APScheduler` (already in requirements.txt) to run `search()` and `auto_apply()` on a timer inside `app.py`, e.g. every morning.
- **Better career-page detection**: the DuckDuckGo-based guesser is best-effort; for higher accuracy, plug in a real search API (e.g. SerpAPI, Bing Web Search) if you're willing to use a paid/limited-free key.
- **Selectors breaking**: Naukri/Indeed/LinkedIn HTML changes periodically. If searches return 0 results, open the site in a browser, inspect a job card element, and update the class names in the relevant file under `scrapers/`.

## Legal/ethical note

Auto-filling applications on a company's own careers page with your own,
truthful information is standard practice (many legitimate tools do this).
Automating actions on LinkedIn/Naukri themselves (beyond reading public
search results) risks account suspension under their ToS — this app
deliberately avoids that.
