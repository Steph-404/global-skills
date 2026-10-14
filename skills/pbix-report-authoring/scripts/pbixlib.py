"""pbixlib - dependency-free authoring for the Power BI *report layer* of a .pbix.

Why this library exists
----------------------
A .pbix is a ZIP container. Its parts split into two very different worlds:

  * the DATA MODEL  (DataModel, Metadata, Connections, DiagramLayout, Settings)
    - an Analysis Services backup, XPress9-compressed binary. Opaque.
  * the REPORT LAYER (Report/definition/**)
    - plain JSON. Fully readable and writable from Python.

So the only layer worth hand-authoring is the report layer, and the way to get
a valid data model without Power BI is to *inherit* one from a donor .pbix
(see references/datamodel.md). This library copies the model parts verbatim and
regenerates only the report layer.

Every shape emitted here was validated against a real .pbix that Power BI
Desktop accepted and rendered. Do not "tidy" the nested dicts - Power BI is
strict about the exact key set.

Requires: Python 3.8+. No third-party packages.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import zipfile

# --------------------------------------------------------------- schema URIs
# Bump these only if Desktop rejects the file and you have a newer example.
VC_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
             "definition/visualContainer/2.13.0/schema.json")
PAGE_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
               "definition/page/2.1.0/schema.json")
PAGES_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                "definition/pagesMetadata/1.1.0/schema.json")
REPORT_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                 "definition/report/3.3.0/schema.json")

# ------------------------------------------------------- aggregation codes
# These are the values that go in {"Aggregation": {"Function": <int>}}.
# ONLY these two are confirmed by inspecting shipped .pbix files:
#   0 = Sum     -> nativeQueryRef renders "Sum of <column>"
#   1 = Average -> nativeQueryRef renders as the bare column name
# One additional sample suggests 3 behaves like Min (a text column displayed as
# "First"), but n=1 is not proof. Anything else: confirm against a reference
# .pbix before trusting it (see references/visual-json.md).
AGG_SUM = 0
AGG_AVERAGE = 1
# AGG_MIN appears to be 3, but verify before use.
AGG_UNVERIFIED = (2, 3, 4, 5, 6)

# ----------------------------------------------------------------- defaults
CANVAS_W = 1280
CANVAS_H = 720

# Desktop clips roughly the top 40px of the canvas. Keep all content below it.
SAFE_TOP = 44


# ============================================================== value literals
# A property value is a DAX *expression* wrapped in {"expr": {...}}. Text values
# are single-quoted inside the string ("'left'"); numbers carry a type suffix
# (D = decimal/double, L = long/int64); booleans are bare.
#
# These four encodings were all observed in real files. Anything else is guesswork.


def lit(value: str) -> dict:
    """Raw literal passthrough. You supply the exact serialized DAX value.

    Examples: lit("'Left'"), lit("12D"), lit("13pt"), lit("true")
    """
    return {"expr": {"Literal": {"Value": value}}}


def txt(value: str) -> dict:
    """DAX text literal. The value is wrapped in single quotes."""
    return lit("'" + str(value).replace("'", "''") + "'")


def dbl(value: float) -> dict:
    """DAX decimal literal, e.g. dbl(1.5) -> "1.5D"."""
    text = repr(float(value))
    return lit(text + "D")


def num(value: int) -> dict:
    """DAX 64-bit integer literal, e.g. num(12) -> "12L"."""
    return lit(str(int(value)) + "L")


def flag(value: bool) -> dict:
    """DAX boolean literal."""
    return lit("true" if value else "false")


def font_size(points: float) -> dict:
    """Font sizes are bare number+unit literals, NOT quoted: "13pt"."""
    return lit(f"{points}pt")


def solid(hex_colour: str) -> dict:
    """Solid colour fill. Accepts '#RRGGBB' or a bare hex string."""
    return {"solid": {"color": txt(hex_colour)}}


# ============================================================ field references
def column(entity: str, prop: str) -> dict:
    """A bare column reference (no aggregation)."""
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}},
                       "Property": prop}}


def measure(entity: str, prop: str, function: int = AGG_SUM) -> dict:
    """An aggregated column reference - the usual 'Values' well contents."""
    return {"Aggregation": {"Expression": column(entity, prop),
                            "Function": function}}


def projection(field: dict, query_ref: str, native_query_ref: str,
               display_name: str = None) -> dict:
    """Package a field into a queryState projection.

    query_ref        Power Query-style, e.g. 'Sales.Amount' or 'Sum(Sales.Amount)'
    native_query_ref the label Power BI shows in the field well, e.g. 'Sum of Amount'
    """
    out = {"field": field, "queryRef": query_ref,
           "nativeQueryRef": native_query_ref}
    if display_name:
        out["displayName"] = display_name
    return out


def col_projection(entity: str, prop: str, display_name: str = None) -> dict:
    """Shorthand for an un-aggregated column projection."""
    return projection(column(entity, prop), f"{entity}.{prop}", prop, display_name)


_AGG_PREFIX = {AGG_SUM: "Sum", AGG_AVERAGE: "Average"}


def measure_projection(entity: str, prop: str, function: int = AGG_SUM,
                       display_name: str = None) -> dict:
    """Shorthand for an aggregated projection with the conventional refs filled in."""
    prefix = _AGG_PREFIX.get(function)
    if prefix is None:
        query_ref = native = prop
    else:
        query_ref = f"{prefix}({entity}.{prop})"
        # Sum reads "Sum of X"; Average shows the bare column name.
        native = f"Sum of {prop}" if function == AGG_SUM else prop
    return projection(measure(entity, prop, function), query_ref, native, display_name)


# ================================================================== containers
def position(x: float, y: float, w: float, h: float, z: float = 0) -> dict:
    """Geometry. z also drives tabOrder and paint order - higher is on top."""
    return {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}


def visual(name: str, visual_type: str, geom: dict, query: dict = None,
           objects: dict = None, sort: dict = None,
           visual_container_objects: dict = None) -> dict:
    """Assemble one visualContainer. This is the atom of the report layer.

    IMPORTANT - nesting. Power BI Desktop puts `drillFilterOtherVisuals` and
    `visualContainerObjects` INSIDE the `visual` object, not at the top level
    of the container. Placing them at the top level is tolerated on load but
    SILENTLY DISCARDED the next time Desktop saves the file, so the styling
    disappears. Verified against Desktop-authored files.
    """
    v = {"visualType": visual_type}
    if query:
        v["query"] = query
    if objects:
        v["objects"] = objects
    if visual_container_objects:
        v["visualContainerObjects"] = visual_container_objects
    v["drillFilterOtherVisuals"] = True
    return {"$schema": VC_SCHEMA, "name": name, "position": geom, "visual": v}


def white_panel(border_colour: str = "#E3E8EF", radius: int = 8,
                background: str = "#FFFFFF") -> dict:
    """The standard white card container used behind most visuals."""
    return {
        "background": [{"properties": {"show": flag(True),
                                       "color": solid(background)}}],
        "border": [{"properties": {"show": flag(True),
                                   "color": solid(border_colour),
                                   "radius": num(radius)}}],
    }


# ==================================================================== styling
def title_properties(text: str, size: float = 13, colour: str = "#1F3864",
                     font: str = "Segoe UI Semibold",
                     alignment: str = "'left'") -> list:
    """A visual's title bar."""
    return [{"properties": {
        "show": flag(True),
        "text": txt(text),
        "fontSize": font_size(size),
        "fontFamily": txt(font),
        "fontColor": solid(colour),
        "alignment": lit(alignment),
    }}]


# =========================================================== visual factories
def card(name: str, geom: dict, entity: str, prop: str, label: str,
         aggregation: int = AGG_SUM, accent: str = "#1F3864",
         value_colour: str = "#132A4D", value_size: float = 22,
         label_size: float = 11) -> dict:
    """A KPI card: coloured frame, rounded corners, soft shadow.

    Object keys are `title`, `value` and `label` - NOT `labels` /
    `categoryLabels`, which Desktop ignores and then drops on save. Card font
    sizes are D-suffixed decimals ("22D"), unlike visual titles which use
    point sizes ("13pt").

    Number formatting is deliberately NOT emitted here: no shipped .pbix
    exposed a card `labelFormat` property to copy. Control the display format
    with a DAX measure using FORMAT(), or set it once in Power BI Desktop.
    """
    return visual(
        name, "cardVisual", geom,
        query={"queryState": {"Data": {"projections": [
            {"field": measure(entity, prop, aggregation),
             "queryRef": prop, "nativeQueryRef": prop,
             "displayName": label}]}}},
        sort={"sort": [{"field": measure(entity, prop, aggregation),
                        "direction": "Descending"}],
              "isDefaultSort": True},
        objects={
            "title": title_properties(label, size=11, colour=accent),
            "value": [{"properties": {"fontSize": lit(f"{value_size}D"),
                                      "fontColor": solid(value_colour)},
                       "selector": {"id": "default"}}],
            "label": [{"properties": {"fontSize": lit(f"{label_size}D"),
                                      "fontColor": solid(accent)},
                       "selector": {"id": "default"}}],
        },
        visual_container_objects={
            "background": [{"properties": {"show": flag(True),
                                           "color": solid("#FFFFFF"),
                                           "transparency": lit("0D")}}],
            "border": [{"properties": {"show": flag(True),
                                       "color": solid(accent),
                                       "width": lit("12D"),
                                       "radius": lit("10D")}}],
            "dropShadow": [{"properties": {"show": flag(True),
                                           "color": solid("#1F3864"),
                                           "transparency": lit("88D"),
                                           "preset": txt("Outer"),
                                           "blur": lit("7D"),
                                           "distance": lit("2D"),
                                           "angle": lit("90D")}}],
            "padding": [{"properties": {"left": lit("10D")}}],
        },
    )


def bar_chart(name: str, geom: dict, entity: str, category: str, value: str,
              heading: str, colour: str = "#2E7D32",
              aggregation: int = AGG_SUM, label_decimals=None,
              horizontal: bool = True) -> dict:
    """Clustered bar/column chart with a single measure, sorted descending.

    A map tells you where; this tells you how much. Keep the pair together.
    """
    visual_type = "clusteredBarChart" if horizontal else "clusteredColumnChart"
    objects = {
        "title": title_properties(heading),
        "labels": [{"properties": dict(
            {"show": flag(True), "fontSize": font_size(8),
             "fontColor": solid("#595959")},
            **({"labelPrecision": lit(f"{label_decimals}D")}
               if label_decimals is not None
               else {"labelPrecision": lit("auto")}))}],
        "categoryAxis": [{"properties": {"show": flag(True),
                                         "fontSize": font_size(8),
                                         "concatenateLabels": flag(False)}}],
        "valueAxis": [{"properties": {"show": flag(False)}}],
        "legend": [{"properties": {"show": flag(False)}}],
        "grid": [{"properties": {"show": flag(False)}}],
        "dataPoint": [{"properties": {"defaultColor": solid(colour)}}],
    }
    return visual(
        name, visual_type, geom,
        query={"queryState": {
            "Category": {"projections": [col_projection(entity, category)]},
            "Y": {"projections": [measure_projection(entity, value, aggregation)]},
        }},
        sort={"sort": [{"field": measure(entity, value, aggregation),
                        "direction": "Descending"}],
              "isDefaultSort": True},
        objects=objects,
        visual_container_objects=white_panel(),
    )


def scatter_chart(name: str, geom: dict, entity: str, x_prop: str, y_prop: str,
                  detail: str, heading: str,
                  aggregation: int = AGG_AVERAGE) -> dict:
    """Scatter with a category in Details so each row becomes a labelled point."""
    return visual(
        name, "scatterChart", geom,
        query={"queryState": {
            "X": {"projections": [measure_projection(entity, x_prop, aggregation)]},
            "Y": {"projections": [measure_projection(entity, y_prop, aggregation)]},
            "Category": {"projections": [col_projection(entity, detail)]},
        }},
        objects={
            "title": title_properties(heading),
            "categoryAxis": [{"properties": {"show": flag(True),
                                             "fontSize": font_size(8)}}],
            "valueAxis": [{"properties": {"show": flag(True),
                                           "fontSize": font_size(8)}}],
        },
        visual_container_objects=white_panel(),
    )


def table(name: str, geom: dict, entity: str, columns: list,
          header_colour: str = "#1F3864") -> dict:
    """Detail table.

    columns: list of (column_name, display_label) for plain columns, or
             (column_name, display_label, aggregation) for measures.
    """
    projections = []
    for spec in columns:
        prop, label = spec[0], spec[1]
        if len(spec) > 2 and spec[2] is not None:
            projections.append(
                measure_projection(entity, prop, spec[2], display_name=label))
        else:
            projections.append(col_projection(entity, prop, display_name=label))
    return visual(
        name, "tableEx", geom,
        query={"queryState": {"Values": {"projections": projections}}},
        objects={
            "grid": [{"properties": {"textSize": font_size(9),
                                     "rowPadding": lit("2D"),
                                     "outlineColor": solid("#E0E0E0")}}],
            "columnHeaders": [{"properties": {
                "fontColor": solid("#FFFFFF"), "backColor": solid(header_colour),
                "fontSize": font_size(9), "bold": lit("true")}}],
            "values": [{"properties": {"backColor": solid("#FFFFFF"),
                                       "backColorSecondary": solid("#F7F9FC"),
                                       "fontSize": font_size(9)}}],
            "total": [{"properties": {"totals": flag(False)}}],
        },
        visual_container_objects=white_panel(),
    )


def text_run(text: str, size: float = 11, colour: str = "#1F3864",
             bold: bool = False, font: str = "Segoe UI") -> dict:
    """One styled run inside a textbox."""
    return {"value": text,
            "textStyle": {"fontWeight": "bold" if bold else "normal",
                          "fontFamily": font, "fontSize": f"{size}pt",
                          "color": colour}}


def textbox(name: str, geom: dict, runs: list,
            alignment: str = "left", container: dict = None) -> dict:
    """A textbox, optionally with a coloured panel behind it.

    GOTCHA: a 'show' key inside the background object makes Power BI discard the
    colour entirely and fall back to white. This function strips it for you.
    """
    out = visual(name, "textbox", geom,
                 objects={"general": [{"properties": {"paragraphs": [
                     {"textRuns": runs,
                      "horizontalTextAlignment": alignment}]}}]})
    if container:
        flat = {}
        for key, entries in container.items():
            props = dict(entries[0]["properties"])
            if key == "background":
                props.pop("show", None)
            flat[key] = [{"properties": props}]
        out["visual"]["visualContainerObjects"] = flat
    return out


def heading(name: str, geom: dict, text: str, size: float = 21,
            colour: str = "#1F3864", subtitle: str = None,
            subtitle_colour: str = "#595959") -> list:
    """Page heading (+ optional subheading), sized to the text-box clipping rule.

    GOTCHA: Power BI clips a textbox whose height is close to its font size.
    Budget ~2x the point size in pixels - a 21pt heading needs ~44px.
    """
    out = [textbox(name, geom, [text_run(text, size, colour, bold=True)])]
    if subtitle:
        sub_h = max(int(subtitle_size(subtitle) * 2), 20)
        out.append(textbox(
            name + "_sub",
            {"x": geom["x"], "y": geom["y"] + geom["height"] + 2,
             "width": geom.get("width", 1100), "height": sub_h, "z": geom["z"] + 1},
            [text_run(subtitle, 10, subtitle_colour)]))
    return out


def subtitle_size(_subtitle: str) -> int:
    return 12


def action_button(name: str, geom: dict, text: str, target_page: str,
                  active: bool = False) -> dict:
    """A page-navigation button.

    GOTCHA: actionButton ignores the container background colour and falls back
    to white. A 'selected' button drawn as white text on a dark fill is
    therefore invisible. Mark the active page with a darker text colour and a
    thicker border instead of a fill.
    """
    return visual(
        name, "actionButton", geom,
        objects={
            "icon": [{"properties": {"shapeType": txt("blank")},
                      "selector": {"id": "default"}}],
            "text": [{"properties": {"show": flag(True)}},
                     {"properties": {"text": txt(text),
                                     "fontFamily": txt("Segoe UI Semibold"),
                                     "fontColor": solid(
                                         "#132A4D" if active else "#1F3864"),
                                     "fontSize": lit("10D")},
                      "selector": {"id": "default"}}],
            "outline": [{"properties": {"show": flag(True)},
                         "selector": {"id": "default"}}],
        },
        visual_container_objects={
            "background": [{"properties": {"show": flag(True),
                                           "color": solid("#FFFFFF"),
                                           "transparency": lit("0D")}}],
            "border": [{"properties": {"show": flag(True),
                                       "color": solid(
                                           "#1F3864" if active else "#C7D2E0"),
                                       "width": lit("4D" if active else "1D"),
                                       "radius": lit("17D")}}],
        },
    )


def action_button_link(target_page: str) -> dict:
    """The visualContainerObjects.visualLink block that makes a button navigate."""
    return {"visualLink": [{"properties": {"show": flag(True),
                                           "type": txt("PageNavigation"),
                                           "navigationSection": txt(target_page)}}]}


def image(name: str, geom: dict, resource_name: str) -> dict:
    """An image visual bound to a registered resource (see resources_and_maps.md)."""
    return visual(
        name, "image", geom,
        objects={"image": [{"properties": {
            "sourceFile": {"image": {
                "name": txt(resource_name),
                "url": {"expr": {"ResourcePackageItem": {
                    "PackageName": "RegisteredResources",
                    "PackageType": 1,
                    "ItemName": resource_name}}},
                "scaling": txt("Fit")}},
            "backgroundEnabled": flag(False),
        }}],
            "border": [{"properties": {"show": flag(False)}}]})


def shape(name: str, geom: dict, fill: str = "#F2F2F2",
          shape_type: str = "'rectangleRounded'", curve: int = 15,
          rotation: int = 0) -> dict:
    """A plain decorative shape - useful for panels and section dividers."""
    return visual(
        name, "shape", geom,
        objects={
            "shape": [{"properties": {"tileShape": txt(shape_type),
                                      "rectangleRoundedCurve": num(curve)}}],
            "rotation": [{"properties": {"shapeAngle": num(rotation)}}],
            "fill": [{"properties": {"fillColor": solid(fill),
                                     "transparency": lit("0D")}}],
        })


def shape_map(name: str, geom: dict, entity: str, location_prop: str,
              value_prop: str, heading_text: str,
              resource_name: str, aggregation: int = AGG_SUM,
              min_colour: str = "#D64045", max_colour: str = "#FFFFFF") -> dict:
    """A Shape Map bound to a registered TopoJSON resource.

    `location_prop` must be a column whose text matches the boundary file's
    region names EXACTLY. Matching is case- and punctuation-sensitive.
    """
    field = measure(entity, value_prop, aggregation)
    fill_rule = {"expr": {"FillRule": {
        "Input": field,
        "FillRule": {"linearGradient2": {
            "min": {"color": lit(min_colour)},
            "max": {"color": lit(max_colour)},
            "nullColor": {"color": lit("#CCCCCC")}}}}}}
    return visual(
        name, "shapeMap", geom,
        query={"queryState": {
            "Category": {"projections": [col_projection(entity, location_prop)]},
            "Value": {"projections": [
                projection(field, f"Sum({entity}.{value_prop})",
                           f"Sum of {value_prop}")]},
        }},
        objects={"dataPoint": [{"properties": {"fill": fill_rule}}],
                 "title": title_properties(heading_text)},
        visual_container_objects=white_panel(),
    )


# ================================================================== assembly
def page(name: str, display_name: str, visuals: list, width: int = CANVAS_W,
         height: int = CANVAS_H) -> dict:
    """Return {"name":..., "displayName":..., "visuals": {id: visualContainer}}.

    Visual ids must be unique within the page; they become directory names.
    """
    seen = set()
    for v in visuals:
        if v["name"] in seen:
            raise ValueError(f"duplicate visual id '{v['name']}' on page '{name}'")
        seen.add(v["name"])
    return {"name": name, "displayName": display_name, "width": width,
            "height": height, "visuals": {v["name"]: v for v in visuals}}


def nav_bar(pages: list, active_index: int, y: int = SAFE_TOP, height: int = 30,
            width: int = 232, gap: int = 8, x_start: int = 20) -> list:
    """One navigation button per page, with the current page marked active.

    pages: list of (page_id, display_name)
    """
    out = []
    for i, (pid, label) in enumerate(pages):
        btn = action_button(f"nav{i}", position(x_start + i * (width + gap), y,
                                                width, height, 900 + i),
                            label, pid, active=(i == active_index))
        btn["visual"]["visualContainerObjects"].update(action_button_link(pid))
        out.append(btn)
    return out


def build_report(pages: list) -> dict:
    """pages: list of page() results. Returns the ordered page list for writing."""
    if not pages:
        raise ValueError("a report needs at least one page")
    order = [p["name"] for p in pages]
    if len(set(order)) != len(order):
        raise ValueError("page ids must be unique")
    return {"pageOrder": order, "activePageName": order[0]}


# --------------------------------------------------------------- the writer
class PbixWriter:
    """Rebuilds the report layer of a donor .pbix, preserving its data model.

    Usage:
        with PbixWriter("donor.pbix") as w:
            w.add_page(page_obj)
            w.add_resource("map.topo.json", topojson_bytes, "ShapeMap")
            w.add_resource("cover.jpg", jpeg_bytes, "Image")
            w.write("out.pbix")

    The writer copies DataModel, Metadata, Connections, DiagramLayout, Settings,
    Version and the base theme byte-for-byte. It deliberately DROPS
    SecurityBindings: Desktop will reject a signed file whose report layer was
    edited. Re-open and re-save in Desktop afterwards to re-sign.
    """

    def __init__(self, donor_path: str):
        if not os.path.isfile(donor_path):
            raise FileNotFoundError(f"donor .pbix not found: {donor_path}")
        self.donor = donor_path
        self.pages = []
        self.resources = []          # (filename, bytes, type)
        self._report_json = None

    # -- inputs -------------------------------------------------------------
    def donor_report_json(self) -> dict:
        with zipfile.ZipFile(self.donor) as z:
            return json.loads(z.read("Report/definition/report.json").decode("utf-8"))

    def donor_data_model_is_present(self) -> bool:
        with zipfile.ZipFile(self.donor) as z:
            return "DataModel" in z.namelist()

    # -- authoring ----------------------------------------------------------
    def add_page(self, page_obj: dict) -> "PbixWriter":
        self.pages.append(page_obj)
        return self

    def add_resource(self, filename: str, payload, resource_type: str) -> "PbixWriter":
        """resource_type is 'Image' or 'ShapeMap'."""
        if isinstance(payload, str):
            with open(payload, "rb") as fh:
                payload = fh.read()
        self.resources.append((filename, payload, resource_type))
        return self

    # -- output -------------------------------------------------------------
    def write(self, out_path: str) -> str:
        meta = build_report(self.pages)
        tmp = out_path + ".tmp"
        with zipfile.ZipFile(self.donor) as zin:
            report = json.loads(zin.read("Report/definition/report.json")
                                .decode("utf-8"))
            content_types = zin.read("[Content_Types].xml").decode("utf-8-sig")

            # Drop the signature: its [Content_Types].xml override has a matching
            # ContentType=""; leaving it behind orphans the override.
            content_types = re.sub(
                r'<Override PartName="/SecurityBindings"[^>]*/>', "", content_types)

            # Carry the donor's theme and settings, replace the resource list.
            items = [{"name": n, "path": n, "type": t}
                     for n, _, t in self.resources]
            packages = []
            if items:
                packages.append({"name": "RegisteredResources",
                                 "type": "RegisteredResources", "items": items})
            existing = report.get("resourcePackages") or []
            for pkg in existing:
                if pkg.get("type") == "RegisteredResources":
                    continue
                if pkg.get("name") == "RegisteredResources":
                    continue
                packages.append(pkg)
            if packages:
                report["resourcePackages"] = packages
            else:
                report.pop("resourcePackages", None)

            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    n = item.filename
                    # Replace wholesale: the old pages, the old registered
                    # resources, the signature.
                    if n.startswith("Report/definition/pages/"):
                        continue
                    if n.startswith("Report/definition/bookmarks"):
                        continue
                    if n.startswith("Report/StaticResources/RegisteredResources/"):
                        continue
                    if n == "SecurityBindings":
                        continue
                    if n == "[Content_Types].xml":
                        zout.writestr(item, content_types.encode("utf-8"))
                        continue
                    if n == "Report/definition/report.json":
                        zout.writestr(item, json.dumps(report).encode("utf-8"))
                        continue
                    # Passing the ZipInfo preserves compress_type - critical for
                    # DataModel, which MUST stay STORED.
                    zout.writestr(item, zin.read(n))

                for filename, payload, _t in self.resources:
                    zout.writestr(
                        f"Report/StaticResources/RegisteredResources/{filename}",
                        payload)

                zout.writestr("Report/definition/pages/pages.json",
                              json.dumps(dict(meta, **{"$schema": PAGES_SCHEMA})))
                for p in self.pages:
                    zout.writestr(
                        f"Report/definition/pages/{p['name']}/page.json",
                        json.dumps({"$schema": PAGE_SCHEMA, "name": p["name"],
                                    "displayName": p["displayName"],
                                    "displayOption": "FitToPage",
                                    "height": p["height"], "width": p["width"]}))
                    for vid, vc in p["visuals"].items():
                        zout.writestr(
                            f"Report/definition/pages/{p['name']}"
                            f"/visuals/{vid}/visual.json", json.dumps(vc))
        shutil.move(tmp, out_path)
        return out_path


def summarise(write_log: str) -> None:
    """No-op placeholder kept so callers have a stable hook for logging."""
    return None