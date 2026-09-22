"""
SmartRecruiters ATS Auto-Apply Handler (smartrecruiters.com).
Uses Playwright to interact with SmartRecruiters forms.
"""
from autofill.browser_engine import run_playwright_apply


def apply_smartrecruiters(job_url: str, profile: dict, resume_path: str, dry_run: bool = False, job_context: dict = None):
    """
    Apply to a SmartRecruiters job posting.
    Returns: (success: bool, note: str, screenshot_file: str, unanswered_fields: list)
    """
    return run_playwright_apply(
        url=job_url,
        profile=profile,
        resume_path=resume_path,
        ats_type="smartrecruiters",
        dry_run=dry_run,
        job_context=job_context or {},
    )
