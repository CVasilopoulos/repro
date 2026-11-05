# Repro report: astanin/python-tabulate#354

**Issue:** [maxcolwidths isn't properly respected: extra whitespace is added](https://github.com/astanin/python-tabulate/issues/354)

## Verdict: Reproduced on the default branch

the bug is present at the reported ref and still present on the default branch

| run | ref | commit | setup exit | repro exits | outcome |
|---|---|---|---|---|---|
| reported | `787851ffe4350a779ba8ecd1e58c570f20d28c34` | `787851ffe435` | 0 | 1, 1 | present |
| default | `master` | `268615a5c27d` | 0 | 1, 1 | present |

Verdicts come from the exit codes of `repro.sh` (1 = bug present, 0 = absent), re-run twice in a fresh sandbox per ref by the backend, not from the model.

## Claim

- **Reported:** tabulate does not respect maxcolwidths: cells are wrapped at the requested width but then extra whitespace is added, making the column 2 characters wider than requested (e.g. maxcolwidths=8 yields 10-char-wide cell content).
- **Expected:** The rendered cell content should never be wider than the requested maxcolwidths; the format's own 1-space padding on each side is added on top of that, so a column with maxcolwidths=8 should show 8-char content lines (10 chars including the grid padding), and maxcolwidths=3 with tablefmt="grid" should show 3-char content (5 chars including padding).
- **Reported ref:** `787851ffe4350a779ba8ecd1e58c570f20d28c34`

**Agent notes:** Reproduced at both the reported ref (787851f, HEAD of master when the issue was filed; reporter used v0.9.0) and current master (268615a): exit 1, "REPRO: BUG PRESENT".

What happens: in tabulate(), minwidths for each column is computed as width_fn(header) + MIN_PADDING (MIN_PADDING = 2) when headers are present (tabulate/__init__.py, line ~2388 on master). _align_column then pads every cell to max(cell_width, minwidth), so a column whose header is at least as long as maxcolwidths gets its data cells padded to maxcolwidths + 2. The data is wrapped at the requested width by _wrap_text_to_colwidths, but the alignment step then adds 2 extra spaces. This matches the maintainer's diagnosis in the issue comments (padding applied twice: once via minwidths from the header, once by the grid format's own padding).

Observed output for the reporter's exact example: 3rd column cell content is 10 chars wide (e.g. "catenate  ") instead of 8; for the maintainer's shorter repro (tabulate([["foo"],["bar"]], headers="firstrow", tablefmt="grid", maxcolwidths=3)) the cell content is 5 chars ("foo  ") instead of 3, i.e. "+-------+" instead of "+-----+".

Verification of the check itself: I simulated a fix (dropping the header-derived minwidth) in a scratch copy and the script then prints "REPRO: BUG ABSENT" and exits 0, so the check is sensitive to the actual defect and not just failing unconditionally. Note the simulated fix is not a proposed patch, only a way to validate the test's negative branch.

Nothing suspicious in the report; the reproduction uses only the reporter's and maintainer's own examples. The scripts are self-contained (repro.sh writes its Python snippet to /tmp). One caveat: `pip install /work/repo` leaves an untracked tabulate/version.py behind (flit_scm build artifact); I removed it from the checkout, and it does not affect the scripts.

### `/work/setup.sh`

```bash
#!/bin/bash
# Setup: install the checked-out python-tabulate into a virtualenv.
set -e
cd /work/repo
python3 -m venv /work/venv
/work/venv/bin/pip install --upgrade pip >/dev/null
/work/venv/bin/pip install /work/repo
```

### `/work/repro.sh`

```bash
#!/bin/bash
# Reproduction for astanin/python-tabulate issue #354:
# "maxcolwidths isn't properly respected: extra whitespace is added"
#
# The reporter's example wraps the 3rd column at maxcolwidths=8, but the
# rendered cells are padded to 10 characters: 2 extra spaces are added on
# top of the format's own padding. The maintainer's shorter repro shows the
# same with maxcolwidths=3 and tablefmt="grid" (cells padded to 5 chars).
#
# Expected: no cell content wider than maxcolwidths (the format's own
#           1-space padding on each side is not part of the content).
#
# Exit 1 + "REPRO: BUG PRESENT" when the extra whitespace is added.
# Exit 0 + "REPRO: BUG ABSENT" when maxcolwidths is respected.
set -e
cd /work/repo

cat > /tmp/repro_354.py <<'PYEOF'
import sys

from tabulate import tabulate

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}{(': ' + detail) if detail else ''}")
        failures.append(name)


# --- Case 1: the reporter's original example -------------------------------
# 3rd column wrapped at maxcolwidths=8; header "Header#3" is 8 chars long,
# which triggers the double padding.
headers = ["Header#1", "Header#2", "Header#3"]
data = [
    [
        "Alpha beta gama zeta omega",
        "The weather was exceptionally good that day again",
        "The files were concatenated and archived for posterity.",
    ],
    [
        "Delta omega beta alpha nu and the rest",
        "The weather was exceptionally good that day",
        "They decided to engage in many businesses and all of them were successful.",
    ],
]
out = tabulate(data, headers=headers, tablefmt="fancy_grid", maxcolwidths=[None, None, 8])
print(out)
print()

VBAR = "\u2502"  # '│' vertical border of fancy_grid
contents = []  # content of the 3rd column, padding stripped
for line in out.splitlines():
    if line.startswith(VBAR):
        cell = line.split(VBAR)[-2]  # last cell before the trailing border
        contents.append(cell[1:-1])  # strip the 1-space padding on both sides
width = max(len(c) for c in contents)
check(
    "reporter's example: no cell content wider than maxcolwidths (8)",
    width == 8,
    f"3rd column content is {width} chars wide, expected 8",
)

# --- Case 2: the maintainer's shorter repro ---------------------------------
out2 = tabulate([["foo"], ["bar"]], headers="firstrow", tablefmt="grid", maxcolwidths=3)
print(out2)
print()
contents2 = []
for line in out2.splitlines():
    if line.startswith("|"):
        contents2.append(line.split("|")[1][1:-1])  # strip 1-space padding
width2 = max(len(c) for c in contents2)
check(
    "maintainer's repro: no cell content wider than maxcolwidths (3)",
    width2 == 3,
    f"column content is {width2} chars wide, expected 3",
)

print()
if failures:
    print("REPRO: BUG PRESENT - maxcolwidths not respected, extra whitespace added")
    sys.exit(1)
print("REPRO: BUG ABSENT - maxcolwidths respected")
sys.exit(0)
PYEOF

exec /work/venv/bin/python /tmp/repro_354.py
```

## Command log

| time | sandbox | step | command | exit | seconds | output sha256 |
|---|---|---|---|---|---|---|
| 11:19:17 | `-agent-30c625` | clone | `git clone --quiet --filter=blob:none https://github.com/astanin/python-tabulate.git /work/repo && git -C /work/repo log -1 --format=%H` | 0 | 1.81 | `74b48c5f1d578515` |
| 11:19:17 | `-agent-30c625` | inspect | `cd /work/repo && echo HEAD=$(git rev-parse HEAD) && echo FILED=$(git rev-list -1 --before=2024-11-14T20:28:00Z HEAD) && echo TAGS=$(git t...` | 0 | 0.1 | `68734e3f4b48ee8c` |
| 11:19:33 | `-agent-30c625` | agent | `cd /work/repo && git log --oneline -5 && git status && ls` | 0 | 0.07 | `6f6ae0f85f62ea08` |
| 11:19:33 | `-agent-30c625` | agent | `cd /work/repo && cat pyproject.toml && ls tabulate test` | 0 | 0.06 | `1d2af5151fb93f5c` |
| 11:19:35 | `-agent-30c625` | agent | `cd /work/repo && git log --oneline -3 787851ffe4350a779ba8ecd1e58c570f20d28c34 && python3 --version && which python3 pip3` | 0 | 0.07 | `c4ddd767705d7f1f` |
| 11:19:35 | `-agent-30c625` | agent | `cd /work/repo && grep -n "maxcolwidths" tabulate/__init__.py \| head -50` | 0 | 0.06 | `becc0e838709e453` |
| 11:19:37 | `-agent-30c625` | agent | `cd /work/repo && sed -n 2230,2290p tabulate/__init__.py` | 0 | 0.05 | `221fff0d55d6a4f4` |
| 11:19:37 | `-agent-30c625` | agent | `cd /work/repo && grep -n "_align_column\\|_pad_row\\|def _format_table\\|_wrap\\|textwrap" tabulate/__init__.py \| head -40` | 0 | 0.05 | `2ddbb20b48a94587` |
| 11:19:39 | `-agent-30c625` | agent | `cd /work/repo && sed -n 1616,1700p tabulate/__init__.py` | 0 | 0.06 | `7703c99577cf2f43` |
| 11:19:39 | `-agent-30c625` | agent | `cd /work/repo && sed -n 1192,1260p tabulate/__init__.py` | 0 | 0.05 | `819c24a9c27d0881` |
| 11:19:41 | `-agent-30c625` | agent | `cd /work/repo && sed -n 2612,2690p tabulate/__init__.py` | 0 | 0.05 | `8252abdb71697967` |
| 11:19:41 | `-agent-30c625` | agent | `cd /work/repo && sed -n 2380,2420p tabulate/__init__.py` | 0 | 0.05 | `41eb5fc4c321556e` |
| 11:19:46 | `-agent-30c625` | agent | `cd /work/repo && grep -n "min_padding\\|minwidths" tabulate/__init__.py` | 0 | 0.06 | `80aca349eebe0e71` |
| 11:19:46 | `-agent-30c625` | agent | `cd /work/repo && sed -n 2330,2385p tabulate/__init__.py` | 0 | 0.05 | `6a444a90658d67ca` |
| 11:19:47 | `-agent-30c625` | agent | `cd /work/repo && sed -n 2285,2300p tabulate/__init__.py && grep -n "MIN_PADDING" tabulate/__init__.py` | 0 | 0.05 | `615c872207bfeaf8` |
| 11:19:47 | `-agent-30c625` | agent | `cd /work/repo && sed -n 2425,2470p tabulate/__init__.py` | 0 | 0.05 | `d255bf5f9b46793e` |
| 11:19:58 | `-agent-30c625` | agent | `cd /work/repo && git tag --list \| tail -20 && git show v0.9.0:pyproject.toml 2>/dev/null \| head -30` | 0 | 0.52 | `0a5b3991960d7d7f` |
| 11:19:59 | `-agent-30c625` | agent | `cd /work/repo && git show v0.9.0:tabulate/__init__.py \| grep -n "MIN_PADDING\\|minwidths = " \| head` | 0 | 0.89 | `177733a42184fe3a` |
| 11:20:02 | `-agent-30c625` | agent | `cd /work/repo && git show v0.9.0:tabulate/__init__.py \| sed -n 2160,2195p` | 0 | 0.06 | `8260964de1b74ad3` |
| 11:20:06 | `-agent-30c625` | agent | `cd /work/repo && git show v0.9.0:tabulate/__init__.py \| grep -n "def _align_column" && git show v0.9.0:tabulate/__init__.py \| sed -n 11...` | 0 | 0.07 | `474e6302184e1b9d` |
| 11:20:10 | `-agent-30c625` | agent | `cd /work/repo && git show v0.9.0:tabulate/__init__.py \| sed -n 1105,1122p` | 0 | 0.05 | `4ab7796c7b3c1b47` |
| 11:20:30 | `-agent-30c625` | agent | `cd /work && python3 -m venv venv && /work/venv/bin/pip install --quiet --upgrade pip 2>&1 \| tail -2 && /work/venv/bin/pip install /work/...` | 0 | 9.15 | `7ad348a5d33fb4f9` |
| 11:20:38 | `-agent-30c625` | agent | `cd /work && /work/venv/bin/python repro.py; echo "exit=$?"` | 0 | 0.35 | `f6a8f26255f63110` |
| 11:20:55 | `-agent-30c625` | agent | `cd /work/repo && git checkout -q 787851ffe4350a779ba8ecd1e58c570f20d28c34 && /work/venv/bin/pip install --quiet /work/repo 2>&1 \| tail -...` | 0 | 4.89 | `0f6cfc1cf28a53eb` |
| 11:20:59 | `-agent-30c625` | agent | `cd /work/repo && git checkout -q master && git log --oneline -1` | 0 | 0.07 | `83d75d27500e8804` |
| 11:21:11 | `-agent-30c625` | agent | `cd /work && rm -rf venv && bash setup.sh >/dev/null 2>&1 && bash repro.sh; echo "exit=$?"` | 0 | 8.69 | `f6a8f26255f63110` |
| 11:21:22 | `-agent-30c625` | agent | `cd /work && bash repro.sh; echo "exit=$?"` | 0 | 0.36 | `8c082f67f8ce93eb` |
| 11:21:24 | `-agent-30c625` | agent | `cd /work && sed -i 's/\\u2551/\\u2502/g' repro.sh && bash repro.sh; echo "exit=$?"` | 0 | 0.4 | `f6a8f26255f63110` |
| 11:21:39 | `-agent-30c625` | agent | `cd /tmp && rm -rf repo_fixed && cp -r /work/repo repo_fixed && cd repo_fixed && python3 - <<'EOF' import re p = "tabulate/__init__.py" s ...` | 0 | 7.58 | `d481c57f3d85e666` |
| 11:22:03 | `-agent-30c625` | agent | `cd /work && bash repro.sh; echo "exit=$?"` | 0 | 0.35 | `a9bf5714d9ac0012` |
| 11:22:05 | `-agent-30c625` | agent | `cd /tmp && sed 's\|/work/venv/bin/python\|/tmp/venv_fixed/bin/python\|' /work/repro.sh > /tmp/repro_fixed.sh && sed -i 's\|cd /work/repo\...` | 0 | 0.36 | `106072bf5a461830` |
| 11:22:15 | `-agent-30c625` | agent | `cd /work/repo && git checkout -q 787851ffe4350a779ba8ecd1e58c570f20d28c34 && cd /work && rm -rf venv && bash setup.sh >/dev/null 2>&1 && ...` | 0 | 9.21 | `40eed096e945ff03` |
| 11:22:26 | `-agent-30c625` | agent | `cd /work/repo && git checkout -q master && cd /work && rm -rf venv && bash setup.sh >/dev/null 2>&1 && bash repro.sh >/tmp/out_master.txt...` | 0 | 9.11 | `e1eb635d561192c1` |
| 11:22:29 | `-agent-30c625` | agent | `cd /work && cat setup.sh && echo "=====" && cat repro.sh && echo "=====" && git -C repo log --oneline -1 && git -C repo status --short` | 0 | 0.08 | `b3628892dda87a10` |
| 11:22:34 | `-agent-30c625` | agent | `cd /work/repo && rm -f tabulate/version.py && git status --short && git log --oneline -1` | 0 | 0.06 | `83d75d27500e8804` |
| 11:22:46 | `efault-29c683` | default: checkout master | `git clone --quiet --filter=blob:none https://github.com/astanin/python-tabulate.git /work/repo && cd /work/repo && (git checkout --quiet ...` | 0 | 1.31 | `74b48c5f1d578515` |
| 11:22:46 | `ported-c4455f` | reported: checkout 787851ffe4350a779ba8ecd1e58c570f20d28c34 | `git clone --quiet --filter=blob:none https://github.com/astanin/python-tabulate.git /work/repo && cd /work/repo && (git checkout --quiet ...` | 0 | 1.93 | `351c531d4645fb0d` |
| 11:22:55 | `efault-29c683` | default: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.14 | `8689b9b844052d2c` |
| 11:22:56 | `efault-29c683` | default: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.41 | `e63232d5ce9edb92` |
| 11:22:56 | `efault-29c683` | default: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.4 | `e63232d5ce9edb92` |
| 11:22:57 | `ported-c4455f` | reported: setup | `cd /work/repo && bash /work/setup.sh` | 0 | 9.88 | `340fc887e4386844` |
| 11:22:57 | `ported-c4455f` | reported: repro run 1 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.22 | `e63232d5ce9edb92` |
| 11:22:57 | `ported-c4455f` | reported: repro run 2 | `cd /work/repo && bash /work/repro.sh` | 1 | 0.23 | `e63232d5ce9edb92` |

## Network egress allowed

`files.pythonhosted.org:443`, `github.com:443`, `pypi.org:443`

## Sandboxes

- `repro-49b38620-agent-30c625` container `591463f68a76`, runtime `runsc`
- `repro-49b38620-verify-reported-c4455f` container `00759912b20e`, runtime `runsc`
- `repro-49b38620-verify-default-29c683` container `75e990e90db9`, runtime `runsc`
- destroyed `repro-49b38620-agent-30c625` after 209.0s: agent phase finished
- destroyed `repro-49b38620-verify-default-29c683` after 12.2s: verification at master finished
- destroyed `repro-49b38620-verify-reported-c4455f` after 13.1s: verification at 787851ffe4350a779ba8ecd1e58c570f20d28c34 finished

Every sandbox: runtime runsc; image repro-sandbox:latest; user 1000:1000 (non-root); root_filesystem read-only; writable {'/work': '3g', '/tmp': '512m', '/home/repro': '512m'}; memory 2g; cpus 2.0; pids 256; capabilities all dropped; no_new_privileges True; network repro-sandbox (internal, no route out; egress only via the gate); docker_socket not mounted; host_mounts none; command_timeout_s 300

Model work: 39 tool calls, 306701 prompt tokens, 20122 completion tokens.

Generated by Repro. Commands, exit codes and output hashes are recorded by the backend, not reported by the model.
