# Repro report: python-humanize/humanize#171

**Issue:** [Negative amounts of time result in `a day` from naturaldelta](https://github.com/python-humanize/humanize/issues/171)

## Verdict: Fixed on the default branch

the bug is present at the reported ref and gone on the default branch; first fixed commit b939b2e50ca7 (Call abs on the whole datetime, not just parts)

**Fixed by:** `b939b2e50ca7` Call abs on the whole datetime, not just parts (git bisect over `b1e5d43c6fd4..d16e6352c978`, 286 commits)

| run | ref | commit | setup exit | repro exits | outcome |
|---|---|---|---|---|---|
| reported | `b1e5d43c6fd44dbaf0ad86339f63bfa04982d707` | `b1e5d43c6fd4` | 0 | 1, 1 | present |
| default | `main` | `d16e6352c978` | 0 | 0, 0 | absent |

Verdicts come from the exit codes of `repro.sh` (1 = bug present, 0 = absent), re-run twice in a fresh sandbox per ref by the backend, not from the model.

## Claim

- **Reported:** naturaldelta(datetime.now() - datetime.now()) returns "a day" instead of "a moment" because a tiny negative timedelta is normalized by Python to days=-1, seconds=86399, microseconds=999999, and humanize takes abs() of individual components rather than of the whole delta.
- **Expected:** naturaldelta of a tiny (negative) timedelta such as datetime.now() - datetime.now() should return "a moment" (or another reasonable representation of a fraction of a second), never "a day".
- **Reported ref:** `b1e5d43c6fd44dbaf0ad86339f63bfa04982d707`

**Agent notes:** Verified at reported ref b1e5d43c (issue filed against 4.9.0, but the code at that ref still has the bug): repro.sh exits 1 with "REPRO: BUG PRESENT"; the issue snippet yields "a day" (mixed with "a moment" since the sign of now()-now() is non-deterministic), and the deterministic equivalent timedelta(days=-1, seconds=86399, microseconds=999999) (== timedelta(microseconds=-1)) yields "a day". On current main d16e635 the same script exits 0 with "REPRO: BUG ABSENT" (both cases return "a moment"), because commit b939b2e "Call abs on the whole datetime, not just parts" (PR #173, follow-up to issue #171) added `delta = abs(delta)` in src/humanize/time.py. setup.sh installs the checkout into /work/venv via pip (hatchling/hatch-vcs build backend, build isolation works; a --no-build-isolation fallback is included). setup.sh is idempotent (ran twice successfully). Nothing suspicious in the report; the reporter's snippet is used directly, plus a deterministic variant since now()-now() can be either sign.

### `/work/setup.sh`

```bash
#!/usr/bin/env bash
# Install the humanize checkout at /work/repo into /work/venv (idempotent).
set -euo pipefail

cd /work/repo

python3 -m venv /work/venv

# Upgrade pip so modern build backends (hatchling/hatch-vcs) are supported.
/work/venv/bin/python -m pip install --upgrade pip setuptools --quiet

# Install the project itself from the current checkout.
/work/venv/bin/python -m pip install --quiet --no-input . \
  || /work/venv/bin/python -m pip install --quiet --no-input --no-build-isolation .

/work/venv/bin/python -c "import humanize; print('humanize installed:', humanize.__file__)"
```

### `/work/repro.sh`

```bash
#!/usr/bin/env bash
# Reproduction for humanize issue #171:
#   naturaldelta(datetime.now() - datetime.now()) returns "a day"
#   instead of "a moment" for a tiny negative timedelta.
set -uo pipefail

cd /work/repo

/work/venv/bin/python - <<'PY'
import datetime as dt
from humanize import naturaldelta

# 1. The exact snippet from the issue (sign is non-deterministic, so run a few times).
issue_results = {naturaldelta(dt.datetime.now() - dt.datetime.now()) for _ in range(20)}

# 2. A deterministic equivalent of the tiny negative delta the issue produces:
#    datetime.now() - datetime.now() is a small negative timedelta, which
#    Python normalizes to days=-1, seconds=86399, microseconds=999999.
tiny_negative = dt.timedelta(days=-1, seconds=86399, microseconds=999999)
assert tiny_negative == dt.timedelta(microseconds=-1), tiny_negative
deterministic_result = naturaldelta(tiny_negative)

print("issue snippet results:", sorted(issue_results))
print("deterministic tiny negative delta:", tiny_negative)
print("deterministic result:", repr(deterministic_result))

buggy = ("a day" in issue_results) or (deterministic_result == "a day")

if buggy:
    print("REPRO: BUG PRESENT")
    raise SystemExit(1)
print("REPRO: BUG ABSENT")
PY
exit $?
```

## Command log

| time | sandbox | step | command | exit | seconds | output sha256 |
|---|---|---|---|---|---|---|
| 12:22:29 | `-agent-38656f` | clone | `git clone --quiet --filter=blob:none https://github.com/python-humanize/humanize.git /work/repo && git -C /work/repo log -1 --format=%H` | 0 | 1.37 | `daff191f8d57e26d` |
| 12:22:29 | `-agent-38656f` | inspect | `cd /work/repo && echo HEAD=$(git rev-parse HEAD) && echo FILED=$(git rev-list -1 --before=2024-02-21T18:29:57Z HEAD) && echo TAGS=$(git t...` | 0 | 0.1 | `1d5834d172f9a27d` |
| 12:22:31 | `-agent-38656f` | agent | `cd /work/repo && git log --oneline -3 && git status \| head -5` | 0 | 0.08 | `581fb198dc3705f2` |
| 12:22:31 | `-agent-38656f` | agent | `cd /work/repo && sed -n 100,200p src/humanize/time.py` | 0 | 0.06 | `6277273a829d1997` |
| 12:22:32 | `-agent-38656f` | agent | `cd /work/repo && git log --oneline b1e5d43c6fd44dbaf0ad86339f63bfa04982d707 -1 && git log --oneline --all --grep="negative" -i \| head -20` | 0 | 0.08 | `67c960be9bf2abf9` |
| 12:23:11 | `-agent-38656f` | agent | `cd /work/repo && git log -S "delta = abs(delta)" --oneline -- src/humanize/time.py \| tail -5` | 0 | 38.93 | `6c02895d78ec06b0` |
| 12:23:16 | `-agent-38656f` | agent | `cd /work/repo && git log --oneline b939b2e -3 && echo --- && git merge-base --is-ancestor b1e5d43c b939b2e && echo "b1e5d43 is ancestor o...` | 0 | 0.07 | `2a6e9a908ab0c8e8` |
| 12:23:22 | `-agent-38656f` | agent | `cd /work/repo && sed -n 1,60p pyproject.toml` | 0 | 0.05 | `ed48ef1fe72cd7e5` |
| 12:23:22 | `-agent-38656f` | agent | `cd /work/repo && git show b1e5d43c:src/humanize/time.py \| sed -n 125,195p` | 0 | 0.05 | `b6f2ff376cc91714` |
| 12:23:28 | `-agent-38656f` | agent | `cd /work/repo && git show 717ef71 --stat && git show 717ef71 \| head -60` | 0 | 0.51 | `5f346f43c6727eac` |
| 12:23:43 | `-agent-38656f` | agent | `cd /work/repo && ls src/humanize && head -20 src/humanize/__init__.py && echo === && git show b1e5d43c:src/humanize/__init__.py \| head -...` | 0 | 0.91 | `4db39289929f5795` |
| 12:24:00 | `-agent-38656f` | agent | `cd /work/repo && git checkout -q b1e5d43c6fd44dbaf0ad86339f63bfa04982d707 && git log --oneline -1 && bash /work/setup.sh 2>&1 \| tail -5` | 0 | 9.15 | `f7c882e2dcfb50fa` |
| 12:24:01 | `-agent-38656f` | agent | `bash /work/repro.sh; echo "exit=$?"` | 0 | 0.36 | `c47944a0c1b9be7a` |
| 12:24:09 | `-agent-38656f` | agent | `cd /work/repo && git checkout -q main && git log --oneline -1 && bash /work/setup.sh 2>&1 \| tail -3 && bash /work/repro.sh; echo "repro ...` | 0 | 6.26 | `b3fb0e59cc2c6be1` |
| 12:24:22 | `-agent-38656f` | agent | `bash /work/setup.sh >/dev/null 2>&1 && echo "second setup run OK" && bash /work/repro.sh; echo "exit=$?"` | 0 | 6.31 | `95f638a7bc7bf7ee` |
| 12:24:30 | `-agent-38656f` | agent | `cd /work/repo && git checkout -q b1e5d43c6fd44dbaf0ad86339f63bfa04982d707 && bash /work/setup.sh >/dev/null 2>&1 && bash /work/repro.sh; ...` | 0 | 6.22 | `c47944a0c1b9be7a` |
| 12:24:38 | `-agent-38656f` | agent | `bash /work/repro.sh; echo "exit=$?"` | 0 | 0.35 | `c47944a0c1b9be7a` |
| 12:24:44 | `efault-7ab3f6` | default: checkout main | `git clone --quiet --filter=blob:none https://github.com/python-humanize/humanize.git /work/repo && cd /work/repo && (git checkout --quiet...` | 0 | 1.49 | `daff191f8d57e26d` |
| 12:24:45 | `ported-65e46e` | reported: checkout b1e5d43c6fd44dbaf0ad86339f63bfa04982d707 | `git clone --quiet --filter=blob:none https://github.com/python-humanize/humanize.git /work/repo && cd /work/repo && (git checkout --quiet...` | 0 | 1.79 | `4ff78b3e87f50979` |
| 12:24:54 | `efault-7ab3f6` | default: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.15 | `c051af69b7558083` |
| 12:24:54 | `efault-7ab3f6` | default: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 0 | 0.17 | `0205c2f23c986ab0` |
| 12:24:54 | `efault-7ab3f6` | default: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 0 | 0.16 | `0205c2f23c986ab0` |
| 12:24:54 | `ported-65e46e` | reported: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.42 | `c051af69b7558083` |
| 12:24:55 | `ported-65e46e` | reported: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.36 | `0deeaf7d7274973b` |
| 12:24:55 | `ported-65e46e` | reported: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.39 | `0deeaf7d7274973b` |
| 12:24:57 | `bisect-104890` | bisect: clone | `git clone --quiet https://github.com/python-humanize/humanize.git /work/repo && git -C /work/repo rev-list --count b1e5d43c6fd44dbaf0ad86...` | 0 | 1.06 | `391feecb66047842` |
| 12:25:50 | `bisect-104890` | bisect: run | `cd /work/repo && git bisect start --term-old=broken --term-new=fixed d16e6352c9785c5ab86de0133222bd22e89b0db2 b1e5d43c6fd44dbaf0ad86339f6...` | 0 | 52.34 | `bc4887cf8c5c801e` |

## Network egress allowed

`files.pythonhosted.org:443`, `github.com:443`, `pypi.org:443`

## Sandboxes

- `repro-bf1557e3-agent-38656f` container `880ced172d7e`, runtime `runsc`
- `repro-bf1557e3-verify-reported-65e46e` container `69b1c73c5b70`, runtime `runsc`
- `repro-bf1557e3-verify-default-7ab3f6` container `30e365418235`, runtime `runsc`
- `repro-bf1557e3-bisect-104890` container `721d2679cc2f`, runtime `runsc`
- destroyed `repro-bf1557e3-agent-38656f` after 134.7s: agent phase finished
- destroyed `repro-bf1557e3-verify-default-7ab3f6` after 11.8s: verification at main finished
- destroyed `repro-bf1557e3-verify-reported-65e46e` after 12.8s: verification at b1e5d43c6fd44dbaf0ad86339f63bfa04982d707 finished
- destroyed `repro-bf1557e3-bisect-104890` after 54.4s: bisect finished

Every sandbox: runtime runsc; image repro-sandbox:latest; user 1000:1000 (non-root); root_filesystem read-only; writable {'/work': '3g', '/tmp': '512m', '/home/repro': '512m'}; memory 2g; cpus 2.0; pids 256; capabilities all dropped; no_new_privileges True; network repro-sandbox (internal, no route out; egress only via the gate); docker_socket not mounted; host_mounts none; command_timeout_s 300

Model work: 19 tool calls, 74512 prompt tokens, 6583 completion tokens.

Generated by Repro. Commands, exit codes and output hashes are recorded by the backend, not reported by the model.
