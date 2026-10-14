# Spec format

The input to `pbix_build.py`. Valid JSON — note that JSON does **not** allow
splitting a string across lines the way Python does.

## Top level

| Key | Required | Meaning |
|---|---|---|
| `donor` | yes | Path to the donor `.pbix` |
| `output` | no | Output path (default `out.pbix`) |
| `navigation` | no | `true` adds a nav button bar to every page |
| `resources` | no | Files to embed |
| `pages` | yes | Ordered list of pages |

## resources

```json
{"file": "assets/cover.jpg", "name": "cover.jpg", "type": "Image"}
```

`file` is read at build time. `name` is what visuals reference and what the
embedded filename becomes. `type` is `Image` or `ShapeMap`.

## pages

```json
{"id": "overview", "title": "Overview", "width": 1280, "height": 720,
 "visuals": [ ... ]}
```

`id` is the page directory name — keep it filesystem-safe. `title` is the tab
label. `width`/`height` default to 1280×720.

## Visual common fields

| Key | Meaning |
|---|---|
| `id` | unique within the page; becomes a directory name |
| `type` | see below |
| `x`, `y`, `w`, `h`, `z` | geometry; `z` is paint/tab order |

## Visual types

### card

```json
{"id": "kpi", "type": "card", "x": 20, "y": 156, "w": 303, "h": 100, "z": 10,
 "entity": "sales", "column": "revenue", "label": "Total revenue",
 "agg": "sum", "accent": "#1F3864", "value_colour": "#132A4D",
 "value_size": 22, "label_size": 11}
```

`agg` is `sum` or `average`. Number formatting is **not** a spec key — use a
DAX measure with `FORMAT()`.

### bar / column

```json
{"id": "bar", "type": "bar", "x": 502, "y": 260, "w": 758, "h": 252, "z": 21,
 "entity": "sales", "category": "region", "value": "revenue",
 "heading": "Revenue by region", "colour": "#2E7D32", "agg": "sum",
 "decimals": 1}
```

`type: "bar"` is horizontal, `"column"` vertical. `decimals` is optional
(`labelPrecision`); omit for auto.

### scatter

```json
{"id": "sc", "type": "scatter", "x": 20, "y": 170, "w": 620, "h": 300, "z": 20,
 "entity": "sales", "x_prop": "a", "y_prop": "b", "detail": "region",
 "heading": "A vs B", "agg": "average"}
```

`detail` puts one labelled point per row. For a geographic scatter, `x_prop`
and `y_prop` must be numeric longitude and latitude.

### table

```json
{"id": "tbl", "type": "table", "x": 20, "y": 518, "w": 1240, "h": 146, "z": 30,
 "entity": "sales",
 "columns": [["region", "Region"], ["revenue", "Revenue", "sum"]]}
```

Each column is `[property, display_label]` or `[property, display_label, agg]`.

### textbox

```json
{"id": "note", "type": "textbox", "x": 20, "y": 668, "w": 1240, "h": 40, "z": 40,
 "runs": [{"text": "Source: ", "size": 8, "bold": true, "colour": "#1F3864"},
          {"text": "ERP export, 2024.", "size": 7.5, "colour": "#595959"}]}
```

Height must be at least twice the largest `size`, or the text clips.

### heading

```json
{"id": "h", "type": "heading", "x": 20, "y": 84, "w": 900, "h": 46, "z": 2,
 "text": "Overview", "size": 21, "subtitle": "Population, 2009 vs 2019"}
```

Emits the heading and, if `subtitle` is present, a second textbox beneath it.

### image

```json
{"id": "cover", "type": "image", "x": 0, "y": 0, "w": 1280, "h": 720, "z": 1,
 "resource": "cover.jpg"}
```

### shape

```json
{"id": "band", "type": "shape", "x": 20, "y": 150, "w": 1240, "h": 6, "z": 1,
 "fill": "#1F3864"}
```

### shapemap

```json
{"id": "map", "type": "shapemap", "x": 20, "y": 260, "w": 470, "h": 252, "z": 20,
 "entity": "geo", "location": "boundary_name", "value": "revenue",
 "heading": "Revenue by region", "resource": "counties.topo.json",
 "agg": "sum", "min_colour": "#D64045", "max_colour": "#FFFFFF"}
```

## Navigation

With `"navigation": true`, every page gets one `actionButton` per page at
`y = 44`, and the current page is marked active by border width and text colour.

The first page in `pages` is the active page on open. Page order comes from the
order of the `pages` array.

## Unknown keys

Unknown keys are ignored. Unknown `type` is an error. Unknown `agg` falls back
to `sum` with a warning.

## Workflow

```bash
python scripts/pbix_build.py spec.json --check-only   # iterate on layout
python scripts/pbix_build.py spec.json                # write the file
python scripts/pbix_validate.py out.pbix              # check it
```