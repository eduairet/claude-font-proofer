---
name: init-font
description: >
  Analyze the fonts in fonts/ and set up this repo for proofing. Runs the containerized
  fontTools introspection, writes a human-readable font summary into CLAUDE.md (and
  machine-precise data into fontinfo.json), then interviews the user about the proof
  they want — page size, orientation, colors, header/footer, margins, and which
  sections to include (tailored to what was detected) — and saves the answers to
  proof.config.json. Use when the user runs /init-font, adds or changes fonts, or asks
  to set up / re-analyze their fonts.
---

# init-font

You are talking to a type designer, usually not a programmer. Be warm and concrete.
Never show raw tracebacks; translate problems into plain language with one clear next
step. Never run Python on the host — everything goes through the container.

## Step 0 — Preflight

Run these checks in order; stop at the first failure with the friendly message.

1. `docker compose version` fails →
   "Docker doesn't seem to be running. Open the Docker Desktop app (install it from
   docker.com if you haven't), wait until it says it's running, then run /init-font
   again." On Linux suggest `sudo systemctl start docker`.
2. `docker image inspect ai-font-proofer` fails → the engine was never built. Tell the
   user you'll build it now (one-time, a few minutes), then run `docker compose build`.
   If the build fails with SSL/certificate errors, antivirus or a corporate network is
   intercepting downloads — point them to the README's troubleshooting section
   (extra-ca.crt) rather than pasting the error wall.
3. `fonts/` contains no files ending in .otf/.ttf/.ttc/.woff/.woff2 (search it
   recursively, case-insensitive) → "Drop your font files into the fonts/ folder first
   — then run /init-font again. Any of .otf, .ttf, .ttc, .woff, .woff2 works."

## Step 1 — Analyze the fonts

Run:

    docker compose run --rm proofer python scripts/inspect_fonts.py

This writes `fontinfo.json` (exact data) and fills the generated section of
`CLAUDE.md` (summary). Red "Conjunct ... does not shape" lines from the language
checker are normal — they explain why borderline languages were excluded.

Then read `fontinfo.json` and give the user a short, encouraging summary of each
font in designer terms: family and style, glyph count, scripts and language count,
the most interesting OpenType features, variable axes if any, color format if any.
If `vertical_metrics.mismatches` is non-empty, explain what it means practically
(e.g. "your win and typo metrics differ — some apps may space lines differently")
— designers care, but don't alarm them; the proof itself is unaffected.

If a file errored, name it, give the plain-language reason, and continue with the
fonts that worked.

## Step 2 — Interview

Ask ONE question at a time (use AskUserQuestion when available). Always show the
default and accept it on a bare confirmation. Use the user's answers so far to keep
later questions short.

Tailor everything to what Step 1 actually found — never offer a section the fonts
can't demonstrate:

| Offer this section            | Only when fontinfo.json shows                          |
| ----------------------------- | ------------------------------------------------------ |
| OpenType feature showcase     | features beyond bare kern/ccmp/locl/rvrn               |
| Variable axis waterfall       | `variable` is non-null                                 |
| Language/script specimens     | per detected scripts (name them, cite language counts) |
| Kerning pair tests            | any GPOS or legacy kerning                             |
| Color glyph showcase          | `color` is non-null                                    |

The questions, in order:

1. **Page size** — [1] US Letter (default) [2] Tabloid [3] A4 [4] Custom.
   Custom → ask width, height, and units (mm, inches, or points).
2. **Orientation** — [1] Portrait (default) [2] Landscape.
3. **Color scheme** — [1] Black on white (default) [2] White on black [3] Custom.
   Custom → ask foreground then background; accept any CSS color, echo back hex.
4. **Header & footer** — default: header with family + style name, footer with page
   number and date. Ask if they want that, something else (which contents: font
   name(s), weight/style, page numbers, date, custom text), or none.
5. **Margins** — offer 20 mm on all sides as the default; accept custom values
   (top/bottom/inner/outer).
6. **Sections** — list the universally useful ones (type waterfall, full character
   set, spacing strings, paragraph specimens) plus the tailored ones from the table
   above, each with a one-line description of what it shows. Recommend a sensible
   default set; let them pick any combination. Reference specifics from their fonts
   ("I found small caps and 7 stylistic sets — want the feature showcase?").
7. **Which fonts** — only if more than one font was analyzed: all of them in one
   proof (default) or a subset.
8. **Output file** — default `output/<FamilyName>-proof.pdf`; let them rename.

## Step 3 — Save and confirm

Write the answers to `proof.config.json` at the repo root, exactly in the shape of
`proof.config.example.json` (same keys; `sections` uses these ids: `waterfall`,
`character-set`, `spacing-strings`, `kerning-pairs`, `paragraphs`,
`opentype-features`, `variable-axes`, `language-specimens`, `color-showcase`).
Custom page size goes in `custom_size` as `{"width": n, "height": n, "unit": "mm"}`
with `size` set to `"custom"`. Margins are always stored in mm — convert if the
user answered in other units.

If a `proof.config.json` already exists, show what would change and ask before
overwriting.

Finish by summarizing their choices in a few lines and saying:
"Setup complete — now just ask me to generate your proof (or a web test page)."

## Re-running

Safe to re-run any time (new fonts, changed fonts). The generated CLAUDE.md section
and fontinfo.json are always rewritten from scratch; the interview only re-runs if
the user wants to change their proof choices — offer to keep the existing
proof.config.json when one is present.
