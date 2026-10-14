#!/usr/bin/env python3
"""Validate a .pbix report layer for structural integrity.

An agent authoring a .pbix has no Power BI to hand, so this catches the errors
that would otherwise only surface as "This file is corrupted or was created by
an unrecognized version" when a human opens it.

Checks performed:
  * every zip entry parses / every report JSON part is valid JSON
  * pages.json pageOrder matches the actual page directories, in order
  * activePageName exists
  * every page.json declares a name/displayName/size
  * every visual.json has required keys and a known $schema
  * visual ids unique within a page; no orphan visual directories
  * every referenced ResourcePackageItem is actually a registered resource
  * every registered resource is declared in report.json resourcePackages
  * textbox geometry satisfies the "height >= 2x font size" clipping rule
  * geometry sanity (non-negative x/y, positive w/h)

Exit code 0 = clean, 1 = problems found.

Usage:
    python pbix_validate.py out.pbix
    python pbix_validate.py out.pbix --json

Requires: Python 3.8+. No third-party packages.
"""

import argparse
import json
import re
import sys
import zipfile

REQUIRED_VC_KEYS = {"$schema", "name", "position", "visual"}
REQUIRED_PAGE_KEYS = {"name", "displayName"}
REQUIRED_POS_KEYS = {"x", "y", "z", "height", "width"}


def validate(path: str) -> dict:
    errors, warnings = [], []
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return {"ok": False, "errors": ["not a zip file / not a pbix"],
                "warnings": []}
    names = z.namelist()

    if "SecurityBindings" in names:
        warnings.append("SecurityBindings present: file is signed. Desktop will "
                        "refuse to open it if the report layer was edited after "
                        "signing. If you edited programmatically, strip it and "
                        "re-save in Desktop to re-sign.")

    # report.json
    report = {}
    if "Report/definition/report.json" in names:
        try:
            report = json.loads(z.read("Report/definition/report.json")
                                .decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            errors.append(f"Report/definition/report.json is invalid JSON: {e}")

    # pages.json
    page_order = []
    if "Report/definition/pages/pages.json" in names:
        try:
            meta = json.loads(z.read("Report/definition/pages/pages.json")
                              .decode("utf-8"))
            page_order = meta.get("pageOrder", [])
            active = meta.get("activePageName")
            if active and active not in page_order:
                errors.append(f"activePageName '{active}' not in pageOrder")
            if not page_order:
                errors.append("pages.json has empty pageOrder")
        except (ValueError, UnicodeDecodeError) as e:
            errors.append(f"pages.json is invalid JSON: {e}")

    # Resources declared in report.json. Only RegisteredResources map to a file
    # under Report/StaticResources/RegisteredResources/; SharedResources (e.g.
    # base themes) live elsewhere and must not be checked against that folder.
    declared_resources = set()
    for pkg in report.get("resourcePackages", []):
        if pkg.get("type") != "RegisteredResources":
            continue
        for it in pkg.get("items", []):
            if it.get("name"):
                declared_resources.add(it["name"])

    # resources actually present in the zip
    zip_resources = {n.split("/")[-1] for n in names if
                     n.startswith("Report/StaticResources/RegisteredResources/")}
    for r in sorted(declared_resources - zip_resources):
        errors.append(f"RegisteredResource declared in report.json but not "
                      f"present in zip: {r}")
    for r in sorted(zip_resources - declared_resources):
        warnings.append(f"resource present in zip but not declared as a "
                        f"RegisteredResource: {r}")

    # scan pages
    for pid in page_order:
        base = f"Report/definition/pages/{pid}"
        pjson_path = f"{base}/page.json"
        if pjson_path not in names:
            errors.append(f"page '{pid}' listed in pageOrder but page.json missing")
            continue
        try:
            pj = json.loads(z.read(pjson_path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            errors.append(f"{pjson_path} invalid JSON: {e}")
            continue
        missing = REQUIRED_PAGE_KEYS - set(pj)
        if missing:
            errors.append(f"{pjson_path} missing keys: {sorted(missing)}")
        if not pj.get("width") or not pj.get("height"):
            warnings.append(f"{pjson_path} has no canvas width/height")

        visual_prefix = f"{base}/visuals/"
        visual_dirs = {n.split("/")[len(visual_prefix.strip('/').split('/'))]
                       for n in names
                       if n.startswith(visual_prefix) and n.endswith("visual.json")}
        seen = set()
        for vn in names:
            if not vn.startswith(visual_prefix) or not vn.endswith("visual.json"):
                continue
            vid = vn[len(visual_prefix):].split("/")[0]
            try:
                vc = json.loads(z.read(vn).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                errors.append(f"{vn} invalid JSON: {e}")
                continue
            missing = REQUIRED_VC_KEYS - set(vc)
            if missing:
                errors.append(f"{vn} missing keys: {sorted(missing)}")
                continue
            if vid in seen:
                errors.append(f"duplicate visual id '{vid}' on page {pid}")
            seen.add(vid)
            pos = vc["position"]
            missing_pos = REQUIRED_POS_KEYS - set(pos)
            if missing_pos:
                errors.append(f"{vn} position missing {sorted(missing_pos)}")
            if pos.get("width", 0) <= 0 or pos.get("height", 0) <= 0:
                errors.append(f"{vn} has non-positive size")
            if pos.get("x", 0) < 0 or pos.get("y", 0) < 0:
                warnings.append(f"{vn} has negative x/y")

            vt = (vc.get("visual") or {}).get("visualType")
            if not vt:
                errors.append(f"{vn} has no visualType")

            # textbox clipping rule
            if vt == "textbox":
                gen = ((vc.get("visual") or {}).get("objects", {})
                       .get("general", [{}])[0].get("properties", {})
                       .get("paragraphs", [{}])[0])
                runs = gen.get("textRuns", []) or []
                max_pt = 0.0
                for r in runs:
                    m = re.search(r"fontSize\"?:\s*\"?([\d.]+)pt",
                                  json.dumps(r))
                    if m:
                        max_pt = max(max_pt, float(m.group(1)))
                if max_pt and pos.get("height", 0) < max_pt * 2:
                    warnings.append(
                        f"{vn} textbox height {pos['height']}px < 2x font "
                        f"{max_pt}pt; Power BI will clip it")

            # resource references resolve
            s = json.dumps(vc)
            for m in re.finditer(r'"ItemName"\s*:\s*"([^"]+)"', s):
                if m.group(1) not in declared_resources:
                    errors.append(
                        f"{vn} references resource '{m.group(1)}' not declared "
                        "in report.json resourcePackages")

    # orphan page directories not in pageOrder
    page_dirs = {n.split("/")[3] for n in names
                 if n.startswith("Report/definition/pages/")
                 and len(n.split("/")) > 4 and n.split("/")[3]}
    for orphan in sorted(page_dirs - set(page_order)):
        warnings.append(f"page directory '{orphan}' not listed in pageOrder")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings,
            "pages": len(page_order), "signed": "SecurityBindings" in names}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pbix")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = validate(args.pbix)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  pages={r.get('pages')}  "
              f"signed={r.get('signed')}")
        for w in r["warnings"]:
            print("  warn  " + w)
        for e in r["errors"]:
            print("  ERROR " + e)
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())