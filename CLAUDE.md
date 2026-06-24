# ai-font-proofer — instructions for Claude

This repository is a template that helps a **type designer** (usually not a programmer) generate print proofs (PDF) and web test pages for the fonts they place in `fonts/`. Talk to the user in plain language; never ask them to edit code or run Python directly.

## How this repo works

- **All Python runs inside the Docker container.** Never run `python`, `pip`, or any font tooling on the host. Use: `docker compose run --rm proofer <command>`.
- `fonts/` — the user's font files (never commit, never redistribute).
- `output/` — rendered PDF proofs land here.
- `web-tests/` — generated browser test pages land here.
- `scripts/` — the Python engine (introspection + rendering). `templates/` — HTML/CSS proof templates.
- `proof.config.json` — the user's proof choices, written by `/init-font`. Treat it as the source of truth for page size, colors, margins, and sections.
- `fontinfo.json` — machine-precise font data written by `/init-font`. Use it when you need exact values (full cmap, feature lists, axis ranges); the summary below is for orientation.

## The workflow

1. The user drops fonts into `fonts/` and runs **`/init-font`** — it inspects the fonts, fills the generated section below, and interviews the user about the proof.
2. To produce a **print proof**: first delegate content decisions to the **typographer** subagent — it returns a complete proof-content JSON document (schema: `templates/CONTENT_SCHEMA.md`), never code. Save its JSON verbatim as `proof.content.json` at the repo root, then have the **font-engineer** subagent render and verify it: `docker compose run --rm proofer python scripts/render_proof.py`
3. To produce **web test pages**: delegate to the **web-engineer** subagent (it asks the user which tests they want, then writes vanilla HTML/CSS/JS into `web-tests/`). Then bake the font into each page so it is self-contained: `docker compose run --rm proofer python scripts/inline_web_fonts.py`. Open the pages in the **Claude app preview** first (they are self-contained, so no server is needed); if a preview isn't available, double-click the .html, or as a last resort serve the repo root: `docker compose run --rm -p 8765:8765 proofer python -m http.server 8765` then open http://localhost:8765/web-tests/

Boundaries: the typographer never writes code or files; the font-engineer never invents editorial content; the web-engineer only writes inside `web-tests/`.

---

<!-- BEGIN GENERATED FONT CONTEXT -->
_No fonts analyzed yet. Run `/init-font` after placing font files in `fonts/`._
<!-- END GENERATED FONT CONTEXT -->
