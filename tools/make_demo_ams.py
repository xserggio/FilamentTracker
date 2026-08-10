"""Loads the sample AMS so the screenshot has something in it.

    py tools/make_demo_ams.py data/filaments.db

Four slots and the external holder, picked to show the range: a spool that is
nearly gone, one that is fine, and one on the side.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Store  # noqa: E402

# El hueco 1 lleva el rojo del laminado de ejemplo y el 2 no lleva el azul:
# asi la captura ensena las dos caras, una fila resuelta por el hueco con el
# color de acuerdo y otra en la que el hueco contesta y el color discrepa.
WANT = ["PLA - red", "PLA - grey", "PETG - black", "PLA Silk - gold", "PLA - black"]


def main(path):
    s = Store(path)
    # The sample owns one of each, because the two are drawn differently and a
    # screenshot of only one says nothing about the other.
    for unit, kind, name in ((1, "lite", "A1"), (2, "ams", "P1S")):
        if not any(u["unit"] == unit for u in s.ams_units()):
            s.add_ams_unit(kind, name)
        else:
            s.save_ams_unit(unit, kind, name)
    by_name = {f["name"]: f["id"] for f in s.filaments()}
    slots = [(1, 1), (1, 2), (1, 3), (1, 4), (2, 1)]
    n = 0
    for (unit, slot), name in zip(slots, WANT):
        if name in by_name:
            s.set_ams_slot(unit, slot, by_name[name])
            n += 1
    print("%d huecos cargados" % n)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/filaments.db")
