---
name: pbix-report-authoring
description: Use when creating, editing, or generating a Power BI .pbix report or dashboard from data - builds multi-page PBIX files with KPI cards, charts, tables, shape maps and navigation by writing the report layer programmatically. Triggers on "pbix", "Power BI file", "Power BI dashboard", "build a pbix", "generate a pbix", "edit a pbix", "add a page to a pbix".
license: MIT
---

# Power BI (.pbix) report authoring

Generate and modify `.pbix` files from a script instead of clicking through
Power BI Desktop. This skill exists because **the report layer of a PBIX is
plain JSON inside a ZIP**, and can be written deterministically — while the data
model inside it cannot.

## The one constraint that shapes everything

A `.pbix` is a ZIP whose parts split into two unrelated worlds:

| Layer | Parts | Format | Can you author it? |
|---|---|---|---|
| **Data model** | `DataModel`, `Metadata`, `Connections`, `DiagramLayout`, `Settings` | XPress9-compressed binary backup | **No** — opaque |
| **Report layer** | `Report/definition/**` | Plain JSON | **Yes** |

`DataModel` begins with the literal string
`This backup was created using XPress9 compression.` It is an Analysis Services
backup. You cannot read, write, or synthesise it from Python.

So the architecture is fixed: **inherit the data model from a donor `.pbix`,
and rewrite only the report layer.** This is the approach this skill automates.

So within *this* skill the architecture is fixed: **inherit the data model from
a donor `.pbix`, and rewrite only the report layer.**

Be precise about what that means. Creating a data model from scratch **is**
possible — just not with Python's standard library, which cannot write those
bytes. The available routes:

| Route | Automatable | Notes |
|---|---|---|
| **PBIP + TMDL** | yes | Preferred. Model becomes plain-text `.tmdl` files. |
| **TMSL (`model.bim`)** | yes | One large JSON file. |
| **TOM client library** | yes | Microsoft's official modelling API. |
| **Tabular Editor** | yes | Free, CLI-scriptable. |
| **Power BI Desktop** | no | The manual route; always the last step. |

If the task is "build a dashboard from scratch", a **PBIP** project is usually
the better target than a `.pbix` — see `references/pbip.md`. This skill covers
the legacy `.pbix` container, which is what you have when a donor already
exists.

## Workflow

```
1. OBTAIN A DONOR   a .pbix that already contains your table
2. INSPECT IT       confirm it has a DataModel and see its resources
3. WRITE A SPEC     pages + visuals, in JSON
4. BUILD            pbix_build.py -> new .pbix
5. VALIDATE         pbix_validate.py -> structural check, no Power BI needed
6. RE-SIGN          open once in Power BI Desktop and save
```

### Step 1 — obtain a donor

Either:
- **Reuse** an existing PBIX that already has the table, or
- **Build a minimal one** by hand once, in Desktop: `Get Data → Text/CSV`,
  pick the CSV, fix the column types, `File → Save as`. One flat table is
  enough; this takes about two minutes and is the step you cannot automate.

Keep the donor pristine. The builder copies from it, never mutates it.

### Step 2 — inspect

```bash
python scripts/pbix_inspect.py donor.pbix
```

Confirms it is a real PBIX, has an uncompressed `DataModel`, whether it is
signed, which pages/visual types it already uses, and which entities its
visuals reference. The **entity names** it prints are what you put in your
spec.

### Step 3 — write a spec

See `references/spec-format.md` for the full reference and
`examples/example_spec.json` for a working two-page report.

```json
{
  "donor": "donor.pbix",
  "output": "out.pbix",
  "navigation": true,
  "resources": [{"file": "shape.topo.json", "name": "shape.topo.json",
                 "type": "ShapeMap"}],
  "pages": [
    {"id": "overview", "title": "Overview", "visuals": [
      {"id": "kpi", "type": "card", "x": 20, "y": 156, "w": 303, "h": 100,
       "z": 10, "entity": "sales", "column": "revenue",
       "label": "Total revenue", "agg": "sum", "accent": "#1F3864"},
      {"id": "bar", "type": "bar", "x": 335, "y": 156, "w": 600, "h": 300,
       "z": 20, "entity": "sales", "category": "region", "value": "revenue",
       "heading": "Revenue by region"}
    ]}
  ]
}
```

Visual types: `card`, `bar`, `column`, `scatter`, `table`, `textbox`,
`heading`, `image`, `shape`, `shapemap`.

### Step 4 — build

```bash
python scripts/pbix_build.py spec.json              # writes the pbix
python scripts/pbix_build.py spec.json --check-only # render, write nothing
```

`--check-only` is cheap. Run it while iterating on geometry.

### Step 5 — validate

```bash
python scripts/pbix_validate.py out.pbix
```

Exit 0 = structurally sound, 1 = problems listed. This catches broken JSON,
page-order mismatches, duplicate visual ids, dangling resource references and
textbox clipping. **Run it before every handoff** — it is the only automated
check you have, since you have no Power BI to hand.

### Step 6 — re-sign

Desktop refuses to open a PBIX whose report layer was edited after signing.
The builder strips `SecurityBindings`, so the output opens — but it is
**unsigned**, and Power BI may warn or restrict editing.

Open it in Power BI Desktop once, confirm the visuals render, then **Save**.
That regenerates the signature and normalises the JSON. Then re-run
`pbix_validate.py` to confirm the round trip did not damage anything.

Desktop normalises aggressively on save (see Gotchas). Prefer: script the
first draft, open in Desktop once, and let Desktop own the final file.

## Critical gotchas

These are verified against shipped PBIX files. Each has cost real time.

**1. `visualContainerObjects` and `drillFilterOtherVisuals` go INSIDE
`visual`.** They are not siblings of it. Desktop writes them nested, and if you
put them at the container's top level Desktop tolerates the file but **silently
discards them on the next save** — your styling vanishes with no error. The
correct shape:

```jsonc
{ "$schema": "...", "name": "kpi1", "position": {...},
  "visual": { "visualType": "cardVisual", "query": {...}, "objects": {...},
              "visualContainerObjects": {...}, "drillFilterOtherVisuals": true } }
```

**2. Card objects are `title`, `value`, `label`** — not `labels`,
`categoryLabels`, or `wordWrap`. The wrong keys are ignored and then dropped.

**3. Font-size units differ by context.** Visual titles and axis fonts use point
sizes (`"13pt"`). Card `value`/`label` sizes use D-suffixed decimals
(`"22D"`). Mixing them makes styling silently drop.

**4. Textboxes clip when the box is short.** Budget roughly twice the point
size in pixels: a 21 pt heading needs ~44 px. A 21 pt heading in a 30 px box
renders as a blank sliver.

**5. Desktop clips the top ~40 px of the canvas.** Keep all content below
`y = 44`, even on a page with no header.

**6. `actionButton` ignores its background colour** and renders white. To mark
the active page, darken the text and thicken the border — a white-on-navy
"selected" state is invisible.

**7. Textbox backgrounds must omit `show`.** A `show` key inside a textbox's
`background` makes Power BI discard the colour and fall back to white.

**8. Shape Map matches region names by exact text.** A data value of
`North Region` will not match a boundary file's `NORTH_REGION`. Build a lookup
column that matches your boundary file and bind *that*. Silent failure: the
region just renders grey. See `references/resources-and-maps.md`.

**9. The Bing `map` visual needs Azure sign-in and often stays disabled.** Use
`shapemap`, which is fully offline.

**10. Power BI Desktop holds an exclusive lock.** Close the file before
building over it, or the write fails with `PermissionError` / `WinError 5`.

**11. Aggregation codes are barely documented.** Only `0` = Sum and
`1` = Average are confirmed. See `references/visual-json.md` before using any
other code.

**12. There is no verified card number-format property.** Control display
formatting with a DAX measure using `FORMAT()`, or set it in Desktop. Emitting
a guessed `labelFormat` does nothing.

## Layout guidance

A page that reads well uses a consistent vertical rhythm. On a 1280×720 canvas:

| Band | y | Height | Contents |
|---|---|---|---|
| Navigation | 44 | 30 | action buttons |
| Title | 84 | 46 | 21 pt heading |
| Subtitle | 132 | 26 | 10 pt grey line |
| KPI row | 156 | 100 | cards |
| Charts | 260 | 252 | main visuals |
| Table | 518 | 146 | detail |
| Caveats | 668 | 40 | sources and limitations |

Reuse these as a starting point, then adjust. Two rules that matter more than
the exact numbers:

- **Pair a map with a bar chart.** The map shows where; the bar chart shows the
  magnitude, which a choropleth hides.
- **State the caveats on the page.** Reference years, exclusions, and any
  figure that does not reconcile. A dashboard whose cards say "Mean 23.0%" next
  to an appendix saying "Median 15.0%" is a bug waiting to be noticed.

## Files

| Path | Purpose |
|---|---|
| `scripts/pbixlib.py` | Library. Primitives, visual factories, `PbixWriter`. |
| `scripts/pbix_build.py` | Spec → PBIX CLI. |
| `scripts/pbix_inspect.py` | Dump container structure and entities. |
| `scripts/pbix_validate.py` | Structural validator. Exit 1 on errors. |
| `references/container-format.md` | Every part, encoding, compression. |
| `references/visual-json.md` | Visual anatomy, literals, aggregation codes. |
| `references/datamodel.md` | Donors, DAX measures, relationship setup. |
| `references/pbip.md` | The PBIP/TMDL folder format — preferred for new builds. |
| `references/resources-and-maps.md` | Images, TopoJSON, Shape Map. |
| `references/spec-format.md` | Full spec reference. |
| `references/troubleshooting.md` | Symptom → cause → fix. |
| `examples/example_spec.json` | Working two-page example. |

## Limits — say these plainly

- This skill inherits the data model; it does not build one. Model creation is
  still possible, but via PBIP/TMDL, TOM, or Tabular Editor — see
  `references/pbip.md`.
- Desktop must be available at least once, to sign the file.
- Visual styling you script is a starting point; Desktop's theme engine has the
  final word and will normalise on save.
- `shapeMap` regions must match the boundary file's naming exactly.
- Lat/long scatter plots need real numeric longitude/latitude columns. Without
  them Power BI reports *"This aggregate is not supported for the x-axis
  field"* regardless of the summarisation chosen.