# PBIP: the better target for from-scratch work

`PBIP` (Power BI Project) is the folder-based project format. It exists
because the legacy `.pbix` container is a binary blob with an undocumented
report layer and a signature that blocks programmatic edits.

**Reach for PBIP when building something new.** Use the `.pbix` approach in this
skill when you already have a donor `.pbix` to inherit a model from.

## Layout

```
Project/
├── Name.pbip                     shortcut to the report folder
├── Name.SemanticModel/
│   ├── definition/               TMDL — the model, plain text
│   │   ├── database.tmdl
│   │   ├── model.tmdl
│   │   ├── relationships.tmdl
│   │   └── tables/*.tmdl         one file per table
│   ├── definition.pbism          core settings + format version
│   └── diagramLayout.json        optional
└── Name.Report/
    ├── definition/               PBIR — the report, plain JSON
    └── definition.pbir           dataset reference
```

`definition.pbism` selects the model format — TMSL in `model.bim`, or TMDL in
`definition/`. Version `4.0`+ supports either; TMDL is the default.

## Why it is better

- **No signature.** Folder of text files, editable by anyone, anytime.
- **The report layer is publicly documented.** PBIR has published JSON
  schemas, so an agent can validate its output. The legacy `visual.json` format
  documented in this skill had to be reverse-engineered.
- **Git-friendly.** TMDL splits per table, so diffs and merges behave. A single
  `model.bim` does not.
- **Still needs Desktop** to compile a project into a distributable `.pbix`.

## The catch

Microsoft is explicit that conversion is Desktop-only:

> Can I convert PBIX into PBIP and vice-versa programmatically?
> **No.** You can only convert a PBIX into a PBIP and vice-versa using Power BI
> Desktop's File > Save as.

So PBIP moves the authoring to text, but the final compile still needs Desktop.
Practical loop:

1. Author the model and report as text (or TOM).
2. Open the folder in Desktop.
3. `Save as` → `.pbix` to distribute.
4. Keep the project folder in version control as the source of truth.

## Authoring the model in TMDL

A table is a text file. Measures, columns and the M partition expression all
live in it:

```tmdl
table sales =
    column revenue
        dataType: double
        formatString: #,0.00

    column region
        dataType: string

    measure 'Revenue ($M)' =
        VAR Total = SUM ( sales[revenue] )
        RETURN FORMAT ( DIVIDE ( Total, 1000000 ), "#,0.0" ) & "M"

    partition sales =
        mode: import
        source =
                let
                    Source = Csv.Document(File.Contents("data/sales.csv"),[Delimiter=",",Encoding=65001]),
                    ...
                in
                    Source
```

That `partition` block is the M expression that loads the data. Pointing it at
a CSV and letting Desktop refresh gives you a working model without a donor.

## Editing safely

Microsoft's warning, which matters: *"modifying the metadata outside of Power
BI Desktop may result in unexpected behavior or, in rare cases, lead to
inconsistencies within the model."*

Practically: let Desktop create the skeleton and the partition expression, then
edit. Hand-writing an M loader that produces the wrong types silently gives you
a model where every column is text.

## Editor support

The TMDL VS Code extension gives intellisense and validation against the same
schemas. Worth using if you are authoring by hand.

## Relationship to this skill

| | Legacy `.pbix` (this skill) | PBIP |
|---|---|---|
| Report layer format | undocumented `visual.json` | documented PBIR + JSON schema |
| Model authoring | inherit from donor | TMDL / TMSL text |
| Validation | structural heuristics | schema validation |
| Signature | must strip, then re-sign | none |
| Needs Desktop | to re-sign | to compile |
| Diffability | poor | good |

If you are starting a new dashboard, use PBIP and treat this skill's format
notes as background on what the compiled `.pbix` will contain.