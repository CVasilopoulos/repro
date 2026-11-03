import json
import time
import uuid

from fastapi import FastAPI, Request

SETUP = "set -e\npython3 -m venv /work/venv\n/work/venv/bin/pip install -q -e /work/repo\n"
REPRO = """set -u
out=$(/work/venv/bin/python -c 'import dura; print(dura.parse("1h30m"))')
echo "parse(1h30m) = $out"
if [ "$out" = "5400" ]; then echo "REPRO: BUG ABSENT"; exit 0; fi
echo "REPRO: BUG PRESENT"; exit 1
"""

SCRIPT = [
    ("Checking the reported tag and the layout.", "run_command", {"command": "cd /work/repo && git tag && ls"}),
    ("Writing the setup script.", "write_file", {"path": "/work/setup.sh", "content": SETUP}),
    ("Writing the reproduction.", "write_file", {"path": "/work/repro.sh", "content": REPRO}),
    ("Running it at v0.1.0.", "run_command",
     {"command": "cd /work/repo && git checkout -q v0.1.0 && bash /work/setup.sh && bash /work/repro.sh; echo exit=$?"}),
    ("Submitting.", "submit", {"reported_ref": "v0.1.0", "claim": "parse('1h30m') returns 3600 instead of 5400",
                               "expected": "5400", "setup_sh": SETUP, "repro_sh": REPRO,
                               "notes": "scripted test model"}),
]

app = FastAPI()


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    step = sum(1 for m in body["messages"] if m["role"] == "assistant")
    text, name, args = SCRIPT[min(step, len(SCRIPT) - 1)]
    return {
        "id": "fake-" + uuid.uuid4().hex[:8],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "fake"),
        "choices": [{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {"role": "assistant", "content": text, "tool_calls": [
                {"id": f"call_{step}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            ]},
        }],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050},
    }
