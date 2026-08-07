"""Builds catalog.json from SpoolmanDB.

    py tools/build_catalog.py

Downloads the community filament database and boils it down to what this app
needs: per manufacturer and product, the printing temperatures, the density and
the real colour list with its hex codes.

Source: https://github.com/Donkie/SpoolmanDB (MIT, Copyright (c) 2024 Donkie).
Re-run it now and then to pick up new products; the result is committed so the
app never needs network access.
"""

import io
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = "https://api.github.com/repos/Donkie/SpoolmanDB/contents/filaments"
RAW = "https://raw.githubusercontent.com/Donkie/SpoolmanDB/master/filaments/"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FilamentTracker"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    names = [f["name"] for f in json.loads(fetch(INDEX)) if f["name"].endswith(".json")]
    print("%d manufacturer files" % len(names))

    makers = []
    colours = products = 0
    for i, fn in enumerate(sorted(names), 1):
        try:
            d = json.loads(fetch(RAW + fn))
        except Exception as e:                       # a single bad file is not fatal
            print("   skipped %s (%s)" % (fn, e))
            continue

        maker = (d.get("manufacturer") or fn[:-5]).strip()
        items = []
        for f in d.get("filaments", []):
            name = (f.get("name") or "").replace("{color_name}", "").strip()
            cols = [
                [c["name"].strip(), "#" + c["hex"].lstrip("#").upper()]
                for c in f.get("colors", [])
                if c.get("name") and c.get("hex")
            ]
            item = {
                "n": name or (f.get("material") or ""),
                "m": f.get("material") or "",
                "c": cols,
            }
            if f.get("extruder_temp"):
                item["t"] = [int(f["extruder_temp"]), int(f.get("bed_temp") or 0)]
            if f.get("density"):
                item["d"] = round(float(f["density"]), 3)
            if item["m"]:
                items.append(item)
                products += 1
                colours += len(cols)
        if items:
            makers.append({"maker": maker, "items": items})
        sys.stdout.write("\r   %d/%d  %s        " % (i, len(names), maker[:24]))
        sys.stdout.flush()

    out = {
        "source": "https://github.com/Donkie/SpoolmanDB",
        "license": "MIT, Copyright (c) 2024 Donkie",
        "makers": sorted(makers, key=lambda m: m["maker"].lower()),
    }
    path = os.path.join(ROOT, "catalog.json")
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    )
    size = os.path.getsize(path) / 1024
    print("\n%d manufacturers, %d products, %d colours -> catalog.json (%.0f KB)"
          % (len(makers), products, colours, size))


if __name__ == "__main__":
    main()
