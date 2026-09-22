"""
Unit tests for Auto-Apply modules and AI Form Filler.
"""
from autofill.ai_form_filler import resolve_field_value, resolve_dropdown_option
from autofill.emailer import send_application_email


def test_resolve_field_value_standard():
    profile = {
        "full_name": "Arjun Sharma",
        "email": "arjun@example.com",
        "phone": "+91 9876543210",
        "current_city": "Bengaluru",
        "current_company": "Acme Corp",
        "total_experience_years": 4.5,
        "current_ctc": "18 LPA",
        "expected_ctc": "25 LPA",
        "notice_period_days": 30,
        "linkedin_url": "https://linkedin.com/in/arjun",
        "work_authorization": "Authorized to work in India",
        "custom_answers": {
            "relocate": "Yes, willing to relocate anywhere in India",
            "certifications": "AWS Certified Solutions Architect",
        }
    }

    assert resolve_field_value("First Name", "text", profile) == "Arjun"
    assert resolve_field_value("Last Name", "text", profile) == "Sharma"
    assert resolve_field_value("Email Address", "text", profile) == "arjun@example.com"
    assert resolve_field_value("Contact Phone", "text", profile) == "+91 9876543210"
    assert resolve_field_value("Current Location", "text", profile) == "Bengaluru"
    assert resolve_field_value("LinkedIn Profile", "text", profile) == "https://linkedin.com/in/arjun"
    assert resolve_field_value("Expected CTC / Salary", "text", profile) == "25 LPA"
    assert resolve_field_value("Notice Period", "text", profile) == "30 days"
    assert resolve_field_value("Are you legally authorized to work in India?", "text", profile) == "Yes"
    assert resolve_field_value("Do you require visa sponsorship?", "text", profile) == "No"
    assert resolve_field_value("Are you open to relocate?", "text", profile) == "Yes, willing to relocate anywhere in India"


def test_resolve_dropdown_option():
    profile = {
        "work_authorization": "Authorized to work in India",
        "gender": "Male",
    }
    opts = ["Select option", "Yes", "No", "Other"]
    assert resolve_dropdown_option(opts, "Are you authorized to work?", profile) == "Yes"

    gender_opts = ["Select gender", "Female", "Male", "Decline to state"]
    assert resolve_dropdown_option(gender_opts, "Gender", profile) == "Male"


def test_email_dry_run():
    profile = {"full_name": "Arjun Sharma", "email": "arjun@example.com"}
    ok, note, _ = send_application_email(
        to_email="careers@company.com",
        job_title="Backend Developer",
        company="StartupCo",
        profile=profile,
        resume_path=None,
        dry_run=True,
    )
    assert ok is True
    assert "Dry-run simulation" in note
