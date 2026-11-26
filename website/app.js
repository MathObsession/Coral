"use strict";

const pages = [
  ["home", "Home", "▦"], ["workspace", "Hermes", "☷"], ["files", "Files", "▱"],
  ["terminal", "Terminal & SSH", "⌘"], ["schedules", "Schedules", "◷"],
  ["usage", "Usage", "▥"], ["extended", "Extended mode", "◴"],
  ["profiles", "Profiles", "◎"], ["settings", "Settings", "⚙"]
];
const state = {
  page: "home", token: sessionStorage.getItem("coral-token"),
  backend: localStorage.getItem("coral-backend") || window.CORAL_CONFIG.backendURL,
  profileId: localStorage.getItem("coral-profile") || "", profiles: [], usage: null, tasks: [],
  schedules: [], notifications: [], files: [], directory: "", file: null, original: "", draft: "",
  scheduleId: null, filter: "All", busy: false, refreshing: false, lastActivity: 0
};
const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const duration = (seconds) => { const n = Math.max(0, Math.floor(seconds || 0)); return n >= 3600 ? `${Math.floor(n / 3600)}h ${Math.floor(n % 3600 / 60)}m` : `${Math.floor(n / 60)}m ${n % 60}s`; };
const countdown = (seconds) => { const n = Math.max(0, Math.floor(seconds || 0)); return `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`; };
const date = (timestamp) => new Date(timestamp * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
const profile = () => state.profiles.find(p => p.id === state.profileId);
const root = () => `/profiles/${encodeURIComponent(state.profileId)}`;
const badge = (status) => `<span class="badge ${escape(status)}">● ${escape(String(status).replaceAll("_", " "))}</span>`;
const button = (label, action, color = "ghost", disabled = false, attrs = "") => `<button class="button ${color}" data-action="${action}" ${disabled || state.busy ? "disabled" : ""} ${attrs}>${label}</button>`;
const empty = (icon, title, detail, action = "") => `<div class="card empty"><div class="empty-icon">${icon}</div><h3>${title}</h3><p>${detail}</p>${action}</div>`;

async function api(path, { method = "GET", body, key } = {}) {
  const base = new URL(state.backend);
  if (base.protocol !== "https:" && !(base.protocol === "http:" && ["127.0.0.1", "localhost"].includes(base.hostname))) throw new Error("Use HTTPS, or localhost for development.");
  const response = await fetch(state.backend.replace(/\/$/, "") + path, {
    method, headers: { ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}), ...(key ? { "Idempotency-Key": key } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(path.endsWith("/connect") ? 600000 : 45000)
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) { state.token = null; sessionStorage.removeItem("coral-token"); }
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status}).`);
  }
  return data;
}

function notice(message) {
  const element = $("#notice");
  element.hidden = !message;
  element.innerHTML = message ? `<span>${escape(message)}</span><button class="icon-button" data-action="dismiss-notice" aria-label="Dismiss message">×</button>` : "";
}

async function refresh() {
  if (!state.token || state.refreshing) return;
  state.refreshing = true;
  try {
    const data = await api("/profiles");
    state.profiles = data.profiles;
    if (!profile()) state.profileId = state.profiles[0]?.id || "";
    if (!state.profileId) return;
    const refreshingProfile = state.profileId;
    const refreshingRoot = `/profiles/${encodeURIComponent(refreshingProfile)}`;
    localStorage.setItem("coral-profile", state.profileId);
    const [usage, tasks, schedules, inbox] = await Promise.all([
      api(refreshingRoot + "/usage"), api(refreshingRoot + "/tasks"), api(refreshingRoot + "/schedules"), api("/notifications")
    ]);
    if (state.profileId !== refreshingProfile) return;
    state.usage = usage; state.tasks = tasks.tasks; state.schedules = schedules.schedules; state.notifications = inbox.notifications;
    if (!["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) && !$("#schedule-dialog").open && !state.busy) render();
    else updateCounters();
  } catch (error) { notice(error.message); if (!state.token) render(); }
  finally { state.refreshing = false; }
}

function updateCounters() {
  document.querySelectorAll("[data-counter]").forEach(node => {
    if (!state.usage) return;
    const field = node.dataset.counter;
    node.textContent = field === "inactivity_seconds" ? countdown(state.usage[field]) : duration(state.usage[field]);
  });
}

async function activity(kind) {
  if (!state.token || profile()?.state !== "available" || Date.now() - state.lastActivity < 15000) return;
  state.lastActivity = Date.now();
  try { await api(root() + "/activity", { method: "POST", body: { kind } }); } catch { /* A failed activity event cannot extend a session. */ }
}

async function mutate(action) {
  if (state.busy) return;
  state.busy = true;
  document.querySelectorAll("button[data-action]").forEach(node => { node.disabled = true; });
  try { await action(); notice(""); }
  catch (error) { notice(error.message); }
  finally { state.busy = false; await refresh(); render(); }
}

function navigate(page) {
  if (!pages.some(p => p[0] === page)) return;
  if (state.file && state.draft !== state.original && !window.confirm("Discard unsaved file changes?")) return;
  state.page = page;
  state.file = null; state.draft = ""; state.original = "";
  history.replaceState(null, "", `#${page}`);
  render(); activity("navigation");
  if (page === "files" && profile()?.state === "available") loadFiles();
}

function render() {
  $("#navigation").innerHTML = pages.map(([id, label, icon]) => `<button class="nav-item ${state.page === id ? "selected" : ""}" data-page="${id}" ${state.page === id ? 'aria-current="page"' : ""}><span class="nav-icon">${icon}</span><span>${label}</span></button>`).join("");
  $("#page-label").textContent = pages.find(p => p[0] === state.page)?.[1] || "Home";
  $("#account-label").innerHTML = `${escape(profile()?.login || "Your personal workspace")}<small>${escape(profile()?.repository || "Connect with GitHub")}</small>`;
  $("#connection").className = "badge " + (profile()?.state || "");
  $("#connection").textContent = profile()?.state || "Not connected";
  const content = { home: homePage, workspace: workspacePage, files: filesPage, terminal: terminalPage,
    schedules: schedulesPage, usage: usagePage, extended: extendedPage, profiles: profilesPage, settings: settingsPage };
  $("#content").innerHTML = content[state.page]();
}

function loginCard() {
  return `<div class="card blue row mobile-stack"><div><h3>A workspace that follows your ideas.</h3><p class="muted small-copy">Connect your GitHub account to bring your Codespace, Hermes, and files together.</p></div>${button("Continue with GitHub ↗", "login", "blue")}</div>`;
}

function quotaCard() {
  const usage = state.usage;
  return `<div class="card"><div class="metric-header"><span class="metric-icon">⌛</span><span class="metric-label">DAILY ALLOWANCE</span></div><div class="row"><div><div class="metric-value" data-counter="remaining_seconds">${usage ? duration(usage.remaining_seconds) : "4 hours"}</div><p class="metric-foot">${usage ? "remaining of 4 hours" : "your daily maximum"}</p></div>${badge(usage ? "available" : "not connected")}</div><progress class="progress" max="14400" value="${usage?.remaining_seconds ?? 14400}" aria-label="Daily time remaining"></progress><div class="row metric-foot"><span>${usage ? duration(usage.used_seconds) : "No session yet"}${usage ? " used today" : ""}</span><span>Resets at 00:00 UTC</span></div></div>`;
}

function idleCard() {
  const usage = state.usage;
  return `<div class="card cream"><div class="metric-header"><span class="metric-icon orange">◴</span><span class="metric-label">${usage?.extended_until ? "EXTENDED MODE" : "TIME UNTIL INACTIVITY"}</span></div><div class="metric-value orange" data-counter="inactivity_seconds">${usage?.session ? countdown(usage.inactivity_seconds) : "Sleeping"}</div><p class="metric-foot">${usage?.extended_until ? `Extension expires ${escape(date(usage.extended_until))}` : "Automatic sleep after 10 minutes without interaction."}</p><div class="row"><p class="metric-foot">A break should feel like a break.</p>${button("Extended mode →", "extended-page", "", !usage?.session)}</div></div>`;
}

function sessionCard() {
  const p = profile(); const running = ["starting", "available", "stopping"].includes(p?.state);
  return `<div class="card"><div class="row"><h3>▱ Your Codespace</h3>${badge(p?.state || "unconfigured")}</div><p class="muted small-copy">${escape(p?.repository || "Connect a repository in Profiles to give your ideas a home.")}</p>${p?.error ? `<p class="danger small-copy">${escape(p.error)}</p>` : ""}<div class="session-actions">${button(p?.state === "stopped" ? "▶ Resume workspace" : "▶ Start workspace", "start", "green", !p?.codespace || running)}${button("■ Stop", "stop", "ghost", !running)}<span class="badge">${p?.hermes ? "Hermes ready" : "Hermes sleeping"}</span></div><div class="detail-row"><span>◷ Session <strong data-counter="session_seconds">${duration(state.usage?.session_seconds)}</strong></span><span>4-hour daily allowance</span><span>Files preserved between sessions</span></div></div>`;
}

function homePage() {
  const upcoming = state.schedules.filter(s => !s.paused).slice(0, 3);
  return `<div class="stack"><section class="card cream hero"><div class="hero-text"><span class="eyebrow">HELLO, POSSIBILITY.</span><h1>Make room for<br>your next great idea.</h1><p>Your own AI workspace. A thoughtful partner. Everything you need to turn “what if” into something real.</p>${button(state.token ? "Open Hermes workspace →" : "Meet your workspace ↗", state.token ? "workspace-page" : "login", "")}</div><img class="mascot" src="assets/mascot.png" alt="Coral’s cheerful orange and cream fox mascot"></section>${state.token ? "" : loginCard()}<div class="grid two">${quotaCard()}${idleCard()}</div>${sessionCard()}<section><div class="section-title"><h2>Coming up next</h2>${button("View schedules →", "schedules-page", "ghost")}</div><div class="stack">${upcoming.length ? upcoming.map(scheduleCard).join("") : empty("◷", "Let Coral take the next shift", "Add a scheduled task. Coral wakes your workspace, gets it done, and saves the result for you.", button("+ Add a schedule", "new-schedule", "green", !state.token))}</div></section>${state.notifications.length ? `<section><div class="section-title"><h2>Your inbox</h2><span class="badge">${state.notifications.filter(n => !n.read).length} unread</span></div><div class="card">${state.notifications.slice(0, 6).map(n => `<div class="history-row row"><div><strong>${escape(n.title)}</strong><p class="muted small-copy">${escape(date(n.created))}</p></div>${n.read ? "" : button("Mark read", "read-notification", "ghost", false, `data-id="${n.id}"`)}</div>`).join("")}</div></section>` : ""}</div>`;
}

function taskCard(task) {
  return `<article class="card"><div class="row"><span class="muted small-copy">${task.schedule_id ? "SCHEDULED TASK" : "YOU"} · ${escape(date(task.created))}</span>${badge(task.status)}</div><div class="task-prompt">${escape(task.prompt)}</div><div class="task-header"><img src="assets/mascot.png" alt="">${task.kind === "terminal" ? "Command output" : "Hermes"}</div><pre class="task-output">${escape(task.output || (["queued", "running"].includes(task.status) ? "Working in your workspace…" : "No output was returned."))}</pre>${task.error ? `<p class="danger small-copy">⚠ ${escape(task.error)}</p>` : ""}${["queued", "running"].includes(task.status) ? button("Cancel task", "cancel-task", "ghost", false, `data-id="${task.id}"`) : ""}</article>`;
}

function workspacePage() {
  if (!state.token) return loginCard();
  const tasks = state.tasks.filter(t => t.kind === "hermes").reverse();
  return `<div class="stack"><div class="card row mobile-stack"><div class="task-header"><img src="assets/mascot.png" alt=""><span>Hermes<br><small class="muted">Your ideas, in good company.</small></span></div>${button(profile()?.hermes ? "Stop Hermes" : "Start Hermes", "toggle-hermes", "ghost", profile()?.state !== "available")}</div>${profile()?.state !== "available" ? sessionCard() : ""}${tasks.length ? tasks.map(taskCard).join("") : empty("☷", "What shall we build?", "Ask Hermes to explore your repository, write a feature, or help untangle your next idea.")}<form id="chat-form" class="card chat-form"><textarea name="prompt" id="chat-prompt" placeholder="Message Hermes or ask to write code…" rows="2" required maxlength="32000" aria-label="Message Hermes"></textarea><div class="row"><span class="hint">${escape(profile()?.repository || "Designated workspace")}<br>⌘ + Enter to send</span><button class="button green" type="submit" ${profile()?.state !== "available" || !profile()?.hermes || state.tasks.some(t => ["queued", "running"].includes(t.status)) ? "disabled" : ""}>Send ↑</button></div></form></div>`;
}

function scheduleCard(schedule) {
  return `<article class="card schedule-card"><div class="row"><div class="schedule-icon">◷</div><div class="schedule-info"><h3>${escape(schedule.title)}</h3><p>${escape(schedule.recurrence)} · ${escape(date(schedule.next_run))}</p><p>${escape(duration(schedule.duration_limit))} limit · ${escape(schedule.prompt.slice(0, 95))}</p></div>${badge(schedule.paused ? "paused" : "active")}<div class="schedule-actions">${button("Edit", "edit-schedule", "ghost", false, `data-id="${schedule.id}"`)}${button(schedule.paused ? "Resume" : "Pause", "pause-schedule", schedule.paused ? "green" : "", false, `data-id="${schedule.id}"`)}<button class="icon-button danger" data-action="delete-schedule" data-id="${schedule.id}" aria-label="Delete ${escape(schedule.title)}">×</button></div></div></article>`;
}

function schedulesPage() {
  if (!state.token) return loginCard();
  const filtered = state.schedules.filter(s => state.filter === "All" || (state.filter === "Active" ? !s.paused : s.paused));
  return `<div class="stack"><div class="card row mobile-stack"><div><span class="eyebrow">LET YOUR IDEAS KEEP MOVING</span><h1>Schedules</h1><p class="muted">Your workspace can take the next shift.</p></div>${button("+ New schedule", "new-schedule", "green")}</div><div class="grid two"><div class="card row"><div><span class="muted small-copy">ACTIVE TASKS</span><div class="metric-value">${state.schedules.filter(s => !s.paused).length}</div></div><span class="metric-icon">✓</span></div><div class="card row"><div><span class="muted small-copy">PAUSED</span><div class="metric-value orange">${state.schedules.filter(s => s.paused).length}</div></div><span class="metric-icon orange">Ⅱ</span></div></div><div class="section-title row wrap"><h2>Your schedules</h2><div class="segmented">${["All", "Active", "Paused"].map(f => `<button class="${state.filter === f ? "selected" : ""}" data-action="filter" data-filter="${f}">${f}</button>`).join("")}</div></div>${filtered.length ? filtered.map(scheduleCard).join("") : empty("◷", "A little planning goes a long way", "Create a one-time, daily, weekly, or recurring task. Coral runs it while your app is closed.")}<h2>Execution history</h2>${state.tasks.filter(t => t.schedule_id).map(taskCard).join("") || `<p class="muted">Scheduled results will appear here, even after the Codespace is stopped.</p>`}</div>`;
}

function usagePage() {
  if (!state.token) return loginCard();
  return `<div class="stack"><div><span class="eyebrow">AT YOUR OWN PACE</span><h1>A little time, well spent.</h1><p class="muted">Your four-hour allowance is a daily maximum, shared across profiles.</p></div><div class="grid two">${quotaCard()}${idleCard()}</div><h2>Session history</h2><div class="card">${state.usage?.history.length ? state.usage.history.map(s => `<div class="history-row row"><div><strong>${escape(date(s.started))}</strong><p class="muted small-copy">${escape(s.mode)} · ${escape(s.ended ? s.reason.replaceAll("_", " ") : "In progress")}</p></div><strong>${duration((s.ended || state.usage.server_time) - s.started)}</strong></div>`).join("") : `<p class="muted">Your first session is just around the corner.</p>`}</div><h2>Daily usage for this profile</h2><div class="card">${state.usage?.daily.map(d => `<div class="history-row row"><strong>${escape(d.day)}</strong><span>${duration(d.seconds)}</span></div>`).join("") || `<p class="muted">No time logged yet.</p>`}</div></div>`;
}

function extendedPage() {
  if (!state.token) return loginCard();
  return `<div class="stack"><div class="card cream"><div class="empty-icon">◴</div><span class="eyebrow">A LITTLE MORE BREATHING ROOM</span><h1>Keep your workspace awake.</h1><p class="muted">Choose a little extra time while you step away. Extended mode pauses the inactivity timeout for a defined duration, up to two hours.</p><form id="extended-form"><label>Keep awake for<select name="seconds"><option value="900">15 minutes</option><option value="1800" selected>30 minutes</option><option value="3600">1 hour</option><option value="5400">90 minutes</option><option value="7200">2 hours</option></select></label><p class="small-copy">${state.usage?.extended_until ? `Current extension expires ${escape(date(state.usage.extended_until))}.` : "Normal mode sleeps after 10 minutes without meaningful interaction."}</p><div class="row wrap"><button class="button" type="submit" ${profile()?.state !== "available" ? "disabled" : ""}>Enable extended mode</button>${button("Return to normal mode", "normal-mode", "ghost", !state.usage?.extended_until)}</div></form></div><div class="card"><h3>Your daily limit stays in place.</h3><p class="muted">Coral stops before your four-hour allowance is exhausted, including during extended mode. Extensions expire and never keep a session running indefinitely.</p></div></div>`;
}

function profilesPage() {
  if (!state.token) return loginCard();
  return `<div class="stack"><div><span class="eyebrow">EVERY PROJECT HAS A HOME</span><h1>Your profiles</h1><p class="muted">Connect the GitHub account that should own and pay for your Codespace.</p></div>${state.profiles.map(p => `<div class="card row"><div><h3>◎ ${escape(p.login)}</h3><p class="muted small-copy">${escape(p.repository || "Choose a workspace")}</p></div>${button(p.id === state.profileId ? "Selected" : "Switch", "switch-profile", "ghost", p.id === state.profileId, `data-id="${p.id}"`)}</div>`).join("")}<form id="connect-form" class="card"><h2>Connect this profile’s workspace</h2><label>Repository (optional)<input name="repository" placeholder="owner/repository"></label><label>Existing Codespace name (optional)<input name="codespace" pattern="[A-Za-z0-9-]*"></label><p class="muted small-copy">Leave both fields empty for a fresh starter workspace. To use an existing Codespace, enter its name. Coral installs Hermes inside the Codespace.</p><button class="button green" type="submit" ${profile()?.codespace ? "disabled" : ""}>Connect &amp; install Hermes</button>${profile()?.codespace ? `<p class="small-copy">Current Codespace: <code>${escape(profile().codespace)}</code></p>${button("Stop and disconnect", "disconnect", "ghost")}` : ""}</form>${button("+ Add another GitHub account", "link-login", "")}</div>`;
}

function settingsPage() {
  return `<div class="stack"><div><span class="eyebrow">MAKE YOURSELF AT HOME</span><h1>Settings</h1></div><form id="settings-form" class="card"><h2>Backend connection</h2><label>Coral backend URL<input name="backend" type="url" value="${escape(state.backend)}" required></label><p class="muted small-copy">Use your always-on backend’s HTTPS address. Your GitHub Pages site is the dashboard.</p><button class="button blue" type="submit">Save connection</button></form><div class="card"><h2>Your account</h2><p class="muted">${state.token ? `Connected as ${escape(profile()?.login || "your GitHub account")}.` : "Connect with GitHub to access your workspace."}</p>${button(state.token ? "Sign out" : "Continue with GitHub", state.token ? "logout" : "login", "ghost")}</div><div class="card"><h2>Workspace shortcuts</h2><div class="row wrap">${button("Profiles", "profiles-page", "ghost")}${button("Usage", "usage-page", "ghost")}${button("Extended mode", "extended-page", "ghost")}</div></div>${["localhost", "127.0.0.1"].includes(new URL(state.backend).hostname) ? `<div class="card cream"><h2>Local development</h2><p class="muted">Use a localhost backend with CORAL_DEMO=1. This mode supports real file editing and shell commands; Hermes requires a configured Codespace and model provider.</p>${button("Open local workspace", "local-login", "")}</div>` : ""}<div class="card"><div class="task-header"><img src="assets/mascot.png" alt=""><h3>Coral 1.0</h3></div><p class="muted small-copy">Task results stay in your backend inbox. Check Home or execution history when you return.</p></div></div>`;
}

function filesPage() {
  if (!state.token) return loginCard();
  if (profile()?.state !== "available") return `<div class="stack">${empty("▱", "Your files are sleeping safely", "Start your workspace to browse and edit your repository.")}${sessionCard()}</div>`;
  return `<div class="stack"><div class="row"><h1>Files</h1>${button("↻ Refresh", "refresh-files", "ghost")}</div><div class="files-layout"><div class="card file-list"><div class="row"><h3>${escape(state.directory || "Workspace")}</h3>${button("↑", "parent-directory", "ghost", !state.directory)}</div>${state.files.map(f => `<button class="file-entry" data-action="open-file" data-path="${escape(f.path)}"><span>${f.directory ? "▱" : "▤"}</span>${escape(f.name)}</button>`).join("") || `<p class="muted small-copy">This directory is empty.</p>`}<form id="new-file-form"><label>New file<input name="filename" placeholder="notes.md" required></label><button class="button ghost small" type="submit">+ Create file</button></form></div><form id="file-form" class="card"><div class="row"><h3>${escape(state.file || "Select a file")}</h3><button class="button green small" type="submit" ${state.file ? "" : "disabled"}>Save</button></div><textarea id="file-editor" class="editor" name="content" ${state.file ? "" : "disabled"} aria-label="File editor">${escape(state.draft)}</textarea><p class="muted small-copy"><span id="file-dirty">${state.draft !== state.original ? "Unsaved changes · " : ""}</span>UTF-8 · up to 1 MB · saved in your Codespace</p></form></div></div>`;
}

function terminalPage() {
  if (!state.token) return loginCard();
  return `<div class="stack"><div><span class="eyebrow">A DIRECT LINE TO YOUR WORKSPACE</span><h1>Terminal & SSH</h1></div>${profile()?.codespace ? `<div class="card"><h3>Official GitHub Codespaces SSH</h3><p><code>gh codespace ssh --codespace ${escape(profile().codespace)}</code></p><p class="muted small-copy">Use your own GitHub CLI login for ${escape(profile().login)} on a computer. Coral’s Mac app can open this session in Terminal or iTerm.</p><p class="small-copy">OpenSSH configuration: <code>gh codespace ssh --codespace ${escape(profile().codespace)} --config</code></p></div>` : ""}<div class="terminal"><div class="terminal-header"><i class="dot"></i><i class="dot yellow"></i><i class="dot green"></i><span class="terminal-title">coral · designated workspace</span></div><div class="terminal-body">${state.tasks.filter(t => t.kind === "terminal").reverse().map(t => `<div class="prompt">$ ${escape(t.prompt)}</div><pre>${escape(t.output || t.status)}</pre>${t.error ? `<p class="danger">${escape(t.error)}</p>` : ""}${["running", "queued"].includes(t.status) ? button("Cancel", "cancel-task", "ghost", false, `data-id="${t.id}"`) : ""}`).join("") || `<p class="prompt">Your workspace terminal is ready.</p><p>Start your Codespace, then enter a command below.<br>Output is saved in your task history.</p>`}</div><form id="terminal-form" class="terminal-form"><span class="prompt">$</span><input name="command" placeholder="Enter a workspace command" required autocomplete="off" aria-label="Terminal command"><button class="button green" type="submit" ${profile()?.state !== "available" ? "disabled" : ""}>Run</button></form></div><p class="muted small-copy">Commands execute as your Codespace user. Your daily allowance and session timeout apply.</p></div>`;
}

async function loadFiles() {
  try { state.files = (await api(root() + "/files?" + new URLSearchParams({ path: state.directory }))).files; render(); }
  catch (error) { notice(error.message); }
}

function showSchedule(schedule = null) {
  if (!state.token) { notice("Sign in before creating a schedule."); return; }
  const form = $("#schedule-form");
  state.scheduleId = schedule?.id || null;
  form.elements.title.value = schedule?.title || "";
  form.elements.prompt.value = schedule?.prompt || "";
  form.elements.recurrence.value = schedule?.recurrence || "once";
  const next = new Date(schedule ? schedule.next_run * 1000 : Date.now() + 3600000);
  form.elements.next_run.value = new Date(next.getTime() - next.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  form.elements.interval.value = Math.max(5, Math.floor((schedule?.interval_seconds || 3600) / 60));
  form.elements.duration.value = Math.max(1, Math.floor((schedule?.duration_limit || 900) / 60));
  $("#schedule-heading").textContent = schedule ? "Edit schedule" : "New schedule";
  $("#schedule-dialog").showModal();
}

function base64url(bytes) { return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", ""); }
async function login(link = false) {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  sessionStorage.setItem("coral-verifier", verifier);
  const data = await api("/auth/prepare", { method: "POST", body: { challenge: base64url(new Uint8Array(digest)), client: "web", link_account: link } });
  window.location.assign(data.url);
}

document.addEventListener("click", async event => {
  const node = event.target.closest("[data-page],[data-action]"); if (!node) return;
  if (node.dataset.page) { navigate(node.dataset.page); return; }
  const action = node.dataset.action, id = node.dataset.id;
  if (action.endsWith("-page")) { navigate(action.replace("-page", "")); return; }
  if (action === "dismiss-notice") { notice(""); return; }
  if (action === "close-dialog") { $("#schedule-dialog").close(); return; }
  if (action === "new-schedule") { showSchedule(); return; }
  if (action === "edit-schedule") { showSchedule(state.schedules.find(s => s.id === id)); return; }
  if (action === "filter") { state.filter = node.dataset.filter; render(); return; }
  if (action === "refresh-files") { await loadFiles(); activity("file"); return; }
  if (action === "parent-directory") { state.directory = state.directory.split("/").slice(0, -1).join("/"); await loadFiles(); activity("file"); return; }
  if (action === "open-file") {
    if (state.draft !== state.original && !window.confirm("Discard unsaved file changes?")) return;
    const entry = state.files.find(f => f.path === node.dataset.path);
    if (entry.directory) { state.directory = entry.path; await loadFiles(); }
    else { try { const result = await api(root() + "/file?" + new URLSearchParams({ path: entry.path })); state.file = entry.path; state.original = state.draft = result.content; render(); } catch (error) { notice(error.message); } }
    activity("file"); return;
  }
  await mutate(async () => {
    if (action === "login" || action === "link-login") { await login(action === "link-login"); }
    else if (action === "local-login") { state.token = (await api("/auth/local", { method: "POST" })).token; sessionStorage.setItem("coral-token", state.token); }
    else if (action === "logout") { await api("/auth/logout", { method: "POST" }); state.token = null; state.profiles = []; state.usage = null; state.tasks = []; state.schedules = []; state.notifications = []; sessionStorage.removeItem("coral-token"); }
    else if (["start", "stop", "disconnect"].includes(action)) { await api(root() + "/" + action, { method: "POST" }); }
    else if (action === "toggle-hermes") { await api(root() + "/hermes", { method: "POST", body: { enabled: !profile().hermes } }); }
    else if (action === "normal-mode") { await api(root() + "/extended", { method: "POST", body: { seconds: 0 } }); }
    else if (action === "cancel-task") { await api(root() + `/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" }); }
    else if (action === "delete-schedule") { await api(root() + `/schedules/${encodeURIComponent(id)}`, { method: "DELETE" }); }
    else if (action === "pause-schedule") { const schedule = state.schedules.find(s => s.id === id); await api(root() + `/schedules/${encodeURIComponent(id)}`, { method: "PUT", body: { ...schedule, paused: !schedule.paused } }); }
    else if (action === "switch-profile") { state.profileId = id; state.usage = null; state.tasks = []; state.schedules = []; }
    else if (action === "read-notification") { await api(`/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }); }
  });
});

document.addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.target, values = Object.fromEntries(new FormData(form));
  if (form.id === "new-file-form") {
    state.file = [state.directory, values.filename].filter(Boolean).join("/"); state.original = ""; state.draft = ""; render(); return;
  }
  await mutate(async () => {
    if (form.id === "settings-form") {
      const url = new URL(values.backend);
      if (url.protocol !== "https:" && !(url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname))) throw new Error("Use HTTPS, or localhost for development.");
      state.backend = url.href.replace(/\/$/, ""); state.token = null; state.profiles = []; state.usage = null; state.tasks = []; state.schedules = []; state.notifications = [];
      localStorage.setItem("coral-backend", state.backend); sessionStorage.removeItem("coral-token");
    } else if (form.id === "connect-form") { await api(root() + "/connect", { method: "POST", body: values }); }
    else if (form.id === "chat-form" || form.id === "terminal-form") {
      await api(root() + "/tasks", { method: "POST", body: { prompt: values.prompt || values.command, kind: form.id === "chat-form" ? "hermes" : "terminal", duration_limit: 900 }, key: crypto.randomUUID() }); form.reset();
    } else if (form.id === "extended-form") { await api(root() + "/extended", { method: "POST", body: { seconds: Number(values.seconds) } }); }
    else if (form.id === "file-form") { await api(root() + "/file", { method: "PUT", body: { path: state.file, content: values.content } }); state.original = state.draft = values.content; }
    else if (form.id === "schedule-form") {
      const prior = state.schedules.find(s => s.id === state.scheduleId);
      await api(root() + "/schedules" + (state.scheduleId ? "/" + state.scheduleId : ""), { method: state.scheduleId ? "PUT" : "POST", body: { title: values.title, prompt: values.prompt, recurrence: values.recurrence, next_run: new Date(values.next_run).getTime() / 1000, interval_seconds: Number(values.interval) * 60, duration_limit: Number(values.duration) * 60, paused: !!prior?.paused } });
      $("#schedule-dialog").close();
    }
  });
});

document.addEventListener("input", event => {
  if (event.target.id === "file-editor") { state.draft = event.target.value; $("#file-dirty").textContent = state.draft !== state.original ? "Unsaved changes · " : ""; activity("file"); }
  else if (event.target.closest("#chat-form")) activity("chat");
  else if (event.target.closest("#terminal-form")) activity("terminal");
});
document.addEventListener("keydown", event => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && $("#chat-form")) { event.preventDefault(); $("#chat-form").requestSubmit(); } });
window.addEventListener("beforeunload", event => { if (state.draft !== state.original) { event.preventDefault(); event.returnValue = ""; } });

(async () => {
  const params = new URLSearchParams(location.hash.slice(1));
  if (params.has("code")) {
    try {
      const verifier = sessionStorage.getItem("coral-verifier");
      const response = await api("/auth/exchange", { method: "POST", body: { code: params.get("code"), verifier } });
      state.token = response.token; sessionStorage.setItem("coral-token", state.token); sessionStorage.removeItem("coral-verifier");
      history.replaceState(null, "", "#home");
    } catch (error) { notice(error.message); }
  } else if (pages.some(p => p[0] === location.hash.slice(1))) state.page = location.hash.slice(1);
  if (new URLSearchParams(location.search).has("error")) { notice(new URLSearchParams(location.search).get("error")); history.replaceState(null, "", "#home"); }
  render(); await refresh();
  if (state.page === "files" && profile()?.state === "available") await loadFiles();
  setInterval(refresh, 5000);
})();
