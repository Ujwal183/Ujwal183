# Job Scout — AI Job Search Agent

Job Scout is a daily job-discovery agent tailored to an early-career candidate with Java, Python, SQL, backend, automation, data, and AI-project experience. It surfaces relevant India-based or remote roles, preserves official application links, and marks unknown eligibility, salary, and deadlines clearly.

## Dashboard

When GitHub Pages is enabled for this repository, visit:

https://ujwal183.github.io/Ujwal183/job-search-agent/

## What it does

- Pulls published vacancies from configured official Greenhouse, Lever, and Ashby job-board APIs.
- Scores postings against target roles, skills, experience signals, and preferred Indian locations.
- Shows a match score and explainable reasons.
- Links to the employer's hosted job posting.
- Extracts salary and application deadline only when present; otherwise displays "Not disclosed".
- Writes results to data/jobs.json and a readable digest to data/latest.md.
- Runs daily at 09:00 India Standard Time using GitHub Actions.

## Verification rules

The source registry lists public career-board feeds. Each job links back to the employer's hosted posting. The collector does not promise eligibility. It estimates early-career suitability from the title and description and lowers or excludes clearly senior or mismatched roles.

Salary and deadlines are never invented. A missing deadline means "Not disclosed", not that the job is open indefinitely.

## Optional AI assessment

The collector works without paid API keys using transparent matching rules. For richer language-model assessment, add an OPENAI_API_KEY repository secret under Settings → Secrets and variables → Actions. Optional assessment is used only on candidate postings; never put keys in source files. The model can be overridden through the OPENAI_MODEL environment variable.

## Add more official sources

Edit sources.json and add a company only after confirming its official hosted job-board URL and public feed slug. Supported providers:

- Greenhouse: public board token from the official hosted board.
- Lever: company slug from jobs.lever.co.
- Ashby: company slug from jobs.ashbyhq.com.

The daily workflow records a status for each source. Invalid or unavailable feeds are marked as errors rather than treated as proof that no jobs exist.

## Run locally

Python 3.11+ is recommended. No third-party packages are needed for collection.

    cd job-search-agent
    python agent.py

Optional AI assessment uses the OpenAI API only when OPENAI_API_KEY is set.

## Resume-aware auto-apply (local, private)

The local application runner extends the daily job feed with resume-based matching, supported browser-form filling, a private application log, and an email report. It is intentionally a local program: your resume and personal answers are stored under your Windows user home folder at `~/.jobscout`, not in this public repository.

### Windows setup

1. Download this repository as a ZIP from GitHub and extract it, or clone it. Open the `job-search-agent` folder in File Explorer.
2. Right-click PowerShell in that folder and run `./setup_windows.ps1`. If Windows blocks the script, in that PowerShell window run `Set-ExecutionPolicy -Scope Process Bypass`, then run the setup script again.
3. Start the local configuration page with `.` + `open_local_app.ps1`. The script opens a local Streamlit web page in your browser.
4. Upload your PDF/DOCX/TXT resume and fill in your name, email, phone, location, education, accurate work-authorization/sponsorship answers (only if known), preferred roles, and locations.
5. Enter SMTP settings for report email. For Gmail, use a Google App Password rather than your normal Google password. The SMTP password is stored in the Windows credential store through Python Keyring; the local `.env` file contains only non-secret mail settings. Never commit credentials to GitHub.
6. Click **Save & test email**. Then run **Save and run now** with automatic submission unchecked first. Review the dry-run report carefully.
7. After you verify every profile answer and the preview, check the explicit auto-submit authorization box and save the profile. The daily task is registered for 9:20 AM local India time by the setup script; it runs the local application runner and emails the results. The PC needs to be powered on and your Windows account logged in.

### How submissions are handled

- Resume matching combines skills detected in your uploaded resume with job-title, posting, location and early-career signals. Only jobs over your configured minimum match threshold are considered.
- The current implementation automates supported public application pages. It fills a field only when it can map the question to an explicit profile answer or the uploaded resume.
- It stops for CAPTCHA/anti-bot checks, unfamiliar required questions, demographic questions, terms-of-service attestations, unsupported upload requirements, or unanswered legal/work-eligibility fields. It does not bypass security checks or guess an answer.
- The log avoids automatically re-submitting jobs when the site showed an application receipt, the result was uncertain, or the posting already needs manual review. To retry a manual-review item after fixing it, remove that specific record from the private `~/.jobscout/applications.json` file first. Confirm uncertain outcomes in the employer portal before retrying.
- Email reports distinguish **Submitted** (a success/receipt signal was seen), **Submission uncertain**, **Manual review**, **Closed**, and errors. An email report is not an employer receipt or a guarantee that an application was accepted.
- Salary and deadlines are not invented. Missing details appear as **Not disclosed**.
- This does not apply to every possible site or form. Some employers restrict automation or require a login, CAPTCHA, custom questions, or a separate application account. Those need manual completion.

### Run from a terminal

From this folder, once the setup script has installed dependencies:

    .\.venv\Scripts\python.exe apply_agent.py --dry-run --max-applications 5
    .\.venv\Scripts\python.exe apply_agent.py --test-email

Actual submissions only run when you explicitly use `--submit` and `auto_apply_enabled` is true in your local profile:

    .\.venv\Scripts\python.exe apply_agent.py --submit --max-applications 5

Do not use the submit command until the dry-run output, candidate details, resume, and email delivery have been verified.

### API and account limits

The public Greenhouse, Lever and Ashby feeds are used to discover public openings. Employer-side submission APIs may require company-issued credentials, so Job Scout does not pretend it can submit to every board with a public listing API key. The local runner uses the public application page and falls back to manual review when it cannot safely finish a form. See the official [Greenhouse Job Board API](https://docs.greenhouse.io/job-board) and [Lever Postings API](https://github.com/lever/postings-api) documentation.

## Current profile

- Locations: Bengaluru, Hyderabad, Chennai, other India-based roles, and genuinely remote roles open to India.
- Roles: Junior Java Developer, Python Developer, Backend Developer, Associate Software Engineer, Data Engineer, Automation Engineer, Junior AI Engineer.
- Skills: Java, Python, SQL/MySQL, JDBC, FastAPI, REST APIs, Pandas, NumPy, Excel automation, and AI/ML project work.

This tool is a job-discovery aid, not a promise of eligibility or employment. Check requirements, work authorization, location conditions, and application status on the official posting before applying.
