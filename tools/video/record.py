import base64
import json
import math
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import cards

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1])
TTS = Path(sys.argv[2])
DRY = "--dry" in sys.argv
HOST = "repro-209-250-235-249.sslip.io"
IP = "209.250.235.249"
BASE = f"https://{HOST}"
ISSUE = "https://github.com/CVasilopoulos/repro-demo/issues/1"
DRY_JOB = "9a1325be940a"
AGENT_BOMB_JOB = "d7a7911abf4b"
HUMANIZE_JOB = "bf1557e3f0da"
GAP = 0.35

INIT = """
(() => {
  const install = () => {
    if (document.getElementById('__cap')) return;
    const css = document.createElement('style');
    css.textContent = `
      html { scroll-behavior: auto !important; }
      body { padding-bottom: 150px; }
      #__cap { position: fixed; left: 0; right: 0; bottom: 0; min-height: 76px; background: rgba(16,19,23,.94); color: #fff; font: 600 23px/1.3 Inter, Arial, 'Liberation Sans', sans-serif; display: none; align-items: center; justify-content: center; text-align: center; padding: 12px 90px; box-sizing: border-box; z-index: 2147483600; }
      #__badge { position: fixed; top: 14px; right: 18px; background: #101317; color: #fff; font: 600 16px Inter, Arial, 'Liberation Sans', sans-serif; padding: 7px 13px; border-radius: 8px; display: none; z-index: 2147483600; }
      #__cur { position: fixed; left: 0; top: 0; width: 22px; height: 22px; z-index: 2147482000; pointer-events: none; transform: translate(-40px, -40px); }
      .__hl { outline: 3px solid #e8590c !important; outline-offset: 2px; border-radius: 6px; }
      #__card { position: fixed; inset: 0; z-index: 2147483000; transition: opacity .55s ease; }
    `;
    document.head.appendChild(css);
    const cap = document.createElement('div'); cap.id = '__cap';
    const badge = document.createElement('div'); badge.id = '__badge';
    const cur = document.createElement('div'); cur.id = '__cur';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M4 2 L4 20 L9 15.5 L12.5 22 L15.5 20.5 L12 14 L19 14 Z" fill="#111" stroke="#fff" stroke-width="1.5"/></svg>';
    document.body.append(cap, badge, cur);
    document.addEventListener('mousemove', (e) => { cur.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`; }, true);
    window.__cap = (t) => { cap.textContent = t; cap.style.display = t ? 'flex' : 'none'; };
    window.__badge = (t) => { badge.textContent = t; badge.style.display = t ? 'block' : 'none'; };
    window.__cur = (x, y) => { cur.style.transform = `translate(${x}px, ${y}px)`; };
    window.__scroll = (y, ms) => {
      const from = window.scrollY, t0 = performance.now();
      const step = (now) => {
        const k = Math.min(1, (now - t0) / ms), e = k * k * (3 - 2 * k);
        window.scrollTo(0, from + (y - from) * e);
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
  };
  if (document.body) install();
  else document.addEventListener('DOMContentLoaded', install);
})();
"""


class Rec:
    def __init__(self, page, cdp):
        self.page, self.cdp = page, cdp
        self.narr = json.loads((HERE / "narration.json").read_text())
        self.dur = json.loads((TTS / "timings.json").read_text())
        (OUT / "frames").mkdir(parents=True, exist_ok=True)
        self.frames, self.lines, self.fast = [], [], []
        self.caption, self.badge = "", ""
        self.x, self.y = 640, 360
        cdp.on("Page.screencastFrame", self.on_frame)

    def on_frame(self, p):
        name = f"f{len(self.frames):06}.jpg"
        (OUT / "frames" / name).write_bytes(base64.b64decode(p["data"]))
        self.frames.append({"ts": p["metadata"]["timestamp"], "file": name})
        self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})

    def start(self):
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})

    def wait(self, seconds):
        self.page.wait_for_timeout(int(seconds * 1000))

    def restore(self):
        self.page.wait_for_function("() => window.__cap")
        self.page.evaluate("([c, b, x, y]) => { __cap(c); __badge(b); __cur(x, y); }", [self.caption, self.badge, self.x, self.y])

    def goto(self, path):
        self.page.goto(BASE + path, wait_until="domcontentloaded")
        self.restore()

    def say(self, scene, k, action=None, after=GAP):
        line = self.narr[scene][k]
        lid = f"{scene}_{k}"
        t0 = time.time()
        self.caption = line["text"]
        self.page.evaluate("(c) => __cap(c)", self.caption)
        self.lines.append({"id": lid, "t": t0, "text": line["text"]})
        if action:
            action()
        rest = t0 + self.dur[lid] + after - time.time()
        if rest > 0:
            self.wait(rest)

    def move(self, loc, click=False):
        loc.scroll_into_view_if_needed()
        b = loc.bounding_box()
        tx, ty = b["x"] + min(b["width"] / 2, 240), b["y"] + b["height"] / 2
        steps = 28
        for i in range(1, steps + 1):
            k = i / steps
            e = k * k * (3 - 2 * k)
            self.page.mouse.move(self.x + (tx - self.x) * e, self.y + (ty - self.y) * e)
            self.page.wait_for_timeout(14)
        self.x, self.y = tx, ty
        if click:
            self.page.mouse.down()
            self.page.mouse.up()

    def scroll_to(self, loc, top=84, ms=800):
        y = loc.evaluate("(e) => e.getBoundingClientRect().top + window.scrollY")
        self.page.evaluate("([y, ms]) => __scroll(y, ms)", [max(0, y - top), ms])
        self.wait(ms / 1000 + 0.1)

    def top(self, ms=700):
        self.page.evaluate("(ms) => __scroll(0, ms)", ms)
        self.wait(ms / 1000 + 0.1)

    def hl(self, *locs):
        self.page.evaluate("() => document.querySelectorAll('.__hl').forEach((e) => e.classList.remove('__hl'))")
        for loc in locs:
            loc.evaluate("(e) => e.classList.add('__hl')")

    def card(self, html):
        self.page.evaluate("""([css, html]) => {
            document.getElementById('__card')?.remove();
            const c = document.createElement('div'); c.id = '__card';
            c.innerHTML = '<style>' + css + '</style>' + html;
            document.body.appendChild(c);
        }""", [cards.STYLE, html])

    def uncard(self):
        self.page.evaluate("() => { const c = document.getElementById('__card'); if (c) c.style.opacity = 0; }")
        self.wait(0.6)
        self.page.evaluate("() => document.getElementById('__card')?.remove()")

    def job_done(self):
        return self.page.evaluate("() => { const v = document.getElementById('verdict'); const s = document.getElementById('job-status'); return !!(v && !v.hidden && s && /^Finished/.test(s.textContent)); }")

    def follow(self):
        self.page.evaluate("() => __scroll(document.documentElement.scrollHeight - innerHeight, 350)")

    def speak_following(self, scene, k):
        end = time.time() + self.dur[f"{scene}_{k}"] + GAP

        def run():
            while time.time() < end - 0.1 and not self.job_done():
                self.follow()
                self.wait(0.6)

        self.say(scene, k, run)

    def wait_job(self, speed, limit=420):
        t0 = time.time()
        if speed > 1:
            self.badge = f"Real run, waiting sped up {speed}x"
            self.page.evaluate("(b) => __badge(b)", self.badge)
        self.caption = ""
        self.page.evaluate("() => __cap('')")
        while not self.job_done():
            if time.time() - t0 > limit:
                raise RuntimeError("job did not finish")
            self.follow()
            self.wait(0.8)
        if speed > 1:
            self.fast.append([t0, time.time(), speed])
            self.badge = ""
            self.page.evaluate("() => __badge('')")

    def lab_click(self, title):
        self.move(self.page.locator("#lab button", has_text=title), click=True)
        self.page.wait_for_url("**/j/*", timeout=15000)
        self.restore()


def scene_title(r):
    r.goto("/")
    r.page.wait_for_selector("#examples button")
    r.card(cards.title())
    r.wait(0.3)
    r.start()
    r.wait(0.8)
    for k in range(3):
        r.say("title", k)
    r.uncard()


def scene_live(r):
    def paste():
        box = r.page.locator("#issue")
        r.move(box, click=True)
        r.page.keyboard.type(ISSUE, delay=28)

    r.say("live", 0, paste, after=0.1)
    button = r.page.locator("#start button")
    r.move(button)
    if DRY:
        r.goto(f"/j/{DRY_JOB}")
    else:
        r.page.mouse.down()
        r.page.mouse.up()
        r.page.wait_for_url("**/j/*", timeout=15000)
        r.restore()
    r.wait(1.0)
    r.speak_following("live", 1)
    r.speak_following("live", 2)
    r.wait_job(8)
    r.wait(0.5)
    job = r.page.url.rsplit("/", 1)[1]
    verdict = r.page.locator("#verdict .label").inner_text()
    print("live job", job, verdict, flush=True)
    return verdict


def scene_verdict(r):
    r.top()
    table = r.page.locator("#verdict table")
    r.say("verdict", 0, lambda: (r.hl(table), r.move(table)))
    decided = r.page.locator("#verdict > div.muted").first
    r.say("verdict", 1, lambda: (r.hl(decided), r.move(decided)))
    why = r.page.locator("#verdict > div").nth(1)
    r.say("verdict", 2, lambda: (r.hl(why), r.move(why)))
    r.hl()

    def tour():
        r.scroll_to(r.page.locator("#timeline li.ok-step").first)
        r.hl(r.page.locator("#timeline li.ok-step .meta").first)
        r.wait(1.8)
        r.hl(r.page.locator("#egress"))
        r.wait(1.8)
        r.scroll_to(r.page.locator("#sandboxes"), top=200)
        r.hl(r.page.locator("#sandboxes"))

    r.say("verdict", 3, tour)
    r.hl()


def scene_lab(r):
    r.goto("/")
    r.page.wait_for_selector("#lab button")
    r.scroll_to(r.page.locator("#lab").locator("xpath=.."))
    r.say("lab_intro", 0)

    r.say("wipe", 0, lambda: (r.lab_click("rm -rf /"), r.page.wait_for_function("() => document.getElementById('job-status')?.textContent.startsWith('Finished')", timeout=90000)))
    out = r.page.locator("#timeline li", has_text="deletions refused").locator("pre")
    r.say("wipe", 1, lambda: (r.scroll_to(r.page.locator("#verdict")), r.hl(out), out.scroll_into_view_if_needed()))
    fresh = r.page.locator("#timeline li", has_text="fresh sandbox:").locator("pre")
    r.say("wipe", 2, lambda: (r.hl(fresh), fresh.scroll_into_view_if_needed()))
    r.hl()

    r.goto("/")
    r.page.wait_for_selector("#lab button")
    r.scroll_to(r.page.locator("#lab").locator("xpath=.."), ms=500)
    r.say("metadata", 0, lambda: (r.lab_click("Steal cloud credentials"), r.page.wait_for_function("() => document.getElementById('job-status')?.textContent.startsWith('Finished')", timeout=90000)))
    gate = r.page.locator("#timeline li", has_text="through the proxy").locator("pre")
    r.say("metadata", 1, lambda: (r.hl(gate, r.page.locator("#egress")), r.scroll_to(r.page.locator("#verdict"))))
    r.hl()

    r.goto("/")
    r.page.wait_for_selector("#lab button")
    r.scroll_to(r.page.locator("#lab").locator("xpath=.."), ms=500)
    r.say("forkbomb", 0, lambda: r.lab_click("Fork bomb"), after=0.1)
    r.wait_job(3)
    bomb = r.page.locator("#timeline li", has_text="killing every process").locator("pre")
    r.scroll_to(r.page.locator("#verdict"))
    r.hl(bomb, r.page.locator("#containment"))
    r.wait(2.5)
    r.hl()


def scene_agent_bomb(r):
    r.goto(f"/j/{AGENT_BOMB_JOB}")
    r.page.wait_for_function("() => document.getElementById('job-status')?.textContent.startsWith('Finished')", timeout=30000)

    def show():
        r.hl(r.page.locator("#verdict details.notes"))
        r.wait(4.0)
        r.scroll_to(r.page.locator("#timeline li.block").first, top=200)
        r.hl(r.page.locator("#timeline li.block").first, r.page.locator("#containment"))

    r.say("agent_bomb", 0, show)
    r.say("agent_bomb", 1)
    r.hl()


def scene_real(r):
    r.goto("/")
    r.page.wait_for_selector("#showcase a")
    show = r.page.locator("#showcase")
    r.scroll_to(show.locator("xpath=.."))
    r.say("real", 0, lambda: r.move(show.locator("a").first))

    def open_fixed():
        r.move(r.page.locator(f'#showcase a[href="/j/{HUMANIZE_JOB}"]'))
        r.wait(0.6)
        r.goto(f"/j/{HUMANIZE_JOB}")
        r.page.wait_for_function("() => document.getElementById('job-status')?.textContent.startsWith('Finished')", timeout=30000)
        r.hl(r.page.locator("#verdict > div").nth(1))

    r.say("real", 1, open_fixed)
    r.hl()
    r.goto("/")
    r.page.wait_for_selector("#showcase a")
    show = r.page.locator("#showcase")
    r.scroll_to(show.locator("xpath=.."), ms=400)
    opens = [show.locator("a", has_text=t) for t in ("python-tabulate", "arrow-py", "parse")]
    r.say("real", 2, lambda: r.hl(*opens))
    r.say("real", 3, lambda: (r.hl(opens[1]), r.move(opens[1])))
    r.hl()
    r.say("real", 4, lambda: r.scroll_to(show.locator("xpath=.."), ms=300))


def scene_cards(r):
    r.card(cards.arch())
    for k in range(3):
        r.say("arch", k)
    r.card(cards.close())
    for k in range(3):
        r.say("close", k)
    r.page.evaluate("() => __cap('')")
    r.wait(3.0)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST} {IP}"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, color_scheme="light", locale="en-GB", timezone_id="UTC", bypass_csp=True)
        ctx.add_init_script(INIT)
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        r = Rec(page, cdp)
        only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), None)
        begin = time.time()
        scene_title(r)
        begin = r.lines[0]["t"] - 1.1
        scenes = {"live": lambda: (scene_live(r), scene_verdict(r)), "lab": lambda: scene_lab(r), "agent": lambda: scene_agent_bomb(r),
                  "real": lambda: scene_real(r), "cards": lambda: scene_cards(r)}
        for name, fn in scenes.items():
            if not only or name in only.split(","):
                fn()
        end = time.time()
        cdp.send("Page.stopScreencast")
        browser.close()
    (OUT / "timeline.json").write_text(json.dumps({"start": begin, "end": end, "frames": r.frames, "lines": r.lines, "fast": r.fast}))
    print("recorded", round(end - begin, 1), "s", len(r.frames), "frames", flush=True)


if __name__ == "__main__":
    main()
