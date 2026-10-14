#!/usr/bin/env python3
"""Build a .pbix report layer from a JSON spec, using a donor .pbix's data model.

This is the workhorse. An agent writes a spec describing pages and visuals; this
renders it into a valid .pbix. Nothing here is specific to any dataset - the
only project-specific input is the spec JSON and the donor file.

WHY A DONOR IS REQUIRED
-----------------------
The DataModel part of a .pbix is an XPress9-compressed Analysis Services
backup - opaque binary. It cannot be authored from Python. So you start from a
donor .pbix that already contains the table you want, and this script rewrites
only the report layer, copying the model parts byte-for-byte. See
references/datamodel.md for how to produce the donor.

SPEC FORMAT (see references/spec-format.md for the full reference)
-----------------------------------------------------------------
{
  "donor": "donor.pbix",
  "output": "out.pbix",
  "navigation": true,
  "resources": [
    {"file": "cover.jpg",  "name": "cover.jpg",  "type": "Image"},
    {"file": "shape.topo.json", "name": "shape.topo.json", "type": "ShapeMap"}
  ],
  "pages": [
    {"id": "overview", "title": "Overview", "visuals": [
      {"id": "kpi", "type": "card", "x": 20, "y": 156, "w": 303, "h": 100, "z": 10,
       "entity": "sales", "column": "revenue", "label": "Total revenue",
       "agg": "sum", "format": "#,0", "accent": "#1F3864"},
      {"id": "bar", "type": "bar", "x": 502, "y": 260, "w": 758, "h": 252, "z": 21,
       "entity": "sales", "category": "region", "value": "revenue",
       "heading": "Revenue by region", "colour": "#2E7D32"},
      {"id": "tbl", "type": "table", "x": 20, "y": 518, "w": 1240, "h": 146, "z": 30,
       "entity": "sales",
       "columns": [["region", "Region"], ["revenue", "Revenue", "sum"]]}
    ]}
  ]
}

Usage:
    python pbix_build.py spec.json
    python pbix_build.py spec.json --check-only

Requires: Python 3.8+. No third-party packages.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbixlib as P  # noqa: E402

AGG_MAP = {"sum": P.AGG_SUM, "avg": P.AGG_AVERAGE, "average": P.AGG_AVERAGE}


def agg_code(name) -> int:
    if name is None:
        return P.AGG_SUM
    if isinstance(name, int):
        return name
    key = str(name).lower()
    if key in AGG_MAP:
        return AGG_MAP[key]
    warnings.append(f"unknown agg '{name}'; defaulting to sum. Verified codes "
                    f"are sum=0 and average=1 only.")
    return P.AGG_SUM


warnings: list = []


def geom(v: dict) -> dict:
    return P.position(v.get("x", 0), v.get("y", 0), v.get("w", 100),
                      v.get("h", 100), v.get("z", 0))


def make_visual(v: dict) -> dict:
    t = v.get("type")
    g = geom(v)
    e = v.get("entity")
    agg = agg_code(v.get("agg"))

    if t == "card":
        return P.card(v["id"], g, e, v["column"], v.get("label", v["column"]),
                      aggregation=agg, accent=v.get("accent", "#1F3864"),
                      value_colour=v.get("value_colour", "#132A4D"),
                      value_size=v.get("value_size", 22),
                      label_size=v.get("label_size", 11))

    if t in ("bar", "column"):
        return P.bar_chart(v["id"], g, e, v["category"], v["value"],
                           v.get("heading", ""), colour=v.get("colour", "#2E7D32"),
                           aggregation=agg, label_decimals=v.get("decimals"),
                           horizontal=(t == "bar"))

    if t == "scatter":
        return P.scatter_chart(v["id"], g, e, v["x_prop"], v["y_prop"],
                               v["detail"], v.get("heading", ""), aggregation=agg)

    if t == "table":
        cols = [(c[0], c[1], agg_code(c[2]) if len(c) > 2 else None)
                for c in v["columns"]]
        return P.table(v["id"], g, e, cols)

    if t == "textbox":
        runs = [P.text_run(r.get("text", ""), r.get("size", 11),
                           r.get("colour", "#1F3864"), r.get("bold", False))
                for r in v.get("runs", [])]
        return P.textbox(v["id"], g, runs, alignment=v.get("align", "left"))

    if t == "heading":
        out = P.heading(v["id"], g, v.get("text", ""), v.get("size", 21),
                        v.get("colour", "#1F3864"), v.get("subtitle"))
        return out[0] if len(out) == 1 else out

    if t == "image":
        return P.image(v["id"], g, v["resource"])

    if t == "shape":
        return P.shape(v["id"], g, fill=v.get("fill", "#F2F2F2"))

    if t == "shapemap":
        return P.shape_map(v["id"], g, e, v["location"], v["value"],
                           v.get("heading", ""), v["resource"], aggregation=agg,
                           min_colour=v.get("min_colour", "#D64045"),
                           max_colour=v.get("max_colour", "#FFFFFF"))

    raise ValueError(f"unknown visual type '{t}' on visual '{v.get('id')}'")


def build_page(p: dict, nav_targets: list, nav_enabled: bool, index: int) -> dict:
    visuals = []
    for v in p.get("visuals", []):
        result = make_visual(v)
        visuals.extend(result if isinstance(result, list) else [result])
    if nav_enabled:
        visuals = P.nav_bar(nav_targets, index) + visuals
    return P.page(p["id"], p.get("title", p["id"]), visuals,
                  width=p.get("width", P.CANVAS_W),
                  height=p.get("height", P.CANVAS_H))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec")
    ap.add_argument("--check-only", action="store_true",
                    help="parse and render the spec without writing a file")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)

    donor = spec["donor"]
    out = spec.get("output", "out.pbix")
    nav_on = bool(spec.get("navigation", False))
    targets = [(p["id"], p.get("title", p["id"])) for p in spec["pages"]]

    pages = [build_page(p, targets, nav_on, i) for i, p in enumerate(spec["pages"])]

    if args.check_only:
        total = sum(len(p["visuals"]) for p in pages)
        print(f"spec OK: {len(pages)} page(s), {total} visual(s)")
        for p in pages:
            print(f"  {p['name']:<14} '{p['displayName']}'  "
                  f"{len(p['visuals'])} visual(s)")
        for w in warnings:
            print("  warn: " + w)
        return 0

    writer = P.PbixWriter(donor)
    for res in spec.get("resources", []):
        writer.add_resource(res["name"], res["file"], res.get("type", "Image"))
    for p in pages:
        writer.add_page(p)
    writer.write(out)

    print(f"wrote {out}")
    print(f"  pages={len(pages)}  visuals={sum(len(p['visuals']) for p in pages)}"
          f"  signed=False (re-save in Power BI Desktop to re-sign)")
    for w in warnings:
        print("  warn: " + w)
    print(f"\nNEXT: run  python pbix_validate.py \"{out}\"  then open "
          f"\"{out}\" in Power BI Desktop once and save, to regenerate the "
          f"signature.")
    return 0


if __name__ == "__main__":
    sys.exit(main())