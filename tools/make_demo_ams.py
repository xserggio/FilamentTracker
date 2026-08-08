"""Loads the sample AMS so the screenshot has something in it.

    py tools/make_demo_ams.py data/filaments.db

Four slots and the external holder, picked to show the range: a spool that is
nearly gone, one that is fine, and one on the side.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Store  # noqa: E402

WANT = ["PLA - black", "PLA - red", "PETG - black", "PLA Silk - gold", "PLA - grey"]


def main(path):
    s = Store(path)
    by_name = {f["name"]: f["id"] for f in s.filaments()}
    slots = [(1, 1), (1, 2), (1, 3), (1, 4), (0, 1)]
    n = 0
    for (unit, slot), name in zip(slots, WANT):
        if name in by_name:
            s.set_ams_slot(unit, slot, by_name[name])
            n += 1
    print("%d huecos cargados" % n)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/filaments.db")
