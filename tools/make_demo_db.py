"""Builds a sample database for the README screenshots.

    py tools/make_demo_db.py data/filaments.db

Touches no real data: it writes to the given path, deleting it first.
"""

import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Store  # noqa: E402

TODAY = date.today()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731

# material, colour, hex, brand, spool type, spares, days since opened
FILAMENTS = [
    ("PLA",     "black",            "#1c1c1e", "Bambu Lab", "plastic",   2, 34),
    ("PLA",     "white",            "#f4f4f2", "Bambu Lab", "plastic",   1, 21),
    ("PLA",     "grey",             "#8a8f96", "eSUN",      "cardboard", 0, 48),
    ("PLA",     "red",              "#d62828", "Sunlu",     "plastic",   1, 12),
    ("PLA",     "blue",             "#1f5fd0", "eSUN",      "cardboard", 0,  9),
    ("PLA",     "yellow",           "#f2c14e", "Sunlu",     "plastic",   0, 55),
    ("PLA",     "sakura pink matte","#f4b9c7", "Bambu Lab", "plastic",   0,  6),
    ("PLA",     "olive green matte","#6b7a3a", "Polymaker", "cardboard", 1, 18),
    ("PLA Silk","gold",             "#d4af37", "Overture",  "cardboard", 0, 27),
    ("PETG",    "black",            "#1c1c1e", "Prusament", "plastic",   1, 41),
    ("PETG",    "transparent",      "#cfd6e0", "eSUN",      "plastic",   0, 15),
    ("TPU",     "orange",           "#e8722c", "Sunlu",     "plastic",   0, 11),
    ("ABS",     "natural",          "#e3ddd0", "Elegoo",    "cardboard", 0, 30),
]

# project, url, failed
PROJECTS = [
    ("Gridfinity 5x5 bins",      "https://gridfinity.xyz", 0),
    ("Gridfinity baseplate",     "", 0),
    ("Desk cable clips",         "", 0),
    ("Headphone stand",          "", 0),
    ("Planter pot",              "", 0),
    ("Phone dock",               "", 0),
    ("Drawer organiser",         "", 0),
    ("Filament swatch",          "", 0),
    ("Benchy",                   "", 0),
    ("Camera mount",             "", 0),
    ("Wall hook x4",             "", 0),
    ("Spool holder",             "", 0),
    ("Toolbox insert",           "", 0),
    ("Keycap set",               "", 0),
    ("Lamp shade",               "", 1),
    ("Vase mode test",           "", 0),
    ("Hinged box",               "", 0),
    ("Cookie cutter",            "", 0),
    ("Tablet stand",             "", 1),
    ("Door stopper",             "", 0),
    ("Pen holder",               "", 0),
    ("Fan duct",                 "", 0),
    ("Bracket v2",               "", 0),
    ("Coaster set",              "", 0),
]


def main(path):
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    s = Store(path)
    rnd = random.Random(20260807)   # fixed seed: reproducible screenshots

    ids = []
    for material, color, hexv, brand, stype, spares, days in FILAMENTS:
        fid = s.add_filament({
            "material": material, "color": color, "hex": hexv, "brand": brand,
            "spool_type": stype, "stock": spares, "roll_weight": 1000,
            "roll_opened": D(days),
        })
        ids.append(fid)

    # the PETG is overdue for drying; the grey PLA was dried recently
    s.mark_dried(ids[2], D(5))

    # Everyday colours (black and white) burn through far faster than a clear
    # PETG: the sample has to show spools in trouble, not all of them at 95%.
    weights = [15, 12, 10, 6, 6, 3, 4, 4, 3, 5, 2, 2, 2]

    for i, (project, url, failed) in enumerate(PROJECTS * 3):
        if i >= 62:
            break
        day = D(rnd.randint(0, 44))
        n_colors = rnd.choices([1, 1, 1, 2, 2, 3], k=1)[0]
        chosen = []
        while len(chosen) < n_colors:
            pick = rnd.choices(ids, weights=weights, k=1)[0]
            if pick not in chosen:
                chosen.append(pick)
        items = []
        for j, fid in enumerate(chosen):
            grams = rnd.choice([2.4, 9.5, 27, 63, 88, 120, 155, 190, 240])
            if j > 0:                      # secondary colours are just accents
                grams = round(grams * rnd.uniform(0.04, 0.22), 2)
            items.append({"filament_id": fid, "grams": round(grams, 2)})
        s.save_print({
            "date": day, "project": project, "url": url,
            "failed": failed, "notes": "", "items": items,
        })

    fils = {f["name"]: f for f in s.filaments()}
    print(f"{len(fils)} filamentos, {len(s.prints())} impresiones")
    for name in ("PLA - black", "PETG - black", "PLA - grey"):
        f = fils[name]
        print(f"   {name:22} {f['remaining']:7.1f} g ({f['pct']:5.1f}%)  "
              f"{f['roll_brand']:10} {f['roll_type']:9} secar={f['needs_dry']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/filaments.db")
