import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1])
SLIDES = ROOT / "docs" / "slides"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    arch = (ROOT / "docs" / "architecture.svg").read_text()
    arch = arch.replace('width="980" height="600"', "")
    html = (SLIDES / "slides.html").read_text().replace("{{ARCH}}", arch)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.set_content(html, wait_until="load")
        page.pdf(path=str(OUT / "repro-slides.pdf"), width="1920px", height="1080px", print_background=True, prefer_css_page_size=True)
        for i, section in enumerate(page.locator("section").all(), 1):
            section.screenshot(path=str(OUT / f"slide-{i}.png"))
        page.goto((SLIDES / "cover.html").as_uri())
        page.screenshot(path=str(OUT / "repro-cover.png"))
        browser.close()


if __name__ == "__main__":
    main()
