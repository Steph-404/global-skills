#!/usr/bin/env python3
"""Inspect a .pbix container and describe what is inside it.

Run this FIRST on any donor or target file. It answers the questions you must
know before you can safely author a report layer:

  * Is this a real .pbix, and which parts does it contain?
  * Does it carry a data model (i.e. can it be used as a donor)?
  * Is it signed (SecurityBindings present)?
  * What report schema version does it target?
  * Which pages and visuals exist, and which visual types / entities are in use?

Usage:
    python pbix_inspect.py report.pbix              # human-readable summary
    python pbix_inspect.py report.pbix --json       # machine-readable
    python pbix_inspect.py report.pbix --entities   # every entity/column referenced

Requires: Python 3.8+. No third-party packages.
"""

import argparse
import collections
import json
import sys
import zipfile


def is_pbix(path: str) -> bool:
    """A .pbix is a ZIP whose first entry is a UTF-16LE 'Version' part."""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "Version" not in names:
                return False
            return z.read("Version").decode("utf-16-le", "replace").strip() != ""
    except zipfile.BadZipFile:
        return False


def read_version(z) -> str:
    try:
        return z.read("Version").decode("utf-16-le").strip()
    except KeyError:
        return "?"


def describe(path: str) -> dict:
    info = {"path": path, "size_bytes": 0, "is_pbix": False, "version": None,
            "signed": False, "has_data_model": False, "data_model_store": None,
            "report_schema_version": None, "pages": [], "visual_types": {},
            "entities": [], "part_count": 0, "registered_resources": []}
    try:
        import os
        info["size_bytes"] = os.path.getsize(path)
    except OSError:
        pass
    info["is_pbix"] = is_pbix(path)
    if not info["is_pbix"]:
        return info

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        info["part_count"] = len(names)
        info["version"] = read_version(z)
        info["signed"] = "SecurityBindings" in names
        info["has_data_model"] = "DataModel" in names
        if info["has_data_model"]:
            info["data_model_store"] = next(
                (i.compress_type == zipfile.ZIP_STORED
                 for i in z.infolist() if i.filename == "DataModel"), None)
        if "Report/definition/version.json" in names:
            try:
                info["report_schema_version"] = json.loads(
                    z.read("Report/definition/version.json").decode("utf-8")
                ).get("version")
            except (ValueError, KeyError):
                pass
        if "Report/definition/pages/pages.json" in names:
            meta = json.loads(
                z.read("Report/definition/pages/pages.json").decode("utf-8"))
            order = meta.get("pageOrder", [])
            for pid in order:
                base = f"Report/definition/pages/{pid}"
                pjson = {"page_id": pid, "display_name": pid, "visuals": {}}
                if f"{base}/page.json" in names:
                    try:
                        pj = json.loads(z.read(f"{base}/page.json").decode("utf-8"))
                        pjson["display_name"] = pj.get("displayName", pid)
                        pjson["width"] = pj.get("width")
                        pjson["height"] = pj.get("height")
                    except (ValueError, KeyError):
                        pass
                vtypes = collections.Counter()
                for n in names:
                    if n.startswith(f"{base}/visuals/") and n.endswith("visual.json"):
                        vid = n.split("/visuals/")[1].split("/")[0]
                        try:
                            v = json.loads(z.read(n).decode("utf-8"))
                            vt = (v.get("visual") or {}).get("visualType", "?")
                            vtypes[vt] += 1
                            pjson["visuals"][vid] = vt
                        except (ValueError, KeyError):
                            vtypes["<unparseable>"] += 1
                pjson["visual_type_counts"] = dict(vtypes)
                info["pages"].append(pjson)

        # resources and entities
        for n in names:
            if n.startswith("Report/StaticResources/RegisteredResources/"):
                info["registered_resources"].append(n.split("/")[-1])
        if "Report/definition/report.json" in names:
            try:
                rj = json.loads(
                    z.read("Report/definition/report.json").decode("utf-8"))
                for pkg in rj.get("resourcePackages", []):
                    for it in pkg.get("items", []):
                        if it.get("name") and it["name"] not in \
                                info["registered_resources"]:
                            info["registered_resources"].append(it["name"])
            except (ValueError, KeyError):
                pass

        seen_vt = collections.Counter()
        seen_entities = set()
        for n in names:
            if not n.endswith("visual.json"):
                continue
            try:
                d = json.loads(z.read(n).decode("utf-8"))
            except (ValueError, KeyError):
                continue
            seen_vt[(d.get("visual") or {}).get("visualType", "?")] += 1
            s = json.dumps(d)
            # crude but reliable for entity extraction
            import re
            for m in re.finditer(r'"SourceRef":\{"Entity":"([^"]+)"\}', s):
                seen_entities.add(m.group(1))
        info["visual_types"] = dict(seen_vt)
        info["entities"] = sorted(seen_entities)
    return info


def entities_of(path: str):
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not n.endswith("visual.json"):
                continue
            try:
                d = json.loads(z.read(n).decode("utf-8"))
            except (ValueError, KeyError):
                continue
            import re
            s = json.dumps(d)
            cols = collections.defaultdict(set)
            for m in re.finditer(
                    r'"SourceRef":\{"Entity":"([^"]+)"\}\},"Property":"([^"]+)"',
                    s):
                cols[m.group(1)].add(m.group(2))
            if cols:
                out[n] = {e: sorted(c) for e, c in cols.items()}
    return out


def print_human(info: dict) -> None:
    print(f"FILE   {info['path']}")
    print(f"SIZE   {info['size_bytes']:,} bytes")
    if not info["is_pbix"]:
        print("NOT A PBIX (not a readable zip with a Version part)")
        return
    print(f"FORMAT container version={info['version']}  "
          f"report schema={info['report_schema_version']}")
    print(f"MODEL  data_model={'yes' if info['has_data_model'] else 'NO'}"
          + ("  (STORED, uncompressed - correct)"
             if info["data_model_store"] else
             ("  (DEFLATED - unusual)" if info["has_data_model"] else "")))
    print(f"SIGN   {'signed (SecurityBindings present)' if info['signed'] else 'UNSIGNED'}")
    if info["registered_resources"]:
        print(f"RES    {', '.join(info['registered_resources'])}")
    if info["visual_types"]:
        print("TYPES  " + ", ".join(f"{k} x{v}" for k, v in
                                    sorted(info["visual_types"].items())))
    print(f"PAGES  {len(info['pages'])}")
    for p in info["pages"]:
        print(f"  - {p['page_id']} ({p['display_name']})  "
              f"{p.get('width')}x{p.get('height')}  "
              f"visuals={sum(p['visual_type_counts'].values())}  "
              f"{p['visual_type_counts']}")
    if info["entities"]:
        print("ENTITIES REFERENCED BY VISUALS: " + ", ".join(info["entities"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pbix")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--entities", action="store_true",
                    help="list every entity/column referenced per visual")
    args = ap.parse_args()
    info = describe(args.pbix)
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print_human(info)
    if args.entities and info["is_pbix"]:
        for vf, cols in entities_of(args.pbix).items():
            print("\n" + vf)
            for e, c in cols.items():
                print(f"   entity {e}: {', '.join(c)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())