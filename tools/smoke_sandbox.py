import json
import sys
import time

from app.config import settings
from app.sandbox import Sandbox, docker_client
from app.verdict import containment_signals

CHECKS = [
    ("clone through the gate", "git clone --quiet --depth 1 https://github.com/pallets/itsdangerous /work/repo && ls /work/repo | head -3", 0),
    ("pip through the gate", "python -m venv /work/venv && /work/venv/bin/pip install -q six==1.16.0 && /work/venv/bin/python -c 'import six; print(six.__version__)'", 0),
    ("metadata endpoint via proxy", "curl -s -m 10 http://169.254.169.254/v1.json; echo; curl -s -m 10 -o /dev/null -w '%{http_code}\\n' http://169.254.169.254/v1.json", None),
    ("metadata endpoint direct", "curl -s -m 5 --noproxy '*' http://169.254.169.254/v1.json || echo direct-failed-$?", None),
    ("exfil host not allowlisted", "curl -s -m 10 https://pastebin.com/ -o /dev/null -w '%{http_code}\\n' || echo exit-$?", None),
    ("no secrets in env", "env | sort | grep -viE '^(HOME|PATH|LANG|HOSTNAME|PWD|SHLVL|_|OLDPWD|TERM)=' ", None),
    ("no docker socket", "ls -l /var/run/docker.sock 2>&1; id", None),
    ("rm -rf / as the sandbox user", "rm -rf --no-preserve-root / 2>&1 | grep -c 'Read-only file system'; ls /work | wc -l; ls /usr/bin | wc -l", None),
    ("fork bomb", "python3 -c \"import os\nn=0\ntry:\n  while True:\n    if os.fork()==0:\n      import time; time.sleep(30); os._exit(0)\n    n+=1\nexcept OSError as e:\n  print('fork refused after', n, 'children:', e)\n\"", None),
]


def main():
    client = docker_client()
    box = Sandbox(client, settings, "smoke" + str(int(time.time())), "smoke")
    info = box.start()
    print(json.dumps({"sandbox": info.name, "ip": info.ip, "runtime": info.runtime}))
    try:
        for name, cmd, expect in CHECKS:
            r = box.exec(cmd, timeout=120)
            sig = [h["signal"] for h in containment_signals(cmd, r.output)]
            status = "ok" if expect is None or r.exit_code == expect else "FAIL"
            print(f"== {name}: exit {r.exit_code} {r.duration}s {status} signals={sig} lost={r.sandbox_lost!r}")
            print(r.output[-800:].rstrip())
            if r.sandbox_lost:
                break
        print("pids now:", box.pids_current())
    finally:
        box.destroy()
        print("destroyed", info.name)


if __name__ == "__main__":
    sys.exit(main())
