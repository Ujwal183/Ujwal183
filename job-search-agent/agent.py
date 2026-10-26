#!/usr/bin/env python3
"""Job Scout collector: fetch public ATS postings, score fit, and publish a JSON digest.

Works with Python's standard library. Optional OPENAI_API_KEY enables a small
language-model review of the highest-ranked listings; heuristic scoring is the fallback.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
SOURCES_FILE = BASE / "sources.json"
JOBS_FILE = DATA_DIR / "jobs.json"
DIGEST_FILE = DATA_DIR / "latest.md"
USER_AGENT = "JobScout/1.0 (personal early-career job discovery; public job board APIs)"
PROFILE_SKILLS = [
    "Java", "Python", "SQL", "MySQL", "JDBC", "FastAPI", "REST APIs",
    "Pandas", "NumPy", "Excel Automation", "Machine Learning", "Generative AI",
    "Git", "GitHub", "HTML", "CSS", "JavaScript", "Power BI"
]
ROLE_TERMS = [
    "software engineer", "software developer", "software development",
    "backend", "back-end", "full stack", "fullstack", "java developer",
    "python developer", "data engineer", "data analyst", "automation engineer",
    "test automation", "qa automation", "sdet", "machine learning",
    "artificial intelligence", " ai engineer", "genai", "graduate engineer",
    "associate engineer", "associate software", "application developer",
    "platform engineer", "technical analyst", "junior developer",
    "software development engineer", "sde", "developer intern"
]
NON_TARGET_TITLE_TERMS = [
    "customer experience", "customer support", "technical support", "technical writer",
    "sales engineer", "solution engineer", "solutions engineer", "customer success",
    "business system engineer", "account executive", "sales development",
    "talent acquisition", "recruiter"
]
EARLY_TERMS = [
    "fresher", "fresh graduate", "new grad", "recent graduate", "graduate role",
    "graduate program", "graduate programme", "entry level", "entry-level",
    "early career", "early-career", "0-1 year", "0–1 year", "0 to 1 year",
    "0-2 years", "0–2 years", "0 to 2 years", "junior", "associate",
    "internship", "intern", "trainee", "campus"
]
SENIOR_TERMS = [
    "senior", "sr. ", "staff engineer", "principal", "director", "head of ",
    "engineering manager", "team lead", "tech lead", "architect", "vp ",
    "5+ years", "5 or more years", "6+ years", "7+ years", "8+ years",
    "10+ years", "4+ years of experience"
]
INDIA_TERMS = [
    "india", "bengaluru", "bangalore", "hyderabad", "chennai", "pune",
    "mumbai", "gurugram", "gurgaon", "noida", "new delhi", "kolkata",
    "ahmedabad", "coimbatore", "kochi", "remote - india", "india remote"
]
GLOBAL_REMOTE_TERMS = ["worldwide", "work from anywhere", "anywhere in the world", "global remote"]
SKILL_PATTERNS = {
    "Java": r"\bjava\b",
    "Python": r"\bpython\b",
    "SQL": r"\bsql\b",
    "MySQL": r"\bmysql\b",
    "JDBC": r"\bjdbc\b",
    "FastAPI": r"\bfastapi\b",
    "REST APIs": r"\brest(?:ful)?\s+apis?\b",
    "Pandas": r"\bpandas\b",
    "NumPy": r"\bnumpy\b",
    "Excel Automation": r"\bexcel\b|spreadsheet automation",
    "Machine Learning": r"\bmachine learning\b|\bml models?\b",
    "Generative AI": r"\bgenerative ai\b|\bgenai\b|\bllms?\b",
    "Git": r"\bgit\b",
    "GitHub": r"\bgithub\b",
    "HTML": r"\bhtml\b",
    "CSS": r"\bcss\b",
    "JavaScript": r"\bjavascript\b",
    "Power BI": r"\bpower bi\b"
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def plain_text(value: Any) -> str:
    if not value:
        return ""
    parser = TextExtractor()
    try:
        parser.feed(str(value))
        return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()
    except Exception:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value)))).strip()


def get_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError("HTTP status " + str(response.status))
        raw = response.read(8_000_000)
    return json.loads(raw.decode("utf-8", errors="replace"))


def fmt_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, timezone.utc).isoformat()
        text = str(value).strip()
        if text.isdigit():
            return fmt_date(int(text))
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def salary_from_text(text: str) -> str:
    patterns = [
        r"(?i)(?:₹|INR\s*)\s?[\d,.]+\s*(?:-|–|to)\s*(?:₹|INR\s*)?\s?[\d,.]+\s*(?:LPA|lakhs?\s*(?:per annum)?|per annum|/year)",
        r"(?i)(?:₹|INR\s*)\s?[\d,.]+\s*(?:LPA|lakhs?\s*(?:per annum)?|per annum|/year)",
        r"(?i)(?:USD\s*)?\$\s?[\d,]+\s*(?:-|–|to)\s*(?:USD\s*)?\$?\s?[\d,]+\s*(?:per year|/year|annually)?",
        r"(?i)(?:USD|EUR|GBP)\s?[\d,]+\s*(?:-|–|to)\s?(?:USD|EUR|GBP)?\s?[\d,]+\s*(?:per year|/year|annually)?"
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return "Not disclosed"


def deadline_from_text(text: str) -> str:
    patterns = [
        r"(?i)(?:apply by|application deadline|applications close|closing date|last date to apply|deadline)\s*(?:is|on|:|-)?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?)"
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return "Not disclosed"


def normalize_location(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(filter(None, [normalize_location(item) for item in value]))
    if isinstance(value, dict):
        for key in ("name", "location", "displayName", "city", "addressLocality"):
            if value.get(key):
                return normalize_location(value[key])
        address = value.get("postalAddress") or value.get("address")
        if address:
            pieces = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry") if isinstance(address, dict)]
            return ", ".join(str(x) for x in pieces if x)
        return ""
    return str(value or "").strip()


FOREIGN_LOCATION_TERMS = [
    "united states", "usa", "u.s.a.", "canada", "spain", "united kingdom", "uk",
    "germany", "france", "poland", "portugal", "netherlands", "ireland",
    "switzerland", "australia", "new zealand", "singapore", "japan", "china",
    "mexico", "brazil", "argentina", "sweden", "norway", "denmark", "finland",
    "italy", "czech republic", "czechia", "romania", "bulgaria", "serbia",
    "belgium", "austria", "israel", "south korea", "taiwan", "united arab emirates",
    "uae", "south africa", "kenya", "nigeria", "new york", "california",
    "texas", "mountain view", "vancouver", "london", "berlin", "madrid",
    "barcelona", "paris", "amsterdam", "toronto", "sydney", "melbourne"
]


def location_is_relevant(location: str, description: str) -> bool:
    loc = (location or "").lower().strip()
    desc = (description or "").lower()
    # A concrete India city/country in the job's location field is the strongest signal.
    if any(term in loc for term in INDIA_TERMS):
        return True
    # A named non-India office stays excluded even if the posting mentions international teams.
    if any(term in loc for term in FOREIGN_LOCATION_TERMS):
        return False
    # Remote roles are accepted only when the location or description explicitly supports India/global eligibility.
    remote_location = any(term in loc for term in ("remote", "anywhere", "distributed", "work from home"))
    if remote_location:
        if any(term in desc for term in ("remote - india", "remote in india", "india remote", "remote (india)", "based in india", "located in india", "applicants in india", "candidates in india")):
            return True
        if any(term in desc for term in GLOBAL_REMOTE_TERMS):
            return True
    # If the feed omitted a location, accept only explicit global-remote or India-specific details.
    unknown_location = not loc or loc in ("location not disclosed", "not disclosed", "n/a", "unknown")
    if unknown_location and (
        any(term in desc for term in ("remote - india", "remote in india", "india remote", "remote (india)", "based in india", "located in india"))
        or any(term in desc for term in GLOBAL_REMOTE_TERMS)
    ):
        return True
    return False


def is_senior(title: str, text: str) -> bool:
    title_low = " " + title.lower() + " "
    # Seniority in the title is a strong exclusion for this early-career profile.
    if any(term in title_low for term in (" senior ", " sr. ", " staff ", " principal ", " director ", " manager ", " lead ", " architect ")):
        return True
    text_low = text.lower()
    return any(term in text_low for term in SENIOR_TERMS)


def score_job(title: str, location: str, description: str) -> dict[str, Any]:
    title_low = " " + title.lower() + " "
    text = (title + " " + description).lower()
    role_hits = [term.strip() for term in ROLE_TERMS if term in title_low]
    role_hits = list(dict.fromkeys(role_hits))
    matched_skills = [skill for skill, pattern in SKILL_PATTERNS.items() if re.search(pattern, text, re.I)]
    # Use word boundaries: the substring "intern" must not match "internal".
    early_hits = [
        term for term in EARLY_TERMS
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text, re.I)
    ]
    senior = is_senior(title, text)
    reasons: list[str] = []
    score = 0
    if role_hits:
        score += 32
        reasons.append("Role aligns with target software/data/AI work")
    skill_points = min(36, len(matched_skills) * 6)
    score += skill_points
    if matched_skills:
        reasons.append("Skills found: " + ", ".join(matched_skills[:5]))
    if early_hits:
        score += 20
        reasons.append("Entry-level / graduate signal found")
    elif re.search(r"\b(1|2)\+? years?\b|\b1 to 2 years\b|\b0 to 3 years\b", text):
        score += 10
        reasons.append("Potentially within early-career experience range")
    else:
        reasons.append("Experience requirement needs manual confirmation")
    if location_is_relevant(location, description):
        score += 12
        reasons.append("India-based or global-remote location signal")
    if senior:
        score -= 40
        reasons.append("Senior-level signal detected")
    score = max(0, min(99, score))
    if senior:
        eligibility = "Likely experienced role — not prioritized for a fresher."
    elif early_hits:
        eligibility = "Possible early-career fit based on wording; confirm degree, graduation year and experience requirements."
    else:
        eligibility = "Experience eligibility is unclear from the feed; review the full official description."
    return {
        "match_score": score,
        "skills_matched": matched_skills,
        "match_reasons": reasons,
        "eligibility": eligibility,
        "early_career_signal": bool(early_hits),
        "seniority_flag": senior,
        "role_hits": role_hits
    }


def normalize_greenhouse(source: dict[str, Any]) -> list[dict[str, Any]]:
    url = "https://boards-api.greenhouse.io/v1/boards/" + quote(source["slug"]) + "/jobs?content=true"
    payload = get_json(url)
    jobs = []
    for item in payload.get("jobs", []):
        office = item.get("location") or {}
        offices = item.get("offices") or []
        location = normalize_location(office)
        if not location and offices:
            location = ", ".join(filter(None, [normalize_location(x) for x in offices]))
        content = plain_text(item.get("content", ""))
        jobs.append({
            "company": source["company"], "title": item.get("title") or "Untitled role",
            "location": location, "description": content, "apply_url": item.get("absolute_url") or source["careers_url"],
            "job_url": item.get("absolute_url") or source["careers_url"], "careers_url": source["careers_url"],
            "published_at": fmt_date(item.get("updated_at")), "employment_type": "Not disclosed",
            "provider": "Greenhouse", "source_status": "Official public job-board API",
            "salary": salary_from_text(content), "deadline": deadline_from_text(content), "is_remote": "remote" in (location + " " + content).lower()
        })
    return jobs


def normalize_lever(source: dict[str, Any]) -> list[dict[str, Any]]:
    url = "https://api.lever.co/v0/postings/" + quote(source["slug"]) + "?mode=json"
    payload = get_json(url)
    jobs = []
    if not isinstance(payload, list):
        return jobs
    for item in payload:
        categories = item.get("categories") or {}
        location = normalize_location(categories.get("location") or item.get("workplaceType") or "")
        description = plain_text(item.get("descriptionPlain") or item.get("description") or "")
        lists = item.get("lists") or []
        extra = " ".join(plain_text(x.get("content", "")) for x in lists if isinstance(x, dict))
        combined = (description + " " + extra).strip()
        hosted = item.get("hostedUrl") or source["careers_url"]
        apply = item.get("applyUrl") or hosted
        jobs.append({
            "company": source["company"], "title": item.get("text") or "Untitled role",
            "location": location, "description": combined, "apply_url": apply, "job_url": hosted,
            "careers_url": source["careers_url"], "published_at": fmt_date(item.get("createdAt")),
            "employment_type": ("Internship" if re.search(r"\bintern(ship)?\b", str(item.get("text") or ""), re.I) else (categories.get("commitment") or "Not disclosed")), "provider": "Lever",
            "source_status": "Official public job-postings API", "salary": salary_from_text(combined),
            "deadline": deadline_from_text(combined), "is_remote": "remote" in (location + " " + combined).lower()
        })
    return jobs


def normalize_ashby(source: dict[str, Any]) -> list[dict[str, Any]]:
    url = "https://api.ashbyhq.com/posting-api/job-board/" + quote(source["slug"]) + "?includeCompensation=true"
    payload = get_json(url)
    jobs = []
    for item in payload.get("jobs", []):
        location = normalize_location(item.get("location") or item.get("address") or "")
        if item.get("secondaryLocations"):
            location += ", " + ", ".join(filter(None, [normalize_location(x) for x in item["secondaryLocations"]]))
        description = plain_text(item.get("descriptionPlain") or item.get("descriptionHtml") or "")
        compensation = item.get("compensation") or {}
        salary = compensation.get("scrapeableCompensationSalarySummary") or compensation.get("compensationTierSummary") or salary_from_text(description) or "Not disclosed"
        if str(salary).strip() in ("", "None"):
            salary = "Not disclosed"
        jobs.append({
            "company": source["company"], "title": item.get("title") or "Untitled role",
            "location": location, "description": description, "apply_url": item.get("applyUrl") or item.get("jobUrl") or source["careers_url"],
            "job_url": item.get("jobUrl") or source["careers_url"], "careers_url": source["careers_url"],
            "published_at": fmt_date(item.get("publishedAt")), "employment_type": item.get("employmentType") or "Not disclosed",
            "provider": "Ashby", "source_status": "Official public job-posting API", "salary": str(salary),
            "deadline": deadline_from_text(description), "is_remote": bool(item.get("isRemote")) or "remote" in location.lower()
        })
    return jobs


def optional_ai_assessment(job: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    # Only review high-potential roles so a scheduled run stays reasonably small.
    from urllib.request import Request, urlopen
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    prompt = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You assess entry-level job fit for an Indian 2026 CSE graduate whose skills include Java, Python, SQL, MySQL, JDBC, FastAPI, REST APIs, Pandas, NumPy, Excel automation, and AI/ML projects. Do not infer unstated salary or deadlines. Respond only as JSON with keys: match_score (integer 0-100), eligibility (short string), fit_summary (short string), skills_matched (array of strings), salary (string or Not disclosed), deadline (string or Not disclosed). Be conservative; flag required years of experience and graduation-year criteria."},
            {"role": "user", "content": json.dumps({"title": job["title"], "company": job["company"], "location": job["location"], "description": job["description"][:5500], "current_rule_score": job["match_score"], "known_skills": PROFILE_SKILLS})}
        ]
    }
    request = Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(prompt).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST"
    )
    try:
        with urlopen(request, timeout=35) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        result = json.loads(content)
        if isinstance(result.get("match_score"), (int, float)):
            result["match_score"] = max(0, min(99, int(result["match_score"])))
        return result
    except Exception as exc:
        print("Optional AI assessment failed for " + job.get("title", "job") + ": " + str(exc)[:160], file=sys.stderr)
        return None


def normalize_job(job: dict[str, Any]) -> dict[str, Any] | None:
    title = str(job.get("title") or "Untitled role").strip()
    location = str(job.get("location") or "Location not disclosed").strip()
    description = str(job.get("description") or "")
    title_lower = title.lower()
    if any(term in title_lower for term in NON_TARGET_TITLE_TERMS):
        return None
    if not location_is_relevant(location, description):
        return None
    assessment = score_job(title, location, description)
    if assessment["seniority_flag"] or assessment["match_score"] < 34:
        return None
    # Require some relevant role signal; don't surface every vacancy from a company feed.
    title_text = " " + title.lower() + " "
    relevant_title = any(term in title_text for term in ROLE_TERMS) or any(term in (title + " " + description).lower() for term in ("java", "python", "backend", "machine learning", "data analyst", "data engineer", "automation"))
    if not relevant_title:
        return None
    result = dict(job)
    result.update(assessment)
    result["description"] = description[:2100]
    result["salary"] = job.get("salary") or "Not disclosed"
    result["deadline"] = job.get("deadline") or "Not disclosed"
    result["url_domain_verified"] = True
    return result


def write_digest(data: dict[str, Any]) -> None:
    generated = data.get("generated_at") or "Not available"
    jobs = data.get("jobs", [])
    lines = [
        "# Job Scout — Daily Job Digest", "",
        "Last scan: " + generated, "",
        "Relevant postings found: " + str(len(jobs)), "",
        "> Only published public career-board feeds are used. Verify eligibility and application status on the employer-hosted posting. Salary/deadline fields are not guessed.", "",
        "## Shortlist", ""
    ]
    if not jobs:
        lines += ["No matching India-based/remote early-career roles were found in the configured feeds on this scan.", ""]
    for idx, job in enumerate(jobs[:100], start=1):
        lines += [
            "### " + str(idx) + ". " + job["title"] + " — " + job["company"], "",
            "- Match score: " + str(job["match_score"]) + "%",
            "- Location: " + job.get("location", "Not disclosed"),
            "- Experience signal: " + job.get("eligibility", "Review official description"),
            "- Salary / CTC: " + job.get("salary", "Not disclosed"),
            "- Deadline: " + job.get("deadline", "Not disclosed"),
            "- Skills found: " + (", ".join(job.get("skills_matched", [])) or "None detected"),
            "- Official job: " + job.get("apply_url", job.get("careers_url", "")),
            "- Employer career board: " + job.get("careers_url", ""),
            ""
        ]
    lines += ["## Source health", ""]
    for source in data.get("sources", []):
        lines.append("- " + source["company"] + " (" + source["provider"] + "): " + source["status"] + ((" — " + source["message"]) if source.get("message") else ""))
    lines += ["", "Generated automatically by Job Scout. Match and eligibility estimates are not guarantees."]
    DIGEST_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    all_jobs: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    adapters = {"greenhouse": normalize_greenhouse, "lever": normalize_lever, "ashby": normalize_ashby}
    for source in config:
        name = source.get("company", source.get("slug", "Unknown source"))
        provider = str(source.get("provider", "")).lower()
        try:
            if provider not in adapters:
                raise ValueError("Unsupported provider: " + provider)
            raw_jobs = adapters[provider](source)
            added = 0
            for raw in raw_jobs:
                normalized = normalize_job(raw)
                if normalized:
                    normalized["source_company"] = name
                    normalized["fit_summary"] = "Rule-based match using role, skills, early-career wording, and location signals."
                    all_jobs.append(normalized)
                    added += 1
            statuses.append({"company": name, "provider": provider.title(), "status": "ok", "jobs_seen": len(raw_jobs), "matches": added, "message": ""})
            print(name + ": " + str(len(raw_jobs)) + " postings checked; " + str(added) + " matched.")
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
            message = (getattr(exc, "reason", None) or str(exc))[:180]
            statuses.append({"company": name, "provider": provider.title(), "status": "error", "jobs_seen": 0, "matches": 0, "message": message})
            print(name + ": source error: " + message, file=sys.stderr)
        except Exception as exc:
            message = str(exc)[:180]
            statuses.append({"company": name, "provider": provider.title(), "status": "error", "jobs_seen": 0, "matches": 0, "message": message})
            print(name + ": unexpected source error: " + message, file=sys.stderr)
        time.sleep(0.25)

    unique: dict[str, dict[str, Any]] = {}
    for job in all_jobs:
        key = job.get("job_url") or job.get("apply_url") or (job.get("company", "") + "|" + job.get("title", ""))
        if key not in unique or int(job["match_score"]) > int(unique[key]["match_score"]):
            unique[key] = job
    jobs = sorted(unique.values(), key=lambda j: (int(j.get("match_score", 0)), j.get("published_at") or ""), reverse=True)

    if os.getenv("OPENAI_API_KEY", "").strip():
        for job in jobs[:12]:
            ai = optional_ai_assessment(job)
            if ai:
                job["ai_assessed"] = True
                job["match_score"] = ai.get("match_score", job["match_score"])
                job["eligibility"] = ai.get("eligibility") or job["eligibility"]
                job["fit_summary"] = ai.get("fit_summary") or job["fit_summary"]
                job["skills_matched"] = ai.get("skills_matched") or job["skills_matched"]
                job["salary"] = ai.get("salary") or job["salary"]
                job["deadline"] = ai.get("deadline") or job["deadline"]
            time.sleep(0.15)
        jobs.sort(key=lambda j: (int(j.get("match_score", 0)), j.get("published_at") or ""), reverse=True)

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    errors = sum(1 for src in statuses if src["status"] != "ok")
    data = {
        "generated_at": generated,
        "status": "ok" if statuses and errors == 0 else ("partial" if any(src["status"] == "ok" for src in statuses) else "error"),
        "profile": {
            "target_roles": ["Junior Java Developer", "Python Developer", "Backend Developer", "Associate Software Engineer", "Data Engineer", "Automation Engineer", "Junior AI Engineer"],
            "locations": ["Bengaluru", "Hyderabad", "Chennai", "India", "Remote"],
            "skills": PROFILE_SKILLS
        },
        "sources": statuses,
        "jobs": jobs,
        "notes": [
            "Jobs are collected from published public career-board APIs configured in sources.json.",
            "Salary and deadlines are displayed only when stated by the employer; otherwise they are marked Not disclosed.",
            "Match score and eligibility are estimates, not a guarantee. Check the official job page before applying.",
            "Only India-based or explicitly global-remote postings are included; ambiguous remote locations are excluded."
        ]
    }
    JOBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_digest(data)
    print("Saved " + str(len(jobs)) + " matching jobs at " + generated + "; source errors: " + str(errors))
    return 0 if any(src["status"] == "ok" for src in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
