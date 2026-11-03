import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _read_secret(var: str) -> str:
    path = os.environ.get(var + "_FILE")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return os.environ.get(var, "")


@dataclass(frozen=True)
class SandboxLimits:
    memory: str = "2g"
    cpus: float = 2.0
    pids: int = 256
    work_size: str = "3g"
    tmp_size: str = "512m"
    home_size: str = "512m"
    command_timeout: int = 300
    setup_timeout: int = 600


@dataclass(frozen=True)
class Settings:
    runtime: str = field(default_factory=lambda: _env("REPRO_RUNTIME", "runsc"))
    sandbox_image: str = field(default_factory=lambda: _env("REPRO_SANDBOX_IMAGE", "repro-sandbox:latest"))
    sandbox_network: str = field(default_factory=lambda: _env("REPRO_SANDBOX_NETWORK", "repro-sandbox"))
    gate_url: str = field(default_factory=lambda: _env("REPRO_GATE_URL", "http://172.30.0.2:3128"))
    gate_ledger: str = field(default_factory=lambda: _env("REPRO_GATE_LEDGER", "/ledger/egress.jsonl"))
    data_dir: str = field(default_factory=lambda: _env("REPRO_DATA_DIR", "/data"))
    inference_url: str = field(default_factory=lambda: _env("REPRO_INFERENCE_URL", "https://api.vultrinference.com/v1"))
    inference_key: str = field(default_factory=lambda: _read_secret("VULTR_INFERENCE_KEY"))
    model: str = field(default_factory=lambda: _env("REPRO_MODEL", "glm-5.3"))
    github_token: str = field(default_factory=lambda: _read_secret("REPRO_GITHUB_TOKEN"))
    comment_repos: tuple[str, ...] = field(
        default_factory=lambda: tuple(r for r in _env("REPRO_COMMENT_REPOS", "").split(",") if r)
    )
    max_tool_calls: int = field(default_factory=lambda: int(_env("REPRO_MAX_TOOL_CALLS", "40")))
    max_concurrent_jobs: int = field(default_factory=lambda: int(_env("REPRO_MAX_JOBS", "2")))
    jobs_per_ip_per_hour: int = field(default_factory=lambda: int(_env("REPRO_JOBS_PER_IP_HOUR", "4")))
    daily_token_budget: int = field(default_factory=lambda: int(_env("REPRO_DAILY_TOKENS", "6000000")))
    limits: SandboxLimits = field(default_factory=SandboxLimits)


settings = Settings()
