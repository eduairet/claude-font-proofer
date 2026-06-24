"""Bake the proofed font(s) into web test pages as base64 data URIs.

Runs inside the container:
    docker compose run --rm proofer python scripts/inline_web_fonts.py

The web-engineer writes each test page with a normal @font-face that points at
the font file (e.g. url("/fonts/MyFont.ttf")). That only resolves when the repo
is served over HTTP. This step rewrites those url(...) references to embedded
`data:` URIs so each page becomes a single self-contained file that renders in
the Claude app preview, by double-click, or in any browser — no server needed.

Idempotent: a url() that is already a data: URI is left untouched, so it is safe
to run repeatedly.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path
from urllib.parse import unquote

MIME = {".ttf": "font/ttf", ".otf": "font/otf",
        ".woff": "font/woff", ".woff2": "font/woff2", ".ttc": "font/collection"}

# url( optional-quote  path  optional-quote )
URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")


def resolve_font(ref: str, html_path: Path, repo_root: Path) -> Path | None:
    """Map a CSS url() reference to a font file on disk, or None if not a font."""
    ref = unquote(ref.split("?", 1)[0].split("#", 1)[0])
    if ref.startswith("data:"):
        return None
    if Path(ref).suffix.lower() not in MIME:
        return None
    # Try, in order: server-absolute (/fonts/..), relative to the page, repo-root
    candidates = []
    if ref.startswith("/"):
        candidates.append(repo_root / ref.lstrip("/"))
    candidates.append((html_path.parent / ref).resolve())
    candidates.append((repo_root / ref).resolve())
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def inline_file(html_path: Path, repo_root: Path) -> int:
    text = html_path.read_text(encoding="utf-8")
    embedded = 0

    def replace(match: re.Match) -> str:
        nonlocal embedded
        ref = match.group(2)
        font = resolve_font(ref, html_path, repo_root)
        if font is None:
            return match.group(0)  # not a local font (or already data:) — leave it
        mime = MIME[font.suffix.lower()]
        data = base64.b64encode(font.read_bytes()).decode("ascii")
        embedded += 1
        return f'url("data:{mime};base64,{data}")'

    new_text = URL_RE.sub(replace, text)
    if embedded:
        html_path.write_text(new_text, encoding="utf-8")
    return embedded


def main() -> int:
    repo_root = Path.cwd()
    args = sys.argv[1:]
    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted(Path("web-tests").glob("*.html"))

    if not targets:
        print("No web test pages found in web-tests/ — generate some first.",
              file=sys.stderr)
        return 0

    total = 0
    for html_path in targets:
        if not html_path.is_file():
            print(f"  note: {html_path} not found; skipping.", file=sys.stderr)
            continue
        n = inline_file(html_path, repo_root)
        total += n
        state = f"embedded {n} font(s)" if n else "already self-contained"
        print(f"  {html_path}: {state}")

    print(f"Done — {total} font reference(s) embedded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
