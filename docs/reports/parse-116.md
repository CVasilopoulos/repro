# Repro report: r1chardj0n3s/parse#116

**Issue:** [explicit string format as {name_:s} does not work](https://github.com/r1chardj0n3s/parse/issues/116)

## Verdict: Reproduced on the default branch

the bug is present at the reported ref and still present on the default branch

| run | ref | commit | setup exit | repro exits | outcome |
|---|---|---|---|---|---|
| reported | `19689cf5b4e0b025821be2e59e0bff0ab5977361` | `19689cf5b4e0` | 0 | 1, 1 | present |
| default | `master` | `616ac26ca407` | 0 | 1, 1 | present |

Verdicts come from the exit codes of `repro.sh` (1 = bug present, 0 = absent), re-run twice in a fresh sandbox per ref by the backend, not from the model.

## Claim

- **Reported:** parse.parse() returns None for a template using the explicit string format spec "{name:s}", even though str.format() with the same template produces a string that should match (e.g. parse.parse("test_{name:s}", "test_hello") -> None).
- **Expected:** parse.parse("test_{name:s}", "test_hello") should return a Result with name='hello', i.e. the ":s" format spec should behave like the default string format as it does in str.format(), instead of being interpreted as "whitespace".
- **Reported ref:** `19689cf5b4e0b025821be2e59e0bff0ab5977361`

**Agent notes:** Reproduced exactly as reported at the issue-time HEAD 19689cf (parse 1.16.0) and still present on current master 616ac26 (parse 1.22.x). parse.parse("test_{name:s}", "test_hello") returns None while parse.parse("test_{name}", "test_hello") works. Root cause is in Parser._handle_field in parse/__init__.py: there is no branch for type == "s", so it falls through to the generic `elif type: s = r"\%s+" % type`, i.e. ":s" is compiled as a whitespace regex (\s+), matching Python's format spec meaning of "s" only for whitespace. The maintainer acknowledged this in the issue comments as a deviation from str.format (he mis-read the format spec) and said a fix would need a backwards-incompatible major release, so the issue is open by design for now. Nothing suspicious in the report; the reproduction is the reporter's own snippet. Note: the sandbox checkout had a pre-existing uncommitted modification to README.rst (a version-history line for 1.16.0 crediting the reporter); I reverted it before testing so both refs are tested from clean trees.

### `/work/setup.sh`

```bash
#!/bin/bash
# Install the `parse` package from the current checkout into /work/venv.
set -e
cd /work/repo

python3 -m venv /work/venv
/work/venv/bin/pip install --upgrade pip setuptools wheel >/dev/null
/work/venv/bin/pip install . >/dev/null
/work/venv/bin/python -c "import parse; print('installed parse', parse.__version__)"
```

### `/work/repro.sh`

```bash
#!/bin/bash
# Reproduction of r1chardj0n3s/parse issue #116:
# an explicit string format spec "{name:s}" does not parse the string that
# str.format() produced for the same template.
set -e
cd /work/repo

PY=/work/venv/bin/python
[ -x "$PY" ] || PY=python3

"$PY" - <<'EOF'
import parse

form = "test_{name:s}"
s = form.format(name="hello")  # -> 'test_hello'

r = parse.parse(form, s)

if r is not None and r["name"] == "hello":
    print("REPRO: BUG ABSENT - parse(%r, %r) -> %r" % (form, s, r))
else:
    print("REPRO: BUG PRESENT - parse(%r, %r) -> %r (expected Result with name='hello')"
          % (form, s, r))
    # show what ":s" is actually being treated as (whitespace) for context
    ws = parse.parse("{:s}", "   ")
    print("       note: parse treats ':s' as whitespace, e.g. parse('{:s}', '   ') -> %r" % (ws,))
    raise SystemExit(1)
EOF
```

## Command log

| time | sandbox | step | command | exit | seconds | output sha256 |
|---|---|---|---|---|---|---|
| 12:26:02 | `-agent-6595d2` | clone | `git clone --quiet --filter=blob:none https://github.com/r1chardj0n3s/parse.git /work/repo && git -C /work/repo log -1 --format=%H` | 0 | 1.21 | `9c46527a516c30b4` |
| 12:26:02 | `-agent-6595d2` | inspect | `cd /work/repo && echo HEAD=$(git rev-parse HEAD) && echo FILED=$(git rev-list -1 --before=2020-08-13T19:16:55Z HEAD) && echo TAGS=$(git t...` | 0 | 0.08 | `da514bc91e7cd0c5` |
| 12:26:04 | `-agent-6595d2` | agent | `cd /work/repo && git log --oneline -3 && ls parse && head -50 parse/__init__.py` | 0 | 0.06 | `fb7f519e094fd45f` |
| 12:26:05 | `-agent-6595d2` | agent | `cd /work/repo && grep -n "type == 's'\\|'s'\\|_handle_field\\|def _parse" parse/__init__.py \| head -50` | 0 | 0.05 | `ac0e7f8ea1d0023f` |
| 12:26:08 | `-agent-6595d2` | agent | `cd /work/repo && sed -n 600,760p parse/__init__.py` | 0 | 0.05 | `5d5ea3298b50334d` |
| 12:26:09 | `-agent-6595d2` | agent | `cd /work/repo && sed -n 760,830p parse/__init__.py` | 0 | 0.05 | `b3a1112e8db4fd66` |
| 12:26:11 | `-agent-6595d2` | agent | `cd /work/repo && sed -n 830,900p parse/__init__.py` | 0 | 0.05 | `bf122ad789c843c3` |
| 12:26:13 | `-agent-6595d2` | agent | `cd /work/repo && python3 -c " import parse form = 'test_{name:s}' s = form.format(name='hello') print(repr(s)) print(parse.parse(form, s)...` | 0 | 0.16 | `06f1f4841b27e3ed` |
| 12:26:13 | `-agent-6595d2` | agent | `cd /work/repo && grep -n "s\b" tests/test_parse.py \| grep -i "type\\|':s'\\|\":s\"" \| head -20` | 0 | 0.06 | `d387298b8306571f` |
| 12:26:17 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -q 19689cf5b4e0b025821be2e59e0bff0ab5977361 && python3 -c " import parse form = 'test_{name:s}' s = form.fo...` | 0 | 0.62 | `4c24542f40bae37a` |
| 12:26:27 | `-agent-6595d2` | agent | `cd /work && bash repro.sh; echo "exit=$?"` | 0 | 0.19 | `c496fd3859a49d4a` |
| 12:26:37 | `-agent-6595d2` | agent | `cd /work && bash setup.sh && bash repro.sh; echo "exit=$?"` | 0 | 9.5 | `7efd68346a767917` |
| 12:26:39 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -q master && cd /work && bash setup.sh >/dev/null 2>&1 && bash repro.sh; echo "exit=$?"` | 0 | 0.05 | `36e93aa1e955d7bf` |
| 12:26:40 | `-agent-6595d2` | agent | `cd /work/repo && git status --porcelain && git diff --stat` | 0 | 0.05 | `b32178e821c380b7` |
| 12:26:41 | `-agent-6595d2` | agent | `cd /work/repo && git diff README.rst` | 0 | 0.06 | `035dd4dc43416028` |
| 12:26:50 | `-agent-6595d2` | agent | `cd /work/repo && git stash && git checkout -q master && git log --oneline -1 && cd /work && bash setup.sh >/dev/null 2>&1 && bash repro.s...` | 0 | 7.66 | `2acf461c284ab68f` |
| 12:26:59 | `-agent-6595d2` | agent | `cd /work && bash setup.sh >/dev/null 2>&1 && bash repro.sh; echo "exit=$?"; cd /work/repo && git stash pop && git status --porcelain` | 1 | 7.8 | `17ba05c6df234eed` |
| 12:27:02 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -- README.rst && git stash drop && rm -rf build parse.egg-info && git status --porcelain && git log --oneli...` | 1 | 0.06 | `9d94f51d8e7a898d` |
| 12:27:03 | `-agent-6595d2` | agent | `cd /work/repo && git reset -q --hard HEAD && git stash drop 2>/dev/null; rm -rf build parse.egg-info; git status --porcelain; git log --o...` | 0 | 0.09 | `2f58e5546341aa71` |
| 12:27:12 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -q 19689cf5b4e0b025821be2e59e0bff0ab5977361 && git status --porcelain && cd /work && bash setup.sh >/dev/nu...` | 0 | 6.69 | `c496fd3859a49d4a` |
| 12:27:15 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -q master && git status --porcelain; cd /work && cat setup.sh repro.sh` | 0 | 0.06 | `30f9e84bfc1657a1` |
| 12:27:16 | `-agent-6595d2` | agent | `cd /work/repo && git diff --stat && git diff \| head -20` | 0 | 0.06 | `621d29ed60e68d51` |
| 12:27:17 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -- README.rst && git status --porcelain && git log --oneline -1` | 0 | 0.06 | `ddfbc68317bcec52` |
| 12:27:24 | `-agent-6595d2` | agent | `cd /work/repo && git checkout -q master && git log --oneline -1 && git status --porcelain && cd /work && bash setup.sh >/dev/null 2>&1 &&...` | 0 | 6.69 | `689a2effe29c76e6` |
| 12:27:27 | `-agent-6595d2` | agent | `cd /work/repo && rm -rf build parse.egg-info && git status --porcelain && git log --oneline -1` | 0 | 0.06 | `02262da861752a60` |
| 12:27:32 | `efault-95fcfe` | default: checkout master | `git clone --quiet --filter=blob:none https://github.com/r1chardj0n3s/parse.git /work/repo && cd /work/repo && (git checkout --quiet maste...` | 0 | 1.23 | `9c46527a516c30b4` |
| 12:27:33 | `ported-1a89bb` | reported: checkout 19689cf5b4e0b025821be2e59e0bff0ab5977361 | `git clone --quiet --filter=blob:none https://github.com/r1chardj0n3s/parse.git /work/repo && cd /work/repo && (git checkout --quiet 19689...` | 0 | 1.75 | `b2380170268c1e6d` |
| 12:27:42 | `efault-95fcfe` | default: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.86 | `8d1bca48eec8cf85` |
| 12:27:42 | `ported-1a89bb` | reported: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.54 | `6ec9c6de2c915723` |
| 12:27:43 | `efault-95fcfe` | default: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.21 | `10d736647eb7a3c7` |
| 12:27:43 | `ported-1a89bb` | reported: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.21 | `10d736647eb7a3c7` |
| 12:27:43 | `efault-95fcfe` | default: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.22 | `10d736647eb7a3c7` |
| 12:27:43 | `ported-1a89bb` | reported: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.22 | `10d736647eb7a3c7` |

## Network egress allowed

`files.pythonhosted.org:443`, `github.com:443`, `pypi.org:443`

## Sandboxes

- `repro-e0db6482-agent-6595d2` container `e8a54ddff02b`, runtime `runsc`
- `repro-e0db6482-verify-reported-1a89bb` container `4383061cf1e8`, runtime `runsc`
- `repro-e0db6482-verify-default-95fcfe` container `d35a6a525487`, runtime `runsc`
- destroyed `repro-e0db6482-agent-6595d2` after 90.3s: agent phase finished
- destroyed `repro-e0db6482-verify-default-95fcfe` after 12.4s: verification at master finished
- destroyed `repro-e0db6482-verify-reported-1a89bb` after 12.6s: verification at 19689cf5b4e0b025821be2e59e0bff0ab5977361 finished

Every sandbox: runtime runsc; image repro-sandbox:latest; user 1000:1000 (non-root); root_filesystem read-only; writable {'/work': '3g', '/tmp': '512m', '/home/repro': '512m'}; memory 2g; cpus 2.0; pids 256; capabilities all dropped; no_new_privileges True; network repro-sandbox (internal, no route out; egress only via the gate); docker_socket not mounted; host_mounts none; command_timeout_s 300

Model work: 26 tool calls, 116249 prompt tokens, 4307 completion tokens.

Generated by Repro. Commands, exit codes and output hashes are recorded by the backend, not reported by the model.
