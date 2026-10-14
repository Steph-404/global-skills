# Visual JSON anatomy

Every value below was confirmed against Desktop-authored `.pbix` files, not
inferred from documentation.

## The container

```jsonc
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.13.0/schema.json",
  "name": "kpi1",
  "position": { "x": 20, "y": 156, "z": 10,
                "height": 100, "width": 303, "tabOrder": 10 },
  "visual": {
    "visualType": "cardVisual",
    "query": { ... },
    "objects": { ... },
    "visualContainerObjects": { ... },
    "drillFilterOtherVisuals": true
  }
}
```

`drillFilterOtherVisuals` and `visualContainerObjects` live **inside `visual`**.
Desktop writes them there and discards them if you place them beside it.

`z` controls paint order and tab order — higher sits on top. Give the
navigation bar a high `z` (e.g. 900) so it floats above page content.

## Property values are DAX expressions

A property value is a serialized DAX expression:

| Kind | JSON | Renders as |
|---|---|---|
| Text | `{"expr":{"Literal":{"Value":"'left'"}}}` | left |
| Decimal | `{"expr":{"Literal":{"Value":"12D"}}}` | 12.0 |
| Long | `{"expr":{"Literal":{"Value":"15L"}}}` | 15 |
| Boolean | `{"expr":{"Literal":{"Value":"true"}}}` | true |
| Font size (visual) | `{"expr":{"Literal":{"Value":"13pt"}}}` | 13 pt |
| Font size (card) | `{"expr":{"Literal":{"Value":"22D"}}}` | 22 pt |

Text is single-quoted **inside** the string. Apostrophes double: `'it''s'`.

## Colours

```json
"color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#1F3864'"}}}}}
```

You may also reference theme colours:

```json
"color": {"expr": {"ThemeDataColor": {"ColorId": 0, "Percent": -0.2}}}
```

`ColorId` indexes the theme palette; `Percent` shifts it lighter/darker.

## Field references

Un-aggregated column:

```json
{"Column": {"Expression": {"SourceRef": {"Entity": "sales"}},
            "Property": "revenue"}}
```

Aggregated measure:

```json
{"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": "sales"}},
                                               "Property": "revenue"}},
                 "Function": 0}}
```

The `Entity` name must match the table name in the data model exactly — run
`pbix_inspect.py --entities` on the donor to list them.

## Aggregation function codes

Only these are verified:

| Code | Meaning | `nativeQueryRef` shows as |
|---|---|---|
| `0` | Sum | `Sum of revenue` |
| `1` | Average | `revenue` (bare column name) |

One additional sample suggests `3` behaves like Min (a text column displayed
as "First"), but n=1 is not proof. For any other code, build a card with that
aggregation in Desktop once, save, and read the code back with
`pbix_inspect.py --entities`. Do not guess.

## queryState

Roles map to a visual's wells. Observed role names and what they bind:

| Role | Well |
|---|---|
| `Category` | axis / location |
| `Y` | primary values |
| `X` | scatter x-axis |
| `Series` | series |
| `Values` | table columns |
| `Value` | shape-map measure |
| `Data` | cards |

Each role holds `projections`, and a projection bundles a field with its refs:

```json
{"field": { ...aggregation... },
 "queryRef": "Sum(sales.revenue)",
 "nativeQueryRef": "Sum of revenue",
 "displayName": "Revenue"}
```

`displayName` is what the field well shows. Set it deliberately — otherwise
Power BI generates an ugly default.

## Sort

```json
"query": {
  "queryState": { ... },
  "sortDefinition": { "sort": [{"field": <agg>, "direction": "Descending"}],
                      "isDefaultSort": true }
}
```

`sortDefinition` is a sibling of `queryState` inside `query`, not inside it.

## Visual object keys

Object keys vary per visual type. Using a key the visual does not define means
it is ignored and then dropped on save.

**Card** — `title`, `value`, `label` (plus `layout`, `accentBar`, `fillCustom`,
`border`, `padding`, `grid`, `shadowCustom`, `outline`, `divider`,
`shapeCustomRectangle`). Sizes on `value`/`label` are `D`-suffixed.

```json
"objects": {
  "title": [{"properties": {"show": {"expr":{"Literal":{"Value":"true"}}},
                            "text": {"expr":{"Literal":{"Value":"'Total revenue'"}}},
                            "fontSize": {"expr":{"Literal":{"Value":"11pt"}}},
                            "fontColor": {"solid":{"color":{"expr":{"Literal":{"Value":"'#1F3864'"}}}}}}}],
  "value": [{"properties": {"fontSize": {"expr":{"Literal":{"Value":"22D"}}},
                            "fontColor": {"solid":{"color":{"expr":{"Literal":{"Value":"'#132A4D'"}}}}},
              "selector": {"id": "default"}}],
  "label": [{"properties": {"fontSize": {"expr":{"Literal":{"Value":"11D"}}}},
             "selector": {"id": "default"}}]
}
```

**textbox** — `general.paragraphs[].textRuns[]`:

```json
"objects": {"general": [{"properties": {"paragraphs": [
  {"textRuns": [{"value": "Overview",
                 "textStyle": {"fontWeight": "bold", "fontFamily": "Segoe UI",
                               "fontSize": "21pt", "color": "#1F3864"}}],
   "horizontalTextAlignment": "left"}]}}]}
```

Here sizes are `"21pt"` strings and colours are bare hex — **not** wrapped in
`expr`. This is the one place the expression wrapper does not apply.

**clusteredBarChart / clusteredColumnChart** — `title`, `labels`,
`categoryAxis`, `valueAxis`, `legend`, `grid`, `dataPoint`. Series colour:

```json
"dataPoint": [{"properties": {"defaultColor":
  {"solid":{"color":{"expr":{"Literal":{"Value":"'#2E7D32'"}}}}}}}]
```

`labels.labelPrecision` accepts `"auto"` or a `D`-suffixed integer.

**tableEx** — `grid`, `columnHeaders`, `values`, `total`.

**actionButton** — `icon`, `text`, `outline`. Navigation needs
`visualContainerObjects.visualLink`:

```json
"visualLink": [{"properties": {"show": {"expr":{"Literal":{"Value":"true"}}},
                               "type": {"expr":{"Literal":{"Value":"'PageNavigation'"}}},
                               "navigationSection": {"expr":{"Literal":{"Value":"'overview'"}}}}}]
```

**shape** — `shape` (`tileShape`, `rectangleRoundedCurve`), `rotation`
(`shapeAngle`), `fill` (`fillColor`, `transparency`).

## visualContainerObjects

Container-level styling: `background`, `border`, `dropShadow`, `padding`,
`visualLink`.

```json
"background": [{"properties": {"show": {"expr":{"Literal":{"Value":"true"}}},
                               "color": {"solid":{"color":{"expr":{"Literal":{"Value":"'#FFFFFF'"}}}}},
                               "transparency": {"expr":{"Literal":{"Value":"0D"}}}}}],
"border": [{"properties": {"show": {"expr":{"Literal":{"Value":"true"}}},
                           "color": {"solid":{"color":{"expr":{"Literal":{"Value":"'#E3E8EF'"}}}}},
                           "width": {"expr":{"Literal":{"Value":"1D"}}},
                           "radius": {"expr":{"Literal":{"Value":"8D"}}}}}]
```

Two per-visual-type traps:

- **textbox**: a `show` key inside `background` makes Power BI discard the
  colour and fall back to white. Omit it.
- **actionButton**: ignores `background` entirely and renders white regardless.
  Convey state via text colour and border width instead.

## Visual types seen in the wild

`textbox`, `image`, `cardVisual`, `shape`, `actionButton`, `clusteredBarChart`,
`clusteredColumnChart`, `stackedBarChart`, `lineChart`, `scatterChart`,
`pieChart`, `donutChart`, `tableEx`, `shapeMap`, `pageNavigator`,
`bookmarkNavigator`, `lineClusteredColumnComboChart`,
`hundredPercentStackedBarChart`, `multiRowCard`, `slicer`.

Type names come from each visual's internal ID, which is usually the PascalCase
name without spaces — but not always. When unsure, build one in Desktop and
read the `visualType` back.

## Schema versions

`$schema` is a versioned URL. `2.13.0` for visualContainer, `2.1.0` for page,
`3.3.0` for report, `1.1.0` for pagesMetadata were current in the files studied.
Desktop is tolerant of older versions. Bump only when Desktop rejects the file
and you have a newer sample to copy — never invent a version number.