# -*- coding: utf-8 -*-
"""Comprobaciones del lector de laminados.

    py tools\\check_slicer.py

Lo que se lee de un .3mf no se puede mirar a ojo, y equivocarse sale caro:
el perfil que sale de aqui es el termino que mas pesa al proponer una bobina.
"""
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slicer  # noqa: E402

# Cuatro huecos configurados, cada uno con una linea de producto distinta.
SLOTS = ["Bambu PLA Basic @BBL A1", "Bambu PETG HF @BBL A1",
         "Bambu PLA Silk @BBL A1", "Bambu PLA Matte @BBL A1"]

PLATE = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <object identify_id="1" name="pieza_de_prueba.stl" skipped="false" />
%s
  </plate>
</config>
"""
FILAMENT = ('    <filament%s tray_info_idx="GFA01" type="PLA" color="#FFFFFF" '
            'used_m="1.32" used_g="4.20" nozzle_diameter="0.40" '
            'used_for_object="true" used_for_support="false"/>')

TMP = tempfile.mkdtemp()
fails = []


def parse(name, ident):
    """Una placa de un solo filamento, con o sin el atributo id."""
    path = os.path.join(TMP, name + ".3mf")
    xml = PLATE % (FILAMENT % (' id="%d"' % ident if ident else ""))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/slice_info.config", xml)
        z.writestr("Metadata/project_settings.config",
                   json.dumps({"filament_settings_id": SLOTS}))
    return slicer.read_slice(path)["items"][0]


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("%-42s %-26s %s" % (label, got, "ok" if ok else "MAL, esperaba %r" % (want,)))


# El caso que fallaba: la placa usa solo el hueco 4, asi que es el unico
# filamento de la lista. Emparejar por posicion le colgaba el perfil del hueco 1
# -- y con "Basic" en vez de "Matte" la propuesta se iba a la bobina equivocada.
cuatro = parse("hueco4", 4)
check("hueco 4: numero de hueco", cuatro["slot"], 4)
check("hueco 4: perfil", cuatro["profile"], SLOTS[3])

uno = parse("hueco1", 1)
check("hueco 1: perfil", uno["profile"], SLOTS[0])

# Si Bambu dejase de escribir el atributo, se vuelve a la posicion: peor, pero
# no peor que antes.
sin = parse("sin_id", 0)
check("sin id: numero de hueco", sin["slot"], 0)
check("sin id: perfil", sin["profile"], SLOTS[0])

print()
if fails:
    print("%d fallo(s): %s" % (len(fails), ", ".join(fails)))
    raise SystemExit(1)
print("todo correcto")
