# The data model, donors, and DAX

## Why this skill needs a donor

`DataModel` is an XPress9-compressed Analysis Services backup. Its first bytes
decode to:

```
This backup was created using XPress9 compression.
```

There is no supported way to author it from Python. Any approach that claims
otherwise either shells out to Power BI, uses Tabular Editor, or is writing a
TOML/TMSL model that Desktop must then import.

So: **every .pbix you build starts from an existing one.**

## Building the donor

In Power BI Desktop, once:

1. `Home → Get data → Text/CSV`, pick your file.
2. Fix column types in the query editor. Text columns silently imported as text
   are the most common cause of a broken dashboard — fix now.
3. Set a useful table name. Your spec's `entity` values must match it.
4. `File → Save as`.

One flat table is enough. Relationships, measures and hierarchies can be added
later in Desktop if needed.

Verify the donor before relying on it:

```bash
python scripts/pbix_inspect.py donor.pbix
```

You want `MODEL data_model=yes (STORED, uncompressed - correct)`. If it says
`NO`, the file is a report template with no data — not usable.

## What gets inherited

The builder copies these byte-for-byte, verified by SHA-256:

| Part | Inherited | Editable by script |
|---|---|---|
| `DataModel` | yes, byte-identical | no |
| `Metadata` | yes, byte-identical | no |
| `Connections` | yes, byte-identical | no |
| `DiagramLayout` | yes, byte-identical | no |
| `Settings` | yes, byte-identical | no |
| `Version` | yes, byte-identical | no |
| Base theme JSON | yes, byte-identical | yes |
| `Report/definition/**` | **replaced** | yes |

Inheritance is exact, which is the whole point: you cannot corrupt a model you
cannot parse.

## Renaming the entity

The spec's `entity` must equal the model table name. To avoid guessing, list
what the donor's visuals already reference:

```bash
python scripts/pbix_inspect.py donor.pbix --entities
```

If the donor has no visuals, open it in Desktop, click the table, and read the
name in the Data pane.

## Measures and number formatting

Card number formatting is best done in the model, not the visual. There is no
verified `labelFormat` property for cards — emitting a guessed one does nothing.

Create a measure in Desktop (`Model view → New measure`) that formats itself:

```DAX
Revenue ($M) =
VAR Total = SUM ( sales[revenue] )
RETURN FORMAT ( DIVIDE ( Total, 1000000 ), "#,0.0" ) & "M"
```

Then point the card at the measure. Because the formatting lives in the model,
it survives every theme change and every Desktop normalisation.

## Relationships

If the donor has more than one table, the spec can bind visuals to any of them
as long as the relationship exists in the model. Relationships are set up in
Desktop's Model view, not by this skill.

A common pattern: a wide summary table for cards and charts, plus a long fact
table for drill-through. Relate them on the key, single-direction from summary
to fact.

## Naming that survives

Table and column names become `Entity` and `Property` strings in every visual
you write. Names with spaces, slashes or punctuation work but make
`queryRef` strings awkward. Prefer `snake_case` or `PascalCase` without spaces
for anything the dashboard references.

Beware characters that need escaping in DAX: `'` in a name doubles, `[]` wraps
a column reference.

## Lat/long scatter plots

A geographic scatter needs real numeric longitude/latitude columns in the
model. Without them Power BI reports:

> This aggregate is not supported for the x-axis field

regardless of the summarisation chosen. There is no report-layer workaround —
add numeric `Longitude` / `Latitude` columns in Desktop and bind them to the
scatter's X and Y.

## When the model itself must change

This skill inherits models; it does not build them. If the donor lacks the
table you need:

1. **Add the table in Desktop**, save, then use that file as the donor. Simplest.
2. **Author the model as PBIP/TMDL** — plain-text `.tmdl` files, no donor
   needed. See `pbip.md`. Desktop still compiles it to a `.pbix` at the end.
3. **Tabular Editor or the TOM library** — both scriptable, both automatable.

Option 2 is usually the right one for a genuinely new dataset.

There is one thing that is genuinely not worth doing: hand-synthesising the
`DataModel` bytes. You would produce a file Desktop cannot open, and the
failure mode is a generic "file is corrupted" message that gives no clue what
went wrong.