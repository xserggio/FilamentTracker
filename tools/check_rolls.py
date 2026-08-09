# -*- coding: utf-8 -*-
"""Comprobaciones del descuadre y de la correccion por bascula.

    py tools\\check_rolls.py

El caso es el de un rollo real: mil gramos nominales, 1075.18 apuntados desde
que se abrio, y una bascula que dice que quedan cien.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import Store  # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("%-40s %-12s %s" % (label, got, "ok" if ok else "MAL, esperaba %s" % (want,)))


s = Store(os.path.join(tempfile.mkdtemp(), "check.db"))
fid = s.add_filament({"name": "PLA - Black", "material": "PLA", "hex": "#1c1c1e",
                      "roll_weight": 1000, "price": 10, "roll_opened": "2026-07-21"})
s.save_print({"date": "2026-07-25", "project": "de todo", "notes": "", "failed": 0,
              "items": [{"filament_id": fid, "grams": 1075.18}]})


def fil():
    return next(x for x in s.filaments() if x["id"] == fid)


def coste():
    return round(list(s.print_costs().values())[0], 2)


# Antes de pesar: el libro esta en negativo, y eso no es "vacio" -- hay plastico
# en la bobina y las cuentas son las que estan mal.
check("descuadre visto", fil()["mismatch"], True)
check("cuanto se pasa", round(fil()["over"], 2), 75.18)
check("restante sin inventarse nada", fil()["remaining"], 0.0)
check("coste con el peso de la etiqueta", coste(), 10.75)

s.adjust_roll(fid, 100)
r = s.roll_history(fid)[0]

check("restante tras pesar", round(fil()["remaining"], 1), 100.0)
check("descuadre resuelto", fil()["mismatch"], False)
check("correccion guardada", round(r["adjust"], 2), 175.18)
check("y con su fecha", bool(r["adjusted_at"]), True)
check("el peso nominal no se toca", r["weight"], 1000.0)
# Diez euros repartidos entre 1175.18 g y no entre 1000: cada impresion de este
# rollo estaba cargada un 15 % de mas.
check("coste sobre lo que llevaba", coste(), round(10 / 1175.18 * 1075.18, 2))
check("precio por kg, igual de corregido",
      round(fil()["price_per_g"] * 1000, 2), round(10 / 1175.18 * 1000, 2))

# El otro camino: la bobina se cambio y no se dijo. Abrir el rollo nuevo con la
# fecha del cambio mueve lo impreso desde entonces al rollo nuevo, y es lo que
# deshace el descuadre sin inventarse gramos.
s2 = Store(os.path.join(tempfile.mkdtemp(), "check2.db"))
f2 = s2.add_filament({"name": "PLA - Black", "material": "PLA", "hex": "#1c1c1e",
                      "roll_weight": 1000, "price": 10, "roll_opened": "2026-07-21"})
s2.save_print({"date": "2026-07-25", "project": "antes", "notes": "", "failed": 0,
               "items": [{"filament_id": f2, "grams": 800}]})
s2.save_print({"date": "2026-08-05", "project": "despues", "notes": "", "failed": 0,
               "items": [{"filament_id": f2, "grams": 400}]})
antes = next(x for x in s2.filaments() if x["id"] == f2)
check("descuadre antes de arreglarlo", antes["mismatch"], True)

s2.new_roll(f2, opened="2026-08-01", weight=1000)
ahora = next(x for x in s2.filaments() if x["id"] == f2)
check("resuelto abriendo el rollo nuevo", ahora["mismatch"], False)
check("resta solo lo de despues", round(ahora["remaining"], 1), 600.0)
check("sin correccion inventada", s2.roll_history(f2)[0]["adjust"], 0.0)

print()
if fails:
    print("%d fallo(s): %s" % (len(fails), ", ".join(fails)))
    raise SystemExit(1)
print("todo correcto")
