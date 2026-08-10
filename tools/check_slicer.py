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


# --------------------------------------------------------------- el AMS
# Un verde brillante en pantalla y un verde oliva en el cajon: por color solo,
# gana el que se le parece. Lo que decide es que el oliva esta en el hueco.
SPOOLS = [
    {"id": 1, "name": "PLA Matte - Olive green", "material": "PLA Matte",
     "hex": "#6b7a3a"},
    {"id": 2, "name": "PLA Matte - green", "material": "PLA Matte",
     "hex": "#2e9e4f"},
    {"id": 3, "name": "PETG - black", "material": "PETG", "hex": "#1c1c1e"},
]
SLICE = {"material": "PLA", "hex": "#00ff40", "slot": 4,
         "profile": "Bambu PLA Matte @BBL A1"}


def pick(loaded):
    return slicer.candidates(SLICE, SPOOLS, None, loaded)


sin = pick(None)
check("sin AMS: gana el color parecido", sin["pick"], 2)
check("sin AMS: sin hueco que ensenar", sin["from_slot"], 0)

con = pick({4: 1})
check("AMS: gana lo que hay en el hueco", con["pick"], 1)
check("AMS: dice de que hueco salio", con["from_slot"], 4)
# el hueco contesta, pero la pantalla decia otro verde: se ensena y se pregunta
check("AMS contra el color: pregunta", con["confident"], False)

# y cuando el color acompana, ya no hay nada que mirar
igual = slicer.candidates(dict(SLICE, hex="#2e9e4f"), SPOOLS, None, {4: 2})
check("AMS con el color: decidido", igual["confident"], True)

# El hueco que no es. No hay razon para tocar nada.
otro = pick({1: 1})
check("otro hueco: no cuenta", otro["pick"], 2)

# Una bobina esta en un hueco o en ninguno, asi que dos huecos de una misma
# placa no pueden acabar en la misma: es lo que se colaba al tratar el hueco
# como un peso mas en vez de como la respuesta.
placa = {1: 1, 2: 2}
a = slicer.candidates(dict(SLICE, slot=1), SPOOLS, None, placa)
b = slicer.candidates(dict(SLICE, slot=2), SPOOLS, None, placa)
check("dos huecos, dos bobinas", a["pick"] != b["pick"], True)

# La pestana esta sin actualizar y dice que en el 4 hay un PETG. El laminado
# dice PLA, asi que esa fila ni siquiera es candidata y el AMS no pinta nada.
viejo = pick({4: 3})
check("AMS caducado: se ignora", viejo["pick"], 2)
check("AMS caducado: sin hueco", viejo["from_slot"], 0)

# El hueco manda, pero si la linea de producto no lo acompana no se presenta
# como seguro: se ensena y se pregunta.
BASIC = [dict(SPOOLS[1]), {"id": 9, "name": "PLA - Grey", "material": "PLA",
                           "hex": "#8a8f96"}]
solo = slicer.candidates(SLICE, BASIC, None, {4: 9})
check("hueco sin linea: elige", solo["pick"], 9)
check("hueco sin linea: pregunta", solo["confident"], False)

# Lo confirmado por el usuario sigue por delante de todo.
recordado = slicer.candidates(SLICE, SPOOLS, 2, {4: 1})
check("lo recordado manda", recordado["pick"], 2)


# ------------------------------------------------------- la fecha del hueco
# Un hueco anotado despues de laminar no estaba puesto cuando se lamino.
import tempfile                                                    # noqa: E402
from core import Store                                             # noqa: E402

st = Store(os.path.join(tempfile.mkdtemp(), "check.db"))
fid = st.add_filament({"name": "PLA Matte - Black", "material": "PLA Matte",
                       "hex": "#26262a", "spool_g": 1000})
# A machine has to exist before anything can be in it: a new database owns none.
unidad = st.add_ams_unit("lite", "A1")
st.set_ams_slot(unidad, 2, fid)
hoy = next(x["loaded_at"] for x in st.ams() if x["filament"])

check("laminado anterior: no cuenta", 2 in st.ams_by_plate_slot("2020-01-01T10:00:00"), False)
check("laminado del mismo dia: cuenta", 2 in st.ams_by_plate_slot(hoy + "T10:00:00"), True)
check("laminado posterior: cuenta", 2 in st.ams_by_plate_slot("2099-01-01T10:00:00"), True)


# Cargar un hueco de una maquina que no existe dejaria la fila fuera del alcance
# de ams(), que recorre las maquinas: ni en el AMS ni libre.
try:
    st.set_ams_slot(3, 1, fid)
    check("hueco de una maquina inexistente", "lo acepto", "que lo rechace")
except ValueError:
    check("hueco de una maquina inexistente", "rechazado", "rechazado")

print()
if fails:
    print("%d fallo(s): %s" % (len(fails), ", ".join(fails)))
    raise SystemExit(1)
print("todo correcto")
