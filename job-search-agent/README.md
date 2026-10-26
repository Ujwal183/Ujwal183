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

## Current profile

- Locations: Bengaluru, Hyderabad, Chennai, other India-based roles, and genuinely remote roles open to India.
- Roles: Junior Java Developer, Python Developer, Backend Developer, Associate Software Engineer, Data Engineer, Automation Engineer, Junior AI Engineer.
- Skills: Java, Python, SQL/MySQL, JDBC, FastAPI, REST APIs, Pandas, NumPy, Excel automation, and AI/ML project work.

This tool is a job-discovery aid, not a promise of eligibility or employment. Check requirements, work authorization, location conditions, and application status on the official posting before applying.
