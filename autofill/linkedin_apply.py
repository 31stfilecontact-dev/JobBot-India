"""
LinkedIn Automated Application Engine with Login Session & External ATS Redirection.
Supports:
1. LinkedIn Authentication with persistent session cookies (storage_state).
2. 'Apply on company website' resolution: Follows external redirect to company ATS (Workday, Greenhouse, Lever, Ashby, etc.) and auto-fills.
3. LinkedIn 'Easy Apply': Fills candidate info, resume PDF, and screening questions via Memory Bank.
4. Dry-run simulation with screenshot proof capture and unanswered question extraction.
"""
import os
import time
import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from scrapers.career_page import detect_ats_from_url, detect_ats_from_html
from autofill.ai_form_filler import resolve_field_value, resolve_dropdown_option, query_memory_bank
from autofill.browser_engine import capture_screenshot
from autofill.greenhouse import apply_greenhouse
from autofill.lever import apply_lever
from autofill.workday import apply_workday
from autofill.smartrecruiters import apply_smartrecruiters
from autofill.ashby import apply_ashby

AUTH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
AUTH_FILE = os.path.join(AUTH_DIR, "linkedin_auth.json")
os.makedirs(AUTH_DIR, exist_ok=True)


def ensure_linkedin_login(browser_context, email: str = None, password: str = None) -> bool:
    """Logs into LinkedIn and caches the session storage state if credentials are provided."""
    email = email or os.environ.get("LINKEDIN_EMAIL", "")
    password = password or os.environ.get("LINKEDIN_PASSWORD", "")

    if not email or not password:
        return False

    page = browser_context.new_page()
    page.set_default_timeout(20000)
    try:
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        time.sleep(1)

        # Check if already logged in
        if "feed" in page.url:
            page.close()
            return True

        # Enter credentials
        user_input = page.locator("input#username")
        pass_input = page.locator("input#password")
        if user_input.count() > 0 and pass_input.count() > 0:
            user_input.first.fill(email)
            pass_input.first.fill(password)
            submit_btn = page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.first.click()
                time.sleep(3)
                # Save session state if successful
                if "feed" in page.url or "checkpoint" not in page.url:
                    try:
                        browser_context.storage_state(path=AUTH_FILE)
                    except Exception:
                        pass
                    page.close()
                    return True
        page.close()
        return True
    except Exception as e:
        print(f"[linkedin_apply] Login attempt note: {e}")
        try:
            page.close()
        except Exception:
            pass
        return False


def apply_linkedin(
    job_url: str,
    profile: dict,
    resume_path: str,
    dry_run: bool = True,
    job_context: dict = None,
) -> tuple[bool, str, str, list]:
    """
    Automates application for a LinkedIn job.
    Handles both 'Apply on company website' external redirects and 'Easy Apply' multi-step modal.
    Returns: (success: bool, note: str, screenshot_file: str, unanswered_fields: list)
    """
    job_context = job_context or {}
    screenshot_file = ""
    unanswered_fields = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            
            # Use saved login session if available
            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "viewport": {"width": 1280, "height": 850},
            }
            if os.path.exists(AUTH_FILE):
                try:
                    context_kwargs["storage_state"] = AUTH_FILE
                except Exception:
                    pass

            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.set_default_timeout(30000)

            print(f"[linkedin_apply] Navigating to LinkedIn job: {job_url}")
            page.goto(job_url, wait_until="domcontentloaded")
            time.sleep(2)

            # Check if login is prompted and credentials exist
            if "login" in page.url or page.locator("a:has-text('Sign in')").count() > 0:
                ensure_linkedin_login(context)
                page.goto(job_url, wait_until="domcontentloaded")
                time.sleep(2)

            # Case 1: Look for "Apply on company website" or external apply button
            external_apply_btn = page.locator(
                "a:has-text('Apply on company website'), button:has-text('Apply on company website'), "
                ".jobs-apply-button:not(.jobs-apply-button--easy-apply), a.apply-button"
            )

            if external_apply_btn.count() > 0:
                # Capture target URL or click to follow redirect to external company website
                href = external_apply_btn.first.get_attribute("href")
                redirect_url = ""

                if href and not href.startswith("#") and "linkedin.com/jobs/view" not in href:
                    redirect_url = href
                else:
                    # Click and wait for external popup/page navigation
                    try:
                        with context.expect_page(timeout=10000) as new_page_info:
                            external_apply_btn.first.click()
                        new_page = new_page_info.value
                        new_page.wait_for_load_state("domcontentloaded")
                        redirect_url = new_page.url
                        new_page.close()
                    except Exception:
                        redirect_url = page.url

                if redirect_url and "linkedin.com" not in redirect_url:
                    print(f"[linkedin_apply] Followed external apply redirect: {redirect_url}")
                    ats = detect_ats_from_url(redirect_url) or "generic"
                    browser.close()

                    # Route to specific ATS handler
                    if ats == "greenhouse":
                        return apply_greenhouse(redirect_url, profile, resume_path, dry_run=dry_run, job_context=job_context)
                    elif ats == "lever":
                        return apply_lever(redirect_url, profile, resume_path, dry_run=dry_run, job_context=job_context)
                    elif ats == "workday":
                        return apply_workday(redirect_url, profile, resume_path, dry_run=dry_run, job_context=job_context)
                    elif ats == "smartrecruiters":
                        return apply_smartrecruiters(redirect_url, profile, resume_path, dry_run=dry_run, job_context=job_context)
                    elif ats == "ashby":
                        return apply_ashby(redirect_url, profile, resume_path, dry_run=dry_run, job_context=job_context)
                    else:
                        from autofill.browser_engine import run_playwright_apply
                        return run_playwright_apply(redirect_url, profile, resume_path, ats_type=ats, dry_run=dry_run, job_context=job_context)

            # Case 2: In-app "Easy Apply"
            easy_apply_btn = page.locator("button.jobs-apply-button, button:has-text('Easy Apply')")
            if easy_apply_btn.count() > 0:
                easy_apply_btn.first.click()
                time.sleep(2)

                # Process Easy Apply modal steps (up to 5 steps)
                for step in range(5):
                    modal = page.locator(".jobs-easy-apply-modal, div[role='dialog']")
                    if modal.count() == 0:
                        break

                    # 1. Fill Text Inputs
                    inputs = modal.locator("input:not([type='hidden']):not([type='file']):not([type='checkbox']):not([type='radio']), textarea")
                    for i in range(inputs.count()):
                        inp = inputs.nth(i)
                        if not inp.is_visible():
                            continue
                        label_cands = [inp.get_attribute("aria-label") or "", inp.get_attribute("name") or "", inp.get_attribute("id") or ""]
                        lbl_text = " ".join(filter(None, label_cands))
                        val = resolve_field_value(lbl_text, "text", profile, job_context)
                        if val:
                            try:
                                inp.fill(val)
                            except Exception:
                                pass
                        else:
                            clean_lbl = " ".join(lbl_text.split())
                            if clean_lbl and clean_lbl not in unanswered_fields:
                                unanswered_fields.append(clean_lbl)

                    # 2. Fill Dropdowns
                    selects = modal.locator("select")
                    for i in range(selects.count()):
                        sel = selects.nth(i)
                        if not sel.is_visible():
                            continue
                        lbl_text = sel.get_attribute("name") or sel.get_attribute("id") or ""
                        options = sel.locator("option").all_inner_texts()
                        best_opt = resolve_dropdown_option(options, lbl_text, profile, job_context)
                        if best_opt:
                            try:
                                sel.select_option(label=best_opt)
                            except Exception:
                                pass
                        else:
                            clean_lbl = " ".join(lbl_text.split())
                            if clean_lbl and clean_lbl not in unanswered_fields:
                                unanswered_fields.append(clean_lbl)

                    # 3. Handle File / Resume Upload
                    if resume_path and os.path.exists(resume_path):
                        file_inps = modal.locator("input[type='file']")
                        if file_inps.count() > 0:
                            try:
                                file_inps.first.set_input_files(resume_path)
                                time.sleep(1)
                            except Exception:
                                pass

                    # Check for Next vs Review vs Submit button
                    next_btn = modal.locator("button:has-text('Next'), button:has-text('Review')")
                    submit_btn = modal.locator("button:has-text('Submit application')")

                    if dry_run and (submit_btn.count() > 0 or next_btn.count() > 0):
                        # Capture preview proof screenshot
                        screenshot_file = capture_screenshot(page, prefix="linkedin_easy_apply_dry_run")
                        browser.close()
                        note = "LinkedIn Easy Apply dry-run: Form filled and preview screenshot captured."
                        return True, note, screenshot_file, unanswered_fields

                    if next_btn.count() > 0:
                        next_btn.first.click()
                        time.sleep(2)
                    elif submit_btn.count() > 0:
                        if not dry_run:
                            submit_btn.first.click()
                            time.sleep(3)
                            screenshot_file = capture_screenshot(page, prefix="linkedin_applied")
                            browser.close()
                            return True, "LinkedIn Easy Apply application successfully submitted.", screenshot_file, unanswered_fields
                        break
                    else:
                        break

                screenshot_file = capture_screenshot(page, prefix="linkedin_dry_run" if dry_run else "linkedin_submission")
                browser.close()
                return True, "LinkedIn Easy Apply processed.", screenshot_file, unanswered_fields

            # Case 3: No direct apply button on page — take screenshot
            screenshot_file = capture_screenshot(page, prefix="linkedin_no_apply_btn")
            browser.close()
            return False, "No active Apply or Easy Apply button found on LinkedIn posting.", screenshot_file, unanswered_fields

    except PlaywrightTimeoutError:
        screenshot_file = capture_screenshot(page, prefix="linkedin_timeout") if 'page' in locals() else ""
        if 'browser' in locals():
            browser.close()
        return False, "LinkedIn page interaction timed out.", screenshot_file, unanswered_fields
    except Exception as e:
        screenshot_file = capture_screenshot(page, prefix="linkedin_error") if 'page' in locals() else ""
        if 'browser' in locals():
            browser.close()
        return False, f"LinkedIn apply error: {str(e)}", screenshot_file, unanswered_fields

