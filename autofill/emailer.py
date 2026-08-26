"""
Fallback auto-apply: send resume + cover letter by email when no ATS
form was detected but an HR/recruiting email was found on the careers page.

SMTP credentials are read from environment variables (set these as Replit
Secrets, never hardcode them):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
For Gmail: host=smtp.gmail.com, port=587, and SMTP_PASS must be a Gmail
"App Password" (not your normal password) — generate one at
myaccount.google.com/apppasswords.
"""
import os
import smtplib
from email.message import EmailMessage


def send_application_email(to_email: str, job_title: str, company: str, profile: dict, resume_path: str):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        return False, "SMTP_USER / SMTP_PASS not set in environment (Replit Secrets)"

    msg = EmailMessage()
    msg["Subject"] = f"Application for {job_title} — {profile.get('full_name', '')}"
    msg["From"] = smtp_user
    msg["To"] = to_email

    body = profile.get("cover_letter_template", "").format(
        job_title=job_title, company=company, full_name=profile.get("full_name", "")
    ) if profile.get("cover_letter_template") else (
        f"Dear Hiring Team,\n\nI would like to apply for the {job_title} position at {company}. "
        f"Please find my resume attached.\n\nRegards,\n{profile.get('full_name', '')}\n"
        f"{profile.get('phone', '')} | {profile.get('email', '')}"
    )
    msg.set_content(body)

    if resume_path and os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename="resume.pdf")

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, "email sent"
    except Exception as e:
        return False, f"email send failed: {e}"
