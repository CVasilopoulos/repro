# Repro report: python-humanize/humanize#57

**Issue:** [`metric(0)` crashes](https://github.com/python-humanize/humanize/issues/57)

## Verdict: Fixed on the default branch

the bug is present at the reported ref and gone on the default branch; first fixed commit b1ee68758208 (Fix metric(0) crash.)

**Fixed by:** `b1ee68758208` Fix metric(0) crash. (git bisect over `dab62bfbc9ac..d16e6352c978`, 523 commits)

| run | ref | commit | setup exit | repro exits | outcome |
|---|---|---|---|---|---|
| reported | `4.3.0` | `dab62bfbc9ac` | 0 | 1, 1 | present |
| default | `main` | `d16e6352c978` | 0 | 0, 0 | absent |

Verdicts come from the exit codes of `repro.sh` (1 = bug present, 0 = absent), re-run twice in a fresh sandbox per ref by the backend, not from the model.

## Claim

- **Reported:** On humanize 4.3.0, `humanize.metric(0)` raises `ValueError: math domain error` because `metric()` computes `int(math.floor(math.log10(abs(value))))` without guarding against value == 0.
- **Expected:** `humanize.metric(0)` should not crash and should return a sensible string such as "0.00" (fixed by PR #47, released in 4.4.0).
- **Reported ref:** `4.3.0`

**Agent notes:** Reporter used humanize 4.3.0 (tag 4.3.0 in this repo), where src/humanize/number.py line 511 reads `exponent = int(math.floor(math.log10(abs(value))))` with no zero guard, so metric(0) raises ValueError: math domain error. Verified: at tag 4.3.0 repro.sh exits 1 with "REPRO: BUG PRESENT"; at the issue-filing HEAD 5553ff5 (which already contains fix PR #47, version reports as 4.4.0) and at current main d16e635 (4.16.1.dev46), metric(0) returns '0.00' and repro.sh exits 0 with "REPRO: BUG ABSENT". So the bug is real but already fixed by the time of the issue-filing HEAD; the reporter's comment confirms it was fixed in PR #47 and released in 4.4.0. setup.sh installs the checkout non-editable with --no-build-isolation (build deps for both old setuptools_scm and new hatch-vcs backends are pre-installed) and is idempotent; the setuptools_scm/hatch-vcs warnings on 4.3.0 are harmless. Nothing suspicious in the report.

### `/work/setup.sh`

```bash
#!/usr/bin/env bash
# Install the humanize package from the current checkout into /work/venv.
set -euo pipefail

cd /work/repo

python3 -m venv /work/venv

# shellcheck disable=SC1091
source /work/venv/bin/activate

# Build deps for both the old (setuptools_scm) and new (hatch-vcs) build systems.
pip install --quiet --upgrade pip
pip install --quiet "setuptools>=42" "setuptools_scm[toml]>=3.4" "hatch-vcs" "hatchling"

# Install the checkout itself (non-editable so the installed copy matches the ref).
pip install --quiet --no-build-isolation .

python3 -c "import humanize, sys; print('installed humanize', humanize.__version__, 'at', humanize.__file__)"
```

### `/work/repro.sh`

```bash
#!/usr/bin/env bash
# Reproduction of issue #57: humanize.metric(0) crashes with
# "ValueError: math domain error" on humanize 4.3.0.
set -uo pipefail

# shellcheck disable=SC1091
source /work/venv/bin/activate

python3 - <<'PY'
import humanize

print("humanize version:", humanize.__version__)

try:
    result = humanize.metric(0)
except ValueError as e:
    # The reported bug: math.log10(abs(0)) -> ValueError: math domain error
    print("REPRO: BUG PRESENT - metric(0) raised ValueError: %s" % e)
    raise SystemExit(1)
except Exception as e:  # any other unexpected failure
    print("REPRO: BUG PRESENT - metric(0) raised %s: %s" % (type(e).__name__, e))
    raise SystemExit(1)

print("metric(0) ->", repr(result))
print("REPRO: BUG ABSENT - metric(0) did not crash")
PY
```

## Command log

| time | sandbox | step | command | exit | seconds | output sha256 |
|---|---|---|---|---|---|---|
| 11:28:23 | `-agent-14efbe` | clone | `git clone --quiet --filter=blob:none https://github.com/python-humanize/humanize.git /work/repo && git -C /work/repo log -1 --format=%H` | 0 | 1.41 | `daff191f8d57e26d` |
| 11:28:23 | `-agent-14efbe` | inspect | `cd /work/repo && echo HEAD=$(git rev-parse HEAD) && echo FILED=$(git rev-list -1 --before=2022-09-21T14:59:09Z HEAD) && echo TAGS=$(git t...` | 0 | 0.1 | `e81acb3a20ac24e2` |
| 11:28:30 | `-agent-14efbe` | agent | `cd /work/repo && git log --oneline -3 && git tag \| head -50 && git status` | 0 | 0.07 | `74c0f847558d0011` |
| 11:28:31 | `-agent-14efbe` | agent | `cd /work/repo && sed -n '480,540p' src/humanize/number.py` | 0 | 0.05 | `48260e0e396977d3` |
| 11:28:35 | `-agent-14efbe` | agent | `cd /work/repo && sed -n '540,620p' src/humanize/number.py` | 0 | 0.05 | `bf129af644e46164` |
| 11:28:35 | `-agent-14efbe` | agent | `cd /work/repo && git show --stat 5553ff5308c363aeaa923362b11b7a8e299129f5 \| head -20 && git log --oneline 5553ff5 -5` | 0 | 0.5 | `eeedb9437725a55f` |
| 11:28:41 | `-agent-14efbe` | agent | `cd /work/repo && git show 5553ff5:src/humanize/number.py \| grep -n "log10" ` | 0 | 0.52 | `a65a8b7c898dc419` |
| 11:29:18 | `-agent-14efbe` | agent | `cd /work/repo && git log --oneline --all --grep="47" -i \| head -10; git log --oneline -S "value != 0 else 0" -- src/humanize/number.py \...` | 0 | 37.36 | `221f395eabec3ea2` |
| 11:29:22 | `-agent-14efbe` | agent | `cd /work/repo && git show 4.3.0:src/humanize/number.py \| grep -n "log10" && git merge-base --is-ancestor b1ee687 5553ff5 && echo "fix in...` | 0 | 0.07 | `aeacfc3f88d5b997` |
| 11:29:26 | `-agent-14efbe` | agent | `cd /work/repo && cat pyproject.toml \| head -60 && python3 --version && pip --version 2>/dev/null; ls /work` | 0 | 0.73 | `2b1833598a1f7e7e` |
| 11:29:31 | `-agent-14efbe` | agent | `cd /work/repo && git show 4.3.0:pyproject.toml \| head -30` | 0 | 0.53 | `58832d11048475c0` |
| 11:29:50 | `-agent-14efbe` | agent | `chmod +x /work/setup.sh /work/repro.sh && cd /work/repo && git checkout -q 4.3.0 && git log --oneline -1 && bash /work/setup.sh 2>&1 \| t...` | 0 | 9.69 | `698d7a2308e1a50f` |
| 11:29:54 | `-agent-14efbe` | agent | `bash /work/repro.sh; echo "exit=$?"` | 0 | 0.36 | `c61007654ce223a4` |
| 11:30:02 | `-agent-14efbe` | agent | `cd /work/repo && git checkout -q 5553ff5308c363aeaa923362b11b7a8e299129f5 && git log --oneline -1 && bash /work/setup.sh 2>&1 \| tail -3 ...` | 0 | 6.42 | `58421b0b097ea73e` |
| 11:30:14 | `-agent-14efbe` | agent | `cd /work/repo && git checkout -q d16e6352c9785c5ab86de0133222bd22e89b0db2 && git log --oneline -1 && bash /work/setup.sh 2>&1 \| tail -3 ...` | 0 | 4.98 | `ab4d63836ae3e61c` |
| 11:30:32 | `-agent-14efbe` | agent | `cd /work/repo && git checkout -q 4.3.0 && rm -rf /work/venv && bash /work/setup.sh >/dev/null 2>&1 && bash /work/repro.sh; echo "exit=$?"...` | 0 | 16.89 | `5946b8f6f0041820` |
| 11:30:49 | `-agent-14efbe` | agent | `cd /work/repo && git checkout -q 4.3.0 && bash /work/setup.sh >/dev/null 2>&1; echo "setup1=$?"; bash /work/setup.sh >/dev/null 2>&1; ech...` | 0 | 12.83 | `5fd893495b0971b8` |
| 11:30:58 | `efault-70da84` | default: checkout main | `git clone --quiet --filter=blob:none https://github.com/python-humanize/humanize.git /work/repo && cd /work/repo && (git checkout --quiet...` | 0 | 1.43 | `daff191f8d57e26d` |
| 11:30:58 | `ported-b92a7e` | reported: checkout 4.3.0 | `git clone --quiet --filter=blob:none https://github.com/python-humanize/humanize.git /work/repo && cd /work/repo && (git checkout --quiet...` | 0 | 1.93 | `33f427ef25adecb6` |
| 11:31:07 | `efault-70da84` | default: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 8.51 | `89c79c3ad9361ae7` |
| 11:31:07 | `efault-70da84` | default: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 0 | 0.16 | `b86950c064606577` |
| 11:31:07 | `efault-70da84` | default: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 0 | 0.16 | `b86950c064606577` |
| 11:31:08 | `ported-b92a7e` | reported: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.39 | `87c21d7c01733e31` |
| 11:31:08 | `ported-b92a7e` | reported: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.35 | `6f91ee9cf4580691` |
| 11:31:09 | `ported-b92a7e` | reported: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.35 | `6f91ee9cf4580691` |
| 11:31:10 | `bisect-d7443e` | bisect: clone | `git clone --quiet https://github.com/python-humanize/humanize.git /work/repo && git -C /work/repo rev-list --count dab62bfbc9ac4cd9e5d558...` | 0 | 0.81 | `308674fe33ad5aa8` |
| 11:32:07 | `bisect-d7443e` | bisect: run | `cd /work/repo && git bisect start --term-old=broken --term-new=fixed d16e6352c9785c5ab86de0133222bd22e89b0db2 dab62bfbc9ac4cd9e5d558b3872...` | 0 | 56.34 | `5706a7e15661aee3` |

## Network egress allowed

`files.pythonhosted.org:443`, `github.com:443`, `pypi.org:443`

## Sandboxes

- `repro-c9f49dce-agent-14efbe` container `af16bc6b4939`, runtime `runsc`
- `repro-c9f49dce-verify-default-70da84` container `7ba9f9946f37`, runtime `runsc`
- `repro-c9f49dce-verify-reported-b92a7e` container `f50daaec61e2`, runtime `runsc`
- `repro-c9f49dce-bisect-d7443e` container `a2cfe448c272`, runtime `runsc`
- destroyed `repro-c9f49dce-agent-14efbe` after 154.2s: agent phase finished
- destroyed `repro-c9f49dce-verify-default-70da84` after 11.1s: verification at main finished
- destroyed `repro-c9f49dce-verify-reported-b92a7e` after 12.9s: verification at 4.3.0 finished
- destroyed `repro-c9f49dce-bisect-d7443e` after 58.1s: bisect finished

Every sandbox: runtime runsc; image repro-sandbox:latest; user 1000:1000 (non-root); root_filesystem read-only; writable {'/work': '3g', '/tmp': '512m', '/home/repro': '512m'}; memory 2g; cpus 2.0; pids 256; capabilities all dropped; no_new_privileges True; network repro-sandbox (internal, no route out; egress only via the gate); docker_socket not mounted; host_mounts none; command_timeout_s 300

Model work: 18 tool calls, 64365 prompt tokens, 3798 completion tokens.

Generated by Repro. Commands, exit codes and output hashes are recorded by the backend, not reported by the model.
