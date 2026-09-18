const $ = (id) => document.getElementById(id);

const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmt = (s) => (s ? Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0") : "0:00");
const short = (cmd, n = 90) => (cmd && cmd.length > n ? cmd.slice(0, n - 3) + "…" : cmd || "");
const qcls = (q) => ({ high: "q-high", medium: "q-medium", low: "q-low" }[q] || "q-low");
const qlabel = (l) => (l.quality_label || "low").toLowerCase();

let isRunning = false;
let baseline = null;
let summary = null;
let summaryShown = false;
const knownNames = new Set();

$("btnRun").addEventListener("click", submitRun);
$("r_optToggle").addEventListener("click", () => $("r_opts").classList.toggle("hidden"));
const nicheBox = $("r_niches");
nicheBox.addEventListener("click", (ev) => {
  const b = ev.target.closest(".nopt");
  if (!b) return;
  if (b.classList.contains("on") && nicheBox.querySelectorAll(".nopt.on").length <= 1) return;
  b.classList.toggle("on");
});
// Target quality: single-select chips -> quality band for this run.
// high 60-100, medium 30-59, low 0-29, any = honor the manual min-q field.
const QUAL_BANDS = { high: [60, 100], medium: [30, 59], low: [0, 29], "": [0, 100] };
const qBox = $("r_quality");
qBox.addEventListener("click", (ev) => {
  const b = ev.target.closest(".nopt");
  if (!b) return;
  qBox.querySelectorAll(".nopt").forEach((x) => x.classList.toggle("on", x === b));
});
$("btnStop").addEventListener("click", async () => {
  try {
    const r = await fetch("/api/stop", { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok && !d.ok) alert("stop failed: " + (d.error || r.status));
  } catch (e) {
    alert("stop failed: " + e.message);
  }
});
["q", "f_niche", "f_q", "f_email"].forEach((id) => {
  $(id).addEventListener(id === "q" ? "input" : "change", () => renderLeads(state.leads || { total: 0, leads: [] }));
});
const state = { leads: { total: 0, leads: [] } };

async function submitRun() {
  const niches = [...nicheBox.querySelectorAll(".nopt.on")].map((b) => b.dataset.niche);
  if (!niches.length) {
    alert("pick at least one niche");
    return;
  }
  const sel = qBox.querySelector(".nopt.on");
  const band = QUAL_BANDS[(sel && sel.dataset.q) || ""] || QUAL_BANDS[""];
  const manual = parseInt($("r_mq").value, 10) || 0;
  const body = {
    niche: niches.join(","),
    max: parseInt($("r_max").value, 10) || 6,
    out: $("r_out").value.trim() || "data/leads.csv",
    seeds: $("r_seeds").value.trim() || "",
    min_quality: (sel && sel.dataset.q) ? band[0] : manual,
    max_quality: (sel && sel.dataset.q) ? band[1] : 100,
    emails_only: $("r_email").checked,
    no_enrich: $("r_noenrich").checked,
  };
  const but = $("btnRun");
  but.disabled = true;
  but.textContent = "starting…";
  try {
    const r = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("run rejected: " + (d.error || r.status));
    } else {
      $("log").textContent = "scrape started — progress shows above, results land below…\n";
      knownNames.clear();
      summary = null;
      summaryShown = false;
      tick();
    }
  } catch (e) {
    alert("failed to start: " + e.message);
  }
  but.textContent = "▶ Start scraping";
}

function renderStatus(s) {
  const running = !!s.running;
  const wasRunning = isRunning;
  isRunning = running;
  if (running && !wasRunning) {
    baseline = state.leads.total || 0;
    summary = null;
    summaryShown = false;
  }
  if (!running && wasRunning && baseline !== null) {
    const delta = (state.leads.total || 0) - baseline;
    summary = { secs: s.elapsed_s, delta };
    baseline = null;
  }
  if (summary && !summaryShown) {
    const d = summary.delta;
    let tail;
    if (d > 0) tail = "+" + d + " new leads saved";
    else if (d < 0) tail = Math.abs(d) + " leads removed by filters";
    else
      tail = "found 0 new leads — free engines get rate-limited; retry in a few min, tick a seed file in options, or set a SERPAPI key in .env for guaranteed discovery";
    $("resNote").textContent = "last run finished in " + fmt(summary.secs || 0) + "s · " + tail;
    summaryShown = true;
    setTimeout(() => $("resultsPanel").scrollIntoView({ behavior: "smooth", block: "start" }), 150);
  }
  $("dot").className = "dot " + (running ? "run" : "idle");
  $("pill").className = "pill " + (running ? "run" : "idle");
  $("pill").textContent = running ? "SCRAPING" : s.exit_code === null ? "IDLE" : "EXIT " + s.exit_code;
  $("sub").textContent = running
    ? "fetching & probing candidates — new leads appear below live"
    : s.exit_code === null
      ? "idle — showing last results"
      : "last run finished in " + fmt(s.elapsed_s) + (s.exit_code === 0 ? "" : " · exit code " + s.exit_code);

  $("s_status").textContent = running ? "SCRAPING…" : s.exit_code === null ? "idle" : "done";
  $("s_pid").textContent = s.pid ? "pid " + s.pid : s.exit_code === null ? "" : "exited " + s.exit_code;
  $("s_niche").textContent = s.niches && s.niches.length ? s.niches.join(", ") : s.niche || "—";
  $("s_search").textContent = (s.searches || 0) + " searches";
  $("s_probed").textContent = s.candidates_probed || 0;
  $("s_query").textContent = s.current_query || "—";
  $("s_leads").textContent = s.leads_found || 0;
  $("s_src").textContent = s.source_file || s.out_file || "—";
  $("s_elapsed").textContent = running ? fmt(s.elapsed_s) + " · running" : s.elapsed_s ? fmt(s.elapsed_s) : "—";
  $("s_cmd").textContent = short(running ? (s.current_url ? "probe " + s.current_url : s.cmd) : s.cmd);

  $("btnRun").disabled = running;
  $("btnStop").disabled = !running;
  $("poll").className = running ? "live" : "";
  $("poll").textContent = running ? "● live scraping · refresh 2s" : "● live · refresh 2s";

  $("runBanner").classList.toggle("hidden", !running);
  if (running) {
    const n = s.niches && s.niches.length ? s.niches.length : 1;
    const mx = (s.max || 6) * n;
    const got = s.leads_found || 0;
    $("rbCount").textContent = got;
    $("rbMax").textContent = mx;
    $("lbar").style.width = mx > 0 ? Math.min(100, Math.round((got / mx) * 100)) + "%" : "0%";
    $("rbSub").textContent =
      "probed " + (s.candidates_probed || 0) + " candidates · " + (s.searches || 0) + " searches · writing to " + (s.out_file || "…");
    const pn = s.per_niche || {};
    $("nicheChips").innerHTML =
      Object.entries(pn)
        .map(([k, v]) => `<span class="nchip">${esc(k)} <b>${v}/<small>${s.max || 6}</small></b></span>`)
        .join("") || `<span class="nchip muted">warming engines…</span>`;
    $("lActivity").innerHTML =
      "<span class='actb'>now probing</span> " +
      esc(s.current_url || "…") +
      (s.current_query ? ` <span class="muted">· query: ${esc(s.current_query)}</span>` : "");
  }

  const el = $("log");
  const lines = s.log_tail || [];
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
  el.textContent = lines.length ? lines.join("\n") : "no output yet — press ▶ Start scraping";
  if (nearBottom) el.scrollTop = el.scrollHeight;
  $("upd").textContent = "updated " + new Date().toLocaleTimeString();
  $("lline").textContent = lines.length ? (lines[lines.length - 1] || "").slice(0, 100) : "";
}

function renderLeads(d) {
  state.leads = d || { total: 0, leads: [] };
  const leads = d.leads || [];
  $("resCount").textContent = leads.length ? "(" + leads.length + ")" : "";
  const q = $("q").value.trim().toLowerCase();
  const nf = $("f_niche").value;
  const qf = $("f_q").value;
  const ef = $("f_email").checked;
  const spec = (l) =>
    [l.business_name, l.website, l.emails || [], l.linkedin_urls || [], l.whatsapp_numbers || [], l.instagram_handles || [], l.phones || [], l.source_query || ""]
      .flat()
      .map(String)
      .join(" ")
      .toLowerCase();

  if (!$("f_niche").dataset.filled) {
    const set = [...new Set(leads.map((l) => l.niche).filter(Boolean))];
    set.forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      $("f_niche").appendChild(o);
    });
    $("f_niche").dataset.filled = "1";
  }

  const visible = leads.filter((l) => {
    if (qf && (l.quality_label || "low").toLowerCase() !== qf) return false;
    if (nf && l.niche !== nf) return false;
    if (ef && !(l.emails && l.emails.length)) return false;
    if (q && !spec(l).includes(q)) return false;
    return true;
  });

  const hi = leads.filter((l) => qlabel(l) === "high").length;
  const med = leads.filter((l) => qlabel(l) === "medium").length;
  const lo = leads.filter((l) => qlabel(l) === "low").length;
  const wEmail = leads.filter((l) => l.emails && l.emails.length).length;
  $("qHigh").textContent = "high " + hi;
  $("qMed").textContent = "medium " + med;
  $("qLow").textContent = "low " + lo;
  $("qEmail").textContent = wEmail;
  $("count").textContent = "showing " + visible.length + " of " + leads.length;

  $("rows").innerHTML = visible.length
    ? visible.map((l) => row(l)).join("")
    : `<tr><td colspan="4" class="muted">${leads.length ? "no leads match the filters" : "no leads yet — hit Start scraping above"}</td></tr>`;
}

function row(l) {
  const nameK = l.business_name || l.website || "?";
  const fresh = isRunning && !knownNames.has(nameK);
  if (isRunning) knownNames.add(nameK);

  const ntag = `<span class="ntag">${esc(l.niche || "")}</span>`;
  const site = l.website
    ? `<a class="site" href="${esc(l.website)}" target="_blank" rel="noopener">${esc(l.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/+$/, ""))}</a>`
    : "";
  const name = `<div class="biz">${esc(l.business_name || "(untitled)")}${ntag}</div>${site}`;

  const ct = (label, cls, arr, fn) =>
    arr && arr.length ? `<div class="ct"><span class="lbl ${cls}">${label}</span><span class="chips">${arr.map(fn).join("")}</span></div>` : "";
  const cMail = ct("email", "mail", l.emails, (e) => `<a class="chip mail" href="mailto:${esc(e)}" title="send email">${esc(e)}</a>`) +
    (l.emails && l.emails.length && l.email_origin != null && l.email_origin !== "scraped"
      ? `<div class="ct"><span class="lbl mute">origin</span><span class="chips"><span class="chip org ${esc(l.email_origin)}" title="email_origin: address was SMTP-verified, not published on the site">${esc(l.email_origin)}</span></span></div>`
      : "");
  const cIg = ct("instagram", "ig", l.instagram_handles, (h) => `<a class="chip ig" href="https://instagram.com/${esc(String(h).replace(/^.*\//, ""))}" target="_blank" rel="noopener">@${esc(String(h).replace(/^.*\//, ""))}</a>`);
  const cLi = ct("linkedin", "li", l.linkedin_urls, (u) => `<a class="chip li" href="${esc(u)}" target="_blank" rel="noopener">in</a>`);
  const cWa = ct("whatsapp", "wa", l.whatsapp_numbers, (p) => `<a class="chip wa" href="https://wa.me/${esc(String(p).replace(/\D/g, ""))}" target="_blank" rel="noopener">${esc(p)}</a>`);
  const cPh = ct("phone", "ph", l.phones, (p) => `<span class="chip ph">${esc(p)}</span>`);
  const contacts = cMail + cIg + cLi + cWa + cPh;
  const noCont = !contacts ? `<div class="ct"><span class="lbl mute">contacts</span><span class="muted">none found</span></div>` : "";

  const q = qlabel(l);
  const qual = `<span class="q ${qcls(q)}">${q}</span><span class="score">${l.quality_score == null ? "" : l.quality_score}</span>`;
  const src = `<div class="src">${esc(l.source_query || "")}<br>${esc(String(l.scraped_at || "").slice(0, 16))}</div>`;
  return `<tr class="${fresh ? "newrow" : ""}"><td>${name}</td><td class="contacts">${contacts || noCont}</td><td>${qual}</td><td>${src}</td></tr>`;
}

async function tick() {
  try {
    const [st, ld] = await Promise.all([
      fetch("/api/status").then((r) => r.json()),
      fetch("/api/leads").then((r) => r.json()),
    ]);
    renderStatus(st);
    renderLeads(ld);
  } catch (e) {
    $("poll").className = "";
    $("poll").textContent = "● dashboard offline";
  }
}
setInterval(tick, 2000);
tick();