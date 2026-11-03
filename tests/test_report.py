from app.report import render_report


def ev(kind, **data):
    return {"seq": 0, "ts": 1700000000.0, "kind": kind, "data": data}


def test_report_contains_verdict_scripts_commands_and_denials():
    events = [
        ev("issue", owner="o", repo="r", number=3, title="crash", url="https://github.com/o/r/issues/3"),
        ev("sandbox_started", name="repro-1-agent-a", container="abc", runtime="runsc", spec={"pids": 256, "env": []}),
        ev("exec_end", sandbox="repro-1-agent-a", label="agent", command="python -c 'print(1) | x'", exit_code=0,
           duration=0.4, sha256="f" * 64),
        ev("file_written", path="/work/repro.sh", content="exit 1"),
        ev("egress", sandbox="repro-1-agent-a", host="169.254.169.254", port=80, allowed=False,
           reason="cloud metadata endpoint"),
        ev("agent_finished", outcome="submit", claim="it crashes", expected="no crash", reported_ref="v1", notes="",
           tool_calls=4, prompt_tokens=10, completion_tokens=5),
        ev("verdict", verdict="fixed", title="Fixed on the default branch", why="gone on main",
           reported={"ref": "v1", "commit": "1" * 40, "setup_exit": 0, "repro_exits": [1, 1], "outcome": "present"},
           default={"ref": "main", "commit": "2" * 40, "setup_exit": 0, "repro_exits": [0, 0], "outcome": "absent"}),
    ]
    md = render_report({"issue_url": "https://github.com/o/r/issues/3"}, events)
    assert "## Verdict: Fixed on the default branch" in md
    assert "| reported | `v1` | `111111111111` | 0 | 1, 1 | present |" in md
    assert "```bash\nexit 1\n```" in md
    assert "`169.254.169.254:80` denied: cloud metadata endpoint" in md
    assert "print(1) \\| x" in md
    assert "runtime `runsc`" in md
