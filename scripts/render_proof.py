"""Render a print proof PDF.

Runs inside the container:
    docker compose run --rm proofer python scripts/render_proof.py

Inputs (all at the repo root):
  proof.config.json    page setup and section choices  (written by /init-font)
  proof.content.json   specimen content                (produced by the typographer)
  fontinfo.json        font facts                      (written by /init-font)

The pipeline: Jinja2 fills templates/proof.html.j2 with the content, headless
Chromium prints it to PDF at the configured page size. Chromium shapes text with
HarfBuzz, so OpenType features, variable instances, and complex scripts render
the way they will in real apps.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

PAGE_SIZES_MM = {
    "letter": (215.9, 279.4),
    "tabloid": (279.4, 431.8),
    "a4": (210.0, 297.0),
}

UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "inch": 25.4, "inches": 25.4,
              "pt": 25.4 / 72, "points": 25.4 / 72}

SRC_FORMATS = {".ttf": "truetype", ".otf": "opentype",
               ".woff": "woff", ".woff2": "woff2", ".ttc": "collection"}

COLOR_SCHEMES = {
    "black-on-white": ("#000000", "#ffffff"),
    "white-on-black": ("#ffffff", "#000000"),
}


def fail(message: str) -> NoReturn:
    print(f"[problem] {message}", file=sys.stderr)
    sys.exit(1)


def load_json(path: Path, hint: str) -> dict:
    if not path.exists():
        fail(f"{path} is missing — {hint}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON ({exc}).")


# ---------------------------------------------------------------- page setup

def resolve_page_mm(config: dict) -> tuple[float, float]:
    page = config.get("page", {})
    size = (page.get("size") or "letter").lower()
    if size == "custom":
        custom = page.get("custom_size") or {}
        unit = UNIT_TO_MM.get((custom.get("unit") or "mm").lower())
        if not unit or not custom.get("width") or not custom.get("height"):
            fail("page.custom_size needs width, height and unit (mm/in/pt).")
        width, height = custom["width"] * unit, custom["height"] * unit
    elif size in PAGE_SIZES_MM:
        width, height = PAGE_SIZES_MM[size]
    else:
        fail(f"Unknown page size '{size}'. Use letter, tabloid, a4 or custom.")
    if (page.get("orientation") or "portrait").lower() == "landscape":
        width, height = height, width
    return width, height


def resolve_colors(config: dict) -> dict:
    colors = config.get("colors", {})
    scheme = (colors.get("scheme") or "black-on-white").lower()
    if scheme in COLOR_SCHEMES:
        fg, bg = COLOR_SCHEMES[scheme]
    else:
        fg = colors.get("foreground") or "#000000"
        bg = colors.get("background") or "#ffffff"
    return {"foreground": fg, "background": bg}


def resolve_margins(config: dict) -> dict:
    margins = {"top": 20, "bottom": 20, "inner": 18, "outer": 18}
    margins.update(config.get("page", {}).get("margins_mm") or {})
    return margins


# ---------------------------------------------------------------- fonts

def build_font_faces(config: dict, fontinfo: dict) -> list[dict]:
    """One CSS @font-face per configured font file, keyed by file path."""
    info_by_file = {f["file"]: f for f in fontinfo.get("fonts", [])}
    faces = []
    for index, file_path in enumerate(config.get("fonts", [])):
        path = Path(file_path)
        if not path.exists():
            fail(f"Configured font {file_path} is not in fonts/ any more — "
                 "re-run /init-font.")
        suffix = path.suffix.lower()
        if suffix == ".ttc":
            print(f"  note: {file_path} is a collection; browsers use its first "
                  "face only.", file=sys.stderr)
        faces.append({
            "file": file_path,
            "css_family": f"proof-font-{index}",
            "src_url": "file:///work/" + quote(path.as_posix()),
            "src_format": SRC_FORMATS.get(suffix, "truetype"),
            "info": info_by_file.get(file_path, {}),
        })
    if not faces:
        fail("proof.config.json lists no fonts.")
    return faces


def family_for(section: dict, faces: list[dict]) -> str:
    """Resolve a content section's optional "font" (file path) to a CSS family."""
    wanted = section.get("font")
    if wanted:
        for face in faces:
            if face["file"] == wanted:
                return face["css_family"]
        print(f"  note: section '{section.get('type')}' asks for {wanted}, which "
              "is not configured; using the first font.", file=sys.stderr)
    return faces[0]["css_family"]


# ------------------------------------------------------------ header/footer

TOKEN_VALUES = {
    "page-number": '<span class="pageNumber"></span> / <span class="totalPages"></span>',
}


def header_footer_html(contents: list[str], faces: list[dict],
                       colors: dict, margins: dict) -> str:
    info = faces[0]["info"]
    names = info.get("names", {}) if info else {}
    rendered = []
    for token in contents:
        if token == "family-name":
            rendered.append(names.get("family") or Path(faces[0]["file"]).stem)
        elif token == "style-name":
            rendered.append(names.get("subfamily") or "")
        elif token == "date":
            rendered.append(date.today().isoformat())
        elif token in TOKEN_VALUES:
            rendered.append(TOKEN_VALUES[token])
        else:
            rendered.append(token)  # free text
    cells = "".join(f"<span>{part}</span>" for part in rendered if part)
    # Chromium renders these in an isolated context: inline styles only, and
    # the font size must be set explicitly or nothing shows up.
    return (
        f'<div style="width:100%; display:flex; justify-content:space-between; '
        f'align-items:baseline; font-family:DejaVu Sans, sans-serif; font-size:6.5pt; '
        f'letter-spacing:0.07em; color:{colors["foreground"]}; '
        f'padding:0 {margins["outer"]}mm 0 {margins["inner"]}mm;">{cells}</div>'
    )


# ---------------------------------------------------------------- rendering

def render_html(config: dict, content: dict, faces: list[dict],
                colors: dict, templates_dir: Path) -> str:
    _, height_mm = resolve_page_mm(config)
    margins = resolve_margins(config)
    content_height_mm = height_mm - margins["top"] - margins["bottom"]
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "j2"]),
    )
    env.filters["cp"] = ord

    sections = []
    for section in content.get("sections", []):
        section = dict(section)
        section_type = section.get("type")
        template_path = templates_dir / "sections" / f"{section_type}.html.j2"
        if not template_path.exists():
            print(f"  note: skipping unknown section type '{section_type}'.",
                  file=sys.stderr)
            continue
        section["font_family"] = family_for(section, faces)
        sections.append(section)
    if not sections:
        fail("proof.content.json has no renderable sections.")

    return env.get_template("proof.html.j2").render(
        title=content.get("title") or "Font proof",
        fonts=faces,
        sections=sections,
        colors=colors,
        content_height_mm=content_height_mm,
        base_css=(templates_dir / "proof.css").read_text(encoding="utf-8"),
    )


def print_pdf(html_path: Path, output_path: Path, config: dict,
              faces: list[dict], colors: dict) -> None:
    from playwright.sync_api import sync_playwright

    width_mm, height_mm = resolve_page_mm(config)
    margins = resolve_margins(config)

    header_cfg = config.get("header") or {}
    footer_cfg = config.get("footer") or {}
    show_hf = bool(header_cfg.get("enabled") or footer_cfg.get("enabled"))

    pdf_options: dict = {
        "path": str(output_path),
        "width": f"{width_mm}mm",
        "height": f"{height_mm}mm",
        "margin": {
            "top": f"{margins['top']}mm",
            "bottom": f"{margins['bottom']}mm",
            "left": f"{margins['inner']}mm",
            "right": f"{margins['outer']}mm",
        },
        "print_background": True,
    }
    if show_hf:
        pdf_options["display_header_footer"] = True
        pdf_options["header_template"] = (
            header_footer_html(header_cfg.get("contents") or [], faces, colors, margins)
            if header_cfg.get("enabled") else "<span></span>"
        )
        pdf_options["footer_template"] = (
            header_footer_html(footer_cfg.get("contents") or [], faces, colors, margins)
            if footer_cfg.get("enabled") else "<span></span>"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page.evaluate("document.fonts.ready")  # wait for the proofed fonts
        page.pdf(**pdf_options)
        browser.close()


def count_pages(pdf_path: Path) -> int | None:
    try:
        data = pdf_path.read_bytes()
        return len(re.findall(rb"/Type\s*/Page[^s]", data)) or None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="proof.config.json", type=Path)
    parser.add_argument("--content", default="proof.content.json", type=Path)
    parser.add_argument("--fontinfo", default="fontinfo.json", type=Path)
    parser.add_argument("--templates", default="templates", type=Path)
    parser.add_argument("--output", type=Path,
                        help="override the output path from the config")
    parser.add_argument("--keep-html", action="store_true",
                        help="keep the intermediate HTML next to the PDF")
    args = parser.parse_args()

    config = load_json(args.config, "run /init-font to create it")
    content = load_json(args.content, "the typographer's content has not been "
                                      "saved yet")
    fontinfo = load_json(args.fontinfo, "run /init-font to create it")

    colors = resolve_colors(config)
    faces = build_font_faces(config, fontinfo)

    output_cfg = config.get("output", {})
    output_dir = Path(output_cfg.get("directory") or "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output or output_dir / (output_cfg.get("filename")
                                               or "proof.pdf")

    html = render_html(config, content, faces, colors, args.templates)
    html_path = output_path.with_suffix(".proof.html")
    html_path.write_text(html, encoding="utf-8")

    print(f"Rendering {output_path} ...")
    print_pdf(html_path, output_path, config, faces, colors)
    if not args.keep_html:
        html_path.unlink(missing_ok=True)

    pages = count_pages(output_path)
    page_note = f", {pages} page(s)" if pages else ""
    print(f"Done — {output_path} ({output_path.stat().st_size:,} bytes{page_note}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
