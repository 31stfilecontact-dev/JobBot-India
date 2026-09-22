"""
Intelligent Form Filler & Question Resolver.
Provides rule-based heuristics and candidate context resolution for application questions,
including salary expectations, notice period, work authorization, diversity questions, and custom prompts.
"""
import re


def resolve_field_value(field_label: str, field_type: str, profile: dict, job_context: dict = None) -> str:
    """
    Given a field label / placeholder / name, resolve the most appropriate candidate value from profile.
    """
    label = (field_label or "").lower()
    custom_answers = profile.get("custom_answers") or {}

    # Check custom answers first
    for custom_k, custom_v in custom_answers.items():
        if custom_k.lower() in label or label in custom_k.lower():
            return str(custom_v)

    # Name fields
    if any(k in label for k in ("first name", "given name", "first_name", "fname")):
        full_name = profile.get("full_name", "")
        return full_name.split()[0] if full_name else ""
    if any(k in label for k in ("last name", "surname", "family name", "last_name", "lname")):
        full_name = profile.get("full_name", "")
        return " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else full_name
    if any(k in label for k in ("full name", "your name", "candidate name", "name")):
        return profile.get("full_name", "")

    # Contact fields
    if any(k in label for k in ("email", "e-mail")):
        return profile.get("email", "")
    if any(k in label for k in ("phone", "mobile", "contact number", "cell")):
        return profile.get("phone", "")
    if any(k in label for k in ("city", "current location", "location", "address")):
        return profile.get("current_city") or profile.get("preferred_cities", "").split(",")[0]

    # Professional URLs
    if "linkedin" in label:
        return profile.get("linkedin_url", "")
    if "github" in label:
        return profile.get("github_url", "")
    if any(k in label for k in ("portfolio", "website", "personal url", "links")):
        return profile.get("portfolio_url") or profile.get("github_url") or profile.get("linkedin_url", "")

    # Work Authorization / Visa
    if any(k in label for k in ("authorized to work", "work authorization", "legally authorized", "eligible to work")):
        return "Yes"
    if any(k in label for k in ("require sponsorship", "visa sponsorship", "sponsorship now or in the future")):
        return "No"

    # Notice Period
    if any(k in label for k in ("notice period", "how soon can you start", "availability")):
        notice = profile.get("notice_period_days", 0)
        if notice == 0:
            return "Immediate / 0 days"
        return f"{notice} days"

    # Compensation / CTC
    if any(k in label for k in ("expected ctc", "expected salary", "salary expectation", "compensation expectation")):
        return str(profile.get("expected_ctc") or "Negotiable / As per market standards")
    if any(k in label for k in ("current ctc", "current salary", "present ctc")):
        return str(profile.get("current_ctc") or "Confidential")

    # Experience
    if any(k in label for k in ("total experience", "years of experience", "how many years")):
        return str(profile.get("total_experience_years", 0))

    # Current Employment
    if any(k in label for k in ("current company", "employer", "current organization")):
        return profile.get("current_company", "")
    if any(k in label for k in ("current title", "designation", "current role")):
        return profile.get("current_title", "")

    # Gender / Diversity
    if "gender" in label:
        return profile.get("gender") or "Decline to Self-Identify"

    # Cover letter / Comments
    if any(k in label for k in ("cover letter", "message to hiring manager", "comments", "summary", "note")):
        template = profile.get("cover_letter_template", "")
        if template and job_context:
            try:
                return template.format(
                    job_title=job_context.get("title", ""),
                    company=job_context.get("company", ""),
                    full_name=profile.get("full_name", ""),
                )
            except Exception:
                return template
        return template or f"Dear Hiring Team,\n\nI am very interested in this opportunity and look forward to contributing my skills. Please find my attached resume.\n\nBest regards,\n{profile.get('full_name', '')}"

    # Default fallback for open-ended questions
    if "?" in label or "why" in label or "describe" in label:
        return f"With {profile.get('total_experience_years', 0)} years of relevant experience, I have developed strong expertise in this domain and am excited to bring value to your team."

    return ""


def resolve_dropdown_option(options: list, field_label: str, profile: dict) -> str:
    """Select the best matching option from a list of dropdown option strings."""
    resolved_val = resolve_field_value(field_label, "select", profile).strip().lower()

    if not resolved_val and any(k in field_label.lower() for k in ("gender", "race", "veteran", "disability")):
        # Prefer 'decline' or 'prefer not to say' for sensitive questions if no preference
        for opt in options:
            if any(w in opt.lower() for w in ("decline", "prefer not", "not wish")):
                return opt

    if resolved_val:
        # 1. Exact match
        for opt in options:
            if opt.strip().lower() == resolved_val:
                return opt

        # 2. Whole word boundary regex match (e.g. avoid matching 'male' in 'female')
        for opt in options:
            if re.search(r"\b" + re.escape(resolved_val) + r"\b", opt.lower()):
                return opt

        # 3. Substring match fallback
        for opt in options:
            if resolved_val in opt.lower():
                return opt

    # Fallback to first non-placeholder option
    for opt in options:
        opt_clean = opt.strip()
        if opt_clean and not any(w in opt_clean.lower() for w in ("select", "choose", "placeholder", "--")):
            return opt

    return options[0] if options else ""
