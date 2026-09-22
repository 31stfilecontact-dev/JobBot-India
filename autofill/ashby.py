"""
Ashby ATS Auto-Apply Handler (jobs.ashbyhq.com).
Uses Playwright to interact with Ashby application forms, upload resumes, and populate screening inputs.
"""
from autofill.browser_engine import run_playwright_apply


def apply_ashby(job_url: str, profile: dict, resume_path: str, dry_run: bool = False, job_context: dict = None):
    """
    Apply to an Ashby job posting.
    Returns: (success: bool, note: str, screenshot_file: str)
    """
    return run_playwright_apply(
        url=job_url,
        profile=profile,
        resume_path=resume_path,
        ats_type="ashby",
        dry_run=dry_run,
        job_context=job_context or {},
    )
