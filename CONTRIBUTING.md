# Contributing to ai-font-proofer

Thanks for your interest! This document is for developers; end-user docs live in the
README, which is written for type designers with no programming background — keep it
that way when you touch it.

## Architecture (one paragraph)

Everything Python runs inside the Docker image defined in `Dockerfile` (fontTools for
introspection, uharfbuzz for shaping checks, headless Chromium for HTML→PDF rendering).
`scripts/inspect_fonts.py` turns the contents of `fonts/` into `fontinfo.json` plus a
human-readable block in `CLAUDE.md`; `scripts/render_proof.py` fills the HTML templates
in `templates/` from `proof.config.json` + typographer-supplied content and prints them
to PDF in `output/`. The Claude Code layer lives in `.claude/`: the `/init-font` skill
and three subagents (`typographer` — read-only editorial; `font-engineer` — Python and
rendering; `web-engineer` — vanilla web test pages scoped to `web-tests/`).

## Ground rules

- **Pin everything.** `requirements.txt` uses exact versions; the Dockerfile pins its
  base image. Reproducibility beats freshness.
- **The container is the only runtime.** No script may assume host Python. If it can't
  run via `docker compose run`, it doesn't ship.
- **Agent boundaries are load-bearing.** The typographer must never gain write/exec
  tools; the web-engineer stays scoped to `web-tests/`. Don't "fix" a workflow by
  widening a tool list.
- **Designer-facing text is jargon-free.** Error messages a user can see must say what
  to do next, not what went wrong internally.

## Development setup

```sh
git clone <your-fork>
cd claude-font-proofer
docker compose build
docker compose run --rm proofer python scripts/inspect_fonts.py --help
```

## Submitting changes

1. Fork, branch from `main`.
2. Keep PRs focused; explain *why* in the description.
3. If you change the introspection output shape, update `proof.config.example.json`
   and the SKILL.md interview accordingly — they're a contract. The same goes for
   section content: a new `templates/sections/*.html.j2` partial must be documented
   in `templates/CONTENT_SCHEMA.md` in the same change.
