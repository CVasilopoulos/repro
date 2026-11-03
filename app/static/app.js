const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString();
const VERDICT_LABEL = {
  reproduced: "Reproduced on the default branch",
  fixed: "Fixed on the default branch",
  not_reproducible: "Not reproducible",
  new_on_default: "Present on the default branch only",
  flaky: "Flaky reproduction",
  inconclusive: "Inconclusive",
};

let config = null;

async function loadConfig() {
  config = await (await fetch("/api/config")).json();
  const rc = config.runtime_check || {};
  const proof = rc.status === "ok" ? ` Self-test: ${rc.gvisor ? "gVisor confirmed" : "runtime " + rc.runtime}, sandbox kernel "${rc.kernel}"${rc.dmesg ? `, dmesg "${rc.dmesg}"` : ""}.` : "";
  $("#foot-model").textContent = `Model: ${config.model} on Vultr Serverless Inference. Sandbox runtime: ${config.sandbox.runtime}.${proof}`;
}

async function home() {
  $("#home").hidden = false;
  const ex = $("#examples");
  ex.innerHTML = "";
  for (const e of config.examples || []) {
    const b = el("button", "example");
    b.type = "button";
    b.append(el("span", "kind" + (e.hostile ? " hostile" : ""), e.kind), el("b", "", e.title), el("small", "", e.url.replace("https://github.com/", "")));
    b.onclick = () => start(e.url);
    ex.append(b);
  }
  const lab = $("#lab");
  lab.innerHTML = "";
  for (const a of config.lab || []) {
    const b = el("button", "example");
    b.type = "button";
    b.append(el("span", "kind hostile", "attack"), el("b", "", a.title), el("small", "", a.explain));
    b.onclick = () => startLab(a.id);
    lab.append(b);
  }
  const rows = await (await fetch("/api/jobs")).json();
  const tb = $("#recent");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = el("tr");
    const label = r.issue_url.startsWith("lab:") ? "attack lab: " + r.issue_url.slice(4) : r.issue_url.replace("https://github.com/", "");
    const a = el("a", "", label);
    a.href = `/j/${r.id}`;
    const td = el("td");
    td.append(a);
    tr.append(td, el("td", "muted", r.verdict ? VERDICT_LABEL[r.verdict] || r.verdict : r.status), el("td", "muted", new Date(r.created * 1000).toLocaleString()));
    tb.append(tr);
  }
  if (!rows.length) tb.append(el("tr", "", "")).append(el("td", "muted", "No runs yet."));
  $("#start").onsubmit = (ev) => {
    ev.preventDefault();
    start($("#issue").value);
  };
}

async function startLab(preset) {
  const res = await fetch("/api/lab", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preset }) });
  const body = await res.json();
  if (!res.ok) {
    const err = $("#form-error");
    err.textContent = body.detail || "Could not start";
    err.hidden = false;
    window.scrollTo(0, 0);
    return;
  }
  location.href = `/j/${body.id}`;
}

async function start(url) {
  const err = $("#form-error");
  err.hidden = true;
  const res = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ issue_url: url }) });
  const body = await res.json();
  if (!res.ok) {
    err.textContent = body.detail || "Could not start";
    err.hidden = false;
    return;
  }
  location.href = `/j/${body.id}`;
}

const state = { sandboxes: new Map(), egress: new Map(), containment: 0, pending: new Map() };

function addStep(cls, meta, ...children) {
  const li = el("li", cls);
  const m = el("div", "meta");
  for (const part of meta) m.append(typeof part === "string" ? el("span", "", part) : part);
  li.append(m, ...children);
  $("#timeline").append(li);
  return li;
}

function pill(text, cls) {
  return el("span", "pill " + (cls || ""), text);
}

function render(e) {
  const d = e.data;
  const t = fmtTime(e.ts);
  switch (e.kind) {
    case "issue":
      $("#job-repo").textContent = `${d.owner}/${d.repo} #${d.number}`;
      $("#job-title").textContent = d.title;
      document.title = `Repro: ${d.owner}/${d.repo}#${d.number}`;
      addStep("", [t, "issue"], el("div", "", `Filed by ${d.author} on ${d.created_at.slice(0, 10)}. The issue text is treated as untrusted input.`));
      break;
    case "lab":
      $("#job-repo").textContent = "Attack lab";
      $("#job-title").textContent = d.title;
      document.title = `Repro attack lab: ${d.title}`;
      addStep("", [t, "attack"], el("div", "", d.explain));
      $("#comment-btn").hidden = true;
      break;
    case "lab_result": {
      const box = $("#verdict");
      box.hidden = false;
      box.className = "verdict " + (d.contained ? "fixed" : "inconclusive");
      box.innerHTML = "";
      box.append(el("div", "label", d.contained ? "Contained" : "Check failed"), el("div", "", d.summary));
      break;
    }
    case "status":
      $("#job-status").textContent = d.message;
      break;
    case "context":
      addStep("", [t, "context"], el("div", "cmd", `HEAD when filed ${d.filed_at_commit.slice(0, 12)}, HEAD now ${d.head_commit.slice(0, 12)}`));
      break;
    case "sandbox_started": {
      state.sandboxes.set(d.name, d);
      const li = el("li", "", `${d.name}: started, ${d.runtime}, container ${d.container}`);
      li.id = "sb-" + d.name;
      $("#sandboxes").append(li);
      renderSpec(d.spec);
      addStep("", [t, pill(d.role)], el("div", "", `Sandbox ${d.name} started (runtime ${d.runtime}, container ${d.container})`));
      break;
    }
    case "sandbox_destroyed": {
      const li = document.getElementById("sb-" + d.name);
      if (li) li.textContent = `${d.name}: destroyed after ${d.lifetime}s (${d.reason})`;
      addStep("", [t, "teardown"], el("div", "muted", `Sandbox ${d.name} destroyed: ${d.reason}`));
      break;
    }
    case "thought":
      addStep("", [t, "agent"], el("div", "thought", d.text));
      break;
    case "exec_start": {
      const li = addStep("", [t, d.sandbox.split("-").slice(2, -1).join("-") || "sandbox", d.label || "command", pill("running")], el("div", "cmd", "$ " + d.command));
      state.pending.set(d.sandbox + "|" + d.command, li);
      break;
    }
    case "exec_end": {
      const key = d.sandbox + "|" + d.command;
      let li = state.pending.get(key);
      state.pending.delete(key);
      if (!li) li = addStep("", [t, d.label || "command"], el("div", "cmd", "$ " + d.command));
      const meta = li.querySelector(".meta");
      meta.lastChild.remove();
      meta.append(pill(`exit ${d.exit_code}`, d.exit_code === 0 ? "ok" : "bad"), el("span", "", `${d.duration}s`), el("span", "", `sha256 ${d.sha256.slice(0, 12)}`));
      li.className = d.exit_code === 0 ? "ok-step" : "fail-step";
      if (d.output) li.append(el("pre", "", d.output));
      break;
    }
    case "file_written": {
      const pre = el("pre", "", d.content);
      addStep("", [t, "write", d.path, `${d.bytes} bytes`], pre);
      break;
    }
    case "containment": {
      state.containment += 1;
      const ul = $("#containment");
      if (state.containment === 1) ul.innerHTML = "";
      ul.append(el("li", "", `${d.label}${d.sample ? ` (${d.sample})` : ""}`));
      addStep("block", [t, pill("contained", "bad"), d.sandbox], el("div", "", d.label), d.sample ? el("div", "cmd", d.sample) : "");
      break;
    }
    case "egress": {
      const key = `${d.allowed}|${d.host}:${d.port}|${d.reason}`;
      const ul = $("#egress");
      if (!state.egress.size) ul.innerHTML = "";
      if (state.egress.has(key)) {
        const row = state.egress.get(key);
        row.count += 1;
        row.li.textContent = `${d.allowed ? "allowed" : "DENIED"} ${d.host}:${d.port} x${row.count}${d.allowed ? "" : ": " + d.reason}`;
        return;
      }
      const li = el("li", d.allowed ? "allow" : "deny", `${d.allowed ? "allowed" : "DENIED"} ${d.host}:${d.port}${d.allowed ? "" : ": " + d.reason}`);
      state.egress.set(key, { li, count: 1 });
      ul.append(li);
      if (!d.allowed) addStep("block", [t, pill("egress denied", "bad"), d.sandbox], el("div", "", `${d.method} ${d.host}:${d.port}: ${d.reason}`));
      break;
    }
    case "agent_finished":
      addStep("", [t, "agent", d.outcome], el("div", "", d.claim ? `Claim: ${d.claim}` : d.reason || ""), d.notes ? el("div", "muted", d.notes) : "", el("div", "muted", `${d.tool_calls} tool calls, ${d.prompt_tokens + d.completion_tokens} tokens`));
      break;
    case "verify_result":
      addStep(d.outcome === "error" ? "fail-step" : "ok-step", [t, pill("verify " + d.role), d.ref], el("div", "", `commit ${d.commit ? d.commit.slice(0, 12) : "?"}, setup exit ${d.setup_exit}, repro exits ${d.repro_exits.join(", ") || "none"}: ${d.outcome}${d.lost ? " (" + d.lost + ")" : ""}`));
      break;
    case "bisect":
      addStep("ok-step", [t, pill("bisect")], el("div", "", d.commit ? `first changed commit ${d.commit.slice(0, 12)}: ${d.subject}` : "bisect found no single commit"), el("div", "muted", `range ${d.range}, ${d.commits_in_range} commits`));
      break;
    case "verdict":
      showVerdict(d);
      break;
    case "comment_posted":
      addStep("", [t, "comment"], el("a", "", d.url));
      break;
    case "error":
      addStep("fail-step", [t, "error"], el("div", "error", d.message));
      break;
    case "done":
      $("#job-status").textContent = `Finished in ${d.seconds}s`;
      break;
  }
}

function renderSpec(spec) {
  const dl = $("#spec");
  if (dl.childElementCount) return;
  for (const [k, v] of Object.entries(spec)) {
    dl.append(el("dt", "", k.replaceAll("_", " ")), el("dd", "", typeof v === "object" ? JSON.stringify(v) : String(v)));
  }
}

function showVerdict(d) {
  const box = $("#verdict");
  box.hidden = false;
  box.className = "verdict " + d.verdict;
  box.innerHTML = "";
  box.append(el("div", "label", d.title), el("div", "", d.why));
  if (d.culprit && d.culprit.commit) {
    box.append(el("div", "cmd", `${d.verdict === "fixed" ? "fixed by" : "introduced by"} ${d.culprit.commit.slice(0, 12)} ${d.culprit.subject || ""}`));
  }
  if (d.reported && d.default) {
    const table = el("table");
    const head = el("tr");
    for (const h of ["run", "ref", "commit", "setup", "repro exits", "outcome"]) head.append(el("th", "", h));
    table.append(head);
    for (const [name, r] of [["reported", d.reported], ["default branch", d.default]]) {
      const tr = el("tr");
      for (const v of [name, r.ref, (r.commit || "").slice(0, 12), r.setup_exit, r.repro_exits.join(", "), r.outcome]) tr.append(el("td", "", String(v)));
      table.append(tr);
    }
    box.append(table, el("div", "muted", "Decided by the exit codes of the reproduction, re-run in fresh sandboxes by the backend, not by the model."));
  }
  if (config && config.comment_repos.length) {
    const repo = $("#job-repo").textContent.split(" ")[0];
    if (config.comment_repos.includes(repo)) $("#comment-btn").hidden = false;
  }
}

async function job(id) {
  $("#job").hidden = false;
  $("#report-link").href = `/api/jobs/${id}/report.md`;
  $("#comment-btn").onclick = async () => {
    if (!confirm("Post this report as a comment on the issue?")) return;
    const res = await fetch(`/api/jobs/${id}/comment`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
    const body = await res.json();
    alert(res.ok ? `Posted: ${body.url}` : body.detail);
  };
  const src = new EventSource(`/api/jobs/${id}/stream`);
  src.onmessage = (m) => {
    const e = JSON.parse(m.data);
    render(e);
    if (e.kind === "done") src.close();
  };
}

(async () => {
  await loadConfig();
  const m = location.pathname.match(/^\/j\/([0-9a-f]+)/);
  if (m) job(m[1]);
  else home();
})();
