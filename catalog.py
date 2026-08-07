"""Filament catalogue: manufacturer colours, temperatures and colour matching.

The data in catalog.json comes from SpoolmanDB (MIT, Copyright (c) 2024 Donkie)
and is regenerated with tools/build_catalog.py. It is bundled so the app never
needs network access.

Two jobs here:

* Look up what a manufacturer actually sells, so picking "Bambu Lab" + "PLA"
  offers their real colour list with the right hex codes instead of asking the
  user to eyeball one.
* Say which spool in the inventory is closest to a given colour, which is what
  turns a hex code from the slicer into "this is your Sakura pink".
"""

import json
import math
import os

_CATALOG = None


def _path():
    from core import APP_DIR

    return os.path.join(APP_DIR, "catalog.json")


def catalog() -> dict:
    """Loaded once and kept in memory; missing file is not fatal."""
    global _CATALOG
    if _CATALOG is None:
        try:
            with open(_path(), encoding="utf-8") as f:
                _CATALOG = json.load(f)
        except (OSError, ValueError):
            _CATALOG = {"makers": []}
    return _CATALOG


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


# ---------------------------------------------------------------- colour maths
#
# Nearest-colour has to be perceptual, not arithmetic: plain RGB distance calls
# a saturated red closer to black than to a slightly different red. So convert
# to CIE Lab and compare with CIEDE2000, the current standard for how different
# two colours actually look.


def rgb(hex_str: str):
    h = (hex_str or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def lab(hex_str: str):
    """sRGB hex -> CIE L*a*b* (D65), or None if the hex is unusable."""
    c = rgb(hex_str)
    if c is None:
        return None

    def linear(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(v) for v in c)
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750) / 1.00000
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(lab1, lab2) -> float:
    """CIEDE2000. Roughly: under 2 is indistinguishable, over 10 is a different
    colour to the eye."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    avg_l = (l1 + l2) / 2
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    avg_c = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(avg_c ** 7 / (avg_c ** 7 + 25 ** 7))) if avg_c else 0
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    avg_cp = (c1p + c2p) / 2

    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dhp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)

    if c1p * c2p == 0:
        avg_hp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        avg_hp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        avg_hp = (h1p + h2p + 360) / 2
    else:
        avg_hp = (h1p + h2p - 360) / 2

    t = (1 - 0.17 * math.cos(math.radians(avg_hp - 30))
         + 0.24 * math.cos(math.radians(2 * avg_hp))
         + 0.32 * math.cos(math.radians(3 * avg_hp + 6))
         - 0.20 * math.cos(math.radians(4 * avg_hp - 63)))
    sl = 1 + (0.015 * (avg_l - 50) ** 2) / math.sqrt(20 + (avg_l - 50) ** 2)
    sc = 1 + 0.045 * avg_cp
    sh = 1 + 0.015 * avg_cp * t
    rt = (-2 * math.sqrt(avg_cp ** 7 / (avg_cp ** 7 + 25 ** 7))
          * math.sin(math.radians(60 * math.exp(-(((avg_hp - 275) / 25) ** 2)))))
    return math.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dhp / sh) ** 2
                     + rt * (dcp / sc) * (dhp / sh))


def match_color(hex_str: str, filaments: list, material: str = None) -> list:
    """Rank the user's filaments by how close they look to `hex_str`.

    Same-material candidates always come first: a PLA that looks identical is a
    better guess than a PETG of exactly the same colour. Returns dicts with the
    filament and its `delta`, closest first.
    """
    target = lab(hex_str)
    if target is None:
        return []
    want = _norm(material)
    scored = []
    for f in filaments:
        if f.get("archived"):
            continue
        other = lab(f.get("hex"))
        if other is None:
            continue
        d = delta_e(target, other)
        same = bool(want) and _norm(f.get("material")) == want
        scored.append({"filament": f, "delta": round(d, 2), "same_material": same})
    scored.sort(key=lambda s: (not s["same_material"], s["delta"]))
    return scored


# ---------------------------------------------------------------- lookups


def makers() -> list:
    return [m["maker"] for m in catalog()["makers"]]


def _maker_items(brand: str):
    b = _norm(brand)
    if not b:
        return []
    for m in catalog()["makers"]:
        mb = _norm(m["maker"])
        if mb == b or (len(b) > 3 and (b in mb or mb in b)):
            return m["items"]
    return []


def colors(brand: str, material: str = None) -> list:
    """Colours this manufacturer sells, optionally narrowed to one material.

    Deduplicated by hex: the same "Jade White" shows up across several product
    lines and the user only needs to see it once.
    """
    want = _norm(material)
    seen, out = set(), []
    for item in _maker_items(brand):
        if want and _norm(item.get("m")) != want:
            continue
        for name, hex_ in item.get("c", []):
            key = hex_.upper()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "hex": key, "product": item.get("n", "")})
    out.sort(key=lambda c: c["name"].lower())
    return out


def specs(brand: str = None, material: str = None, name: str = "") -> dict:
    """Printing temperatures and density, with where the numbers came from.

    Matching never relies on the user typing a product name exactly. It walks
    from most to least specific and stops at the first hit:

      1. the manufacturer's product whose words appear in the filament name
         (a filament called "PLA - black matte" of Bambu Lab finds "PLA Matte")
      2. any product of that manufacturer with the same material
      3. the generic table for that material

    `source` says which of the three answered, so the interface can show it and
    the user can tell a measured value from a guess.
    """
    want_mat = _norm(material)
    words = set(w for w in _norm(name).replace("-", " ").split() if len(w) > 2)
    hay = _norm(name)

    best = None
    if brand:
        same_mat = [i for i in _maker_items(brand)
                    if not want_mat or _norm(i.get("m")) == want_mat]
        # a product whose distinctive word ("matte", "silk") is in the name
        for item in same_mat:
            label = _norm(item.get("n"))
            extra = label.replace(_norm(item.get("m")), "")
            if extra and len(extra) > 2 and (extra in hay or extra in words):
                best = (item, "product")
                break
        if best is None and same_mat:
            plain = sorted(same_mat, key=lambda i: len(i.get("n", "")))
            best = (plain[0], "brand")

    if best is not None:
        item, how = best
        temp = item.get("t") or []
        return {
            "extruder": temp[0] if temp else None,
            "bed": temp[1] if len(temp) > 1 and temp[1] else None,
            "density": item.get("d"),
            "source": how,
            "product": item.get("n", ""),
            "brand": brand or "",
        }

    gen = GENERIC.get((material or "").strip().upper()) or GENERIC.get(
        (material or "").strip().split()[0].upper() if material else "")
    if gen:
        return {"extruder": gen[0], "bed": gen[1], "density": gen[2],
                "source": "generic", "product": "", "brand": ""}
    return {"extruder": None, "bed": None, "density": None,
            "source": "none", "product": "", "brand": ""}


# Fallback when the manufacturer is unknown: typical ranges for each family,
# taken as the middle of what the material generally prints at. Always beaten
# by a real manufacturer figure.
#              extruder, bed, density
GENERIC = {
    "PLA":     (210, 60, 1.24),
    "PLA+":    (215, 60, 1.24),
    "PLA HS":  (230, 55, 1.24),
    "PLA SILK": (225, 60, 1.30),
    "PLA MATTE": (215, 60, 1.31),
    "PLA GLOW": (215, 60, 1.25),
    "PLA MARBLE": (215, 60, 1.30),
    "PLA-CF":  (220, 55, 1.23),
    "PLA WOOD": (200, 50, 1.21),
    "PLA METAL": (215, 60, 1.60),
    "PETG":    (240, 80, 1.27),
    "PETG-CF": (250, 80, 1.28),
    "PCTG":    (250, 80, 1.23),
    "PET":     (250, 80, 1.38),
    "ABS":     (250, 95, 1.04),
    "ABS-GF":  (260, 100, 1.12),
    "ASA":     (255, 95, 1.07),
    "HIPS":    (240, 100, 1.04),
    "TPU":     (225, 45, 1.21),
    "TPE":     (220, 45, 1.20),
    "PC":      (270, 100, 1.20),
    "PC-CF":   (280, 100, 1.19),
    "PP":      (230, 80, 0.90),
    "PPS-CF":  (320, 120, 1.43),
    "PEEK":    (400, 130, 1.30),
    "PEI":     (370, 140, 1.27),
    "PA":      (270, 60, 1.15),
    "PA-CF":   (280, 60, 1.18),
    "PA6":     (270, 60, 1.14),
    "PA12":    (250, 60, 1.02),
    "NYLON":   (260, 60, 1.14),
    "PVA":     (200, 60, 1.23),
    "BVOH":    (210, 60, 1.24),
    "SUPPORT": (220, 60, 1.24),
}
