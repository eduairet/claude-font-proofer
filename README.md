# ai-font-proofer

Generate professional print proofs (PDF) and interactive web test pages for your
fonts — without writing code or installing Python. You drop your fonts in a folder,
answer a few questions, and Claude Code does the rest. Everything technical runs
inside a container you never have to look into.

## What you get

- **Print proofs** — clean vector PDFs at your chosen page size: type waterfalls,
  full character sets, spacing and kerning tests, OpenType feature showcases
  (small caps, oldstyle figures, ligatures…), language specimens, and variable-axis
  ramps when your font has them. Text is shaped by the same engine browsers use,
  so complex scripts and OpenType features render the way they will in the world.
- **Web test pages** — self-contained pages you open in a browser, with sliders and
  toggles to poke at your font: size, variable axes, feature on/off switches,
  kerning comparison, light/dark mode, and editable sample text.

## What you need (two installs, once)

1. **Docker** — the container app that runs the engine.
   Windows / Mac: install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   and open it once so it's running. Linux: install
   [Docker Engine](https://docs.docker.com/engine/install/).
2. **[Claude Code](https://claude.com/claude-code)** — the AI assistant this
   template is built around.

No Python, no package managers, no terminals full of red text.

## Quick start

1. Click **Use this template** on GitHub (or download this repository) and open
   the folder on your computer.
2. Drop your font files into the `fonts/` folder — `.otf`, `.ttf`, `.ttc`,
   `.woff`, `.woff2`, variable and color fonts all work.
3. Build the engine (one time, a few minutes — it downloads its own rendering
   browser). In a terminal opened in the project folder:

       docker compose build

4. Start Claude Code in the project folder and type:

       /init-font

   It reads your fonts, tells you what it found (glyphs, languages, features,
   axes…), and asks a few questions about the proof you want — page size, colors,
   which sections. Defaults are always offered; you can just keep saying yes.
5. Ask for what you want, in plain words:

   > "Generate my proof" → a PDF appears in `output/`
   >
   > "Make me a web test page" → a page appears in `web-tests/`

To re-do anything, just ask. Added new fonts? Run `/init-font` again.

## The folders

| Folder       | What it's for                                                 |
| ------------ | ------------------------------------------------------------- |
| `fonts/`     | Put your font files here. Never committed, never shared.      |
| `output/`    | Finished PDF proofs appear here.                              |
| `web-tests/` | Generated browser test pages appear here.                     |

## Viewing web test pages

Browsers are picky about loading font files straight from disk, so serve the
project with this command, then open the address it gives you:

    docker compose run --rm -p 8765:8765 proofer python -m http.server 8765

→ http://localhost:8765/web-tests/  (stop it with Ctrl-C when you're done)

## How it works (the short version)

`/init-font` inspects your fonts with professional font tooling and writes
everything it learns — metrics, character coverage, language support, OpenType
features, variable axes — into a context file Claude reads. From then on, three
specialists do the work: a **typographer** decides what the proof should show
(specimen texts, size ramps, kerning strings), a **font engineer** runs the
rendering pipeline that turns those decisions into a PDF, and a **web engineer**
builds the browser test pages. You only ever talk to Claude in plain language.

## If something goes wrong

**"Docker doesn't seem to be running"** — open the Docker Desktop app and wait for
it to say it's running, then try again. (Linux: `sudo systemctl start docker`.)

**The build fails with "certificate" or "SSL" errors** — your antivirus or company
network inspects internet traffic, and the engine doesn't trust it yet. Easiest
fix: tell Claude Code *"the build failed with a certificate error — please fix
it"*. It can detect the program responsible, export its certificate to a file
called `extra-ca.crt` in the project folder, and rebuild — that file is all the
engine needs, and it never leaves your machine.

**"No fonts found"** — check your files are directly inside `fonts/` (subfolders
are fine) and end in `.otf`, `.ttf`, `.ttc`, `.woff`, or `.woff2`.

**The first build is slow or the download is big** — normal. The engine includes
its own rendering browser (~1 GB once). It only happens again if the engine's
ingredients change.

**On Linux: generated files are owned by root** — run commands with your user
mapped: `export HOST_UID=$(id -u) HOST_GID=$(id -g)` before `docker compose ...`.

**Anything else** — ask Claude Code. It can read the error and usually fix it.
The engine self-test is: `docker compose run --rm proofer python scripts/check_setup.py`

## License

This template's **code** is released under the [MIT License](LICENSE).

**Your fonts are not covered by that license.** Anything you place in `fonts/`
remains entirely yours, under its own license or EULA. Fonts are excluded from
git, are never uploaded anywhere, and are never redistributed by this project.

## Contributing

Found a bug or want to add a proof section? See [CONTRIBUTING.md](CONTRIBUTING.md)
(that one's written for developers).
