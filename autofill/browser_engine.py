"""
Playwright Browser Automation Engine.
Provides headless browser automation for interacting with complex JavaScript-based ATS forms (Workday, SmartRecruiters, Ashby, Greenhouse, Lever).
Supports:
- Realistic browser headers & stealth
- Dry-run mode with timestamped screenshot generation
- Intelligent DOM element identification and auto-filling
- File upload handling for PDF resumes
"""
import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from autofill.ai_form_filler import resolve_field_value, resolve_dropdown_option

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def capture_screenshot(page, prefix: str = "dry_run") -> str:
    """Captures a screenshot of the current page and returns the filename."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.png"
    filepath = os.path.join(SCREENSHOTS_DIR, filename)
    try:
        page.screenshot(path=filepath, full_page=True)
        return filename
    except Exception as e:
        print(f"[browser_engine] Screenshot capture failed: {e}")
        return ""


def run_playwright_apply(
    url: str,
    profile: dict,
    resume_path: str,
    ats_type: str,
    dry_run: bool = True,
    job_context: dict = None,
) -> tuple[bool, str, str]:
    """
    Executes an automated application using Playwright.
    Returns: (success: bool, notes: str, screenshot_filename: str)
    """
    screenshot_file = ""
    job_context = job_context or {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.set_default_timeout(25000)

            print(f"[browser_engine] Navigating to {url} (ATS: {ats_type}, DryRun: {dry_run})")
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(2)

            # Look for an 'Apply' or 'Apply Now' button if on landing page
            apply_buttons = page.locator("a:has-text('Apply'), button:has-text('Apply'), a:has-text('Apply for this job')")
            if apply_buttons.count() > 0 and not page.locator("form").is_visible():
                try:
                    apply_buttons.first.click()
                    time.sleep(2)
                except Exception:
                    pass

            # Handle Resume Upload
            if resume_path and os.path.exists(resume_path):
                file_inputs = page.locator("input[type='file']")
                if file_inputs.count() > 0:
                    try:
                        file_inputs.first.set_input_files(resume_path)
                        time.sleep(1)
                    except Exception as e:
                        print(f"[browser_engine] File upload failed: {e}")

            # Fill Text Inputs & Textareas
            inputs = page.locator("input:not([type='hidden']):not([type='file']):not([type='submit']):not([type='checkbox']):not([type='radio']), textarea")
            count = inputs.count()
            for i in range(count):
                inp = inputs.nth(i)
                if not inp.is_visible():
                    continue

                # Derive label from aria-label, name, id, placeholder, or parent text
                label_candidates = [
                    inp.get_attribute("aria-label") or "",
                    inp.get_attribute("placeholder") or "",
                    inp.get_attribute("name") or "",
                    inp.get_attribute("id") or "",
                ]
                label_str = " ".join(filter(None, label_candidates))

                # If still empty, inspect label element
                inp_id = inp.get_attribute("id")
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if lbl.count() > 0:
                        label_str += " " + lbl.first.inner_text()

                value_to_fill = resolve_field_value(label_str, "text", profile, job_context)
                if value_to_fill:
                    try:
                        inp.fill(value_to_fill)
                    except Exception:
                        pass

            # Fill Dropdowns / Selects
            selects = page.locator("select")
            for i in range(selects.count()):
                sel = selects.nth(i)
                if not sel.is_visible():
                    continue
                label_str = sel.get_attribute("name") or sel.get_attribute("id") or ""
                options = sel.locator("option").all_inner_texts()
                best_opt = resolve_dropdown_option(options, label_str, profile)
                if best_opt:
                    try:
                        sel.select_option(label=best_opt)
                    except Exception:
                        pass

            # Take dry-run or pre-submission screenshot
            screenshot_file = capture_screenshot(page, prefix=f"{ats_type}_dry_run" if dry_run else f"{ats_type}_submission")

            if dry_run:
                browser.close()
                return True, "Dry-run successful: form filled and preview screenshot captured.", screenshot_file

            # Non-dry-run: Click Submit button
            submit_btn = page.locator("button[type='submit'], input[type='submit'], button:has-text('Submit Application'), button:has-text('Submit')")
            if submit_btn.count() > 0:
                submit_btn.first.click()
                time.sleep(4)
                screenshot_file = capture_screenshot(page, prefix=f"{ats_type}_post_submit")
                browser.close()
                return True, "Application successfully submitted.", screenshot_file
            else:
                browser.close()
                return False, "Could not locate final Submit button.", screenshot_file

        except PlaywrightTimeoutError:
            if 'page' in locals():
                screenshot_file = capture_screenshot(page, prefix=f"{ats_type}_timeout")
            browser.close()
            return False, "Page load or element interaction timed out.", screenshot_file
        except Exception as e:
            if 'page' in locals():
                screenshot_file = capture_screenshot(page, prefix=f"{ats_type}_error")
            browser.close()
            return False, f"Browser automation error: {str(e)}", screenshot_file
