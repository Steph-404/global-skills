# PBIX container format

A `.pbix` is an OPC/ZIP container. Reference reading below is from real files
written by Power BI Desktop (container `Version` 1.32, report schema 2.0.0).

## Part inventory

| Part | Encoding | Compression | Authorable? |
|---|---|---|---|
| `Version` | UTF-16LE (`1.32`) | deflate | no |
| `[Content_Types].xml` | UTF-8 **with BOM** | deflate | edit only |
| `DataModel` | XPress9 binary | **STORED** | **no** |
| `Metadata` | UTF-16LE JSON | deflate | no |
| `Settings` | UTF-16LE JSON | deflate | no |
| `DiagramLayout` | UTF-16LE JSON | deflate | no |
| `Connections` | UTF-8 JSON | deflate | no |
| `SecurityBindings` | binary signature | deflate | delete |
| `Report/definition/version.json` | UTF-8 JSON | deflate | yes |
| `Report/definition/report.json` | UTF-8 JSON | deflate | yes |
| `Report/definition/pages/pages.json` | UTF-8 JSON | deflate | yes |
| `Report/definition/pages/<pageId>/page.json` | UTF-8 JSON | deflate | yes |
| `Report/definition/pages/<pageId>/visuals/<visualId>/visual.json` | UTF-8 JSON | deflate | yes |
| `Report/StaticResources/SharedResources/BaseThemes/*.json` | UTF-8 JSON | deflate | yes (theme) |
| `Report/StaticResources/RegisteredResources/*` | any binary | deflate | yes |

`DataModel` must stay **STORED** (uncompressed). If you re-zip with a blanket
`ZIP_DEFLATED`, Power BI may fail to open the file. Always copy the original
`ZipInfo` so `compress_type` carries over:

```python
for item in zin.infolist():
    zout.writestr(item, zin.read(item.filename))  # ZipInfo preserves compress_type
```

## `[Content_Types].xml`

Declares content types per part. Note that Desktop writes **empty**
`ContentType=""` attributes for the PBIX-specific parts — this is normal:

```xml
<Override PartName="/DataModel" ContentType="" />
```

When you strip `SecurityBindings`, you must also remove its override, or the
override dangles:

```python
content_types = re.sub(r'<Override PartName="/SecurityBindings"[^>]*/>', "", content_types)
```

## `Report/definition/report.json`

Report-wide settings plus two resource packages.

- `themeCollection` — names the base theme. **Preserve this from the donor**;
  it is what makes Desktop-authored styling render as expected.
- `resourcePackages` — two kinds:
  - `RegisteredResources` — images and shape maps referenced by name from
    visuals. Files live under `Report/StaticResources/RegisteredResources/`.
  - `SharedResources` — e.g. the base theme under `BaseThemes/`.

When you add resources, declare each in a `RegisteredResources` package **and**
place the file in the matching zip folder, or the reference will dangle.

## Pages

`pages.json` sets the order and the initially active page:

```json
{ "pageOrder": ["overview", "detail"], "activePageName": "overview" }
```

Each `page.json`:

```json
{ "$schema": "...page/2.1.0/schema.json", "name": "overview",
  "displayName": "Overview", "displayOption": "FitToPage",
  "height": 720, "width": 1280 }
```

`pageOrder` must list every page directory, in order. A page directory not in
`pageOrder` is ignored (Desktop warns); a `pageOrder` entry with no directory is
an error.

## Visuals

One `visual.json` per visual, under `visuals/<visualId>/`. The `visualId`
becomes a directory name and must be unique within the page. Use semantic ids
(`kpi_revenue`, `map_main`, `nav_0`) — they survive editing and make diffs
readable, where hash ids do not.

Full anatomy in `visual-json.md`.

## Resources

`RegisteredResources` files are addressed from a visual via:

```json
"url": { "expr": { "ResourcePackageItem": {
  "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": "cover.jpg" }}}
```

`PackageType: 1` = RegisteredResources. The `ItemName` must exactly match both
the `name` in `report.json`'s `resourcePackages` and the filename in the zip.

## SecurityBindings

A signature over the report layer. Desktop refuses to open a PBIX whose report
layer changed after signing, reporting *"This file is corrupted or was created
by an unrecognized version of Power BI Desktop."*

Therefore: strip it when you programmatically edit the report layer, then
re-save through Desktop once to regenerate. Never strip it from a file you did
not create — you would break its authenticity.