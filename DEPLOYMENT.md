# 🚀 Deployment Guide: Render.com & GitHub Actions (100% Free)

This guide walks you step-by-step through setting up **JobBot India** for **$0/month** using Render.com (Web UI) and GitHub Actions (Automated Daily Bot Runner).

---

## 🌐 Part 1: Deploy Web Dashboard on Render (100% Free)

Render allows you to host the web dashboard with a free HTTPS URL.

### Step 1: Push Code to GitHub
Ensure your latest code is pushed to your GitHub repository:
```bash
git add .
git commit -m "Deploy JobBot India with Docker and Playwright"
git push origin main
```

### Step 2: Create Web Service on Render
1. Go to [dashboard.render.com](https://dashboard.render.com) and log in (with GitHub).
2. Click **New +** → **Web Service**.
3. Select **"Build and deploy from a Git repository"** and choose your `JobBot-India` repository.
4. Render will automatically detect the `Dockerfile`:
   - **Name**: `jobbot-india`
   - **Region**: Choose closest to you (e.g. Singapore / Frankfurt)
   - **Instance Type**: **Free**
5. (Optional) Set Environment Variables in the **Environment** tab:
   - `FLASK_SECRET`: Enter any random secret string.
   - `SMTP_USER`: (Optional) Your Gmail address for email applications.
   - `SMTP_PASS`: (Optional) Gmail App Password.
6. Click **Deploy Web Service**.
7. Once deployed, Render will provide a live URL like `https://jobbot-india.onrender.com`.

---

## ⚡ Part 2: Enable Automated Daily Job Search via GitHub Actions

GitHub Actions runs the bot automatically every morning at **09:00 AM IST (03:30 UTC)** with zero server cost and pre-installed Chrome.

### Step 1: Configure Repository Secrets (Optional, for Email Applications)
If you want email fallback applications to send emails:
1. Open your repository on GitHub: `https://github.com/31stfilecontact-dev/JobBot-India`
2. Go to **Settings** → **Secrets and variables** → **Actions**.
3. Click **New repository secret** and add:
   - `SMTP_USER`: your email address
   - `SMTP_PASS`: your Gmail App Password

### Step 2: Triggering or Customizing the Bot Run
- **Automatic Schedule**: The bot will run every day at 9:00 AM IST automatically.
- **Manual Trigger Anytime**:
  1. Go to your repository on GitHub → **Actions** tab.
  2. Click on **Daily JobBot India Automation** on the left menu.
  3. Click **Run workflow** dropdown:
     - Choose Mode: `dry_run` (to test and get screenshot proofs) or `apply` (to submit).
     - Click **Run workflow**.

### Step 3: View Application Screenshots on GitHub
Whenever a workflow run finishes:
1. Click on the completed workflow run.
2. Scroll down to **Artifacts**.
3. Download `jobbot-application-screenshots.zip` to see the full-page screenshots of all filled application forms.

---

## 🖥️ Part 3: Local Quickstart (Windows / Mac / Linux)

To run everything locally on your machine:
```bash
# 1. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 2. Run diagnostics
python scripts/verify_system.py

# 3. Start local server
python app.py
```
Open [http://localhost:5000](http://localhost:5000) in your browser.
