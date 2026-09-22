# JobBot India — Automated Job Discovery & Auto-Apply Suite

An intelligent Flask application tailored for the Indian job market that discovers jobs across top job portals and direct company ATS feeds, automatically parses requirements, and submits applications using your saved candidate profile, resume PDF, and Playwright-powered browser automation.

---

## 🚀 Key Features

### 1. Multi-Portal Job Discovery Engine
- **Aggregators & Major Portals**:
  - 🔍 **Naukri.com** — JSON API integration with experience & salary parsing.
  - 💼 **LinkedIn** — Multi-page guest job search with location & remote filtering.
  - 📌 **Indeed India** — Server-rendered job cards with salary snippet extraction.
  - 🌐 **Google Jobs** — Direct index search for Indian roles.
  - 🏢 **Foundit (Monster India)** & **Shine.com** — Broad general career portal indexing.
  - ⚡ **Cutshort & Instahyre** — Curated Indian tech and startup job feeds.
- **Direct ATS Career Portals**:
  - Live indexing from company boards on **Greenhouse**, **Lever**, and **Ashby** APIs.

### 2. Intelligent Auto-Apply Engine
- **Supported ATS Platforms**:
  - ✅ **Greenhouse** (`boards.greenhouse.io`) — Direct API + Playwright browser fallback.
  - ✅ **Lever** (`jobs.lever.co`) — Direct API + Playwright browser fallback.
  - ✅ **Workday** (`myworkdayjobs.com`) — Headless browser multi-step form interaction.
  - ✅ **SmartRecruiters** (`smartrecruiters.com`) — Browser form-filling.
  - ✅ **Ashby** (`jobs.ashbyhq.com`) — Automated field mapping & submission.
  - ✉️ **Email Fallback** — Sends tailored application email + attached resume PDF via SMTP when HR contact is found.
- **AI & Heuristic Question Resolver**:
  - Automatically answers screening questions (CTC, notice period, work authorization, location, diversity, why join us).
  - Custom Screening Q&A dictionary on the Profile page to store exact responses for custom company questions.

### 3. Safety Guardrails & Audit Trail
- 🧪 **Dry-Run Mode**: Test applications without submitting. Captures timestamped full-page screenshots stored under `artifacts/screenshots/`.
- 📋 **Audit Trail**: Detailed log of every apply attempt (live vs dry-run, method, status, error diagnostics, and screenshot artifacts).

---

## ☁️ 100% Free Cloud Hosting & Automation

For complete step-by-step instructions on deploying the Web UI to **Render.com** and setting up the **Daily 9:00 AM IST Automated Bot** on **GitHub Actions** for **$0/month**, see:

👉 **[Complete Deployment Guide (DEPLOYMENT.md)](DEPLOYMENT.md)**

---

## 🛠️ Quickstart (Run Locally)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Verify System
```bash
python scripts/verify_system.py
```

### 3. Start Application
```bash
python app.py
```
Open your browser at `http://localhost:5000`.

### 4. Workflow
1. Go to **Profile & Settings** (`/profile`):
   - Fill in your name, contact info, experience, CTC, notice period.
   - Upload your resume PDF.
   - Add any custom answers for common screening questions.
2. Go to **Dashboard** (`/`):
   - Select your target job sources (Naukri, LinkedIn, Indeed, Google Jobs, Cutshort, etc.).
   - Enter your keywords and cities, then click **Search All Selected Sources**.
3. Apply:
   - Click **Dry-Run** on any job to test-fill and view the generated proof screenshot.
   - Click **Apply** or run **⚡ Run Live Auto-Apply on All New Jobs**.
4. Review outcomes in **Applied Report** (`/report`) and **Audit Trail** (`/audit`).

---

## 🧪 Testing

Run the automated unit and integration tests:
```bash
python -m pytest
```
