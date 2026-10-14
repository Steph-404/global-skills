# Images and Shape Maps

## Registering a resource

Three things must agree, or the reference dangles and the visual renders blank:

1. The file sits at `Report/StaticResources/RegisteredResources/<name>`
2. `report.json` declares it in a `RegisteredResources` package:

```json
{"name": "RegisteredResources", "type": "RegisteredResources",
 "items": [{"name": "cover.jpg", "path": "cover.jpg", "type": "Image"}]}
```

3. The visual references `<name>` exactly via `ResourcePackageItem`.

In the spec:

```json
"resources": [{"file": "assets/cover.jpg", "name": "cover.jpg", "type": "Image"}]
```

`type` is `Image` or `ShapeMap`. The `file` is read from disk at build time and
its bytes embedded, so the output PBIX is self-contained — it will not break
when the source moves.

`pbix_build.py` handles all three; you just list them.

## Images

```json
"objects": {"image": [{"properties": {
  "sourceFile": {"image": {
    "name": {"expr": {"Literal": {"Value": "'cover.jpg'"}}},
    "url": {"expr": {"ResourcePackageItem": {
      "PackageName": "RegisteredResources", "PackageType": 1,
      "ItemName": "cover.jpg"}}},
    "scaling": {"expr": {"Literal": {"Value": "'Fit'"}}}}},
  "backgroundEnabled": {"expr": {"Literal": {"Value": "false"}}},
  "border": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]}}]}
```

`scaling` is `Fit`, `Fill`, or `Stretch`. `Fit` preserves aspect ratio and
letterboxes; `Fill` crops to the frame. For a full-bleed cover, `Fill` is
usually what you want.

Practical note: text rendered into a cover image is not selectable, searchable
or accessible. Use real textboxes for anything that matters. Image covers suit
decorative title plates.

## Shape Map

Shape Map draws regions from a boundary file and is fully offline. This is the
map to use — the Bing `map` visual requires Azure sign-in and is often disabled
even when enabled.

### Getting a boundary file

Shape Map accepts **TopoJSON**. GeoJSON must be converted first (an online
converter, or `geojson2topo`).

Provenance matters: boundaries are usually published under ODbL or similar, and
some government portals restrict redistribution. Record the source and licence
next to the dashboard, and confirm before publishing outside your organisation.
A boundary file inherited from an unknown donor has unverified provenance —
treat it as provisional and say so on the report.

### The name-matching trap

Shape Map matches your data to the boundary regions by **exact text**, case- and
punctuation-sensitive. This is the failure that defeats most attempts.

Typical mismatches:

| Your data | Boundary file |
|---|---|
| `North Region` | `NORTH_REGION` |
| `District A/B` | `DISTRICT A-B` |
| `Springfield` | `SPRINGFIELD CITY` |

**Failure is silent.** The region simply renders grey. There is no error.

**Fix: build a lookup column in Power BI, not in the map file.** Create a small
table mapping your label to the boundary file's label, merge it onto your data,
and bind the *merged* column to the visual's `location` field. That keeps the
boundary file canonical and the fix lives in the model.

### Spec

```json
{"id": "map", "type": "shapemap", "x": 20, "y": 260, "w": 470, "h": 252,
 "z": 20, "entity": "geo", "location": "boundary_name",
 "value": "revenue", "heading": "Revenue by region",
 "resource": "counties.topo.json", "agg": "sum"}
```

`location` is the column holding boundary-matching names. `value` is the
measure driving the fill.

### The fill rule

```json
"dataPoint": [{"properties": {"fill": {"expr": {"FillRule": {
  "Input": <aggregation>,
  "FillRule": {"linearGradient2": {
    "min": {"color": {"expr": {"Literal": {"Value": "'#D64045'"}}}},
    "max": {"color": {"expr": {"Literal": {"Value": "'#FFFFFF'"}}}},
    "nullColor": {"color": {"expr": {"Literal": {"Value": "'#CCCCCC'"}}}}}}}}}}]
```

`Input` must be your own measure. A fill rule copied from a donor can retain the
donor's entity and column — check it before trusting a map that looks right.

`nullColor` is the grey you see when a region fails to match, so a fully grey
map means every region failed. Diagnose by temporarily binding the visual to a
table filtered to blanks, or compare your label list against the boundary
file's names.

### Verify every region filled

A partially grey map is a data-matching bug, not a rendering quirk. Check it
before delivering. One robust check: build a `tableEx` with the location column
and confirm it has no blanks.

## Pair the map with a chart

A choropleth encodes magnitude as area and colour together, which makes small
regions unreadable. Always put a sorted bar chart of the same measure beside
it: the map shows *where*, the chart shows *how much*.