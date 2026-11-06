from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = "repro-209-250-235-249.sslip.io"
REPO = "github.com/CVasilopoulos/repro"
STYLE = """
.rc { position: absolute; inset: 0 0 0 0; background: #101317; color: #eef0f3; font-family: Inter, 'Helvetica Neue', Arial, 'Liberation Sans', sans-serif; display: flex; flex-direction: column; justify-content: center; padding: 0 84px 60px; box-sizing: border-box; }
.rc .brand { display: flex; align-items: center; gap: 14px; font-size: 30px; font-weight: 600; color: #fff; }
.rc .brand i { width: 22px; height: 22px; border-radius: 5px; background: #2f7fe6; display: inline-block; }
.rc h1 { font-size: 60px; line-height: 1.12; font-weight: 700; margin: 34px 0 22px; letter-spacing: -0.5px; max-width: 1090px; }
.rc p { font-size: 25px; line-height: 1.42; color: #b6bbc4; margin: 0; max-width: 1040px; }
.rc .flow { display: flex; gap: 14px; margin-top: 44px; align-items: stretch; }
.rc .flow div { flex: 1; background: #1a1f26; border: 1px solid #2c333d; border-radius: 12px; padding: 16px 18px; font-size: 19px; line-height: 1.3; color: #d9dce1; }
.rc .flow b { display: block; color: #fff; font-size: 21px; margin-bottom: 6px; }
.rc .links { margin-top: 36px; font-size: 25px; line-height: 1.6; color: #fff; }
.rc .links span { color: #8d94a0; display: inline-block; width: 90px; font-size: 22px; }
.rc small { display: block; margin-top: 40px; font-size: 19px; color: #8d94a0; }
.rc.arch { background: #fff; justify-content: center; align-items: center; padding: 0 0 70px; }
.rc.arch svg { height: 600px; width: auto; }
"""
BRAND = '<div class="brand"><i></i>Repro</div>'


def title():
    return f"""<div class="rc">{BRAND}
<h1>Is this bug report real? Run it, safely, and find out.</h1>
<p>An agent writes the reproduction. Fresh gVisor sandboxes on a Vultr VM run it. Exit codes decide the verdict.</p>
<div class="flow"><div><b>Issue URL</b>untrusted input</div><div><b>Agent</b>Vultr Serverless Inference</div><div><b>Sandboxes</b>reported version and default branch, twice each</div><div><b>Verdict</b>from exit codes, with the full log</div></div>
</div>"""


def arch():
    return f'<div class="rc arch">{(ROOT / "docs" / "architecture.svg").read_text()}</div>'


def close():
    return f"""<div class="rc">{BRAND}
<h1>Try to break it.</h1>
<p>Paste an issue, or fire the attack lab yourself.</p>
<div class="links"><span>Live</span>https://{URL}<br><span>Code</span>https://{REPO} (MIT)</div>
<small>Built for Vultr Agent Rush, Blast Radius Zero. Narration is synthetic. AI-assisted, human-directed.</small>
</div>"""
