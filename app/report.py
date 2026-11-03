import time


def _ts(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(t))


def _fence(text: str, lang: str = "") -> str:
    text = text.replace("```", "``\u200b`")
    return f"```{lang}\n{text.rstrip()}\n```"


def render_report(job: dict, events: list[dict]) -> str:
    by_kind: dict[str, list[dict]] = {}
    for e in events:
        by_kind.setdefault(e["kind"], []).append(e)
    issue = (by_kind.get("issue") or [{"data": {}}])[0]["data"]
    verdict = (by_kind.get("verdict") or [{"data": {}}])[-1]["data"]
    agent = (by_kind.get("agent_finished") or [{"data": {}}])[-1]["data"]
    lines = [f"# Repro report: {issue.get('owner', '')}/{issue.get('repo', '')}#{issue.get('number', '')}", ""]
    lines += [f"**Issue:** [{issue.get('title', '')}]({issue.get('url', job.get('issue_url', ''))})", ""]
    if verdict:
        lines += [f"## Verdict: {verdict.get('title', '')}", "", verdict.get("why", ""), ""]
        culprit = verdict.get("culprit") or {}
        if culprit.get("commit"):
            label = "Fixed by" if verdict.get("verdict") == "fixed" else "Introduced by"
            lines += [f"**{label}:** `{culprit['commit'][:12]}` {culprit.get('subject', '')} (git bisect over "
                      f"`{culprit.get('range', '')}`, {culprit.get('commits_in_range', '?')} commits)", ""]
        rows = []
        for key in ("reported", "default"):
            r = verdict.get(key)
            if r:
                rows.append(f"| {key} | `{r.get('ref', '')}` | `{(r.get('commit') or '')[:12]}` | {r.get('setup_exit')} | "
                            f"{', '.join(str(x) for x in r.get('repro_exits', []))} | {r.get('outcome')} |")
        if rows:
            lines += ["| run | ref | commit | setup exit | repro exits | outcome |", "|---|---|---|---|---|---|", *rows, ""]
        lines += ["Verdicts come from the exit codes of `repro.sh` (1 = bug present, 0 = absent), re-run twice in a fresh "
                  "sandbox per ref by the backend, not from the model.", ""]
    if agent.get("claim"):
        lines += ["## Claim", "", f"- **Reported:** {agent.get('claim', '')}", f"- **Expected:** {agent.get('expected', '')}",
                  f"- **Reported ref:** `{agent.get('reported_ref', '')}`", ""]
        if agent.get("notes"):
            lines += [f"**Agent notes:** {agent['notes']}", ""]
    scripts = {}
    for e in by_kind.get("file_written", []):
        path = e["data"].get("path", "")
        if path in ("/work/setup.sh", "/work/repro.sh"):
            scripts[path] = e["data"].get("content", "")
    for path, content in scripts.items():
        lines += [f"### `{path}`", "", _fence(content, "bash"), ""]
    containment = by_kind.get("containment", [])
    denied = [e for e in by_kind.get("egress", []) if not e["data"].get("allowed")]
    if containment or denied:
        lines += ["## Containment events", ""]
        for e in containment:
            d = e["data"]
            lines.append(f"- {_ts(e['ts'])} `{d.get('sandbox', '')}`: {d.get('label', '')}"
                         + (f" (`{d.get('sample', '')}`)" if d.get("sample") else ""))
        for e in denied:
            d = e["data"]
            lines.append(f"- {_ts(e['ts'])} `{d.get('sandbox', '')}`: egress to `{d.get('host')}:{d.get('port')}` "
                         f"denied: {d.get('reason')}")
        lines.append("")
    lines += ["## Command log", "", "| time | sandbox | step | command | exit | seconds | output sha256 |", "|---|---|---|---|---|---|---|"]
    for e in by_kind.get("exec_end", []):
        d = e["data"]
        cmd = d.get("command", "").replace("|", "\\|").replace("\n", " ")
        if len(cmd) > 140:
            cmd = cmd[:137] + "..."
        lines.append(f"| {_ts(e['ts'])[11:19]} | `{d.get('sandbox', '')[-13:]}` | {d.get('label', '')} | `{cmd}` | "
                     f"{d.get('exit_code')} | {d.get('duration')} | `{d.get('sha256', '')[:16]}` |")
    lines.append("")
    allowed = [e for e in by_kind.get("egress", []) if e["data"].get("allowed")]
    if allowed:
        hosts = sorted({f"{e['data'].get('host')}:{e['data'].get('port')}" for e in allowed})
        lines += ["## Network egress allowed", "", ", ".join(f"`{h}`" for h in hosts), ""]
    sandboxes = by_kind.get("sandbox_started", [])
    if sandboxes:
        spec = sandboxes[0]["data"].get("spec", {})
        lines += ["## Sandboxes", ""]
        for e in sandboxes:
            d = e["data"]
            lines.append(f"- `{d.get('name')}` container `{d.get('container')}`, runtime `{d.get('runtime')}`")
        for e in by_kind.get("sandbox_destroyed", []):
            d = e["data"]
            lines.append(f"- destroyed `{d.get('name')}` after {d.get('lifetime')}s: {d.get('reason')}")
        lines += ["", "Every sandbox: " + "; ".join(f"{k} {v}" for k, v in spec.items() if k != "env"), ""]
    if agent:
        lines += [f"Model work: {agent.get('tool_calls', 0)} tool calls, {agent.get('prompt_tokens', 0)} prompt tokens, "
                  f"{agent.get('completion_tokens', 0)} completion tokens.", ""]
    lines += ["Generated by Repro. Commands, exit codes and output hashes are recorded by the backend, not reported by the model."]
    return "\n".join(lines) + "\n"
