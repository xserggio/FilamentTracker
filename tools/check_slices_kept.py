# -*- coding: utf-8 -*-
"""El laminado sobrevive a que Bambu Studio borre su fichero.

    py tools\\check_slices_kept.py

El caso: sale la tarjeta, te das cuenta de que tienes que poner el rollo nuevo
en el inventario, vas y lo pones, vuelves a buscar el laminado -- y Bambu ya ha
limpiado su carpeta. Lo que la app leyo tiene que seguir ahi.
"""
import json
import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slicer  # noqa: E402
from core import Store  # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("%-44s %-14s %s" % (label, got, "ok" if ok else "MAL, esperaba %s" % (want,)))


XML = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <object identify_id="1" name="soporte_kindle.stl" skipped="false" />
    <filament id="1" tray_info_idx="GFA01" type="PLA" color="#FFFFFF" \
used_m="26.07" used_g="81.52" nozzle_diameter="0.40" used_for_object="true"/>
  </plate>
</config>
"""
STUB = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header><header_item key="X-BBL-Client-Type" value="slicer"/></header>
</config>
"""

cache = tempfile.mkdtemp()
run = os.path.join(cache, "Sun_Aug_09", "14_52_26#10052#50", "Metadata")
os.makedirs(run)
plate = os.path.join(run, ".10052.1_config.3mf")
with zipfile.ZipFile(plate, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("Metadata/slice_info.config", XML)
    z.writestr("Metadata/project_settings.config",
               json.dumps({"filament_settings_id": ["Bambu PLA Matte @BBL A1"]}))

s = Store(os.path.join(tempfile.mkdtemp(), "check.db"))

# 1. La app lee la carpeta y se queda con lo que hay.
stamp_original = os.path.getmtime(plate)
leidos = slicer.latest_slices(limit=12, since=0, custom=cache)
check("la carpeta trae la placa", len(leidos), 1)
for sl in leidos:
    s.remember_slice(sl)
check("guardada", len(s.stored_slices()), 1)
check("con sus gramos", s.stored_slices()[0]["total"], 81.52)
check("y con su color", s.stored_slices()[0]["items"][0]["hex"], "#FFFFFF")

# 2. Bambu Studio limpia: se lleva el fichero de la placa y deja en su sitio el
#    proyecto, cuyo slice_info viene vacio. Es lo que paso de verdad el 9 de
#    agosto: quedo el .gcode y un .3mf sin plate ni filament.
os.remove(plate)
resto = os.path.join(cache, "Sun_Aug_09", "14_52_26#10052#50", ".3mf")
with zipfile.ZipFile(resto, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("Metadata/slice_info.config", STUB)

check("la carpeta ya no la tiene", len(slicer.latest_slices(limit=12, since=0, custom=cache)), 0)
check("la app si", len(s.stored_slices()), 1)
check("intacta", s.stored_slices()[0]["project"], "soporte kindle")
# y lo intacta que esta se demuestra releyendo: los gramos no salen de lo que
# se apunto entonces, salen del fichero que la app se guardo
check("releida del fichero propio", s.stored_slices()[0]["items"][0]["grams"], 81.52)

# 2b. Y la copia esta en el directorio de la app, con la fecha del original.
copia = s.stored_slices()[0]["copy_path"]
check("hay copia propia", bool(copia) and os.path.exists(copia), True)
check("en data/slices", os.path.dirname(copia), s.slice_archive())
check("conserva la fecha del original",
      round(os.path.getmtime(copia)), round(stamp_original))

# 3. Leerla dos veces no la duplica: la identidad es el contenido, no la ruta.
otra = os.path.join(cache, "Sun_Aug_09", "14_52_26#10052#50", "Metadata",
                    ".10052.9_config.3mf")
shutil.copy2(os.path.join(os.path.dirname(plate), os.pardir, ".3mf"), otra)
with zipfile.ZipFile(otra, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("Metadata/slice_info.config", XML)
    z.writestr("Metadata/project_settings.config",
               json.dumps({"filament_settings_id": ["Bambu PLA Matte @BBL A1"]}))
for sl in slicer.latest_slices(limit=12, since=0, custom=cache):
    s.remember_slice(sl)
check("la misma placa no se duplica", len(s.stored_slices()), 1)

# 4. Una vez apuntada, la lista lo dice.
fp = s.stored_slices()[0]["fingerprint"]
s.mark_slice_logged(fp)
check("marcada como apuntada", bool(s.stored_slices()[0]["logged_at"]), True)

# 5. No crece sin fin.
s.KEEP_SLICES = 3
for i in range(6):
    s.remember_slice({"fingerprint": "x%d" % i, "sliced_at": "2026-08-%02d" % (i + 1),
                      "project": "p%d" % i, "total": i, "items": []})
check("se queda con las ultimas", len(s.stored_slices(limit=99)), 3)
# y la poda no se lleva por delante la copia de una que sigue en la tabla
check("la copia de la que sigue, sigue", os.path.exists(copia), True)
check("no quedan copias huerfanas",
      len([f for f in os.listdir(s.slice_archive()) if f.endswith(".3mf")]), 1)


# --------------------------------------------- descartar sin fichero delante
# Antes se hacia stat del fichero para saber hasta donde se habia mirado. Si ya
# no estaba, el stat fallaba y se guardaba un cero -- que no significa "nada
# descartado", significa que toda la carpeta se vuelve a ofrecer.
import app as bridge  # noqa: E402

api = bridge.Api.__new__(bridge.Api)
api._store = s
api._window = None

s.set_settings({"slicer_seen": "1000"})
api.dismiss_slice({"path": os.path.join(cache, "no-existe.3mf"), "stamp": 0})
check("sin fichero y sin marca: no lo toca", s.get_settings().get("slicer_seen"), "1000")

api.dismiss_slice({"path": os.path.join(cache, "no-existe.3mf"), "stamp": 2500.5})
check("sin fichero pero con marca: la usa", s.get_settings().get("slicer_seen"), "2500.5")

print()
if fails:
    print("%d fallo(s): %s" % (len(fails), ", ".join(fails)))
    raise SystemExit(1)
print("todo correcto")
