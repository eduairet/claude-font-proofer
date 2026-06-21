# proof.content.json — the content contract

This is the handoff format between the **typographer** (who decides what text a proof shows) and the **renderer** (`scripts/render_proof.py`). The typographer produces this JSON; the main agent saves it as `proof.content.json` at the repo root; the font-engineer runs the renderer. Section ids in `proof.config.json`'s `sections` list correspond to the `type` values here.

Top level:

```json
{
  "title": "Acme Grotesk — proof",
  "sections": [ ...section objects, rendered in order... ]
}
```

Common keys every section accepts:

- `type` (required) — one of the section types below; picks the template.
- `title` — heading printed at the top of the section (each type has a default).
- `font` — file path (as listed in proof.config.json `fonts`) this section showcases. Omitted → the first configured font.

Sizes are points. Text is plain text (the renderer escapes it); pick characters that actually exist in the font — check `coverage.ranges` in fontinfo.json.

## cover
```json
{ "type": "cover", "title": "Acme Grotesk", "subtitle": "Variable · 842 glyphs",
  "lines": ["Proof generated 2026-06-12", "fonts/AcmeGrotesk.ttf"] }
```

## waterfall
```json
{ "type": "waterfall", "text": "Hamburgefonstiv",
  "sizes_pt": [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 21, 24, 28, 36, 48, 60, 72] }
```

## character-set
`chars` is a plain string; each character becomes a cell with its codepoint.
```json
{ "type": "character-set", "groups": [
    { "label": "Uppercase", "chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZ" },
    { "label": "Figures",   "chars": "0123456789" } ] }
```

## spacing-strings / kerning-pairs (same shape)
```json
{ "type": "kerning-pairs", "size_pt": 14, "strings": [
    { "label": "round/straight caps", "text": "HHOOHOHO DODGE" },
    { "label": "classic problem pairs", "text": "AV AW Ta Te To Va Wa Ya P. F. L'" } ] }
```
Per-string `size_pt` overrides the section default.

## paragraphs / language-specimens (same shape)
`lang` is a BCP-47 tag — it activates the font's `locl` behavior; `dir: "rtl"` for right-to-left scripts. `style_extra` is appended to the inline CSS (e.g. `"font-feature-settings: 'onum' 1;"`).
```json
{ "type": "language-specimens", "specimens": [
    { "label": "Polish", "lang": "pl", "size_pt": 10, "line_height": 1.45,
      "text": "Zażółć gęślą jaźń..." } ] }
```

## opentype-features
Each item renders the text twice: feature forced off, feature forced on. Choose `text` so the difference is visible (check the feature actually substitutes — the font-engineer can verify with uharfbuzz).
```json
{ "type": "opentype-features", "size_pt": 14, "items": [
    { "feature": "smcp", "label": "small caps", "text": "Hamburg 123" },
    { "feature": "onum", "label": "oldstyle figures", "text": "0123456789" } ] }
```

## variable-axes
Steps are raw axis values from fvar min→max (include the default).
```json
{ "type": "variable-axes", "size_pt": 22, "axes": [
    { "tag": "wght", "name": "Weight", "text": "Hamburgefonstiv",
      "steps": [100, 200, 300, 400, 500, 600, 700, 800, 900] } ] }
```

## color-showcase
```json
{ "type": "color-showcase", "text": "😀🎨🌈", "sizes_pt": [18, 36, 72] }
```

## Adding a new section type

The font-engineer owns this: add `templates/sections/<type>.html.j2`, document the shape here, and the renderer picks it up automatically (unknown types are skipped with a note, never an error).
