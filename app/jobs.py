import asyncio
import json
import os
import shlex
import time
from dataclasses import asdict

from openai import AsyncOpenAI

from .agent import Agent, ToolOutcome, clip
from .config import Settings
from .github import Issue, fetch_issue
from .report import render_report
from .sandbox import ExecResult, Sandbox, docker_client
from .store import Store
from .verdict import VERDICTS, RefRun, containment_signals, decide


class SandboxRegistry:
    def __init__(self):
        self.by_ip: dict[str, tuple[str, str]] = {}

    def register(self, ip: str, job_id: str, name: str) -> None:
        if ip:
            self.by_ip[ip] = (job_id, name)

    def unregister(self, ip: str) -> None:
        self.by_ip.pop(ip, None)

    def lookup(self, ip: str):
        return self.by_ip.get(ip)


async def tail_ledger(path: str, store: Store, registry: SandboxRegistry) -> None:
    while not os.path.exists(path):
        await asyncio.sleep(1)
    with open(path, encoding="utf-8") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if not line:
                await asyncio.sleep(0.3)
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            owner = registry.lookup(entry.get("src", ""))
            if not owner:
                continue
            job_id, sandbox = owner
            store.emit(job_id, "egress", sandbox=sandbox, host=entry.get("host"), port=entry.get("port"),
                       method=entry.get("method"), allowed=entry.get("allowed"), reason=entry.get("reason"),
                       url=entry.get("url"))


class JobRunner:
    def __init__(self, settings: Settings, store: Store, registry: SandboxRegistry):
        self.settings = settings
        self.store = store
        self.registry = registry
        self.docker = docker_client()
        self.slots = asyncio.Semaphore(settings.max_concurrent_jobs)
        self.llm = AsyncOpenAI(base_url=settings.inference_url, api_key=settings.inference_key or "missing", timeout=180)

    async def run(self, job_id: str, issue_url: str) -> None:
        emit = lambda kind, **data: self.store.emit(job_id, kind, **data)
        self.store.update_job(job_id, status="waiting")
        async with self.slots:
            self.store.update_job(job_id, status="running")
            started = time.time()
            try:
                await self._run(job_id, issue_url, emit)
            except Exception as exc:
                emit("error", message=f"{type(exc).__name__}: {exc}")
                self.store.update_job(job_id, status="failed", finished=time.time(), verdict="inconclusive",
                                      summary=str(exc)[:500])
            finally:
                emit("done", seconds=round(time.time() - started, 1))

    async def _start_sandbox(self, job_id: str, role: str, emit) -> Sandbox:
        box = Sandbox(self.docker, self.settings, job_id, role)
        info = await asyncio.to_thread(box.start)
        self.registry.register(info.ip, job_id, info.name)
        emit("sandbox_started", role=role, name=info.name, container=info.container_id, runtime=info.runtime,
             ip=info.ip, spec=info.spec)
        return box

    async def _destroy(self, box: Sandbox, emit, reason: str) -> None:
        if not box.info:
            return
        await asyncio.to_thread(box.destroy)
        await asyncio.sleep(0.5)
        self.registry.unregister(box.info.ip)
        emit("sandbox_destroyed", name=box.info.name, container=box.info.container_id, reason=reason,
             lifetime=round(time.time() - box.info.started, 1))

    async def _exec(self, box: Sandbox, command: str, emit, timeout: int | None = None, label: str = "",
                    quiet: bool = False) -> ExecResult:
        emit("exec_start", sandbox=box.info.name, command=command, label=label)
        result = await asyncio.to_thread(box.exec, command, timeout)
        emit("exec_end", sandbox=box.info.name, command=command, label=label, exit_code=result.exit_code,
             duration=result.duration, sha256=result.sha256, truncated=result.truncated, timed_out=result.timed_out,
             output=clip(result.output, 1500, 3500) if not quiet else clip(result.output, 300, 700))
        for hit in containment_signals(command, result.output):
            emit("containment", sandbox=box.info.name, **hit)
        if result.timed_out:
            emit("containment", sandbox=box.info.name, signal="time_limit",
                 label=f"time limit reached ({timeout or self.settings.limits.command_timeout}s): command killed",
                 count=1, sample="")
        if result.sandbox_lost:
            emit("containment", sandbox=box.info.name, signal="sandbox_lost", label=result.sandbox_lost, count=1,
                 sample="")
        return result

    async def _write(self, box: Sandbox, path: str, content: str, emit) -> ExecResult:
        result = await asyncio.to_thread(box.write_file, path, content)
        emit("file_written", sandbox=box.info.name, path=path, bytes=len(content.encode()), exit_code=result.exit_code,
             content=content[:6000])
        return result

    async def _prepare(self, box: Sandbox, issue: Issue, emit) -> dict:
        repo = shlex.quote(issue.clone_url)
        clone = await self._exec(box, f"git clone --quiet --filter=blob:none {repo} /work/repo && git -C /work/repo log -1 --format=%H",
                                 emit, timeout=300, label="clone")
        if clone.exit_code != 0:
            raise RuntimeError("could not clone the repository")
        probe = await self._exec(
            box,
            "cd /work/repo && echo HEAD=$(git rev-parse HEAD) && "
            f"echo FILED=$(git rev-list -1 --before={shlex.quote(issue.created_at)} HEAD) && "
            "echo TAGS=$(git tag --sort=-creatordate | head -8 | tr '\\n' ' ') && "
            "echo FILES=$(ls -1A | head -40 | tr '\\n' ' ')",
            emit, timeout=60, label="inspect", quiet=True,
        )
        values = {}
        for line in probe.output.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                values[k.strip()] = v.strip()
        head = values.get("HEAD", "")
        return {
            "head_commit": head,
            "filed_at_commit": values.get("FILED") or head,
            "tags": values.get("TAGS", "").split(),
            "files": values.get("FILES", "").split(),
        }

    async def _run(self, job_id: str, issue_url: str, emit) -> None:
        emit("status", message="Fetching the issue")
        issue = await fetch_issue(issue_url, self.settings.github_token)
        emit("issue", **{k: v for k, v in asdict(issue).items() if k != "comments"}, comments=len(issue.comments))
        if not self.settings.inference_key:
            raise RuntimeError("no inference key configured")
        emit("status", message="Starting the agent sandbox")
        box = await self._start_sandbox(job_id, "agent", emit)
        holder = {"box": box}
        try:
            prep = await self._prepare(box, issue, emit)
            ctx = {"issue": {**asdict(issue), "full_name": issue.full_name}, **prep}
            emit("context", head_commit=prep["head_commit"], filed_at_commit=prep["filed_at_commit"], tags=prep["tags"])

            async def respawn(reason: str) -> str:
                old = holder["box"]
                await self._destroy(old, emit, reason)
                fresh = await self._start_sandbox(job_id, "agent", emit)
                holder["box"] = fresh
                await self._prepare(fresh, issue, emit)
                return (f"The sandbox was destroyed: {reason}. A fresh sandbox is ready with the repository cloned at "
                        "/work/repo (default branch). Files you wrote earlier are gone.")

            async def run_command(args: dict) -> ToolOutcome:
                b = holder["box"]
                timeout = int(args.get("timeout_seconds") or 180)
                timeout = max(5, min(timeout, 600))
                result = await self._exec(b, str(args.get("command", "")), emit, timeout=timeout, label="agent")
                text = f"exit code {result.exit_code} after {result.duration}s\n{clip(result.output)}"
                if result.sandbox_lost:
                    text += "\n" + await respawn(result.sandbox_lost)
                else:
                    check = await asyncio.to_thread(b.exec, "test -d /work/repo/.git", 15)
                    if check.exit_code != 0:
                        emit("containment", sandbox=b.info.name, signal="workspace_wiped",
                             label="the command deleted the sandbox workspace; nothing outside the sandbox was touched",
                             count=1, sample="")
                        text += "\n" + await respawn("the workspace was deleted by the last command")
                return ToolOutcome(text)

            async def write_file(args: dict) -> ToolOutcome:
                b = holder["box"]
                result = await self._write(b, str(args.get("path", "")), str(args.get("content", "")), emit)
                if result.sandbox_lost:
                    return ToolOutcome("write failed\n" + await respawn(result.sandbox_lost))
                return ToolOutcome("written" if result.exit_code == 0 else f"write failed: {result.output[-500:]}")

            async def submit(args: dict) -> ToolOutcome:
                return ToolOutcome("submitted", final=args)

            def budget_check(tokens: int) -> bool:
                return self.store.add_tokens(tokens) <= self.settings.daily_token_budget

            agent = Agent(self.llm, self.settings.model, self.settings.max_tool_calls,
                          lambda kind, **d: emit(kind, **d), budget_check)
            emit("status", message=f"Agent working ({self.settings.model} on Vultr Serverless Inference)")
            result = await agent.run(ctx, {"run_command": run_command, "write_file": write_file, "submit": submit})
            emit("agent_finished", outcome=result.kind, tool_calls=result.tool_calls, prompt_tokens=result.prompt_tokens,
                 completion_tokens=result.completion_tokens, **{k: v for k, v in result.payload.items()
                                                                if k not in ("setup_sh", "repro_sh")})
        finally:
            await self._destroy(holder["box"], emit, "agent phase finished")

        if result.kind != "submit":
            reason = result.payload.get("reason", result.kind)
            self.store.update_job(job_id, status="done", verdict="inconclusive", finished=time.time(), summary=reason)
            emit("verdict", verdict="inconclusive", title=VERDICTS["inconclusive"], why=reason)
            return

        sub = result.payload
        emit("status", message="Verifying in two fresh sandboxes")
        reported_ref = (sub.get("reported_ref") or prep["filed_at_commit"]).strip()
        runs = await asyncio.gather(
            self._verify(job_id, issue, reported_ref, "reported", sub, emit),
            self._verify(job_id, issue, issue.default_branch, "default", sub, emit),
        )
        verdict, why = decide(runs[0], runs[1])
        emit("verdict", verdict=verdict, title=VERDICTS[verdict], why=why,
             reported={"ref": runs[0].ref, "commit": runs[0].commit, "outcome": runs[0].outcome,
                       "setup_exit": runs[0].setup_exit, "repro_exits": runs[0].repro_exits},
             default={"ref": runs[1].ref, "commit": runs[1].commit, "outcome": runs[1].outcome,
                      "setup_exit": runs[1].setup_exit, "repro_exits": runs[1].repro_exits})
        self.store.update_job(job_id, status="done", verdict=verdict, finished=time.time(),
                              summary=f"{VERDICTS[verdict]}: {sub.get('claim', '')}"[:500])

    async def _verify(self, job_id: str, issue: Issue, ref: str, role: str, sub: dict, emit) -> RefRun:
        box = await self._start_sandbox(job_id, f"verify-{role}", emit)
        run = RefRun(ref=ref, commit="", setup_exit=-1, repro_exits=[])
        try:
            repo = shlex.quote(issue.clone_url)
            q = shlex.quote(ref)
            co = await self._exec(
                box,
                f"git clone --quiet --filter=blob:none {repo} /work/repo && cd /work/repo && "
                f"(git checkout --quiet {q} 2>/dev/null || (git fetch --quiet origin {q} && git checkout --quiet FETCH_HEAD)) && "
                "git rev-parse HEAD",
                emit, timeout=300, label=f"{role}: checkout {ref}", quiet=True,
            )
            if co.exit_code != 0 or co.sandbox_lost:
                run.lost = co.sandbox_lost or "checkout failed"
                return run
            run.commit = co.output.strip().splitlines()[-1][:40]
            await self._write(box, "/work/setup.sh", sub.get("setup_sh", ""), emit)
            await self._write(box, "/work/repro.sh", sub.get("repro_sh", ""), emit)
            setup = await self._exec(box, "cd /work/repo && bash /work/setup.sh", emit,
                                     timeout=self.settings.limits.setup_timeout, label=f"{role}: setup", quiet=True)
            run.setup_exit = setup.exit_code
            if setup.exit_code != 0 or setup.sandbox_lost:
                run.lost = setup.sandbox_lost
                return run
            for attempt in (1, 2):
                rep = await self._exec(box, "cd /work/repo && bash /work/repro.sh", emit, timeout=240,
                                       label=f"{role}: repro run {attempt}")
                run.repro_exits.append(rep.exit_code)
                if rep.sandbox_lost:
                    run.lost = rep.sandbox_lost
                    break
            return run
        finally:
            emit("verify_result", role=role, ref=ref, commit=run.commit, setup_exit=run.setup_exit,
                 repro_exits=run.repro_exits, outcome=run.outcome, lost=run.lost)
            await self._destroy(box, emit, f"verification at {ref} finished")


def job_report(store: Store, job_id: str) -> str:
    return render_report(store.job(job_id) or {}, store.events(job_id))
