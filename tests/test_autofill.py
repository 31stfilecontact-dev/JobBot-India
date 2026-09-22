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
    ok, note, _, _ = send_application_email(
        to_email="careers@company.com",
        job_title="Backend Developer",
        company="StartupCo",
        profile=profile,
        resume_path=None,
        dry_run=True,
    )
    assert ok is True
    assert "Dry-run simulation" in note


def test_memory_bank_resolution():
    from autofill.ai_form_filler import query_memory_bank, learn_memory
    from models import ApplicationMemory
    from app import app, db

    with app.app_context():
        db.create_all()
        # Clean up any existing memories in test
        ApplicationMemory.query.delete()
        db.session.commit()

        # Learn a memory
        saved = learn_memory(
            question="What is your primary tech stack experience?",
            answer="Python, Django, FastAPI, PostgreSQL",
            company="Razorpay",
            ats_type="greenhouse"
        )
        assert saved is True

        # Query company-specific exact/fuzzy match
        ans = query_memory_bank(
            field_label="What is your primary tech stack experience?",
            company="Razorpay",
            ats_type="greenhouse"
        )
        assert ans == "Python, Django, FastAPI, PostgreSQL"

        # Query global fallback
        learn_memory(
            question="Are you willing to work in rotational shifts?",
            answer="Yes, open to rotational shifts",
            company=None
        )
        ans_global = query_memory_bank(
            field_label="Are you comfortable working in rotational shifts?",
            company="SomeOtherCompany"
        )
        assert ans_global == "Yes, open to rotational shifts"


def test_linkedin_apply_mock(mocker):
    from autofill.linkedin_apply import apply_linkedin
    mocker.patch("autofill.linkedin_apply.sync_playwright", side_effect=Exception("Mocked Playwright context"))
    profile = {"full_name": "Aman Mehta", "email": "aman@example.com"}
    ok, note, screenshot, unanswered = apply_linkedin("https://in.linkedin.com/jobs/view/12345", profile, None, dry_run=True)
    assert ok is False
    assert "Mocked Playwright context" in note



