import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .github import parse_issue_url, post_comment
from .jobs import JobRunner, SandboxRegistry, job_report, tail_ledger
from .lab import PRESETS
from .sandbox import sandbox_spec
from .store import Store

STATIC = os.path.join(os.path.dirname(__file__), "static")
EXAMPLES_FILE = os.path.join(os.path.dirname(__file__), "examples.json")

store = Store(os.path.join(settings.data_dir, "repro.db"))
registry = SandboxRegistry()
runner: JobRunner | None = None
tasks: set[asyncio.Task] = set()
runtime_check: dict = {"status": "pending"}


async def check_runtime() -> None:
    from .sandbox import Sandbox

    box = Sandbox(runner.docker, settings, "selftest", "selftest")
    try:
        info = await asyncio.to_thread(box.start)
        result = await asyncio.to_thread(box.exec, "uname -sr; dmesg 2>/dev/null | head -1", 30)
        lines = result.output.strip().splitlines()
        runtime_check.update(status="ok", runtime=info.runtime, kernel=lines[0] if lines else "",
                             dmesg=lines[1] if len(lines) > 1 else "", gvisor="gVisor" in result.output)
    except Exception as exc:
        runtime_check.update(status="error", error=str(exc)[:300])
    finally:
        await asyncio.to_thread(box.destroy)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner
    store.loop = asyncio.get_running_loop()
    runner = JobRunner(settings, store, registry)
    ledger_task = asyncio.create_task(tail_ledger(settings.gate_ledger, store, registry))
    asyncio.create_task(check_runtime())
    yield
    ledger_task.cancel()


app = FastAPI(title="Repro", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class JobRequest(BaseModel):
    issue_url: str


class LabRequest(BaseModel):
    preset: str


class CommentRequest(BaseModel):
    confirm: bool = False


def client_id(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/j/{job_id}", response_class=HTMLResponse)
async def job_page(job_id: str):
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/config")
async def config():
    examples = []
    if os.path.exists(EXAMPLES_FILE):
        with open(EXAMPLES_FILE, encoding="utf-8") as fh:
            examples = json.load(fh)
    return {
        "model": settings.model,
        "inference": settings.inference_url,
        "sandbox": sandbox_spec(settings),
        "runtime_check": runtime_check,
        "examples": examples,
        "comment_repos": list(settings.comment_repos),
        "lab": [{"id": k, "title": v["title"], "explain": v["explain"]} for k, v in PRESETS.items()],
        "limits": {"jobs_per_ip_per_hour": settings.jobs_per_ip_per_hour, "max_concurrent": settings.max_concurrent_jobs},
    }


@app.post("/api/jobs")
async def create_job(req: JobRequest, request: Request):
    try:
        parse_issue_url(req.issue_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    who = client_id(request)
    if store.jobs_from_client_since(who, time.time() - 3600) >= settings.jobs_per_ip_per_hour:
        raise HTTPException(429, f"limit of {settings.jobs_per_ip_per_hour} jobs per hour reached; try a recent report below")
    if store.tokens_today() >= settings.daily_token_budget:
        raise HTTPException(503, "today's inference budget is used up; recent reports are still browsable")
    job_id = store.create_job(req.issue_url.strip(), who)
    task = asyncio.create_task(runner.run(job_id, req.issue_url.strip()))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"id": job_id}


@app.post("/api/lab")
async def create_lab(req: LabRequest, request: Request):
    if req.preset not in PRESETS:
        raise HTTPException(400, "unknown attack")
    who = client_id(request)
    if store.jobs_from_client_since(who, time.time() - 3600, lab=True) >= settings.jobs_per_ip_per_hour * 5:
        raise HTTPException(429, "too many runs from your address this hour")
    job_id = store.create_job(f"lab:{req.preset}", who)
    task = asyncio.create_task(runner.run_lab(job_id, req.preset))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"id": job_id}


@app.get("/api/jobs")
async def list_jobs():
    return store.recent_jobs(30)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {"job": job, "events": store.events(job_id)}


@app.get("/api/jobs/{job_id}/stream")
async def stream(job_id: str, request: Request, after: int = 0):
    if not store.job(job_id):
        raise HTTPException(404, "no such job")
    queue = store.subscribe(job_id)

    async def gen():
        try:
            last = after
            for e in store.events(job_id, after):
                last = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e)}\n\n"
                if e["kind"] == "done":
                    return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    e = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if e["seq"] <= last:
                    continue
                last = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e)}\n\n"
                if e["kind"] == "done":
                    return
        finally:
            store.unsubscribe(job_id, queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/report.md", response_class=PlainTextResponse)
async def report(job_id: str):
    if not store.job(job_id):
        raise HTTPException(404, "no such job")
    return PlainTextResponse(job_report(store, job_id), media_type="text/markdown; charset=utf-8")


@app.post("/api/jobs/{job_id}/comment")
async def comment(job_id: str, req: CommentRequest):
    job = store.job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(400, "the job has not finished")
    if not req.confirm:
        raise HTTPException(400, "a human has to confirm the comment")
    owner, repo, number = parse_issue_url(job["issue_url"])
    full = f"{owner}/{repo}"
    if full not in settings.comment_repos or not settings.github_token:
        raise HTTPException(403, f"posting is enabled only for {', '.join(settings.comment_repos) or 'no repositories'}; download the report instead")
    body = job_report(store, job_id)
    url = await post_comment(full, number, body[:60000], settings.github_token)
    store.emit(job_id, "comment_posted", url=url)
    return {"url": url}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "jobs_running": len(tasks)}
