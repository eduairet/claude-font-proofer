"""Verify the proofing engine works end to end.

Runs inside the container:  docker compose run --rm proofer python scripts/check_setup.py

Checks that every library imports at its pinned version, then renders a one-page
PDF through headless Chromium to prove the full pipeline works. All output is
written for a non-programmer: each line says what was checked, and failures say
what to do next.
"""

import sys
from pathlib import Path

OUTPUT_DIR = Path("output")
CHECK_PDF = OUTPUT_DIR / "setup-check.pdf"

OK = "  [ok]"
FAIL = "  [problem]"


def check_imports() -> bool:
    print("Checking the font tools are installed...")
    from importlib.metadata import version

    ok = True
    for module, dist, label in [
        ("fontTools", "fonttools", "fontTools (reads your font files)"),
        ("uharfbuzz", "uharfbuzz", "HarfBuzz (text shaping)"),
        ("jinja2", "Jinja2", "Jinja2 (page templating)"),
        ("playwright", "playwright", "Playwright (drives the PDF renderer)"),
    ]:
        try:
            __import__(module)
            print(f"{OK} {label} — {version(dist)}")
        except ImportError as exc:
            print(f"{FAIL} {label} failed to load: {exc}")
            ok = False
    return ok


def check_pdf_rendering() -> bool:
    print("Rendering a test PDF with the built-in browser engine...")
    from playwright.sync_api import sync_playwright

    html = """
    <!doctype html>
    <html><head><style>
      @page { size: letter; margin: 25mm; }
      body { font-family: sans-serif; }
      h1 { font-size: 28pt; }
    </style></head>
    <body>
      <h1>ai-font-proofer setup check</h1>
      <p>If you can read this PDF, the proofing engine is working.</p>
      <p style="font-size:18pt;">Hamburgefonstiv 0123456789 — fi fl ff ÆŒß</p>
    </body></html>
    """

    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html)
            page.pdf(path=str(CHECK_PDF), prefer_css_page_size=True)
            browser.close()
    except Exception as exc:
        print(f"{FAIL} The PDF renderer did not start: {exc}")
        print("        Try rebuilding the engine:  docker compose build --no-cache")
        return False

    if CHECK_PDF.exists() and CHECK_PDF.stat().st_size > 0:
        print(f"{OK} Test PDF written to {CHECK_PDF}")
        return True
    print(f"{FAIL} The renderer ran but no PDF appeared in {OUTPUT_DIR}/.")
    print("        Check that you started this from the project folder.")
    return False


def main() -> int:
    print("— ai-font-proofer setup check —\n")
    imports_ok = check_imports()
    print()
    pdf_ok = imports_ok and check_pdf_rendering()
    print()
    if imports_ok and pdf_ok:
        print("Everything works! Open output/setup-check.pdf to see the test page.")
        print("Next step: put your fonts in the fonts/ folder and run /init-font.")
        return 0
    print("Something needs attention — see the [problem] lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
