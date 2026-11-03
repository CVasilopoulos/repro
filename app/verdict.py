import re
from dataclasses import dataclass

VERDICTS = {
    "reproduced": "Reproduced on the default branch",
    "fixed": "Fixed on the default branch",
    "not_reproducible": "Not reproducible",
    "new_on_default": "Present on the default branch only",
    "flaky": "Flaky reproduction",
    "inconclusive": "Inconclusive",
}


@dataclass
class RefRun:
    ref: str
    commit: str
    setup_exit: int
    repro_exits: list[int]
    lost: str = ""

    @property
    def outcome(self) -> str:
        if self.lost:
            return "error"
        if self.setup_exit != 0:
            return "error"
        if not self.repro_exits or any(e not in (0, 1) for e in self.repro_exits):
            return "error"
        if len(set(self.repro_exits)) > 1:
            return "flaky"
        return "present" if self.repro_exits[0] == 1 else "absent"


def decide(reported: RefRun, default: RefRun) -> tuple[str, str]:
    r, d = reported.outcome, default.outcome
    if "error" in (r, d):
        which = "reported ref" if r == "error" else "default branch"
        return "inconclusive", f"the check could not run on the {which}"
    if "flaky" in (r, d):
        return "flaky", "the same check gave different results on repeated runs"
    if r == "present" and d == "present":
        return "reproduced", "the bug is present at the reported ref and still present on the default branch"
    if r == "present" and d == "absent":
        return "fixed", "the bug is present at the reported ref and gone on the default branch"
    if r == "absent" and d == "absent":
        return "not_reproducible", "the reported behaviour does not happen at the reported ref or on the default branch"
    return "new_on_default", "the behaviour is absent at the reported ref but present on the default branch"


PATTERNS = [
    ("read_only_root", re.compile(r"Read-only file system", re.I),
     "write to the read-only root filesystem blocked"),
    ("process_limit", re.compile(r"(fork: retry|Resource temporarily unavailable|fork: Cannot allocate|BlockingIOError: \[Errno 11\])", re.I),
     "process limit reached: new processes refused"),
    ("egress_blocked", re.compile(r"(repro egress gate: [^\n]+|Network is unreachable|Could not resolve host|Temporary failure in name resolution)", re.I),
     "network access outside the allowlist refused"),
    ("metadata_probe", re.compile(r"169\.254\.169\.254|metadata\.google\.internal|/latest/meta-data|v1\.json", re.I),
     "attempt to reach the cloud metadata endpoint"),
    ("permission", re.compile(r"Permission denied|Operation not permitted", re.I),
     "privileged operation refused (non-root, no capabilities)"),
]


def containment_signals(command: str, output: str) -> list[dict]:
    hits = []
    text = output[-200000:]
    for key, rx, label in PATTERNS:
        matches = rx.findall(text) if key != "metadata_probe" else rx.findall(command + "\n" + text)
        if matches:
            first = matches[0] if isinstance(matches[0], str) else matches[0][0]
            hits.append({"signal": key, "label": label, "count": len(matches), "sample": first[:160]})
    return hits
