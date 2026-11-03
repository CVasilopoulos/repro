import base64
import hashlib
import shlex
import threading
import time
import uuid
from dataclasses import dataclass, field

import docker
from docker.errors import APIError, NotFound

from .config import Settings

OUTPUT_CAP = 2_000_000
CHUNK = 48_000


@dataclass
class ExecResult:
    command: str
    exit_code: int
    output: str
    sha256: str
    duration: float
    truncated: bool
    timed_out: bool
    sandbox_lost: str = ""


@dataclass
class SandboxInfo:
    name: str
    container_id: str
    ip: str
    runtime: str
    started: float
    spec: dict = field(default_factory=dict)


def sandbox_env(settings: Settings) -> dict:
    proxy = settings.gate_url
    return {
        "HOME": "/home/repro",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HTTP_PROXY": proxy,
        "HTTPS_PROXY": proxy,
        "http_proxy": proxy,
        "https_proxy": proxy,
        "NO_PROXY": "",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def sandbox_spec(settings: Settings) -> dict:
    lim = settings.limits
    return {
        "runtime": settings.runtime,
        "image": settings.sandbox_image,
        "user": "1000:1000 (non-root)",
        "root_filesystem": "read-only",
        "writable": {"/work": lim.work_size, "/tmp": lim.tmp_size, "/home/repro": lim.home_size},
        "memory": lim.memory,
        "cpus": lim.cpus,
        "pids": lim.pids,
        "capabilities": "all dropped",
        "no_new_privileges": True,
        "network": f"{settings.sandbox_network} (internal, no route out; egress only via the gate)",
        "docker_socket": "not mounted",
        "host_mounts": "none",
        "env": sorted(sandbox_env(settings).keys()),
        "command_timeout_s": lim.command_timeout,
    }


class Sandbox:
    def __init__(self, client: docker.DockerClient, settings: Settings, job_id: str, role: str):
        self.client = client
        self.settings = settings
        self.job_id = job_id
        self.role = role
        self.container = None
        self.info: SandboxInfo | None = None
        self.lost_reason = ""

    def start(self) -> SandboxInfo:
        lim = self.settings.limits
        name = f"repro-{self.job_id[:8]}-{self.role}-{uuid.uuid4().hex[:6]}"
        tmpfs = {
            "/work": f"rw,exec,size={lim.work_size},mode=1777",
            "/tmp": f"rw,exec,size={lim.tmp_size},mode=1777",
            "/home/repro": f"rw,exec,size={lim.home_size},uid=1000,gid=1000,mode=0755",
        }
        kwargs = dict(
            image=self.settings.sandbox_image,
            command=["sleep", "infinity"],
            name=name,
            detach=True,
            read_only=True,
            tmpfs=tmpfs,
            user="1000:1000",
            working_dir="/work",
            network=self.settings.sandbox_network,
            mem_limit=lim.memory,
            memswap_limit=lim.memory,
            nano_cpus=int(lim.cpus * 1e9),
            pids_limit=lim.pids,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            environment=sandbox_env(self.settings),
            hostname="sandbox",
            init=True,
            labels={"repro.job": self.job_id, "repro.role": self.role},
        )
        if self.settings.runtime and self.settings.runtime != "runc":
            kwargs["runtime"] = self.settings.runtime
            kwargs["ulimits"] = [docker.types.Ulimit(name="nproc", soft=lim.pids, hard=lim.pids)]
        self.container = self.client.containers.run(**kwargs)
        self.container.reload()
        nets = self.container.attrs["NetworkSettings"]["Networks"]
        ip = next(iter(nets.values()))["IPAddress"] if nets else ""
        self.info = SandboxInfo(
            name=name,
            container_id=self.container.id[:12],
            ip=ip,
            runtime=self.container.attrs["HostConfig"].get("Runtime") or "runc",
            started=time.time(),
            spec=sandbox_spec(self.settings),
        )
        return self.info

    def alive(self) -> bool:
        if not self.container:
            return False
        try:
            self.container.reload()
        except NotFound:
            return False
        return self.container.status == "running"

    def state(self) -> dict:
        try:
            self.container.reload()
            return self.container.attrs.get("State", {})
        except (NotFound, APIError):
            return {}

    def exec(self, command: str, timeout: int | None = None, on_output=None) -> ExecResult:
        timeout = timeout or self.settings.limits.command_timeout
        wrapped = f"timeout --kill-after=5 {int(timeout)} bash -lc {shlex.quote(command)}"
        started = time.time()
        if not self.alive():
            return ExecResult(command, -1, "", hashlib.sha256(b"").hexdigest(), 0.0, False, False, self.lost())
        api = self.client.api
        try:
            exec_id = api.exec_create(self.container.id, ["bash", "-c", wrapped], workdir="/work", user="1000:1000")["Id"]
            stream = api.exec_start(exec_id, stream=True, demux=False)
        except APIError as exc:
            return ExecResult(command, -1, f"exec failed: {exc.explanation}", hashlib.sha256(b"").hexdigest(),
                              time.time() - started, False, False, self.lost())
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        truncated = False
        deadline = started + timeout + 30
        watchdog = threading.Timer(timeout + 30, self._kill_on_deadline)
        watchdog.start()
        try:
            for chunk in stream:
                digest.update(chunk)
                if size < OUTPUT_CAP:
                    chunks.append(chunk[: OUTPUT_CAP - size])
                    size += len(chunk)
                else:
                    truncated = True
                if on_output:
                    on_output(chunk.decode("utf-8", "replace"))
                if time.time() > deadline:
                    break
        except Exception:
            pass
        finally:
            watchdog.cancel()
        try:
            exit_code = api.exec_inspect(exec_id).get("ExitCode")
        except (APIError, NotFound):
            exit_code = None
        output = b"".join(chunks).decode("utf-8", "replace")
        lost = "" if self.alive() else self.lost()
        if exit_code is None:
            exit_code = -1
        return ExecResult(
            command=command,
            exit_code=exit_code,
            output=output,
            sha256=digest.hexdigest(),
            duration=round(time.time() - started, 2),
            truncated=truncated,
            timed_out=exit_code in (124, 137) and time.time() - started >= timeout - 1,
            sandbox_lost=lost,
        )

    def _kill_on_deadline(self) -> None:
        self.lost_reason = "wall-clock limit: sandbox killed"
        self.destroy()

    def lost(self) -> str:
        if self.lost_reason:
            return self.lost_reason
        st = self.state()
        if st.get("OOMKilled"):
            self.lost_reason = f"memory limit {self.settings.limits.memory} reached: sandbox OOM-killed"
        elif st:
            self.lost_reason = f"sandbox exited ({st.get('Status')}, code {st.get('ExitCode')})"
        else:
            self.lost_reason = "sandbox is gone"
        return self.lost_reason

    def write_file(self, path: str, content: str) -> ExecResult:
        if not path.startswith("/"):
            path = "/work/" + path
        data = base64.b64encode(content.encode()).decode()
        parts = [data[i : i + CHUNK] for i in range(0, len(data), CHUNK)] or [""]
        qpath = shlex.quote(path)
        result = self.exec(f"mkdir -p \"$(dirname {qpath})\" && : > {qpath}", timeout=30)
        for part in parts:
            if result.exit_code != 0:
                break
            result = self.exec(f"printf %s {shlex.quote(part)} | base64 -d >> {qpath}", timeout=30)
        result.command = f"write {path} ({len(content)} bytes, sha256 {hashlib.sha256(content.encode()).hexdigest()[:12]})"
        return result

    def pids_current(self) -> int | None:
        try:
            stats = self.container.stats(stream=False)
            return stats.get("pids_stats", {}).get("current")
        except Exception:
            return None

    def destroy(self) -> None:
        if not self.container:
            return
        try:
            self.container.remove(force=True)
        except (NotFound, APIError):
            pass


def docker_client() -> docker.DockerClient:
    return docker.from_env(timeout=120)
