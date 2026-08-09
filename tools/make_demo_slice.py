"""Writes a sliced plate that never came off a real printer.

    py tools/make_demo_slice.py data/_demo_slices

The Bambu Studio card can only be photographed with something in the slice
cache, and whatever is really in there is somebody's own project. This builds a
plate in the same shape Bambu Studio writes -- the two files the app reads,
inside the same folder layout -- so the screenshot goes through the real code
path instead of a mock, without putting anyone's work in the README.

Colours and materials match the sample database from make_demo_db.py.
"""

import json
import os
import sys
import zipfile

# One 3mf, two filaments: the red carries the plate, the blue is an accent.
# Both are Basic profiles, which is what makes the app fall back to colour and
# ask for a confirmation -- the state worth showing.
PLATE = [
    {"id": 1, "type": "PLA", "color": "#D62828", "used_m": "8.09", "used_g": "24.13",
     "profile": "Bambu PLA Basic @BBL A1"},
    {"id": 2, "type": "PLA", "color": "#1F5FD0", "used_m": "1.14", "used_g": "3.40",
     "profile": "Bambu PLA Basic @BBL A1"},
]
OBJECT = "desk_organiser_tray.stl"

SLICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="02.07.01.62"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="printer_model_id" value="N2S"/>
    <metadata key="nozzle_diameters" value="0.4"/>
    <metadata key="prediction" value="9240"/>
    <metadata key="weight" value="%(weight)s"/>
    <object identify_id="1" name="%(object)s" skipped="false" />
%(filaments)s
  </plate>
</config>
"""

FILAMENT = ('    <filament id="%(id)d" tray_info_idx="GFL99" type="%(type)s" '
            'color="%(color)s" used_m="%(used_m)s" used_g="%(used_g)s" '
            'nozzle_diameter="0.40" used_for_object="true" used_for_support="false"/>')


def main(root):
    # Bambu Studio nests each run under a day and a run folder; the app walks
    # the tree, so the fixture keeps the same shape.
    folder = os.path.join(root, "Mon_Jan_01", "12_00_00#1234#1", "Metadata")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, ".1234.1_config.3mf")

    total = sum(float(f["used_g"]) for f in PLATE)
    xml = SLICE_INFO % {
        "weight": "%.2f" % total,
        "object": OBJECT,
        "filaments": "\n".join(FILAMENT % f for f in PLATE),
    }
    # un perfil por hueco del printer, no por filamento usado: asi es como
    # lo escribe Bambu Studio, y es lo que hace que el numero de hueco importe
    slots = {}
    for f in PLATE:
        slots[f["id"]] = f["profile"]
    settings = {"filament_settings_id": [slots.get(i + 1, "Bambu PLA Basic @BBL A1")
                                         for i in range(max(slots))]}

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Metadata/slice_info.config", xml)
        z.writestr("Metadata/project_settings.config", json.dumps(settings))

    print("%s  (%d filamentos, %.2f g)" % (path, len(PLATE), total))
    return path


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/_demo_slices")
