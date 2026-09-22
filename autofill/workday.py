"""
Workday ATS Auto-Apply Handler (myworkdayjobs.com).
Uses Playwright to navigate Workday application flows, upload resumes, and populate candidate fields.
"""
from autofill.browser_engine import run_playwright_apply


def apply_workday(job_url: str, profile: dict, resume_path: str, dry_run: bool = False, job_context: dict = None):
    """
    Apply to a Workday job posting.
    Returns: (success: bool, note: str, screenshot_file: str, unanswered_fields: list)
    """
    return run_playwright_apply(
        url=job_url,
        profile=profile,
        resume_path=resume_path,
        ats_type="workday",
        dry_run=dry_run,
        job_context=job_context or {},
    )
