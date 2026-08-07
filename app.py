"""Filament Tracker - inventario y historial de impresión 3D.

Ventana de escritorio (pywebview) con interfaz HTML y base de datos SQLite local.
"""

import os
import sys
import traceback

import webview

from core import (APP_DIR, DB_PATH, DRY_DAYS, SPOOL_TYPES, Store,
                  clean_url, guess_hex)
from importer import import_excel

WEB_DIR = os.path.join(APP_DIR, "web")

# pywebview 6 sustituyó las constantes OPEN_DIALOG/SAVE_DIALOG por el enum FileDialog
_FD = getattr(webview, "FileDialog", None)
DLG_OPEN = _FD.OPEN if _FD else webview.OPEN_DIALOG
DLG_SAVE = _FD.SAVE if _FD else webview.SAVE_DIALOG


def ok(data=None, **extra):
    r = {"ok": True, "data": data}
    r.update(extra)
    return r


def err(message):
    return {"ok": False, "error": str(message)}


class Api:
    def __init__(self):
        self._store = Store(DB_PATH)
        self._window = None

    # ---------- arranque ----------

    def bootstrap(self):
        try:
            s = self._store
            return ok(
                {
                    "filaments": s.filaments(),
                    "prints": s.prints(),
                    "projects": s.projects(),
                    "stats": s.stats(),
                    "settings": s.get_settings(),
                    "dry_days": s.dry_days(),
                    "materials": sorted(DRY_DAYS),
                    "spool_tare": s.spool_tare(),
                    "brands": s.brands(),
                    "spool_types": list(SPOOL_TYPES),
                    "backups": s.backup_info(),
                    "empty": s.is_empty(),
                    "db_path": s.path,
                }
            )
        except Exception as e:
            traceback.print_exc()
            return err(e)

    def refresh(self, payload=None):
        payload = payload or {}
        try:
            s = self._store
            return ok(
                {
                    "filaments": s.filaments(),
                    "prints": s.prints(
                        search=payload.get("search", ""),
                        filament_id=payload.get("filament_id") or None,
                        date_from=payload.get("date_from", ""),
                        date_to=payload.get("date_to", ""),
                    ),
                    "projects": s.projects(),
                    "stats": s.stats(),
                    "settings": s.get_settings(),
                    "dry_days": s.dry_days(),
                    "materials": sorted(DRY_DAYS),
                    "spool_tare": s.spool_tare(),
                    "brands": s.brands(),
                    "spool_types": list(SPOOL_TYPES),
                    "backups": s.backup_info(),
                    "empty": s.is_empty(),
                    "db_path": s.path,
                }
            )
        except Exception as e:
            traceback.print_exc()
            return err(e)

    # ---------- filamentos ----------

    def save_filament(self, data):
        try:
            if data.get("id"):
                self._store.update_filament(int(data["id"]), data)
                return ok()
            return ok({"id": self._store.add_filament(data)})
        except Exception as e:
            return err(e)

    def delete_filament(self, fid):
        try:
            self._store.delete_filament(int(fid))
            return ok()
        except Exception as e:
            return err(e)

    def set_stock(self, data):
        try:
            self._store.set_stock(int(data["id"]), int(data["stock"]))
            return ok()
        except Exception as e:
            return err(e)

    def new_roll(self, data):
        try:
            self._store.new_roll(
                int(data["id"]),
                weight=data.get("weight"),
                opened=data.get("opened"),
                brand=data.get("brand"),
                spare_id=int(data["spare_id"]) if data.get("spare_id") else None,
                from_stock=bool(data.get("from_stock", False)),
                spool_type=data.get("spool_type"),
            )
            return ok()
        except Exception as e:
            return err(e)

    def add_spare(self, data):
        try:
            sid = self._store.add_spare(
                int(data["id"]), brand=data.get("brand"), weight=data.get("weight"),
                spool_type=data.get("spool_type")
            )
            return ok({"id": sid})
        except Exception as e:
            return err(e)

    def update_spare(self, data):
        try:
            self._store.update_spare(
                int(data["spare_id"]), brand=data.get("brand"), weight=data.get("weight"),
                spool_type=data.get("spool_type")
            )
            return ok()
        except Exception as e:
            return err(e)

    def delete_spare(self, sid):
        try:
            self._store.delete_spare(int(sid))
            return ok()
        except Exception as e:
            return err(e)

    def mark_dried(self, data):
        try:
            self._store.mark_dried(int(data["id"]), when=data.get("when"))
            return ok()
        except Exception as e:
            return err(e)

    def save_dry_days(self, data):
        try:
            self._store.set_dry_days(data or {})
            return ok()
        except Exception as e:
            return err(e)

    def adjust_roll(self, data):
        try:
            self._store.adjust_roll(int(data["id"]), float(data["remaining"]),
                                    tare=float(data.get("tare") or 0))
            return ok()
        except Exception as e:
            return err(e)

    def filament_detail(self, fid):
        """Todo lo de un filamento para su ficha: rollos e impresiones."""
        try:
            fid = int(fid)
            fil = next((f for f in self._store.filaments() if f["id"] == fid), None)
            if fil is None:
                return err("Filamento no encontrado.")
            return ok({
                "filament": fil,
                "rolls": self._store.roll_history(fid),
                "prints": self._store.filament_prints(fid),
            })
        except Exception as e:
            traceback.print_exc()
            return err(e)

    def save_spool_tare(self, data):
        try:
            self._store.set_spool_tare(data or {})
            return ok()
        except Exception as e:
            return err(e)

    def make_backup(self):
        try:
            self._store.backup()
            return ok(self._store.backup_info())
        except Exception as e:
            return err(e)

    def open_backups(self):
        try:
            os.startfile(self._store.backup_info()["dir"])
            return ok()
        except Exception as e:
            return err(e)

    def guess_color(self, name):
        return ok(guess_hex(name or ""))

    # ---------- impresiones ----------

    def save_print(self, data):
        try:
            return ok({"id": self._store.save_print(data)})
        except Exception as e:
            return err(e)

    def delete_print(self, pid):
        try:
            self._store.delete_print(int(pid))
            return ok()
        except Exception as e:
            return err(e)

    # ---------- ajustes / archivos ----------

    def save_settings(self, data):
        try:
            self._store.set_settings(data)
            return ok()
        except Exception as e:
            return err(e)

    def pick_excel(self):
        try:
            paths = self._window.create_file_dialog(
                DLG_OPEN,
                allow_multiple=False,
                file_types=("Excel (*.xlsx;*.xlsm)", "Todos los archivos (*.*)"),
            )
            return ok(paths[0] if paths else None)
        except Exception as e:
            return err(e)

    def import_excel(self, data):
        try:
            path = data.get("path")
            if not path or not os.path.exists(path):
                return err("No se ha encontrado el archivo.")
            res = import_excel(self._store, path, replace=bool(data.get("replace")))
            return ok(res)
        except Exception as e:
            traceback.print_exc()
            return err(e)

    def export_excel(self):
        try:
            import openpyxl

            path = self._window.create_file_dialog(
                DLG_SAVE,
                save_filename="Filamentos.xlsx",
                file_types=("Excel (*.xlsx)",),
            )
            if not path:
                return ok(None)
            if isinstance(path, (list, tuple)):
                path = path[0]

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Inventario"
            ws.append(
                ["Filamento", "Material", "Color", "Marca", "Rollo (g)", "Usado (g)",
                 "Restante (g)", "%", "Stock", "Rollo abierto", "Último secado"]
            )
            for f in self._store.filaments():
                ws.append([f["name"], f["material"], f["color"], f["roll_brand"],
                           f["roll_weight"], f["used"], f["remaining"], f["pct"],
                           f["stock"], f["roll_opened"], f["dried_at"]])

            ws3 = wb.create_sheet("Repuestos")
            ws3.append(["Filamento", "Material", "Color", "Marca", "Peso (g)"])
            for f in self._store.filaments():
                for sp in f["spares"]:
                    ws3.append([f["name"], f["material"], f["color"], sp["brand"], sp["weight"]])

            ws2 = wb.create_sheet("Historial")
            ws2.append(["Fecha", "Proyecto", "Filamento", "Gramos", "Fallida", "Enlace", "Notas"])
            for p in self._store.prints():
                for it in p["items"]:
                    ws2.append([p["date"], p["project"], it["name"], it["grams"],
                                "sí" if p["failed"] else "", p["url"], p["notes"]])

            for sheet in (ws, ws2, ws3):
                for col in sheet.columns:
                    width = max(len(str(c.value or "")) for c in col) + 2
                    sheet.column_dimensions[col[0].column_letter].width = min(38, width)
                sheet.freeze_panes = "A2"

            wb.save(path)
            return ok(path)
        except Exception as e:
            traceback.print_exc()
            return err(e)

    def open_url(self, url):
        try:
            import webbrowser

            safe = clean_url(url)
            if not safe:
                return err("Ese enlace no es válido.")
            webbrowser.open(safe)
            return ok()
        except Exception as e:
            return err(e)

    def known_materials(self):
        return ok(sorted(DRY_DAYS))

    def open_data_folder(self):
        try:
            os.startfile(os.path.dirname(self._store.path))
            return ok()
        except Exception as e:
            return err(e)


def main():
    api = Api()
    window = webview.create_window(
        "Filament Tracker",
        os.path.join(WEB_DIR, "index.html"),
        js_api=api,
        width=1360,
        height=880,
        min_size=(1020, 660),
        background_color="#0f1116",
    )
    api._window = window
    debug = "--debug" in sys.argv
    icon = os.path.join(WEB_DIR, "icon.ico")
    try:
        webview.start(debug=debug, icon=icon if os.path.exists(icon) else None)
    except TypeError:
        # backends antiguos de pywebview no aceptan icon=
        webview.start(debug=debug)


if __name__ == "__main__":
    main()
