"""
Intelligent Form Filler & Question Resolver with Persistent Memory.
Supports:
- Memory Bank lookup with semantic token-overlap & fuzzy similarity
- Company-specific overrides and Global memory fallbacks
- Candidate profile context mapping (CTC, notice period, work authorization)
- Dynamic learning from manual resolutions
"""
import re
from datetime import datetime


def _stem(word: str) -> str:
    """Basic suffix stemmer for common English word forms."""
    if len(word) > 4 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 3 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _normalize_tokens(text: str) -> set:
    """Extract and stem meaningful semantic tokens from text."""
    if not text:
        return set()
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    stop_words = {
        "are", "you", "the", "a", "an", "is", "in", "to", "for", "of", "and", "or",
        "do", "does", "please", "your", "our", "this", "can", "will", "would", "be", "with"
    }
    tokens = set()
    for w in text.split():
        if w not in stop_words and len(w) > 1:
            tokens.add(_stem(w))
    return tokens


def _normalize_text(text: str) -> str:
    """Strip punctuation and stop words for plain substring checks."""
    if not text:
        return ""
    return " ".join(sorted(list(_normalize_tokens(text))))


def _token_overlap_score(q1: str, q2: str) -> float:
    """Calculate token overlap similarity between two question prompts."""
    t1 = _normalize_tokens(q1)
    t2 = _normalize_tokens(q2)
    if not t1 or not t2:
        return 0.0
    intersection = t1.intersection(t2)
    if not intersection:
        return 0.0
    jaccard = len(intersection) / len(t1.union(t2))
    overlap = len(intersection) / min(len(t1), len(t2))
    return max(jaccard, overlap * 0.7)



def query_memory_bank(field_label: str, company: str = None, ats_type: str = None) -> str:
    """
    Look up previously learned answers from the persistent ApplicationMemory database table.
    Prioritizes:
    1. Company-specific memory
    2. ATS-specific memory
    3. Global memory (company is None)
    """
    try:
        from models import db, ApplicationMemory
        norm_label = _normalize_text(field_label)
        if not norm_label:
            return ""

        query = ApplicationMemory.query
        all_memories = query.all()
        if not all_memories:
            return ""

        best_match = None
        highest_score = 0.0

        # Sort memories to test company-specific first
        def memory_priority(m):
            score = 0
            if company and m.company and m.company.lower() in company.lower():
                score += 3
            if ats_type and m.ats_type and m.ats_type.lower() == ats_type.lower():
                score += 2
            if not m.company:
                score += 1
            return score

        sorted_memories = sorted(all_memories, key=memory_priority, reverse=True)

        for mem in sorted_memories:
            # Check company mismatch
            if mem.company and company and mem.company.lower() not in company.lower() and company.lower() not in mem.company.lower():
                continue

            # Exact keyword in label check
            clean_pattern = _normalize_text(mem.question_pattern)
            if clean_pattern and (clean_pattern in norm_label or norm_label in clean_pattern):
                return mem.answer_value

            # Fuzzy token overlap check
            score = _token_overlap_score(field_label, mem.question_pattern)
            if score > 0.35 and score > highest_score:
                highest_score = score
                best_match = mem

        if best_match and highest_score >= 0.35:
            return best_match.answer_value

    except Exception as e:
        print(f"[ai_form_filler] Memory query failed: {e}")

    return ""


def learn_memory(question: str, answer: str, company: str = None, ats_type: str = None, field_type: str = "text") -> bool:
    """Store or update a learned question-answer pair in the persistent ApplicationMemory database."""
    if not question or not answer:
        return False
    try:
        from models import db, ApplicationMemory
        clean_q = question.strip()
        clean_a = answer.strip()

        # Check if already exists for this company/global
        existing = ApplicationMemory.query.filter(
            (ApplicationMemory.question_pattern == clean_q) &
            (ApplicationMemory.company == (company.strip() if company else None))
        ).first()

        if existing:
            existing.answer_value = clean_a
            existing.last_used_at = datetime.utcnow()
        else:
            new_mem = ApplicationMemory(
                question_pattern=clean_q,
                answer_value=clean_a,
                company=company.strip() if company else None,
                ats_type=ats_type.strip() if ats_type else None,
                field_type=field_type,
                times_used=1,
                last_used_at=datetime.utcnow(),
            )
            db.session.add(new_mem)

        db.session.commit()
        return True
    except Exception as e:
        print(f"[ai_form_filler] Failed to learn memory: {e}")
        return False


def resolve_field_value(field_label: str, field_type: str, profile: dict, job_context: dict = None) -> str:
    """
    Given a field label / placeholder / name, resolve the most appropriate candidate value.
    Hierarchy:
    1. Persistent Memory Bank (ApplicationMemory)
    2. Profile Custom Answers dictionary
    3. Candidate Profile core attributes
    4. Heuristic & Diversity fallbacks
    """
    label = (field_label or "").lower()
    job_context = job_context or {}
    company = job_context.get("company")
    ats_type = job_context.get("ats_type")

    # 1. Check Persistent Memory Bank
    learned_answer = query_memory_bank(field_label, company=company, ats_type=ats_type)
    if learned_answer:
        return learned_answer

    # 2. Check Profile Custom Answers
    custom_answers = profile.get("custom_answers") or {}
    for custom_k, custom_v in custom_answers.items():
        if custom_k.lower() in label or label in custom_k.lower():
            return str(custom_v)

    # 3. Standard Name fields
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

    # Default fallback for general open-ended questions
    if "?" in label or "why" in label or "describe" in label:
        return f"With {profile.get('total_experience_years', 0)} years of relevant experience, I have developed strong expertise in this domain and am excited to bring value to your team."

    return ""


def resolve_dropdown_option(options: list, field_label: str, profile: dict, job_context: dict = None) -> str:
    """Select the best matching option from a list of dropdown option strings."""
    resolved_val = resolve_field_value(field_label, "select", profile, job_context).strip().lower()

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
