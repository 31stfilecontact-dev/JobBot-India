"""
Fallback auto-apply: send resume + cover letter by email when an HR/recruiting email
is found on the careers page.
"""
import os
import smtplib
from email.message import EmailMessage


def send_application_email(to_email: str, job_title: str, company: str, profile: dict, resume_path: str, dry_run: bool = False):
    """
    Sends application email to target HR/recruiter.
    Returns: (success: bool, note: str, screenshot_file: str)
    """
    if dry_run:
        return True, f"Dry-run simulation: would send email to {to_email} with attached resume.", ""

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER") or profile.get("smtp_email")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        return False, "SMTP credentials (SMTP_USER / SMTP_PASS) not configured.", ""

    msg = EmailMessage()
    msg["Subject"] = f"Application for {job_title} — {profile.get('full_name', '')}"
    msg["From"] = smtp_user
    msg["To"] = to_email

    custom_template = profile.get("cover_letter_template", "")
    if custom_template:
        try:
            body = custom_template.format(
                job_title=job_title, company=company, full_name=profile.get("full_name", "")
            )
        except Exception:
            body = custom_template
    else:
        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {job_title} role.\n"
            f"With my background in software development and proven expertise, I am confident in delivering immediate value to your team.\n\n"
            f"Please find my resume attached.\n\n"
            f"Best regards,\n"
            f"{profile.get('full_name', '')}\n"
            f"Phone: {profile.get('phone', '')}\n"
            f"Email: {profile.get('email', '')}\n"
            f"LinkedIn: {profile.get('linkedin_url', '')}\n"
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
        return True, f"Application email successfully sent to {to_email}", ""
    except Exception as e:
        return False, f"Email delivery failed: {e}", ""
