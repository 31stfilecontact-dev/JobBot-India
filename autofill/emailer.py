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
    Returns: (success: bool, note: str, screenshot_file: str, unanswered_fields: list)
    """
    if dry_run:
        return True, f"Dry-run simulation: would send email to {to_email} with attached resume.", "", []

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER") or profile.get("smtp_email")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        return False, "SMTP credentials (SMTP_USER / SMTP_PASS) not configured.", "", []

    msg = EmailMessage()
    msg["Subject"] = f"Application for {job_title} — {profile.get('full_name', '')}"
    msg["From"] = smtp_user
    msg["To"] = to_email

    custom_template = profile.get("cover_letter_template", "")
    if custom_template:
        try:
            body = custom_template.format(
                job_title=job_title, company=company, full_name=profile.get("full_name", "Aman Mehta")
            )
        except Exception:
            body = custom_template
    else:
        full_name = profile.get("full_name", "Aman Mehta")
        phone = profile.get("phone", "+91 9052572066")
        email = profile.get("email", "amanmehta8799@gmail.com")
        location = profile.get("current_city", "Hyderabad, India")
        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {job_title} opportunity at {company}.\n\n"
            f"I am a Chartered Accountant currently working as Assistant Manager (Corporate International Tax) at BSR & Co. LLP / KPMG, with prior Big 4 consulting experience at Ernst & Young (EY). Over 5+ years of practice, I have advised corporate clients on direct tax compliance, FEMA regulations, cross-border restructuring, and statutory/tax audits.\n\n"
            f"Key highlights of my qualifications:\n"
            f"• Corporate & International Tax: End-to-end direct tax compliance for 14+ corporate clients, withholding tax (Form 15CA/15CB, 10F), and representation before CIT(Appeals) / NFAC.\n"
            f"• FEMA & Cross-Border Structuring: Permanent Establishment (PE) exposure evaluations for GCCs, FC-GPR/FLA filings, and AD bank compliance.\n"
            f"• Financial Reporting & Audit: Standalone and consolidated financial statement preparation under Ind AS / Accounting Standards, with extensive statutory & tax audit leadership.\n"
            f"• Technical Proficiencies: Microsoft Dynamics, Tally, advanced financial modeling, and GST reconciliation (GSTR 2A/2B).\n\n"
            f"Please find my resume attached for your review. I look forward to the opportunity to discuss how my skill set aligns with your team's objectives.\n\n"
            f"Warm regards,\n"
            f"{full_name}\n"
            f"Chartered Accountant\n"
            f"Phone: {phone}\n"
            f"Email: {email}\n"
            f"Location: {location}\n"
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
        return True, f"Application email successfully sent to {to_email}", "", []
    except Exception as e:
        return False, f"Email delivery failed: {e}", "", []
