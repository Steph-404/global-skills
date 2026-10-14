# Troubleshooting

## File-level

| Symptom | Cause | Fix |
|---|---|---|
| "This file is corrupted or was created by an unrecognized version of Power BI Desktop" | `SecurityBindings` signature present after the report layer was edited | Builder strips it. If you edited by hand, remove the part **and** its `[Content_Types].xml` override |
| `PermissionError` / `WinError 5` on write | Power BI Desktop has the file open | Close Desktop first; it holds an exclusive lock |
| Desktop opens the file then re-saves with no styling | `visualContainerObjects` was at the top level instead of inside `visual` | Nest it; Desktop silently discards the misplaced form |
| File opens but every visual is blank | entity or column names do not match the model | `pbix_inspect.py donor.pbix --entities` and compare exactly |
| Image or map renders blank | resource not declared in `report.json`, or name mismatch | All three names must agree; run `pbix_validate.py` |
| `DataModel` unreadable after re-zip | whole archive rewritten with `ZIP_DEFLATED` | Copy `ZipInfo` so `DataModel` stays STORED |
| Validator reports orphan page directory | a page folder exists that `pages.json` does not list | Add it to `pageOrder` or remove the folder |

## Visual-level

| Symptom | Cause | Fix |
|---|---|---|
| Text renders as a blank sliver | textbox height too small for the font | height ≥ 2× the point size; a 21 pt heading needs ~44 px |
| Page title missing entirely | textbox above `y = 40` | Desktop clips the top of the canvas; start content at `y = 44` |
| Card shows no number | bound to a text column | Fix the column type in Desktop and re-save the donor |
| Card shows `4.76E+07` | column is text, or default scientific format | Fix the type; then use a `FORMAT()` measure |
| Card shows `1,498%` | value already a percentage, multiplied again | Do not multiply; format with `0.0"%"` as text |
| Card styling ignored | wrong object keys | Use `title`, `value`, `label` — not `labels`/`categoryLabels` |
| Card font size ignored | used `"22pt"` instead of `"22D"` | Card `value`/`label` sizes are D-suffixed decimals |
| Nav "active" button invisible | `actionButton` ignores its background colour | Mark state with text colour and border width |
| Textbox background always white | a `show` key inside `background` | Remove `show` for textboxes |
| Chart renders in scientific notation | no number format applied | `labels.labelPrecision`, or a `FORMAT()` measure |
| Value axis or gridlines showing unexpectedly | defaults not overridden | Set `valueAxis.show` / `grid.show` to `false` |

## Map

| Symptom | Cause | Fix |
|---|---|---|
| Regions render grey | name did not match the boundary file | Build a lookup column and bind that; failure is silent |
| Every region grey | the whole location column mismatches | Compare against the boundary file's names, case-sensitively |
| Map visual disabled / asks to sign in | it is the Bing `map` visual | Use `shapeMap`, which is offline |
| Map colours look right but legend is wrong | `fillRule.Input` still points at a donor's measure | Point `Input` at your own measure |
| Scatter shows *"This aggregate is not supported for the x-axis field"* | no numeric longitude/latitude in the model | Add real lat/long columns in Desktop; no report-layer fix exists |

## Validator warnings

| Warning | Meaning |
|---|---|
| `SecurityBindings present` | file is signed; Desktop will refuse edits made after signing |
| `resource present in zip but not declared` | an unused registered resource — harmless, remove for cleanliness |
| `textbox height < 2x font` | will clip on render |
| `page directory not listed in pageOrder` | Desktop will ignore that page |
| `negative x/y` | off-canvas; usually means a typo in the spec |

## When the validator passes but Desktop still complains

Structural validity is necessary, not sufficient. The validator checks JSON
shape, ordering, resource references and geometry — it cannot evaluate DAX or
confirm your entity names exist. If Desktop still rejects a validated file:

1. Confirm the donor has a `DataModel` (`pbix_inspect.py`).
2. Confirm `DataModel` is STORED in the output.
3. Confirm the `report.json` `themeCollection` survived.
4. Compare a generated visual's JSON side-by-side with a Desktop-authored one
   for the same visual type — `visual-json.md` documents the shapes, and
   Desktop's normalisation on save is the best available spec.

The fastest ground truth is always: build one visual of the type in Desktop,
save, and read the JSON back.