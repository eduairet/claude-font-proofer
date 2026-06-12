"""Inspect every font in fonts/ and write the proofing context.

Runs inside the container:
    docker compose run --rm proofer python scripts/inspect_fonts.py

Outputs:
  - fontinfo.json        machine-precise data the subagents consume
  - CLAUDE.md            human-readable summary, written between the
                         BEGIN/END GENERATED FONT CONTEXT markers

Every per-font failure is caught and reported; one broken file never stops
the others from being analyzed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fontTools import unicodedata as ucd
from fontTools.ttLib import TTCollection, TTFont

FONT_EXTENSIONS = {".otf", ".ttf", ".ttc", ".woff", ".woff2"}

CLAUDE_BEGIN = "<!-- BEGIN GENERATED FONT CONTEXT -->"
CLAUDE_END = "<!-- END GENERATED FONT CONTEXT -->"

# OpenType feature tags grouped the way a type designer thinks about them.
FEATURE_GROUPS = [
    ("Ligatures", {"liga", "dlig", "clig", "hlig", "rlig"}),
    ("Capitals & case", {"smcp", "c2sc", "pcap", "c2pc", "case", "cpsp", "unic", "titl"}),
    ("Numerals", {"lnum", "onum", "pnum", "tnum", "frac", "afrc", "numr", "dnom",
                  "sinf", "subs", "sups", "zero", "ordn"}),
    ("Stylistic", {"salt", "swsh", "cswh", "hist", "ornm", "rand", "nalt"}),
    ("Contextual & shaping", {"calt", "ccmp", "locl", "rvrn", "rclt", "curs",
                              "init", "medi", "fina", "isol", "med2", "fin2", "fin3",
                              "ljmo", "vjmo", "tjmo", "akhn", "rphf", "pref", "blwf",
                              "half", "pstf", "vatu", "cjct", "abvf", "abvs", "blws",
                              "pres", "psts", "haln"}),
    ("Positioning", {"kern", "mark", "mkmk", "dist", "abvm", "blwm", "opbd", "lfbd", "rtbd"}),
    ("Vertical", {"vert", "vrt2", "vkrn", "vpal", "vhal", "vrtr"}),
]


# ---------------------------------------------------------------- discovery

def discover_font_files(fonts_dir: Path) -> list[Path]:
    files = [
        p for p in sorted(fonts_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in FONT_EXTENSIONS
    ]
    return files


def load_fonts(path: Path) -> list[tuple[TTFont, int | None]]:
    """Return (font, ttc_index) pairs; non-collections get index None."""
    if path.suffix.lower() == ".ttc":
        collection = TTCollection(str(path), lazy=True)
        return [(font, i) for i, font in enumerate(collection.fonts)]
    return [(TTFont(str(path), lazy=True), None)]


# ---------------------------------------------------------------- name table

def get_names(font: TTFont) -> dict:
    name = font["name"]

    def first(*name_ids: int) -> str | None:
        for nid in name_ids:
            value = name.getDebugName(nid)
            if value:
                return value.strip()
        return None

    return {
        "family": first(16, 1),
        "subfamily": first(17, 2),
        "full_name": first(4),
        "postscript_name": first(6),
        "version": first(5),
        "manufacturer": first(8),
        "designer": first(9),
    }


# ---------------------------------------------------------------- metrics

def get_style(font: TTFont) -> dict:
    os2 = font["OS/2"] if "OS/2" in font else None
    post = font["post"] if "post" in font else None
    fs_selection = getattr(os2, "fsSelection", 0) if os2 else 0
    return {
        "weight_class": getattr(os2, "usWeightClass", None) if os2 else None,
        "width_class": getattr(os2, "usWidthClass", None) if os2 else None,
        "bold_flag": bool(fs_selection & 0x20),
        "italic_flag": bool(fs_selection & 0x01),
        "italic_angle": getattr(post, "italicAngle", None) if post else None,
        "monospaced": bool(getattr(post, "isFixedPitch", 0)) if post else None,
    }


def get_vertical_metrics(font: TTFont) -> dict:
    upm = font["head"].unitsPerEm
    hhea = font["hhea"]
    os2 = font["OS/2"] if "OS/2" in font else None

    metrics: dict = {
        "upm": upm,
        "hhea": {
            "ascender": hhea.ascent,
            "descender": hhea.descent,
            "line_gap": hhea.lineGap,
        },
    }
    mismatches: list[str] = []

    if os2 is not None:
        metrics["os2_typo"] = {
            "ascender": os2.sTypoAscender,
            "descender": os2.sTypoDescender,
            "line_gap": os2.sTypoLineGap,
        }
        metrics["os2_win"] = {"ascent": os2.usWinAscent, "descent": os2.usWinDescent}
        metrics["cap_height"] = getattr(os2, "sCapHeight", None)
        metrics["x_height"] = getattr(os2, "sxHeight", None)
        metrics["use_typo_metrics"] = bool(os2.fsSelection & 0x80)

        if (hhea.ascent, hhea.descent, hhea.lineGap) != (
            os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap
        ):
            mismatches.append(
                f"hhea ({hhea.ascent}/{hhea.descent}/{hhea.lineGap}) differs from "
                f"OS/2 typo ({os2.sTypoAscender}/{os2.sTypoDescender}/{os2.sTypoLineGap})"
            )
        if os2.usWinAscent != hhea.ascent or os2.usWinDescent != -hhea.descent:
            mismatches.append(
                f"OS/2 win ({os2.usWinAscent}/-{os2.usWinDescent}) differs from "
                f"hhea ({hhea.ascent}/{hhea.descent}) — platforms may clip or "
                "space lines differently"
            )
    else:
        mismatches.append("no OS/2 table")

    metrics["mismatches"] = mismatches
    return metrics


# ---------------------------------------------------------------- coverage

def to_ranges(codepoints: list[int]) -> list[str]:
    ranges: list[str] = []
    start = prev = None
    for cp in codepoints:
        if start is None:
            start = prev = cp
        elif cp == prev + 1:
            prev = cp
        else:
            ranges.append(f"{start:04X}" if start == prev else f"{start:04X}-{prev:04X}")
            start = prev = cp
    if start is not None:
        ranges.append(f"{start:04X}" if start == prev else f"{start:04X}-{prev:04X}")
    return ranges


def get_coverage(font: TTFont) -> dict:
    try:
        cmap = font.getBestCmap()
    except Exception:
        cmap = {}
    codepoints = sorted(cmap)

    blocks: Counter[str] = Counter()
    scripts: Counter[str] = Counter()
    for cp in codepoints:
        char = chr(cp)
        blocks[ucd.block(char)] += 1
        script_code = ucd.script(char)
        if script_code not in ("Zyyy", "Zinh", "Zzzz"):
            scripts[ucd.script_name(script_code)] += 1

    return {
        "codepoint_count": len(codepoints),
        "ranges": to_ranges(codepoints),
        "blocks": dict(blocks.most_common()),
        "scripts": dict(scripts.most_common()),
    }


# ---------------------------------------------------------------- layout

def get_layout(font: TTFont) -> dict:
    layout: dict = {}
    for table_tag in ("GSUB", "GPOS"):
        if table_tag not in font:
            continue
        table = font[table_tag].table
        entry: dict = {"scripts": {}, "features": []}
        if table.ScriptList:
            for record in table.ScriptList.ScriptRecord:
                langs = ["dflt"] if record.Script.DefaultLangSys else []
                langs += [ls.LangSysTag.strip() for ls in record.Script.LangSysRecord]
                entry["scripts"][record.ScriptTag.strip()] = langs
        if table.FeatureList:
            entry["features"] = sorted(
                {fr.FeatureTag for fr in table.FeatureList.FeatureRecord}
            )
        layout[table_tag] = entry
    return layout


def group_features(tags: set[str]) -> dict:
    grouped: dict[str, list[str]] = {}
    remaining = set(tags)
    for group_name, members in FEATURE_GROUPS:
        hits = sorted(remaining & members)
        if hits:
            grouped[group_name] = hits
            remaining -= members
    stylistic_sets = sorted(t for t in remaining if t.startswith(("ss", "cv"))
                            and len(t) == 4 and t[2:].isdigit())
    if stylistic_sets:
        grouped.setdefault("Stylistic", []).extend(stylistic_sets)
        grouped["Stylistic"] = sorted(grouped["Stylistic"])
        remaining -= set(stylistic_sets)
    if remaining:
        grouped["Other"] = sorted(remaining)
    return grouped


# ---------------------------------------------------------------- kerning

def _pair_pos_stats(subtable) -> tuple[int, int]:
    """Return (flat_pairs, class_pairs_nonzero) for one PairPos subtable."""
    if subtable.Format == 1:
        flat = sum(len(ps.PairValueRecord) for ps in subtable.PairSet)
        return flat, 0
    if subtable.Format == 2:
        nonzero = 0
        for c1 in subtable.Class1Record:
            for c2 in c1.Class2Record:
                for value in (c2.Value1, c2.Value2):
                    if value is not None and any(
                        getattr(value, attr, 0)
                        for attr in ("XAdvance", "XPlacement", "YAdvance", "YPlacement")
                    ):
                        nonzero += 1
                        break
        return 0, nonzero
    return 0, 0


def get_kerning(font: TTFont) -> dict:
    info = {
        "gpos_kern_feature": False,
        "gpos_flat_pairs": 0,
        "gpos_class_kerning": False,
        "gpos_class_pairs_nonzero": 0,
        "legacy_kern_table_pairs": 0,
    }

    if "GPOS" in font:
        table = font["GPOS"].table
        if table.FeatureList:
            info["gpos_kern_feature"] = any(
                fr.FeatureTag == "kern" for fr in table.FeatureList.FeatureRecord
            )
        if table.LookupList:
            for lookup in table.LookupList.Lookup:
                for subtable in lookup.SubTable:
                    if lookup.LookupType == 9:  # Extension
                        subtable = subtable.ExtSubTable
                    if getattr(subtable, "LookupType", lookup.LookupType) == 2 or (
                        lookup.LookupType == 2
                    ):
                        if hasattr(subtable, "Format"):
                            flat, class_nonzero = _pair_pos_stats(subtable)
                            info["gpos_flat_pairs"] += flat
                            if class_nonzero:
                                info["gpos_class_kerning"] = True
                                info["gpos_class_pairs_nonzero"] += class_nonzero

    if "kern" in font:
        try:
            info["legacy_kern_table_pairs"] = sum(
                len(sub.kernTable)
                for sub in font["kern"].kernTables
                if hasattr(sub, "kernTable")
            )
        except Exception:
            info["legacy_kern_table_pairs"] = -1  # present but unreadable
    return info


# ---------------------------------------------------------------- variable

def get_variable(font: TTFont) -> dict | None:
    if "fvar" not in font:
        return None
    fvar = font["fvar"]
    name = font["name"]
    axes = [
        {
            "tag": axis.axisTag,
            "name": name.getDebugName(axis.axisNameID) or axis.axisTag,
            "min": axis.minValue,
            "default": axis.defaultValue,
            "max": axis.maxValue,
        }
        for axis in fvar.axes
    ]
    instances = [
        {
            "name": name.getDebugName(inst.subfamilyNameID) or "?",
            "coordinates": dict(inst.coordinates),
        }
        for inst in fvar.instances
    ]
    return {
        "axes": axes,
        "named_instances": instances,
        "has_avar": "avar" in font,
        "has_stat": "STAT" in font,
    }


# ---------------------------------------------------------------- color

def get_color(font: TTFont) -> dict | None:
    formats: dict = {}
    if "COLR" in font:
        colr = font["COLR"]
        formats["COLR"] = {"version": colr.version}
    if "CPAL" in font:
        cpal = font["CPAL"]
        formats["CPAL"] = {
            "palettes": len(cpal.palettes),
            "entries_per_palette": cpal.numPaletteEntries,
        }
    if "SVG " in font:
        formats["SVG"] = {"documents": len(font["SVG "].docList)}
    if "sbix" in font:
        formats["sbix"] = {"strike_ppems": sorted(font["sbix"].strikes.keys())}
    if "CBDT" in font or "CBLC" in font:
        formats["CBDT"] = {}
    return formats or None


# ---------------------------------------------------------------- languages

def get_languages(path: Path) -> dict | None:
    """Language support via hyperglot; returns None when unavailable.

    get_supported_languages() returns {script_name: {iso_code: Language}}.
    """
    import logging

    logging.disable(logging.WARNING)  # hyperglot logs every borderline conjunct
    try:
        from hyperglot.checker import FontChecker

        supported = FontChecker(str(path)).get_supported_languages()
        by_script: dict[str, list[str]] = {}
        all_names: set[str] = set()
        for script, langs in supported.items():
            names = sorted(
                getattr(lang, "name", None) or code for code, lang in langs.items()
            )
            by_script[script] = names
            all_names.update(names)
        return {"count": len(all_names), "by_script": by_script}
    except Exception as exc:
        print(f"  (language detection skipped: {exc})", file=sys.stderr)
        return None
    finally:
        logging.disable(logging.NOTSET)


# ---------------------------------------------------------------- per font

def detect_format(path: Path, font: TTFont) -> str:
    outlines = "CFF" if font.sfntVersion == "OTTO" else "TrueType"
    flavor = font.flavor  # 'woff', 'woff2', or None
    if flavor:
        return f"{flavor.upper()} ({outlines} outlines)"
    if path.suffix.lower() == ".ttc":
        return f"Collection ({outlines} outlines)"
    return "OpenType/CFF" if outlines == "CFF" else "TrueType"


def inspect_font(path: Path, font: TTFont, ttc_index: int | None,
                 fonts_dir: Path, with_languages: bool) -> dict:
    layout = get_layout(font)
    all_features = set()
    for entry in layout.values():
        all_features.update(entry["features"])

    return {
        "file": path.as_posix(),
        "ttc_index": ttc_index,
        "format": detect_format(path, font),
        "names": get_names(font),
        "glyph_count": font["maxp"].numGlyphs,
        "style": get_style(font),
        "vertical_metrics": get_vertical_metrics(font),
        "coverage": get_coverage(font),
        "languages": get_languages(path) if with_languages else None,
        "layout": layout,
        "features_grouped": group_features(all_features),
        "kerning": get_kerning(font),
        "variable": get_variable(font),
        "color": get_color(font),
    }


# ---------------------------------------------------------------- CLAUDE.md

def fmt_int(value) -> str:
    return f"{value:,}" if isinstance(value, int) else "?"


def font_to_markdown(info: dict) -> str:
    names = info["names"]
    vm = info["vertical_metrics"]
    cov = info["coverage"]
    kern = info["kerning"]
    var = info["variable"]

    title = f"{names['family'] or Path(info['file']).stem} {names['subfamily'] or ''}".strip()
    if var:
        title += " (Variable)"
    lines = [f"### {title}", ""]

    meta = f"- File: `{info['file']}`"
    if info["ttc_index"] is not None:
        meta += f" (collection font #{info['ttc_index']})"
    meta += f" • {info['format']} • UPM {vm['upm']} • {fmt_int(info['glyph_count'])} glyphs"
    lines.append(meta)

    credits = [v for v in (names["version"], names["designer"], names["manufacturer"]) if v]
    if credits:
        lines.append(f"- {' • '.join(credits)}")

    hhea = vm["hhea"]
    metric_bits = [f"hhea {hhea['ascender']}/{hhea['descender']}/{hhea['line_gap']}"]
    if "os2_typo" in vm:
        typo = vm["os2_typo"]
        metric_bits.append(f"typo {typo['ascender']}/{typo['descender']}/{typo['line_gap']}")
        win = vm["os2_win"]
        metric_bits.append(f"win {win['ascent']}/-{win['descent']}")
    if vm.get("cap_height"):
        metric_bits.append(f"cap {vm['cap_height']}")
    if vm.get("x_height"):
        metric_bits.append(f"x-height {vm['x_height']}")
    lines.append(f"- Vertical metrics: {' • '.join(metric_bits)}")
    if vm.get("use_typo_metrics"):
        lines.append("- USE_TYPO_METRICS is set (apps should honor typo values)")
    for mismatch in vm["mismatches"]:
        lines.append(f"- ⚠ Metrics: {mismatch}")

    script_summary = ", ".join(
        f"{script} ({count})" for script, count in list(cov["scripts"].items())[:8]
    ) or "none detected"
    extra = len(cov["scripts"]) - 8
    if extra > 0:
        script_summary += f", +{extra} more"
    lines.append(f"- Coverage: {fmt_int(cov['codepoint_count'])} codepoints — {script_summary}")

    if info["languages"]:
        langs = info["languages"]
        per_script = ", ".join(
            f"{script}: {len(names)}" for script, names in langs["by_script"].items()
        )
        lines.append(
            f"- Languages (hyperglot): {langs['count']} supported ({per_script})"
        )

    for tag in ("GSUB", "GPOS"):
        if tag in info["layout"]:
            scripts = info["layout"][tag]["scripts"]
            rendered = ", ".join(
                f"{s} [{', '.join(l)}]" if l else s for s, l in scripts.items()
            )
            if rendered:
                lines.append(f"- {tag} scripts: {rendered}")

    kern_bits = []
    if kern["gpos_class_kerning"]:
        kern_bits.append(
            f"GPOS class kerning (~{fmt_int(kern['gpos_class_pairs_nonzero'])} class pairs)"
        )
    if kern["gpos_flat_pairs"]:
        kern_bits.append(f"GPOS flat pairs ({fmt_int(kern['gpos_flat_pairs'])})")
    if kern["legacy_kern_table_pairs"]:
        kern_bits.append(f"legacy kern table ({fmt_int(kern['legacy_kern_table_pairs'])} pairs)")
    lines.append(f"- Kerning: {'; '.join(kern_bits) if kern_bits else 'none found'}")

    if info["features_grouped"]:
        lines.append("- OpenType features:")
        for group, tags in info["features_grouped"].items():
            lines.append(f"  - {group}: {', '.join(tags)}")
    else:
        lines.append("- OpenType features: none")

    if var:
        axes = "; ".join(
            f"{a['tag']} {a['min']}–{a['max']} (default {a['default']})" for a in var["axes"]
        )
        lines.append(f"- Variable axes: {axes}")
        lines.append(
            f"- Named instances: {len(var['named_instances'])}"
            + (" • avar present" if var["has_avar"] else "")
            + (" • STAT present" if var["has_stat"] else "")
        )

    if info["color"]:
        lines.append(f"- Color font: {', '.join(info['color'].keys())}")

    lines.append("")
    return "\n".join(lines)


def build_claude_section(results: list[dict], errors: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"## Font context (generated by /init-font, {stamp})",
        "",
        f"{len(results)} font(s) analyzed. Exact data (full character ranges, feature",
        "lists, axis values) lives in `fontinfo.json` — read that file when precision",
        "matters; the summary below is for orientation.",
        "",
    ]
    parts += [font_to_markdown(info) for info in results]
    for err in errors:
        parts.append(f"### ⚠ {err['file']}\n\n- Could not be read: {err['error']}\n")
    return "\n".join(parts).rstrip() + "\n"


def update_claude_md(claude_md: Path, section: str) -> None:
    text = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    block = f"{CLAUDE_BEGIN}\n{section}{CLAUDE_END}"
    if CLAUDE_BEGIN in text and CLAUDE_END in text:
        before = text.split(CLAUDE_BEGIN)[0]
        after = text.split(CLAUDE_END, 1)[1]
        text = before + block + after
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    claude_md.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonts-dir", default="fonts", type=Path)
    parser.add_argument("--json", default="fontinfo.json", type=Path,
                        dest="json_path")
    parser.add_argument("--claude-md", default="CLAUDE.md", type=Path)
    parser.add_argument("--no-languages", action="store_true",
                        help="skip hyperglot language detection (faster)")
    args = parser.parse_args()

    files = discover_font_files(args.fonts_dir)
    if not files:
        print(f"No font files found in {args.fonts_dir}/.")
        print("Supported formats: " + ", ".join(sorted(FONT_EXTENSIONS)))
        return 1

    results: list[dict] = []
    errors: list[dict] = []
    for path in files:
        print(f"Analyzing {path.as_posix()} ...")
        try:
            for font, ttc_index in load_fonts(path):
                results.append(
                    inspect_font(path, font, ttc_index, args.fonts_dir,
                                 with_languages=not args.no_languages)
                )
                font.close()
        except Exception as exc:
            print(f"  could not read this file: {exc}", file=sys.stderr)
            errors.append({"file": path.as_posix(), "error": str(exc)})

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonts_dir": args.fonts_dir.as_posix(),
        "fonts": results,
        "errors": errors,
    }
    args.json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {args.json_path} ({len(results)} font(s), {len(errors)} error(s)).")

    update_claude_md(args.claude_md, build_claude_section(results, errors))
    print(f"Updated the generated section of {args.claude_md}.")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
