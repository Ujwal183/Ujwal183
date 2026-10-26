from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from apply_agent import APP_HOME, ENV_PATH, LOG_PATH, PROFILE_PATH, read_env, save_json

st.set_page_config(page_title="Job Scout Auto-Apply Setup", page_icon="🧭", layout="wide")
st.markdown("""
<style>
.stApp { background: #0b1220; color: #eef4ff; }
h1, h2, h3 { letter-spacing: -0.04em; }
[data-testid="stMetric"] { background:#142035; border:1px solid #28374d; padding:18px; border-radius:14px; }
div.stButton>button, div.stFormSubmitButton>button { border-radius:10px; min-height:2.8rem; font-weight:700; }
[data-testid="stAlert"] { border-radius:12px; }
</style>
""", unsafe_allow_html=True)

st.title("🧭 Job Scout — Resume-aware Auto-Apply")
st.caption("Your resume, candidate profile, mail settings and application history stay on this computer. Only the job postings are fetched from the public Job Scout feed.")
st.warning("This is a local application assistant. It does not bypass CAPTCHA or anti-bot controls, invent answers, or answer unknown mandatory questions. Those applications are stopped for manual review.")

profile = {}
if PROFILE_PATH.exists():
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        profile = {}
env = read_env()
APP_HOME.mkdir(parents=True, exist_ok=True)

if LOG_PATH.exists():
    try:
        history = json.loads(LOG_PATH.read_text(encoding="utf-8")).get("applications", [])
    except Exception:
        history = []
else:
    history = []
applied_count = sum(1 for item in history if item.get("status") == "submitted")
pending_count = sum(1 for item in history if item.get("status") in ("manual_review", "submission_uncertain"))
col1, col2, col3 = st.columns(3)
col1.metric("Confirmed submission signals", applied_count)
col2.metric("Manual review / needs attention", pending_count)
col3.metric("Private application records", len(history))
st.divider()

def value(key: str, default: str = "") -> str:
    v = profile.get(key, default)
    return "" if v is None else str(v)

st.subheader("1. Resume and candidate details")
st.markdown("Upload the resume you want the agent to use. Fill required answers accurately; the agent will not infer legal work eligibility, sponsorship, or private demographic answers.")
with st.form("profile_form", clear_on_submit=False):
    upload = st.file_uploader("Resume file (PDF, DOCX, TXT or MD)", type=["pdf", "docx", "txt", "md"], help="The file is saved in your local user folder, not in the public GitHub repository.")
    c1, c2 = st.columns(2)
    with c1:
        first_name = st.text_input("First / given name *", value=value("first_name"))
        last_name = st.text_input("Last / family name *", value=value("last_name"))
        email = st.text_input("Application email *", value=value("email"))
        phone = st.text_input("Phone number *", value=value("phone"))
        city_region = st.text_input("City / region", value=value("city_region", "Bengaluru, Karnataka, India"))
        country = st.text_input("Country", value=value("country", "India"))
        street_address = st.text_input("Street address (only needed if a form requires it)", value=value("street_address"))
        university = st.text_input("University / college", value=value("university", "Mohan Babu University"))
    with c2:
        degree = st.text_input("Degree", value=value("degree", "B.Tech — Computer Science and Engineering"))
        graduation_year = st.text_input("Graduation year", value=value("graduation_year", "2026"))
        years_experience = st.text_input("Relevant experience in years (enter what is accurate)", value=value("years_experience"))
        current_company = st.text_input("Current / most recent company", value=value("current_company"))
        linkedin_url = st.text_input("LinkedIn profile URL", value=value("linkedin_url"))
        github_url = st.text_input("GitHub URL", value=value("github_url", "https://github.com/Ujwal183"))
        portfolio_url = st.text_input("Portfolio URL", value=value("portfolio_url"))
        project_summary = st.text_input("Relevant project summary (optional)", value=value("project_summary"))

    st.markdown("**Preferences**")
    pc1, pc2 = st.columns(2)
    with pc1:
        default_roles = ["Junior Java Developer", "Python Developer", "Backend Developer", "Associate Software Engineer", "Data Engineer", "Automation Engineer", "Junior AI Engineer"]
        default_locations = ["Bengaluru", "Hyderabad", "Chennai", "India", "Remote"]
        target_roles_text = st.text_area("Target roles (comma-separated)", value=", ".join(profile.get("target_roles", default_roles)), height=85)
        locations_text = st.text_input("Preferred locations (comma-separated)", value=", ".join(profile.get("preferred_locations", default_locations)))
        skills_text = st.text_input("Skills (comma-separated)", value=", ".join(profile.get("skills", [])))
        minimum_match_score = st.slider("Minimum resume-match score", min_value=40, max_value=95, value=int(profile.get("minimum_match_score", 65)), step=5)
        max_applications = st.slider("Maximum applications per run", min_value=1, max_value=10, value=int(profile.get("max_applications_per_run", 5)))
    with pc2:
        work_auth_options = ["Not set", "Yes", "No"]
        prev_auth = value("authorized_to_work")
        auth_index = work_auth_options.index(prev_auth) if prev_auth in work_auth_options else 0
        authorized_to_work = st.selectbox("Legally authorized to work in India? * if asked", work_auth_options, index=auth_index)
        sponsor_options = ["Not set", "Yes", "No"]
        prev_sponsor = value("requires_sponsorship")
        sponsor_index = sponsor_options.index(prev_sponsor) if prev_sponsor in sponsor_options else 0
        requires_sponsorship = st.selectbox("Will you require visa/work sponsorship? * if asked", sponsor_options, index=sponsor_index)
        expected_salary = st.text_input("Expected salary / CTC (leave blank to require manual review)", value=value("expected_salary"))
        notice_period = st.text_input("Notice period / start availability", value=value("notice_period"))
        accept_privacy_notices = st.checkbox("Allow ticking required applicant privacy/data-processing notices", value=bool(profile.get("accept_privacy_notices", False)), help="Only applies to a required checkbox explicitly describing applicant privacy or data processing. Terms of service and legal certifications still require manual review.")
        auto_apply_enabled = st.checkbox("I authorize automatic application submissions when the resume match meets my threshold and all mandatory answers are known", value=bool(profile.get("auto_apply_enabled", False)))
    st.caption("If auto-submit is off, Run now performs a dry run and fills supported forms without submitting. CAPTCHA, unknown required questions, terms/legal attestations, and unsupported fields stop for manual review.")
    st.markdown("**Email report settings (saved locally)**")
    ec1, ec2 = st.columns(2)
    with ec1:
        smtp_host = st.text_input("SMTP server", value=env.get("SMTP_HOST", "smtp.gmail.com"))
        smtp_port = st.number_input("SMTP port", min_value=1, max_value=65535, value=int(env.get("SMTP_PORT", "587")))
        smtp_username = st.text_input("SMTP username / sender address", value=env.get("SMTP_USERNAME", ""))
    with ec2:
        smtp_password = st.text_input("SMTP password / app password", value="", type="password", help="Leave blank to keep the saved password. For Gmail, use an App Password, not your normal account password.")
        report_to = st.text_input("Send reports to email address", value=env.get("REPORT_TO", ""))
        report_from = st.text_input("From address (optional)", value=env.get("REPORT_FROM", ""))

    b1, b2, b3 = st.columns(3)
    save_clicked = b1.form_submit_button("Save profile & settings", use_container_width=True)
    run_clicked = b2.form_submit_button("Save and run now", type="primary", use_container_width=True)
    test_clicked = b3.form_submit_button("Save & test email", use_container_width=True)

def save_current_settings() -> tuple[bool, str]:
    try:
        if upload is not None:
            suffix = Path(upload.name).suffix.lower()
            if suffix not in (".pdf", ".docx", ".txt", ".md"):
                return False, "Unsupported resume format."
            resume_path = APP_HOME / ("resume" + suffix)
            resume_path.write_bytes(upload.getvalue())
            try:
                os.chmod(resume_path, 0o600)
            except OSError:
                pass
        else:
            old_path = value("resume_path")
            if old_path and Path(old_path).exists():
                resume_path = Path(old_path).resolve()
            else:
                candidates = [APP_HOME / ("resume" + suffix) for suffix in (".pdf", ".docx", ".txt", ".md")]
                resume_path = next((p for p in candidates if p.exists()), None)
                if resume_path is None:
                    return False, "Upload your resume first."
        if not first_name.strip() or not last_name.strip() or not email.strip() or not phone.strip():
            return False, "Fill in your first name, last name, application email, and phone number."
        if "@" not in email or "@" not in (report_to or ""):
            return False, "Enter a valid application email and report recipient email."
        auth_value = "" if authorized_to_work == "Not set" else authorized_to_work
        sponsor_value = "" if requires_sponsorship == "Not set" else requires_sponsorship
        fresh_profile = {
            "first_name": first_name.strip(), "last_name": last_name.strip(), "email": email.strip(),
            "phone": phone.strip(), "city_region": city_region.strip(), "country": country.strip(),
            "street_address": street_address.strip(), "university": university.strip(), "degree": degree.strip(),
            "graduation_year": graduation_year.strip(), "years_experience": years_experience.strip(),
            "current_company": current_company.strip(), "linkedin_url": linkedin_url.strip(),
            "github_url": github_url.strip(), "portfolio_url": portfolio_url.strip(),
            "project_summary": project_summary.strip(), "target_roles": [x.strip() for x in target_roles_text.split(",") if x.strip()],
            "preferred_locations": [x.strip() for x in locations_text.split(",") if x.strip()],
            "skills": [x.strip() for x in skills_text.split(",") if x.strip()],
            "minimum_match_score": int(minimum_match_score), "max_applications_per_run": int(max_applications),
            "authorized_to_work": auth_value, "requires_sponsorship": sponsor_value,
            "expected_salary": expected_salary.strip(), "notice_period": notice_period.strip(),
            "accept_privacy_notices": bool(accept_privacy_notices), "auto_apply_enabled": bool(auto_apply_enabled),
            "resume_path": str(resume_path)
        }
        save_json(PROFILE_PATH, fresh_profile)
        env_values = read_env()
        env_values.update({
            "SMTP_HOST": smtp_host.strip(), "SMTP_PORT": str(int(smtp_port)),
            "SMTP_USERNAME": smtp_username.strip(), "REPORT_TO": report_to.strip(),
            "REPORT_FROM": report_from.strip()
        })
        if smtp_password.strip():
            env_values["SMTP_PASSWORD"] = smtp_password.strip()
        ENV_PATH.write_text("\n".join(k + "=" + v.replace("\n", "").replace("\r", "") for k, v in env_values.items()) + "\n", encoding="utf-8")
        try:
            os.chmod(ENV_PATH, 0o600)
        except OSError:
            pass
        return True, "Saved locally under " + str(APP_HOME) + ". No resume/profile/email credentials are saved to the public repository."
    except Exception as exc:
        return False, "Could not save settings: " + str(exc)

if save_clicked or run_clicked or test_clicked:
    ok, message = save_current_settings()
    if not ok:
        st.error(message)
    else:
        st.success(message)
        if test_clicked:
            with st.spinner("Sending test report email…"):
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("apply_agent.py")), "--test-email"], cwd=str(Path(__file__).parent), capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                st.success(result.stdout.strip() or "Test email sent.")
            else:
                st.error((result.stdout + "\n" + result.stderr).strip() or "Test email failed. Check SMTP settings.")
        elif run_clicked:
            mode = "AUTO-SUBMIT" if auto_apply_enabled else "DRY RUN"
            st.info("Starting " + mode + ". Browser automation stops safely when a question or security check needs your input.")
            arguments = ["--max-applications", str(int(max_applications))]
            arguments.append("--submit" if auto_apply_enabled else "--dry-run")
            with st.spinner("Inspecting current job feed and supported application forms…"):
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("apply_agent.py")), *arguments], cwd=str(Path(__file__).parent), capture_output=True, text=True, timeout=3600)
            out = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            st.text_area("Run report", value=out[-18000:], height=420)
            if result.returncode == 0:
                st.success("Run finished. Check the report above and your email if configured.")
            else:
                st.warning("The run stopped safely. Review the diagnostic output above, complete the missing configuration, and try again.")

st.divider()
st.subheader("2. Run automatically every day on this PC")
st.markdown("""
1. Save your candidate details, upload the resume, and configure email above.
2. First use Save and run now with automatic submission unchecked to preview what the tool would do.
3. After reviewing the preview and checking every answer for accuracy, enable the auto-submit authorization checkbox and run it again.
4. Open the repository folder in Windows PowerShell and run .\\setup_windows.ps1. It installs the local dependencies and registers a daily 9:20 AM task. The PC must be powered on and your Windows account logged in for the scheduled task.
5. The scheduled run fetches the latest public Job Scout list, checks your local resume and private application history, and emails a report. If a CAPTCHA, required unknown answer, legal attestation or unsupported form appears, the job is recorded for manual review instead of being force-submitted.
""")
st.caption("Security: do not upload your resume or mail password to the public GitHub repo or paste secrets into ChatGPT. This local app stores private files in your home folder at ~/.jobscout.")
