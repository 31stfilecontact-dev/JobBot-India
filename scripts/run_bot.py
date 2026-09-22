"""
Headless CLI Bot Runner for Scheduled Automations (e.g. GitHub Actions or Cron).
Executes multi-source job search and auto-apply or dry-run based on profile settings.
"""
import os
import sys
import argparse

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, get_profile, run_search, run_auto_apply, _parse_csv


def main():
    parser = argparse.ArgumentParser(description="JobBot India Headless Automated Runner")
    parser.add_argument("--mode", choices=["dry_run", "apply"], default=None, help="Execution mode")
    parser.add_argument("--sources", nargs="+", default=None, help="Job sources to query")
    parser.add_argument("--pages", type=int, default=1, help="Search pagination depth")
    args = parser.parse_args()

    print("=" * 60)
    print("[RUNNER] Starting JobBot India Scheduled Automation")
    print("=" * 60)

    with app.app_context():
        profile = get_profile()
        keywords = _parse_csv(profile.keywords)
        cities = _parse_csv(profile.preferred_cities)
        sources = args.sources or ["naukri", "linkedin", "indeed", "google_jobs", "foundit", "shine", "cutshort", "instahyre"]

        print(f"Keywords: {keywords}")
        print(f"Target Locations: {cities}")
        print(f"Sources: {sources}")
        print(f"Search Pages: {args.pages}")

        # 1. Run Discovery
        print("\n[Step 1] Running multi-source job discovery...")
        search_res = run_search(keywords, cities, sources=sources, pages=args.pages)
        print(f"Discovery Results: Found {search_res['jobs_found']} jobs, added {search_res['jobs_added']} new jobs.")

        # 2. Determine apply mode
        if args.mode:
            is_dry_run = (args.mode == "dry_run")
        else:
            is_dry_run = bool(profile.dry_run_mode_enabled)

        mode_str = "Dry-Run Simulation" if is_dry_run else "Live Application"
        print(f"\n[Step 2] Executing auto-apply engine ({mode_str})...")

        apply_res = run_auto_apply(dry_run=is_dry_run)
        if is_dry_run:
            print(f"Auto-Apply Results: {apply_res['dry_run']} simulated, {apply_res['failed']} failed.")
        else:
            print(f"Auto-Apply Results: {apply_res['applied']} applied, {apply_res['failed']} failed.")

        print("\n" + "=" * 60)
        print("[SUCCESS] Scheduled automation run completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    main()
