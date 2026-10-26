(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { jobs: [], data: null };
  const escapeHTML = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[char]));
  const dateLabel = (value) => {
    if (!value) return "Not disclosed";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  };
  const textHas = (text, terms) => terms.some((term) => text.toLowerCase().includes(term));
  function roleMatch(job, role) {
    if (role === "all") return true;
    const title = (job.title + " " + job.description).toLowerCase();
    const groups = {
      java: ["java", "spring boot", "jdbc", "j2ee"],
      python: ["python", "fastapi", "django", "flask"],
      backend: ["backend", "back-end", "back end", "api developer", "software engineer", "software development", "full stack", "fullstack"],
      data: ["data engineer", "data analyst", "automation", "pandas", "etl", "excel", "business intelligence"],
      ai: ["artificial intelligence", "machine learning", " ai ", "genai", "generative ai", "llm", "nlp"],
      qa: ["qa", "quality assurance", "test automation", "sdet", "software tester"]
    };
    return textHas(" " + title + " ", groups[role] || []);
  }
  function locationMatch(job, selected) {
    if (selected === "all") return true;
    const loc = (job.location || "").toLowerCase();
    if (selected === "Bengaluru") return /bengaluru|bangalore/.test(loc);
    if (selected === "Hyderabad") return /hyderabad/.test(loc);
    if (selected === "Chennai") return /chennai/.test(loc);
    if (selected === "Remote") return job.is_remote === true || /remote|work from home|anywhere/.test(loc);
    return /india|bengaluru|bangalore|hyderabad|chennai|pune|mumbai|noida|gurugram|gurgaon|new delhi|remote/.test(loc);
  }
  function visibleJobs() {
    const q = $("search-input").value.trim().toLowerCase();
    const location = $("location-filter").value;
    const role = $("role-filter").value;
    const minimum = Number($("match-filter").value);
    const sort = $("sort-filter").value;
    const items = state.jobs.filter((job) => {
      const haystack = [job.title, job.company, job.location, job.description, ...(job.skills_matched || [])].join(" ").toLowerCase();
      return (!q || haystack.includes(q)) && locationMatch(job, location) && roleMatch(job, role) && Number(job.match_score || 0) >= minimum;
    });
    items.sort((a,b) => sort === "recent" ? String(b.published_at || "").localeCompare(String(a.published_at || "")) : sort === "company" ? String(a.company || "").localeCompare(String(b.company || "")) : Number(b.match_score || 0) - Number(a.match_score || 0));
    return items;
  }
  function renderCard(job) {
    const score = Number(job.match_score || 0);
    const avatar = escapeHTML((job.company || "?").trim().slice(0,1).toUpperCase());
    const skills = (job.skills_matched || []).slice(0,5).map(s => '<span class="skill-tag">' + escapeHTML(s) + '</span>').join("");
    const extraCount = Math.max(0, (job.skills_matched || []).length - 5);
    const reasons = (job.match_reasons || []).slice(0,2).map(escapeHTML).join(" · ");
    const url = job.apply_url || job.job_url || job.careers_url || "";
    const validUrl = /^https:\/\//i.test(url) ? url : "";
    const desc = job.description || "The employer did not provide a description in the feed. Open the official posting to review the requirements.";
    const salary = job.salary || "Not disclosed";
    const deadline = job.deadline || "Not disclosed";
    const eligibility = job.eligibility || "Eligibility not clear from the listing — review the official requirements.";
    const apply = validUrl ? '<a class="apply-button" href="' + escapeHTML(validUrl) + '" target="_blank" rel="noopener noreferrer">View official job ↗</a>' : '<span class="apply-button disabled">No verified apply link</span>';
    return '<article class="job-card">' +
      '<div class="job-card-top"><div class="company-row"><div class="company-avatar">' + avatar + '</div><div><div class="company-name">' + escapeHTML(job.company) + '</div><div class="verified">✓ Official career feed</div></div></div>' +
      '<div class="match-badge ' + (score < 55 ? 'medium' : '') + '">' + score + '% fit</div></div>' +
      '<h3 class="job-title">' + escapeHTML(job.title) + '</h3>' +
      '<div class="job-meta"><span>⌖ ' + escapeHTML(job.location || "Location not disclosed") + '</span><span>◷ ' + escapeHTML(job.employment_type || "Type not disclosed") + '</span><span>' + escapeHTML(job.provider || "Career site") + '</span></div>' +
      '<p class="job-description">' + escapeHTML(desc) + '</p>' +
      '<div class="job-skills">' + skills + (extraCount ? '<span class="skill-tag more">+' + extraCount + ' more</span>' : '') + '</div>' +
      '<div class="job-detail-grid"><div class="detail-item"><div class="detail-label">Salary / CTC</div><div class="detail-value ' + (salary === "Not disclosed" ? "unknown" : "") + '">' + escapeHTML(salary) + '</div></div><div class="detail-item"><div class="detail-label">Application deadline</div><div class="detail-value ' + (deadline === "Not disclosed" ? "unknown" : "") + '">' + escapeHTML(deadline) + '</div></div></div>' +
      '<div class="eligibility-note"><span>✦</span><div><strong>Eligibility signal:</strong> ' + escapeHTML(eligibility) + (reasons ? '<br><span style="color:#9aa9c0">Match reasons: ' + reasons + '</span>' : '') + '</div></div>' +
      '<div class="job-card-footer"><span class="posted-date">' + (job.published_at ? "Posted " + escapeHTML(dateLabel(job.published_at)) : "Posting date not provided") + '</span>' + apply + '</div></article>';
  }
  function render() {
    const jobs = visibleJobs();
    $("result-count").textContent = jobs.length + " matching " + (jobs.length === 1 ? "opportunity" : "opportunities");
    $("job-list").innerHTML = jobs.map(renderCard).join("");
    $("empty-state").classList.toggle("hidden", jobs.length > 0);
  }
  function setNotice(message) {
    const el = $("notice");
    el.textContent = message || "";
    el.classList.toggle("visible", Boolean(message));
  }
  function updateStats(data) {
    const jobs = data.jobs || [];
    const sources = data.sources || [];
    $("stat-open").textContent = jobs.length;
    $("stat-strong").textContent = jobs.filter(j => Number(j.match_score || 0) >= 70).length;
    $("stat-sources").textContent = sources.filter(s => s.status === "ok").length + "/" + sources.length;
    $("stat-source-note").textContent = sources.filter(s => s.status === "ok").length + " feeds checked successfully";
    $("stat-updated").textContent = data.generated_at ? new Date(data.generated_at).toLocaleString("en-IN", {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit",hour12:true}) : "Waiting";
    const err = sources.filter(s => s.status !== "ok").length;
    $("feed-status").textContent = data.generated_at ? (err ? "Feed updated · " + err + " source issue(s)" : "Feed updated") : "Awaiting first scan";
    if (data.status === "awaiting_first_run") {
      setNotice("The dashboard is live, but the first scheduled scan has not run yet. In the repository, open Actions → Job Scout Daily Scan → Run workflow to fetch the first results.");
    } else if (jobs.length === 0 && err === sources.length) {
      setNotice("No job feed could be fetched on this scan. Source errors are recorded in data/jobs.json; try again after a later scan.");
    } else if (err) {
      setNotice(err + " source(s) could not be reached on this scan. Displayed jobs come from successful public feeds; a source error does not mean the employer has no vacancies.");
    } else {
      setNotice("");
    }
  }
  async function load() {
    $("refresh-btn").disabled = true;
    $("feed-status").textContent = "Checking feed…";
    try {
      const response = await fetch("./data/jobs.json?ts=" + Date.now(), {cache:"no-store"});
      if (!response.ok) throw new Error("Could not load job data.");
      const data = await response.json();
      state.data = data;
      state.jobs = Array.isArray(data.jobs) ? data.jobs : [];
      updateStats(data);
      render();
    } catch (error) {
      setNotice("Could not load job data. Make sure the GitHub Pages site has finished deploying and try again.");
      $("feed-status").textContent = "Feed unavailable";
    } finally {
      $("refresh-btn").disabled = false;
    }
  }
  ["search-input","location-filter","role-filter","match-filter","sort-filter"].forEach(id => $(id).addEventListener(id === "search-input" ? "input" : "change", render));
  $("refresh-btn").addEventListener("click", load);
  $("reset-btn").addEventListener("click", () => {
    $("search-input").value = "";
    $("location-filter").value = "all";
    $("role-filter").value = "all";
    $("match-filter").value = "40";
    $("sort-filter").value = "match";
    render();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "/" && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)) {
      e.preventDefault(); $("search-input").focus();
    }
  });
  load();
})();