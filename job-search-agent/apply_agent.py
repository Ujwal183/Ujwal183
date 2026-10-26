#!/usr/bin/env python3
"""Local resume-aware application runner for Job Scout.

Privacy: resume, profile, mail credentials and application log stay under ~/.jobscout.
By default the runner is DRY RUN. Submission requires --submit and auto_apply_enabled=true.
It never bypasses CAPTCHA or invents answers to required questions.
"""
from __future__ import annotations

import argparse
import email.message
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

APP_HOME = Path.home() / ".jobscout"
PROFILE_PATH = APP_HOME / "profile.json"
ENV_PATH = APP_HOME / ".env"
LOG_PATH = APP_HOME / "applications.json"
REPORT_DIR = APP_HOME / "reports"
JOBS_URL = "https://raw.githubusercontent.com/Ujwal183/Ujwal183/main/job-search-agent/data/jobs.json"
USER_AGENT = "JobScout-Local-Applicant/1.0"

SKILL_PATTERNS = {
    "Java": r"\bjava\b", "Spring Boot": r"\bspring\s*boot\b", "Python": r"\bpython\b",
    "SQL": r"\bsql\b", "MySQL": r"\bmysql\b", "JDBC": r"\bjdbc\b", "FastAPI": r"\bfastapi\b",
    "REST APIs": r"\brest(?:ful)?\s+apis?\b", "Pandas": r"\bpandas\b", "NumPy": r"\bnumpy\b",
    "Excel": r"\bexcel\b|\bspreadsheets?\b", "Machine Learning": r"\bmachine learning\b|\bml\b",
    "Generative AI": r"\bgenerative ai\b|\bgenai\b|\bllms?\b", "Git": r"\bgit\b",
    "JavaScript": r"\bjavascript\b", "HTML": r"\bhtml5?\b", "CSS": r"\bcss3?\b",
    "Power BI": r"\bpower bi\b", "React": r"\breact(?:\.js)?\b", "Docker": r"\bdocker\b",
    "AWS": r"\baws\b|\bamazon web services\b", "PostgreSQL": r"\bpostgres(?:ql)?\b",
    "Hibernate": r"\bhibernate\b", "REST": r"\brest api\b", "OOP": r"\boop\b|object[- ]oriented"
}
SENSITIVE_TERMS = (
    "race", "ethnicity", "gender", "sexual orientation", "disability", "disabled",
    "veteran", "military status", "religion", "date of birth", "marital status",
    "medical condition", "accommodation", "national origin", "demographic"
)
CAPTCHA_TERMS = (
    "captcha", "verify you are human", "verification challenge", "unusual traffic",
    "complete the security check", "checking your browser", "cloudflare ray id",
    "press and hold to confirm"
)
SUCCESS_TERMS = (
    "application has been submitted", "application submitted", "thank you for applying",
    "thanks for applying", "we have received your application", "application received",
    "successfully applied", "your application is complete", "thank you for your application"
)
ENTRY_TERMS = ("junior", "entry level", "entry-level", "graduate", "associate", "intern", "trainee", "fresher", "sde i")
FOREIGN_LOCATIONS = (
    "united states", "usa", "canada", "spain", "united kingdom", "germany", "france",
    "poland", "portugal", "netherlands", "ireland", "switzerland", "australia",
    "new zealand", "singapore", "japan", "china", "mexico", "brazil", "sweden",
    "norway", "denmark", "finland", "italy", "czech republic", "belgium",
    "austria", "israel", "south korea", "taiwan", "united arab emirates",
    "south africa", "new york", "california", "texas", "mountain view",
    "vancouver", "london", "berlin", "madrid", "paris", "amsterdam", "toronto", "sydney"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        row = line.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, value = row.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def fetch_jobs(jobs_file: str | None = None) -> dict[str, Any]:
    if jobs_file:
        return load_json(Path(jobs_file).expanduser().resolve(), {})
    request = Request(JOBS_URL + "?ts=" + str(int(time.time())), headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Job feed returned HTTP " + str(response.status))
        payload = response.read(8_000_000)
    data = json.loads(payload.decode("utf-8", errors="replace"))
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise RuntimeError("Job feed schema was not recognized.")
    return data


def extract_resume_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Resume file was not found: " + str(path))
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -r requirements-auto-apply.txt") from exc
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -r requirements-auto-apply.txt") from exc
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(
            " | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows
        )
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Supported resume types are PDF, DOCX, TXT or MD.")


def detected_skills(text: str) -> set[str]:
    return {skill for skill, pattern in SKILL_PATTERNS.items() if re.search(pattern, text or "", re.I)}


def canonical_url(url: str) -> str:
    return (url or "").strip().rstrip("/").split("?")[0].lower()


def location_ok(location: str, preferred: list[str]) -> bool:
    loc = (location or "").lower()
    if any(f in loc for f in FOREIGN_LOCATIONS):
        return False
    if not any(term in loc for term in ("india", "bengaluru", "bangalore", "hyderabad", "chennai", "pune", "mumbai", "gurugram", "gurgaon", "noida", "coimbatore", "kochi", "remote")):
        return False
    if not preferred:
        return True
    return any(p.lower() in loc for p in preferred) or ("india" in loc and any(p.lower() in ("india", "remote") for p in preferred))


def fit_job(job: dict[str, Any], resume_text: str, profile: dict[str, Any]) -> dict[str, Any]:
    resume_skill_set = detected_skills(resume_text + " " + " ".join(profile.get("skills", [])))
    desc = (str(job.get("title", "")) + " " + str(job.get("description", ""))).lower()
    job_skills = {skill for skill, pattern in SKILL_PATTERNS.items() if re.search(pattern, desc, re.I)}
    overlap = sorted(resume_skill_set & job_skills)
    base_score = max(0, min(100, int(job.get("match_score", 0) or 0)))
    if job_skills:
        skills_score = round(100 * len(overlap) / min(len(job_skills), 7))
    else:
        skills_score = 0
    title = str(job.get("title", "")).lower()
    target_roles = [str(x).strip().lower() for x in profile.get("target_roles", []) if str(x).strip()]
    target_match = any(target in title for target in target_roles)
    if not target_match:
        # Support common role equivalents without requiring exact title text.
        role_aliases = {
            "java": ("java",), "python": ("python",), "backend": ("backend", "back-end", "software engineer", "software developer"),
            "associate software engineer": ("associate", "sde i", "software engineer"),
            "data engineer": ("data engineer", "data platform"), "automation engineer": ("automation", "qa automation", "sdet"),
            "ai": ("ai engineer", "machine learning", "ml/ai", "artificial intelligence")
        }
        target_match = any(any(alias in title for alias in aliases) for target in target_roles for key, aliases in role_aliases.items() if key in target)
    score = round(base_score * 0.55 + skills_score * 0.4 + (5 if target_match else 0))
    if not overlap:
        score = min(score, 54)
    if not location_ok(str(job.get("location", "")), profile.get("preferred_locations", [])):
        score = min(score, 0)
    experience_requirement = re.findall(r"\b(\d{1,2})\s*\+?\s*years?(?:\s+of\s+(?:relevant\s+)?experience)?", desc)
    if experience_requirement and max(int(y) for y in experience_requirement) >= 3 and not any(term in desc for term in ENTRY_TERMS):
        score = min(score, 45)
    return {
        "resume_match_score": min(99, score),
        "resume_skills_found": sorted(resume_skill_set),
        "overlapping_skills": overlap,
        "job_skills_detected": sorted(job_skills),
        "target_role_match": target_match,
        "location_match": location_ok(str(job.get("location", "")), profile.get("preferred_locations", []))
    }


def _profile_value(profile: dict[str, Any], key: str) -> str:
    value = profile.get(key, "")
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).strip()


def map_field(label: str, profile: dict[str, Any], full_name: str) -> tuple[str | None, str]:
    """Return (answer, action); action is text, select, radio, file, check or skip."""
    text = re.sub(r"\s+", " ", label.lower()).strip()
    if not text:
        return None, "unknown"
    if any(term in text for term in SENSITIVE_TERMS):
        return None, "sensitive"
    if "resume" in text or re.search(r"\bcv\b", text):
        return _profile_value(profile, "resume_path"), "file"
    if "cover letter" in text:
        return _profile_value(profile, "cover_letter_text"), "text"
    if "email" in text or "e-mail" in text:
        return _profile_value(profile, "email"), "text"
    if re.search(r"\b(first|given)\s+name\b", text):
        return _profile_value(profile, "first_name"), "text"
    if re.search(r"\b(last|family|surname)\s+name\b", text):
        return _profile_value(profile, "last_name"), "text"
    if re.search(r"\b(full|legal)\s+name\b", text) or text == "name":
        return full_name, "text"
    if "phone" in text or "mobile" in text or "telephone" in text:
        return _profile_value(profile, "phone"), "text"
    if "linkedin" in text:
        return _profile_value(profile, "linkedin_url"), "text"
    if "github" in text:
        return _profile_value(profile, "github_url"), "text"
    if "portfolio" in text or "personal website" in text or text == "website":
        return _profile_value(profile, "portfolio_url"), "text"
    if "sponsorship" in text or "sponsor" in text or "visa" in text:
        value = _profile_value(profile, "requires_sponsorship")
        if not value:
            return None, "unknown"
        if "visa status" in text and profile.get("visa_status"):
            return _profile_value(profile, "visa_status"), "text"
        return value, "radio"
    if ("authorized" in text or "authorised" in text or "right to work" in text or "legally eligible to work" in text):
        value = _profile_value(profile, "authorized_to_work")
        return (value, "radio") if value else (None, "unknown")
    if "street address" in text or re.search(r"\baddress line\b|\bhome address\b", text):
        value = _profile_value(profile, "street_address")
        return (value, "text") if value else (None, "unknown")
    if "city" in text or "location" in text or "where are you based" in text:
        return _profile_value(profile, "city_region"), "text"
    if "country" in text:
        return _profile_value(profile, "country"), "select"
    if "current company" in text or "current employer" in text or text == "company":
        return _profile_value(profile, "current_company"), "text"
    if "university" in text or "college" in text or "school name" in text or "institution" in text:
        return _profile_value(profile, "university"), "text"
    if "degree" in text or "education level" in text:
        return _profile_value(profile, "degree"), "select"
    if "graduation year" in text or "year of graduation" in text or "graduating year" in text:
        return _profile_value(profile, "graduation_year"), "select"
    if "years of experience" in text or "experience in years" in text or "total experience" in text:
        return _profile_value(profile, "years_experience"), "text"
    if "notice period" in text or "availability to start" in text:
        return _profile_value(profile, "notice_period"), "select"
    if "salary" in text or "compensation" in text or "ctc" in text or "pay expectation" in text:
        return _profile_value(profile, "expected_salary"), "text"
    if "how did you hear" in text or "source" == text:
        return _profile_value(profile, "application_source") or "Company careers website", "select"
    if "cover letter" in text or "why do you want" in text:
        return _profile_value(profile, "cover_letter_text"), "text"
    if "privacy" in text or "data processing" in text:
        return ("YES", "privacy") if profile.get("accept_privacy_notices") else (None, "consent")
    if "terms and conditions" in text or "terms of service" in text:
        return None, "consent"
    return None, "unknown"


def build_cover_letter(profile: dict[str, Any], job: dict[str, Any], overlap: list[str]) -> str:
    name = " ".join(x for x in (_profile_value(profile, "first_name"), _profile_value(profile, "last_name")) if x)
    role = str(job.get("title", "the role"))
    company = str(job.get("company", "your organization"))
    skills = ", ".join(overlap[:5]) or ", ".join(profile.get("skills", [])[:4])
    project = _profile_value(profile, "project_summary")
    body = (
        "Dear Hiring Team,\n\n"
        "I am applying for the " + role + " position at " + company + ". "
        "My background is in " + (_profile_value(profile, "degree") or "Computer Science and Engineering") +
        ", and the skills most relevant to this opportunity include " + (skills or "software development fundamentals") + ". "
    )
    if project:
        body += "Relevant project experience: " + project.strip() + ". "
    body += (
        "I am interested in contributing to practical engineering work while continuing to grow as a developer. "
        "Thank you for considering my application. I would welcome the opportunity to discuss my background and fit for the role.\n\n"
        "Sincerely,\n" + (name or "Applicant")
    )
    return body


def _field_label(element: dict[str, Any]) -> str:
    return " ".join(str(element.get(k) or "") for k in (
        "labels", "fieldset_label", "legend", "aria_label", "placeholder", "name", "id", "autocomplete"
    )).strip()


def _select_value(locator: Any, requested: str) -> bool:
    if not requested:
        return False
    options = locator.locator("option").evaluate_all("(els) => els.map(e => ({value:e.value, label:(e.label || e.textContent || '').trim()}))")
    wanted = requested.strip().lower()
    for option in options:
        if option["label"].strip().lower() == wanted or option["value"].strip().lower() == wanted:
            locator.select_option(value=option["value"])
            return True
    for option in options:
        label = option["label"].strip().lower()
        if wanted and (wanted in label or label in wanted) and option["value"] != "":
            locator.select_option(value=option["value"])
            return True
    return False


def inspect_and_fill(page: Any, profile: dict[str, Any], resume_path: Path, job: dict[str, Any], match: dict[str, Any], allow_submit: bool) -> tuple[str, str]:
    """Fill safe known fields. Submit only when no required field is unknown."""
    body = page.locator("body").inner_text(timeout=5000)
    if any(term in body.lower() for term in CAPTCHA_TERMS) or page.locator('iframe[src*="captcha" i], iframe[title*="captcha" i], [class*="captcha" i]').count() > 0:
        return "manual_review", "CAPTCHA or anti-bot challenge detected. No attempt was made to bypass it."
    if re.search(r"\b(job|position)\s+(has\s+been\s+)?closed\b|\bno longer accepting applications\b", body, re.I):
        return "closed", "The posting page appears closed or no longer accepting applications."
    full_name = " ".join(x for x in (_profile_value(profile, "first_name"), _profile_value(profile, "last_name")) if x)
    profile["resume_path"] = str(resume_path)
    profile["cover_letter_text"] = build_cover_letter(profile, job, match.get("overlapping_skills", []))
    fields = page.locator("input, textarea, select").evaluate_all("""els => els.map((e, i) => {
      const labels = Array.from(e.labels || []).map(l => (l.innerText || l.textContent || '').trim()).filter(Boolean).join(' ');
      const fs = e.closest('fieldset');
      const legend = fs ? (fs.querySelector('legend')?.innerText || fs.querySelector('legend')?.textContent || '') : '';
      const parent = e.closest('[role=group]');
      const groupLabel = parent ? (parent.getAttribute('aria-label') || parent.innerText || '') : '';
      return {i, tag:e.tagName.toLowerCase(), type:(e.type || '').toLowerCase(), name:e.name || '', id:e.id || '',
        labels, fieldset_label:(legend || groupLabel).trim().slice(0,300), aria_label:e.getAttribute('aria-label') || '',
        placeholder:e.getAttribute('placeholder') || '', autocomplete:e.getAttribute('autocomplete') || '',
        required:!!e.required || e.getAttribute('aria-required') === 'true', disabled:!!e.disabled,
        value:e.value || '', checked:!!e.checked, options:e.tagName==='SELECT'?Array.from(e.options).map(o=>o.text):[]};
    })""")
    locator_all = page.locator("input, textarea, select")
    missing: list[str] = []
    blocked: list[str] = []
    radio_done: set[str] = set()
    for field in fields:
        if field["disabled"] or field["type"] == "hidden":
            continue
        label = _field_label(field)
        field_type = field["type"]
        index = field["i"]
        locator = locator_all.nth(index)
        if field_type in ("submit", "button", "reset", "image"):
            continue
        if field_type == "radio":
            group_key = field["name"] or field.get("fieldset_label") or str(index)
            if group_key in radio_done:
                continue
            radio_done.add(group_key)
            answer, action = map_field(label, profile, full_name)
            group = [x for x in fields if x["type"] == "radio" and (x["name"] or x.get("fieldset_label") or str(x["i"])) == group_key]
            if action == "sensitive":
                if any(x["required"] for x in group):
                    blocked.append(label or group_key)
                continue
            if action == "consent":
                blocked.append(label or group_key)
                continue
            if answer is None:
                if any(x["required"] for x in group):
                    missing.append(label or group_key)
                continue
            matched = None
            wanted = str(answer).strip().lower()
            for option in group:
                option_text = (str(option.get("labels","")) + " " + str(option.get("value",""))).strip().lower()
                if wanted == option_text or wanted in option_text or option_text in wanted:
                    matched = option
                    break
            if matched:
                locator_all.nth(matched["i"]).check(timeout=3000)
            elif any(x["required"] for x in group):
                missing.append(label or group_key)
            continue

        answer, action = map_field(label, profile, full_name)
        if field_type == "file":
            if not answer and ("resume" in label.lower() or "cv" in label.lower()):
                answer = str(resume_path)
                action = "file"
            if answer and Path(answer).exists() and ("resume" in label.lower() or "cv" in label.lower() or field["required"]):
                try:
                    locator.set_input_files(answer, timeout=5000)
                except Exception:
                    if field["required"]:
                        missing.append(label or field["name"] or "required upload")
            elif field["required"]:
                missing.append(label or field["name"] or "required file upload")
            continue
        if field_type == "checkbox":
            label_lower = label.lower()
            if action == "privacy" and profile.get("accept_privacy_notices"):
                try:
                    locator.check(timeout=2500)
                except Exception:
                    if field["required"]:
                        blocked.append(label or "privacy consent")
            elif action == "consent" or any(t in label_lower for t in ("terms and conditions", "terms of service", "certify that", "i certify")):
                if field["required"]:
                    blocked.append(label or "required legal acknowledgement")
            elif field["required"] and not field["checked"]:
                blocked.append(label or field["name"] or "required checkbox")
            continue
        if action == "sensitive":
            if field["required"] and not field["value"]:
                blocked.append(label or field["name"] or "required sensitive question")
            continue
        if action in ("consent", "unknown"):
            if field["required"] and not field["value"]:
                missing.append(label or field["name"] or "required unanswered field")
            continue
        if action == "file":
            answer = str(resume_path)
            try:
                locator.set_input_files(answer, timeout=5000)
            except Exception:
                if field["required"]:
                    missing.append(label or "resume upload")
            continue
        if not answer:
            if field["required"] and not field["value"]:
                missing.append(label or field["name"] or "required field")
            continue
        try:
            if field_type == "select-one" or field["tag"] == "select":
                ok = _select_value(locator, str(answer))
                if not ok and field["required"] and not field["value"]:
                    missing.append(label or field["name"] or "required select")
            elif field_type in ("checkbox", "radio"):
                pass
            else:
                locator.fill(str(answer), timeout=3000)
        except Exception:
            if field["required"]:
                missing.append(label or field["name"] or "required field")
    if blocked:
        return "manual_review", "Manual review required for privacy/terms, demographic, or required legal acknowledgements: " + "; ".join(dict.fromkeys(blocked))[:500]
    if missing:
        return "manual_review", "Required fields could not be safely answered: " + "; ".join(dict.fromkeys(missing))[:700]
    if not allow_submit:
        return "ready_dry_run", "Form fields filled in dry-run mode; nothing was submitted."
    # Submit only an unambiguous application-submit control. Never click generic Apply/Next buttons.
    candidates = page.get_by_role("button", name=re.compile(r"^(submit application|submit your application|send application|finish application|submit)$", re.I))
    if candidates.count() == 0:
        candidates = page.locator('button[type="submit"], input[type="submit"]')
    if candidates.count() == 0:
        return "manual_review", "All known fields were filled, but no clear submit button was found."
    try:
        candidates.first.click(timeout=6000)
        page.wait_for_timeout(1800)
        new_body = page.locator("body").inner_text(timeout=5000).lower()
        if any(term in new_body for term in SUCCESS_TERMS):
            return "submitted", "The site displayed an application-received/thank-you confirmation."
        if any(term in new_body for term in CAPTCHA_TERMS):
            return "manual_review", "A security challenge appeared at submission. No attempt was made to bypass it."
        return "submission_uncertain", "The submit control was clicked, but the site did not show a clear success confirmation. Verify manually before retrying."
    except Exception as exc:
        return "manual_review", "Submission could not be completed: " + str(exc)[:350]


def application_log() -> dict[str, Any]:
    return load_json(LOG_PATH, {"applications": []})


def already_applied(log: dict[str, Any], url: str) -> bool:
    key = canonical_url(url)
    done_statuses = {"submitted", "submission_uncertain"}
    for item in log.get("applications", []):
        if item.get("status") not in done_statuses:
            continue
        known_urls = [
            canonical_url(item.get("application_key", "")),
            canonical_url(item.get("apply_url", "")),
            canonical_url(item.get("job_url", "")),
            canonical_url(item.get("posting_url", ""))
        ]
        if key and key in known_urls:
            return True
    return False


def send_email_report(subject: str, body: str, env: dict[str, str]) -> tuple[bool, str]:
    required = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "REPORT_TO")
    missing = [key for key in required if not env.get(key)]
    if missing:
        return False, "Email not configured; missing " + ", ".join(missing) + ". Configure the local settings in Job Scout."
    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = env.get("REPORT_FROM") or env["SMTP_USERNAME"]
    message["To"] = env["REPORT_TO"]
    message.set_content(body)
    port = int(env.get("SMTP_PORT", "587"))
    timeout = 25
    try:
        if port == 465:
            with smtplib.SMTP_SSL(env["SMTP_HOST"], port, timeout=timeout, context=ssl.create_default_context()) as server:
                server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
                server.send_message(message)
        else:
            with smtplib.SMTP(env["SMTP_HOST"], port, timeout=timeout) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
                server.send_message(message)
        return True, "Email report sent to " + env["REPORT_TO"]
    except Exception as exc:
        return False, "Email sending failed: " + str(exc)[:300]


def format_report(run_mode: str, outcomes: list[dict[str, Any]], started: str, ended: str, email_note: str = "") -> str:
    counts: dict[str, int] = {}
    for item in outcomes:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    lines = [
        "JOB SCOUT — APPLICATION REPORT", "=" * 36, "Mode: " + run_mode,
        "Started: " + started, "Finished: " + ended, "",
        "Summary: " + ", ".join(f"{count} {status.replace('_',' ')}" for status, count in sorted(counts.items())),
        "", "IMPORTANT: 'Submitted' means the application page showed a receipt/thank-you signal. 'Submission uncertain' requires manual verification. This report is not a receipt from the employer.",
        ""
    ]
    if not outcomes:
        lines.append("No eligible unprocessed jobs met the configured resume-match threshold.")
    for item in outcomes:
        lines += [
            "- [" + item["status"].upper().replace("_", " ") + "] " + item.get("title", "Untitled") + " — " + item.get("company", "Unknown company"),
            "  Location: " + item.get("location", "Not disclosed"),
            "  Resume fit: " + str(item.get("resume_match_score", "N/A")) + "%",
            "  Matched skills: " + (", ".join(item.get("overlapping_skills", [])) or "None detected"),
            "  Reason: " + item.get("message", ""),
            "  Official application: " + item.get("apply_url", ""),
            ""
        ]
    if email_note:
        lines += ["Email: " + email_note, ""]
    return "\n".join(lines)


def run_agent(submit: bool, jobs_file: str | None = None, max_applications: int = 5) -> tuple[list[dict[str, Any]], str]:
    APP_HOME.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    profile = load_json(PROFILE_PATH, {})
    if not profile:
        raise RuntimeError("Candidate profile not found. Open local_app.py and save your profile first.")
    if not profile.get("resume_path"):
        raise RuntimeError("Resume path is not configured. Upload your resume in local_app.py first.")
    resume_path = Path(profile["resume_path"]).expanduser().resolve()
    resume_text = extract_resume_text(resume_path)
    if len(resume_text.strip()) < 80:
        raise RuntimeError("Could not extract enough text from the resume. Try a text-based PDF or DOCX.")
    if submit and not profile.get("auto_apply_enabled", False):
        raise RuntimeError("Auto-submit is disabled in your local profile. Enable it in the local app after reviewing your details.")
    data = fetch_jobs(jobs_file)
    jobs = data.get("jobs", [])
    candidate_skills = detected_skills(resume_text + " " + " ".join(profile.get("skills", [])))
    if len(candidate_skills) < 2:
        raise RuntimeError("The resume parser found fewer than two known skills. Check that the resume is text-based and readable.")
    log = application_log()
    records: list[dict[str, Any]] = []
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    minimum = int(profile.get("minimum_match_score", 65))
    for job in jobs:
        url = job.get("apply_url") or job.get("job_url") or ""
        if not url.startswith("https://"):
            continue
        match = fit_job(job, resume_text, profile)
        if match["resume_match_score"] < minimum:
            continue
        if not match["location_match"]:
            continue
        if already_applied(log, url):
            continue
        candidates.append((job, match))
    candidates.sort(key=lambda item: item[1]["resume_match_score"], reverse=True)
    candidates = candidates[:max(1, max_applications)]
    if not candidates:
        started_empty = now_iso()
        ended_empty = now_iso()
        report = format_report("AUTO-SUBMIT" if submit else "DRY RUN — NO APPLICATIONS SENT", [], started_empty, ended_empty)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        empty_report_path = REPORT_DIR / ("report-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".txt")
        empty_report_path.write_text(report, encoding="utf-8")
        mail_ok, mail_note = send_email_report("Job Scout application report — " + datetime.now().strftime("%d %b %Y"), report, read_env())
        report += "\\n" + mail_note + "\\n"
        print(report)
        return [], report

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Browser automation is not installed. Run: pip install -r requirements-auto-apply.txt; then python -m playwright install chromium") from exc

    started = now_iso()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("JOBSCOUT_HEADLESS", "true").lower() != "false")
        context = browser.new_context(accept_downloads=False)
        page = context.new_page()
        for job, match in candidates:
            url = job.get("apply_url") or job.get("job_url")
            item = {
                "job_url": url, "apply_url": url, "application_key": canonical_url(url),
                "posting_url": job.get("job_url") or url,
                "company": job.get("company", "Unknown"), "title": job.get("title", "Untitled"),
                "location": job.get("location", "Not disclosed"), "resume_match_score": match["resume_match_score"],
                "overlapping_skills": match["overlapping_skills"], "status": "pending", "message": ""
            }
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1200)
                status, message = inspect_and_fill(page, profile, resume_path, job, match, submit)
                item["status"] = status
                item["message"] = message
                item["processed_at"] = now_iso()
                if status in ("submitted", "submission_uncertain"):
                    item["application_ref"] = "Verify on employer portal/email; Job Scout does not receive an ATS record ID."
                # Persist after each role in case the process is interrupted.
                log.setdefault("applications", []).append(item)
                save_json(LOG_PATH, log)
                records.append(item)
                print(status.upper() + ": " + item["title"] + " — " + item["company"] + " — " + message)
                if status in ("submitted", "submission_uncertain", "manual_review", "closed"):
                    # Stop at the first manual intervention requirement rather than silently trying other forms.
                    if status == "manual_review":
                        break
            except Exception as exc:
                item["status"] = "error"
                item["message"] = str(exc)[:400]
                item["processed_at"] = now_iso()
                log.setdefault("applications", []).append(item)
                save_json(LOG_PATH, log)
                records.append(item)
            time.sleep(2)
        context.close()
        browser.close()

    ended = now_iso()
    mode = "AUTO-SUBMIT" if submit else "DRY RUN — NO APPLICATIONS SENT"
    report = format_report(mode, records, started, ended)
    report_path = REPORT_DIR / ("report-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".txt")
    report_path.write_text(report, encoding="utf-8")
    env = read_env()
    mail_ok, mail_note = send_email_report("Job Scout application report — " + datetime.now().strftime("%d %b %Y"), report, env)
    report += "\n" + mail_note + "\n"
    print(report)
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Job Scout's local resume-aware application runner.")
    parser.add_argument("--submit", action="store_true", help="Submit applications only when auto-submit is enabled in your local profile.")
    parser.add_argument("--dry-run", action="store_true", help="Fill supported forms without submitting (default).")
    parser.add_argument("--jobs-file", help="Use a local jobs.json instead of the latest public feed.")
    parser.add_argument("--max-applications", type=int, default=5, help="Limit the number of roles processed in one run (default: 5).")
    parser.add_argument("--test-email", action="store_true", help="Send a test email using local SMTP settings.")
    args = parser.parse_args()
    APP_HOME.mkdir(parents=True, exist_ok=True)
    if args.test_email:
        ok, note = send_email_report("Job Scout test email", "Your Job Scout email configuration is working.", read_env())
        print(note)
        return 0 if ok else 1
    try:
        run_agent(submit=args.submit and not args.dry_run, jobs_file=args.jobs_file, max_applications=args.max_applications)
        return 0
    except (RuntimeError, FileNotFoundError, ValueError, HTTPError, URLError) as exc:
        print("Job Scout stopped safely: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
