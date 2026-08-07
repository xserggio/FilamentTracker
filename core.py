"""Data layer: SQLite schema and all the inventory/history logic."""

import glob
import json
import locale
import os
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime

FROZEN = getattr(sys, "frozen", False)


def _res_dir() -> str:
    """Read-only resources (web/, icon).

    Packaged with PyInstaller these live inside the bundle, which in onefile mode
    is a temporary folder extracted on every launch.
    """
    if FROZEN:
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Data that must survive: always next to the .exe, never inside the bundle."""
    root = os.path.dirname(sys.executable) if FROZEN \
        else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "data")


APP_DIR = _res_dir()
DATA_DIR = _data_dir()
DB_PATH = os.path.join(DATA_DIR, "filaments.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS filaments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    material      TEXT NOT NULL DEFAULT 'PLA',
    color         TEXT NOT NULL DEFAULT '',
    hex           TEXT NOT NULL DEFAULT '#8a8f96',
    brand         TEXT NOT NULL DEFAULT '',
    stock         INTEGER NOT NULL DEFAULT 0,
    archived      INTEGER NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rolls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filament_id   INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    opened_at     TEXT NOT NULL,
    weight        REAL NOT NULL DEFAULT 1000,
    adjust        REAL NOT NULL DEFAULT 0,
    brand         TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_rolls_fil ON rolls(filament_id, opened_at);

-- Every unopened spool is a row, so one colour can have spares from a different
-- brand (or weight) than the roll currently fitted.
CREATE TABLE IF NOT EXISTS spares (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filament_id   INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    brand         TEXT NOT NULL DEFAULT '',
    weight        REAL NOT NULL DEFAULT 1000,
    added_at      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_spares_fil ON spares(filament_id, id);

CREATE TABLE IF NOT EXISTS prints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    project       TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prints_date ON prints(date);

CREATE TABLE IF NOT EXISTS print_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    print_id      INTEGER NOT NULL REFERENCES prints(id) ON DELETE CASCADE,
    filament_id   INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    grams         REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_print ON print_items(print_id);
CREATE INDEX IF NOT EXISTS idx_items_fil ON print_items(filament_id);

CREATE TABLE IF NOT EXISTS settings (
    key           TEXT PRIMARY KEY,
    value         TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "low_threshold_pct": "15",     # below this % a roll is flagged as low
    "default_spool_g": "1000",     # default weight of a new roll
    "warn_no_stock": "1",          # warn when a roll runs low with no spare
    "lang": "",                    # interface language ("" = detect from the OS)
}

# How long an open spool lasts before it is worth drying, by plastic family.
# PLA is forgiving; PETG much less so; nylon and the solubles soak up moisture
# in a matter of days. This is the app's starting knowledge: it is copied into
# settings on first launch and can be changed from there.
DRY_DAYS = {
    # --- PLA and its variants ---
    "PLA": 60, "PLA+": 60, "PLA HS": 60, "PLA Silk": 60, "PLA Matte": 60,
    "PLA Glow": 45, "PLA Marble": 45, "PLA-CF": 45, "PLA Metal": 30, "PLA Wood": 30,
    # --- polyesters ---
    "PETG": 30, "PETG-CF": 25, "PCTG": 25, "PET": 20,
    # --- styrenics ---
    "ABS": 45, "ABS-GF": 40, "ASA": 45, "HIPS": 45,
    # --- flexibles ---
    "TPU": 14, "TPE": 14,
    # --- engineering ---
    "PC": 14, "PC-CF": 12, "PP": 30, "PPS-CF": 12, "PEEK": 10, "PEI": 10,
    # --- polyamides: the thirstiest of the lot ---
    "PA": 7, "PA-CF": 7, "PA6": 7, "PA12": 10, "Nylon": 7,
    # --- soluble supports ---
    "PVA": 5, "BVOH": 5, "Support": 30,
}
DRY_FALLBACK = 45

# Empty spool weight (tare) in grams, by brand and spool type.
#
# Sources: SpoolmanDB (github.com/Donkie/SpoolmanDB, community-curated), cross-
# checked against theemptyspool.cc and the Bambu Lab forum. Beware: the spread is
# wide even within one brand -- Bambu ranges from 196 g in cardboard to 253 g in
# plastic, eSUN from 161 to 253 -- because the tooling changes between versions.
# These are starting points: the moment the user weighs one of their own spools,
# the app stores that figure and uses it instead.
SPOOL_TARE = {
    "Bambu Lab":  {"plastic": 250, "cardboard": 196},
    "eSUN":       {"plastic": 240, "cardboard": 170},
    "Sunlu":      {"plastic": 130},
    "Polymaker":  {"cardboard": 140},
    "Prusament":  {"plastic": 193},
    "Overture":   {"cardboard": 155},
    "Elegoo":     {"cardboard": 154, "plastic": 154},
    "Creality":   {"cardboard": 120, "plastic": 225},
    "Anycubic":   {"plastic": 127, "cardboard": 125},
    "Hatchbox":   {"plastic": 251},
    "Eryone":     {"plastic": 187},
    "Geeetech":   {"plastic": 180},
    "JAYO":       {"cardboard": 120},
}
TARE_FALLBACK = 220
TARE_GENERIC = {"plastic": 220, "cardboard": 160, "metal": 320, "other": 220}

# Spool type shifts the tare as much as the brand does: the same eSUN weighs
# 240 g in plastic and 170 in cardboard.
SPOOL_TYPES = ("plastic", "cardboard", "metal", "other")


# Languages the interface ships with. English is the fallback for everyone else.
SUPPORTED_LANGS = ("en", "es", "fr", "de", "pt", "it")


def detect_lang() -> str:
    """Interface language taken from the OS, falling back to English.

    Only used until the user picks one in Settings; from then on their choice is
    stored and this is not consulted again.
    """
    code = ""
    try:
        if sys.platform == "win32":
            import ctypes

            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            code = locale.windows_locale.get(lcid, "")
        if not code:
            code = (locale.getdefaultlocale()[0] or "")
    except Exception:
        code = ""
    two = code.replace("-", "_").split("_")[0].lower()
    return two if two in SUPPORTED_LANGS else "en"


def _norm(s: str) -> str:
    """Letters and digits only, lowercased, so 'Bambu Lab' matches 'bambulab'."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_type(kind: str) -> str:
    k = (kind or "").strip().lower()
    return k if k in SPOOL_TYPES else "plastic"


def guess_tare(brand: str, kind: str = "plastic") -> float:
    """Suggested tare for a brand. Falls back to the generic figure."""
    b = _norm(brand)
    entry = None
    if b:
        table = {_norm(k): v for k, v in SPOOL_TARE.items()}
        entry = table.get(b)
        if entry is None:
            # 'Bambu Lab PLA Basic' is still Bambu Lab
            for key, val in table.items():
                if key in b or b in key:
                    entry = val
                    break
    if entry is None:
        entry = TARE_GENERIC
    return float(entry.get(kind) or next(iter(entry.values()), TARE_FALLBACK))

# Palette for the colour names people typically use
COLOR_MAP = {
    "black": "#1c1c1e",
    "black matte": "#26262a",
    "white": "#f4f4f2",
    "white matte": "#eae7e0",
    "grey": "#8a8f96",
    "gray": "#8a8f96",
    "silver": "#c3c8ce",
    "blue": "#1f5fd0",
    "light blue matte": "#7fb4e6",
    "blue navy matte": "#1e2b52",
    "red": "#d62828",
    "fire engine red": "#d62828",
    "yellow": "#f2c14e",
    "gold": "#d4af37",
    "green": "#2e9e4f",
    "olive green matte": "#6b7a3a",
    "hot pink": "#ff5fa2",
    "sakura pink matte": "#f4b9c7",
    "purple matte": "#7a52a1",
    "oak matte": "#bb9464",
    "dark brown matte": "#4a3728",
    "orange": "#e8722c",
    "transparent": "#cfd6e0",
    "natural": "#e3ddd0",
}


def guess_hex(color: str) -> str:
    c = (color or "").strip().lower()
    if c in COLOR_MAP:
        return COLOR_MAP[c]
    # partial match: "light blue matte" -> "blue"
    for key in sorted(COLOR_MAP, key=len, reverse=True):
        if key in c:
            return COLOR_MAP[key]
    return "#8a8f96"


SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def clean_url(value: str) -> str:
    """Solo se admiten enlaces http(s).

    Si el texto ya trae un esquema distinto (javascript:, file:, ftp:…) se
    dropped rather than prefixed with https://, which would let junk through.
    Sin esquema se asume https, que es lo normal al pegar 'printables.com/...'.
    """
    u = (value or "").strip()
    if not u:
        return ""
    if SCHEME_RE.match(u):
        return u if u.lower().startswith(("http://", "https://")) else ""
    return "https://" + u.lstrip("/")


def today() -> str:
    return date.today().isoformat()


def days_since(iso: str):
    """Days elapsed since an ISO date, or None if there is no valid date."""
    if not iso:
        return None
    try:
        return (date.today() - date.fromisoformat(str(iso)[:10])).days
    except ValueError:
        return None


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        for k, v in DEFAULT_SETTINGS.items():
            self.db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)", (k, v))
        self.db.commit()
        try:
            self.backup()
        except Exception:      # a failed backup must never stop the app opening
            pass

    def _migrate(self):
        """Adds new columns to databases created by earlier versions."""
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(rolls)")}
        if "brand" not in cols:
            self.db.execute("ALTER TABLE rolls ADD COLUMN brand TEXT NOT NULL DEFAULT ''")
            # existing rolls inherit whatever brand the filament had
            self.db.execute(
                "UPDATE rolls SET brand = COALESCE("
                "(SELECT f.brand FROM filaments f WHERE f.id = rolls.filament_id), '')"
            )
            self.db.commit()

        # the filaments.stock integer becomes one row per spare
        done = self.db.execute(
            "SELECT value FROM settings WHERE key='spares_migrated'"
        ).fetchone()
        if done is None:
            row = self.db.execute(
                "SELECT value FROM settings WHERE key='default_spool_g'"
            ).fetchone()
            default_g = float(row["value"]) if row else 1000.0
            for r in self.db.execute("SELECT id, brand, stock FROM filaments WHERE stock > 0"):
                for _ in range(int(r["stock"])):
                    self.db.execute(
                        "INSERT INTO spares(filament_id, brand, weight, added_at) VALUES(?,?,?,?)",
                        (r["id"], r["brand"] or "", default_g, today()),
                    )
            self.db.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES('spares_migrated','1')"
            )
            self.db.commit()

        rcols = {r["name"] for r in self.db.execute("PRAGMA table_info(rolls)")}
        if "dried_at" not in rcols:
            self.db.execute("ALTER TABLE rolls ADD COLUMN dried_at TEXT NOT NULL DEFAULT ''")
            self.db.commit()
        if "tare" not in rcols:
            self.db.execute("ALTER TABLE rolls ADD COLUMN tare REAL NOT NULL DEFAULT 0")
            self.db.commit()
        if "spool_type" not in rcols:
            self.db.execute(
                "ALTER TABLE rolls ADD COLUMN spool_type TEXT NOT NULL DEFAULT 'plastic'")
            self.db.commit()
        if "spool_type" not in {r["name"] for r in self.db.execute("PRAGMA table_info(spares)")}:
            self.db.execute(
                "ALTER TABLE spares ADD COLUMN spool_type TEXT NOT NULL DEFAULT 'plastic'")
            self.db.commit()

        pcols = {r["name"] for r in self.db.execute("PRAGMA table_info(prints)")}
        if "failed" not in pcols:
            self.db.execute("ALTER TABLE prints ADD COLUMN failed INTEGER NOT NULL DEFAULT 0")
            self.db.commit()
        if "url" not in pcols:
            self.db.execute("ALTER TABLE prints ADD COLUMN url TEXT NOT NULL DEFAULT ''")
            self.db.commit()

        if self.db.execute("SELECT value FROM settings WHERE key='dry_days'").fetchone() is None:
            self.db.execute("INSERT INTO settings(key, value) VALUES('dry_days', ?)",
                            (json.dumps(DRY_DAYS),))
            self.db.commit()

    # ---------- settings ----------

    def get_settings(self) -> dict:
        rows = self.db.execute("SELECT key, value FROM settings").fetchall()
        out = {r["key"]: r["value"] for r in rows}
        # an empty lang means "not chosen yet": resolve it from the OS
        if not out.get("lang"):
            out["lang"] = detect_lang()
        return out

    def set_settings(self, values: dict):
        for k, v in values.items():
            self.db.execute(
                "INSERT INTO settings(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )
        self.db.commit()

    def is_empty(self) -> bool:
        return self.db.execute("SELECT COUNT(*) c FROM filaments").fetchone()["c"] == 0

    # ---------- filaments ----------

    def current_roll(self, filament_id: int):
        return self.db.execute(
            "SELECT * FROM rolls WHERE filament_id=? ORDER BY opened_at DESC, id DESC LIMIT 1",
            (filament_id,),
        ).fetchone()

    def filaments(self, include_archived: bool = True) -> list:
        """Every filament with its fitted roll and the grams consumed from it."""
        sql = "SELECT * FROM filaments"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY material, name COLLATE NOCASE"
        rows = self.db.execute(sql).fetchall()

        settings = self.get_settings()
        low_pct = float(settings.get("low_threshold_pct", 15))
        default_g = float(settings.get("default_spool_g", 1000))
        dry_days = self.dry_days()

        out = []
        for r in rows:
            roll = self.current_roll(r["id"])
            dried = roll["dried_at"] if roll else ""
            roll_type = (roll["spool_type"] if roll else "plastic") or "plastic"
            if roll is None:
                weight, opened, adjust, roll_id = default_g, None, 0.0, None
                roll_brand = r["brand"]
                used = 0.0
            else:
                weight = float(roll["weight"])
                opened = roll["opened_at"]
                adjust = float(roll["adjust"])
                roll_id = roll["id"]
                roll_brand = roll["brand"] or r["brand"]
                used = self.db.execute(
                    "SELECT COALESCE(SUM(pi.grams),0) g FROM print_items pi "
                    "JOIN prints p ON p.id = pi.print_id "
                    "WHERE pi.filament_id=? AND p.date >= ?",
                    (r["id"], opened),
                ).fetchone()["g"]

            remaining = max(0.0, weight - used + adjust)
            pct = (remaining / weight * 100) if weight else 0.0
            total_used = self.db.execute(
                "SELECT COALESCE(SUM(grams),0) g FROM print_items WHERE filament_id=?",
                (r["id"],),
            ).fetchone()["g"]
            rolls_used = self.db.execute(
                "SELECT COUNT(*) c FROM rolls WHERE filament_id=?", (r["id"],)
            ).fetchone()["c"]

            # A freshly opened spool comes dry from the factory, so if it has never
            # been dried the clock runs from the opening date.
            dry_limit = int(dry_days.get(r["material"], DRY_FALLBACK))
            since_dry = days_since(dried or opened)
            needs_dry = since_dry is not None and since_dry > dry_limit

            spares = [
                {"id": s["id"], "brand": s["brand"], "weight": round(float(s["weight"]), 2),
                 "spool_type": s["spool_type"] or "plastic"}
                for s in self.db.execute(
                    "SELECT id, brand, weight, spool_type FROM spares "
                    "WHERE filament_id=? ORDER BY id",
                    (r["id"],),
                )
            ]

            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "material": r["material"],
                    "color": r["color"],
                    "hex": r["hex"],
                    "brand": r["brand"],
                    "spares": spares,
                    "stock": len(spares),
                    "spare_g": round(sum(s["weight"] for s in spares), 2),
                    "archived": r["archived"],
                    "notes": r["notes"],
                    "roll_id": roll_id,
                    "roll_weight": round(weight, 2),
                    "roll_opened": opened,
                    "roll_brand": roll_brand,
                    "dried_at": dried,
                    "tare": round(float(roll["tare"]), 1) if roll else 0.0,
                    "roll_type": roll_type,
                    "tare_hint": round(self.tare_for(roll_brand, roll_type), 1),
                    "days_open": days_since(opened),
                    "days_since_dry": since_dry,
                    "dry_limit": dry_limit,
                    "needs_dry": needs_dry,
                    "used": round(used, 2),
                    "adjust": round(adjust, 2),
                    "remaining": round(remaining, 2),
                    "pct": round(pct, 1),
                    "low": pct < low_pct,
                    "empty": remaining <= 0.5,
                    "total_used": round(total_used, 2),
                    "rolls_used": rolls_used,
                }
            )
        return out

    def add_filament(self, data: dict) -> int:
        name = (data.get("name") or "").strip()
        material = (data.get("material") or "PLA").strip()
        color = (data.get("color") or "").strip()
        if not name:
            name = f"{material} - {color}".strip(" -")
        if not name:
            raise ValueError("The filament needs a name.")
        hexv = (data.get("hex") or "").strip() or guess_hex(color)
        brand = (data.get("brand") or "").strip()
        cur = self.db.execute(
            "INSERT INTO filaments(name, material, color, hex, brand, stock, notes, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                name,
                material,
                color,
                hexv,
                brand,
                int(data.get("stock") or 0),
                (data.get("notes") or "").strip(),
                now(),
            ),
        )
        fid = cur.lastrowid
        weight = float(data.get("roll_weight") or self.get_settings().get("default_spool_g", 1000))
        opened = data.get("roll_opened") or today()
        stype = norm_type(data.get("spool_type"))
        self.db.execute(
            "INSERT INTO rolls(filament_id, opened_at, weight, adjust, brand, note, spool_type) "
            "VALUES(?,?,?,0,?,?,?)",
            (fid, opened, weight, brand, "rollo inicial", stype),
        )
        self.db.commit()
        for _ in range(int(data.get("stock") or 0)):
            self.add_spare(fid, brand=brand, weight=weight, spool_type=stype)
        return fid

    def update_filament(self, fid: int, data: dict):
        cur = self.db.execute("SELECT * FROM filaments WHERE id=?", (fid,)).fetchone()
        if cur is None:
            raise ValueError("Filament not found.")
        name = (data.get("name") or cur["name"]).strip()
        material = (data.get("material") or cur["material"]).strip()
        color = data.get("color", cur["color"]).strip()
        hexv = (data.get("hex") or "").strip() or guess_hex(color)
        # The brand lives on the roll; on the filament it is only kept as the
        # default for rolls opened later.
        brand = data.get("brand", cur["brand"]).strip()
        self.db.execute(
            "UPDATE filaments SET name=?, material=?, color=?, hex=?, brand=?, stock=?, "
            "notes=?, archived=? WHERE id=?",
            (
                name,
                material,
                color,
                hexv,
                brand,
                cur["stock"],
                data.get("notes", cur["notes"]).strip(),
                int(data.get("archived", cur["archived"]) or 0),
                fid,
            ),
        )
        # the fitted roll's weight and date are editable from the same dialog
        roll = self.current_roll(fid)
        if roll is not None:
            weight = float(data.get("roll_weight", roll["weight"]) or roll["weight"])
            opened = data.get("roll_opened") or roll["opened_at"]
            self.db.execute(
                "UPDATE rolls SET weight=?, opened_at=?, brand=?, spool_type=? WHERE id=?",
                (weight, opened, brand,
                 norm_type(data.get("spool_type", roll["spool_type"])), roll["id"]),
            )
        self.db.commit()
        if "stock" in data:
            self.set_stock(fid, data["stock"])

    def delete_filament(self, fid: int):
        self.db.execute("DELETE FROM filaments WHERE id=?", (fid,))
        self.db.commit()

    # ---------- spares ----------

    def default_brand(self, fid: int) -> str:
        roll = self.current_roll(fid)
        if roll and roll["brand"]:
            return roll["brand"]
        r = self.db.execute("SELECT brand FROM filaments WHERE id=?", (fid,)).fetchone()
        return r["brand"] if r else ""

    def add_spare(self, fid: int, brand: str = None, weight: float = None,
                  spool_type: str = None) -> int:
        if brand is None:
            brand = self.default_brand(fid)
        if weight is None:
            weight = float(self.get_settings().get("default_spool_g", 1000))
        if spool_type is None:
            roll = self.current_roll(fid)
            spool_type = (roll["spool_type"] if roll else "plastic") or "plastic"
        cur = self.db.execute(
            "INSERT INTO spares(filament_id, brand, weight, added_at, spool_type) "
            "VALUES(?,?,?,?,?)",
            (fid, (brand or "").strip(), float(weight), today(), norm_type(spool_type)),
        )
        self.db.commit()
        return cur.lastrowid

    def update_spare(self, sid: int, brand: str = None, weight: float = None,
                     spool_type: str = None):
        cur = self.db.execute("SELECT * FROM spares WHERE id=?", (sid,)).fetchone()
        if cur is None:
            raise ValueError("That spare no longer exists.")
        self.db.execute(
            "UPDATE spares SET brand=?, weight=?, spool_type=? WHERE id=?",
            ((brand if brand is not None else cur["brand"]).strip(),
             float(weight if weight is not None else cur["weight"]),
             norm_type(spool_type if spool_type is not None else cur["spool_type"]), sid),
        )
        self.db.commit()

    def delete_spare(self, sid: int):
        self.db.execute("DELETE FROM spares WHERE id=?", (sid,))
        self.db.commit()

    def set_stock(self, fid: int, stock: int):
        """Reconciles the number of spares with the requested count: new ones
        inherit the fitted roll's brand, extras are removed newest first."""
        stock = max(0, int(stock))
        have = [r["id"] for r in self.db.execute(
            "SELECT id FROM spares WHERE filament_id=? ORDER BY id", (fid,))]
        if stock > len(have):
            for _ in range(stock - len(have)):
                self.add_spare(fid)
        elif stock < len(have):
            for sid in have[stock:]:
                self.db.execute("DELETE FROM spares WHERE id=?", (sid,))
        self.db.commit()

    # ---------- rolls ----------

    def new_roll(self, fid: int, weight: float = None, opened: str = None,
                 brand: str = None, spare_id: int = None, from_stock: bool = False,
                 spool_type: str = None):
        """Fits a new roll: usage is counted from its opening date onwards.

        If a spare is given, the roll inherits its brand and weight (which may
        differ from the outgoing roll) and that spare leaves the stock.
        """
        spare = None
        if spare_id:
            spare = self.db.execute(
                "SELECT * FROM spares WHERE id=? AND filament_id=?", (spare_id, fid)
            ).fetchone()
            if spare is None:
                raise ValueError("That spare is no longer available.")

        if weight is None:
            weight = float(spare["weight"]) if spare else float(
                self.get_settings().get("default_spool_g", 1000))
        if brand is None:
            brand = spare["brand"] if spare else self.default_brand(fid)
        brand = (brand or "").strip()
        if spool_type is None:
            if spare is not None:
                spool_type = spare["spool_type"]
            else:
                prev = self.current_roll(fid)
                spool_type = prev["spool_type"] if prev else "plastic"
        opened = opened or today()

        self.db.execute(
            "INSERT INTO rolls(filament_id, opened_at, weight, adjust, brand, note, spool_type) "
            "VALUES(?,?,?,0,?,'',?)",
            (fid, opened, float(weight), brand, norm_type(spool_type)),
        )
        # the newly fitted roll's brand becomes the default suggestion
        self.db.execute("UPDATE filaments SET brand=? WHERE id=?", (brand, fid))

        if spare is not None:
            self.db.execute("DELETE FROM spares WHERE id=?", (spare["id"],))
        elif from_stock:
            oldest = self.db.execute(
                "SELECT id FROM spares WHERE filament_id=? ORDER BY id LIMIT 1", (fid,)
            ).fetchone()
            if oldest:
                self.db.execute("DELETE FROM spares WHERE id=?", (oldest["id"],))
        self.db.commit()

    def adjust_roll(self, fid: int, remaining: float, tare: float = 0):
        """Sets the real remaining grams, e.g. after weighing the spool."""
        roll = self.current_roll(fid)
        if roll is None:
            raise ValueError("This filament has no roll fitted.")
        used = self.db.execute(
            "SELECT COALESCE(SUM(pi.grams),0) g FROM print_items pi "
            "JOIN prints p ON p.id = pi.print_id "
            "WHERE pi.filament_id=? AND p.date >= ?",
            (fid, roll["opened_at"]),
        ).fetchone()["g"]
        adjust = float(remaining) - (float(roll["weight"]) - used)
        self.db.execute("UPDATE rolls SET adjust=? WHERE id=?", (adjust, roll["id"]))
        if tare:
            self.db.execute("UPDATE rolls SET tare=? WHERE id=?", (float(tare), roll["id"]))
            # the brand learns from the scale: this replaces the table value
            saved = json.loads(self.get_settings().get("spool_tare") or "{}")
            brand = (roll["brand"] or "").strip()
            kind = norm_type(roll["spool_type"])
            if brand:
                slot = saved.get(brand)
                if not isinstance(slot, dict):
                    slot = {"plastic": slot} if slot else {}
                slot[kind] = round(float(tare), 1)
                saved[brand] = slot
                self.db.execute(
                    "INSERT INTO settings(key, value) VALUES('spool_tare', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(saved),))
        self.db.commit()

    def dry_days(self) -> dict:
        """Days of leeway before drying, per material. Settings win."""
        raw = self.get_settings().get("dry_days")
        out = dict(DRY_DAYS)
        if raw:
            try:
                out.update({k: int(v) for k, v in json.loads(raw).items()})
            except (ValueError, TypeError, AttributeError):
                pass
        return out

    def set_dry_days(self, values: dict):
        clean = {}
        for k, v in (values or {}).items():
            k = str(k).strip()
            try:
                if k and int(v) > 0:
                    clean[k] = int(v)
            except (TypeError, ValueError):
                continue
        self.set_settings({"dry_days": json.dumps(clean)})

    def mark_dried(self, fid: int, when: str = None):
        """Logs that the fitted roll was dried; resets the moisture clock."""
        roll = self.current_roll(fid)
        if roll is None:
            raise ValueError("This filament has no roll fitted.")
        self.db.execute("UPDATE rolls SET dried_at=? WHERE id=?",
                        (when or today(), roll["id"]))
        self.db.commit()

    def roll_history(self, fid: int) -> list:
        """Rolls this filament has had, newest first, with how much was consumed
        during each one's stint."""
        rows = self.db.execute(
            "SELECT * FROM rolls WHERE filament_id=? ORDER BY opened_at DESC, id DESC", (fid,)
        ).fetchall()
        out = []
        for i, r in enumerate(rows):
            # a roll's stint ends where the next one begins
            nxt = rows[i - 1]["opened_at"] if i > 0 else None
            if nxt:
                used = self.db.execute(
                    "SELECT COALESCE(SUM(pi.grams),0) g FROM print_items pi "
                    "JOIN prints p ON p.id = pi.print_id "
                    "WHERE pi.filament_id=? AND p.date >= ? AND p.date < ?",
                    (fid, r["opened_at"], nxt),
                ).fetchone()["g"]
            else:
                used = self.db.execute(
                    "SELECT COALESCE(SUM(pi.grams),0) g FROM print_items pi "
                    "JOIN prints p ON p.id = pi.print_id "
                    "WHERE pi.filament_id=? AND p.date >= ?",
                    (fid, r["opened_at"]),
                ).fetchone()["g"]
            d = dict(r)
            d["used"] = round(used, 2)
            d["current"] = i == 0
            d["closed_at"] = nxt
            d["days"] = None
            if nxt:
                a, b = days_since(r["opened_at"]), days_since(nxt)
                if a is not None and b is not None:
                    d["days"] = a - b
            else:
                d["days"] = days_since(r["opened_at"])
            out.append(d)
        return out

    def filament_prints(self, fid: int) -> list:
        """Prints this filament appears in, with their grams."""
        rows = self.db.execute(
            "SELECT p.id, p.date, p.project, p.failed, p.url, pi.grams "
            "FROM print_items pi JOIN prints p ON p.id = pi.print_id "
            "WHERE pi.filament_id=? ORDER BY p.date DESC, p.id DESC",
            (fid,),
        ).fetchall()
        return [
            {"id": r["id"], "date": r["date"], "project": r["project"],
             "failed": int(r["failed"] or 0), "url": r["url"] or "",
             "grams": round(float(r["grams"]), 2)}
            for r in rows
        ]

    # ---------- backups ----------

    def backup(self, keep: int = 10) -> str:
        """One copy per day in data/backups/, keeping the last `keep`.

        Uses SQLite's backup API rather than copying the file, so the copy is
        consistent even mid-write.
        """
        bdir = os.path.join(os.path.dirname(self.path), "backups")
        os.makedirs(bdir, exist_ok=True)
        dest = os.path.join(bdir, f"filaments-{today()}.db")
        if not os.path.exists(dest):
            tmp = dest + ".part"
            out = sqlite3.connect(tmp)
            try:
                self.db.backup(out)
            finally:
                out.close()
            shutil.move(tmp, dest)
        old = sorted(glob.glob(os.path.join(bdir, "filaments-*.db")))
        for f in old[:-keep]:
            try:
                os.remove(f)
            except OSError:
                pass
        return dest

    def backup_info(self) -> dict:
        bdir = os.path.join(os.path.dirname(self.path), "backups")
        files = sorted(glob.glob(os.path.join(bdir, "filaments-*.db")))
        return {
            "dir": bdir,
            "count": len(files),
            "last": os.path.basename(files[-1])[10:-3] if files else "",
        }

    # ---------- spool tare ----------

    def spool_tare(self) -> dict:
        """Tares by brand and spool type; whatever the user measured wins.

        Accepts the old format ({brand: grams}), read as plastic.
        """
        raw = self.get_settings().get("spool_tare")
        out = {k: dict(v) for k, v in SPOOL_TARE.items()}
        if raw:
            try:
                index = {_norm(k): k for k in out}
                for k, v in json.loads(raw).items():
                    key = index.get(_norm(k), k)
                    slot = out.setdefault(key, {})
                    if isinstance(v, dict):
                        for kind, grams in v.items():
                            if kind in SPOOL_TYPES:
                                slot[kind] = float(grams)
                    else:
                        slot["plastic"] = float(v)
            except (ValueError, TypeError, AttributeError):
                pass
        return out

    def set_spool_tare(self, values: dict):
        clean = {}
        for brand, entry in (values or {}).items():
            brand = str(brand).strip()
            if not brand:
                continue
            if not isinstance(entry, dict):
                entry = {"plastic": entry}
            slot = {}
            for kind, grams in entry.items():
                if kind not in SPOOL_TYPES:
                    continue
                try:
                    if float(grams) > 0:
                        slot[kind] = round(float(grams), 1)
                except (TypeError, ValueError):
                    continue
            if slot:
                clean[brand] = slot
        self.set_settings({"spool_tare": json.dumps(clean)})

    def tare_for(self, brand: str, kind: str = "plastic") -> float:
        kind = norm_type(kind)
        user = self.get_settings().get("spool_tare")
        if user:
            try:
                for k, v in json.loads(user).items():
                    if _norm(k) != _norm(brand):
                        continue
                    if isinstance(v, dict):
                        if kind in v:
                            return float(v[kind])
                    elif kind == "plastic":
                        return float(v)
            except (ValueError, TypeError, AttributeError):
                pass
        return guess_tare(brand, kind)

    def brands(self) -> list:
        """Known brands plus the ones already in use, without duplicates."""
        used = [r["brand"] for r in self.db.execute(
            "SELECT DISTINCT brand FROM rolls WHERE brand <> '' "
            "UNION SELECT DISTINCT brand FROM spares WHERE brand <> ''")]
        out, seen = [], set()
        for b in list(SPOOL_TARE) + sorted(used):
            if _norm(b) not in seen:
                seen.add(_norm(b))
                out.append(b)
        return sorted(out, key=str.lower)

    # ---------- prints ----------

    def prints(self, limit: int = None, search: str = "", filament_id: int = None,
               date_from: str = "", date_to: str = "") -> list:
        sql = "SELECT p.* FROM prints p"
        args = []
        where = []
        if filament_id:
            sql += " JOIN print_items pi ON pi.print_id = p.id"
            where.append("pi.filament_id = ?")
            args.append(filament_id)
        if search:
            where.append("p.project LIKE ?")
            args.append(f"%{search}%")
        if date_from:
            where.append("p.date >= ?")
            args.append(date_from)
        if date_to:
            where.append("p.date <= ?")
            args.append(date_to)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY p.id ORDER BY p.date DESC, p.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.execute(sql, args).fetchall()

        ids = [r["id"] for r in rows]
        items_by_print = {i: [] for i in ids}
        if ids:
            q = ",".join("?" * len(ids))
            for it in self.db.execute(
                f"SELECT pi.*, f.name, f.hex, f.material FROM print_items pi "
                f"JOIN filaments f ON f.id = pi.filament_id "
                f"WHERE pi.print_id IN ({q}) ORDER BY pi.grams DESC",
                ids,
            ):
                items_by_print[it["print_id"]].append(
                    {
                        "filament_id": it["filament_id"],
                        "name": it["name"],
                        "hex": it["hex"],
                        "material": it["material"],
                        "grams": round(float(it["grams"]), 2),
                    }
                )
        out = []
        for r in rows:
            items = items_by_print.get(r["id"], [])
            out.append(
                {
                    "id": r["id"],
                    "date": r["date"],
                    "project": r["project"],
                    "notes": r["notes"],
                    "failed": int(r["failed"] or 0),
                    "url": r["url"] or "",
                    "items": items,
                    "total": round(sum(i["grams"] for i in items), 2),
                }
            )
        return out

    def save_print(self, data: dict) -> int:
        pid = data.get("id")
        pdate = data.get("date") or today()
        project = (data.get("project") or "").strip()
        if not project:
            raise ValueError("Enter the project name.")
        items = [
            i for i in (data.get("items") or [])
            if i.get("filament_id") and float(i.get("grams") or 0) > 0
        ]
        if not items:
            raise ValueError("Add at least one filament with grams.")
        notes = (data.get("notes") or "").strip()
        failed = 1 if data.get("failed") else 0
        url = clean_url(data.get("url"))

        if pid:
            self.db.execute(
                "UPDATE prints SET date=?, project=?, notes=?, failed=?, url=? WHERE id=?",
                (pdate, project, notes, failed, url, pid),
            )
            self.db.execute("DELETE FROM print_items WHERE print_id=?", (pid,))
        else:
            cur = self.db.execute(
                "INSERT INTO prints(date, project, notes, created_at, failed, url) "
                "VALUES(?,?,?,?,?,?)",
                (pdate, project, notes, now(), failed, url),
            )
            pid = cur.lastrowid
        for i in items:
            self.db.execute(
                "INSERT INTO print_items(print_id, filament_id, grams) VALUES(?,?,?)",
                (pid, int(i["filament_id"]), round(float(i["grams"]), 2)),
            )
        self.db.commit()
        return pid

    def delete_print(self, pid: int):
        self.db.execute("DELETE FROM prints WHERE id=?", (pid,))
        self.db.commit()

    def projects(self) -> list:
        rows = self.db.execute(
            "SELECT DISTINCT project FROM prints ORDER BY project COLLATE NOCASE"
        ).fetchall()
        return [r["project"] for r in rows]

    # ---------- statistics ----------

    def stats(self) -> dict:
        db = self.db
        by_month = [
            {"month": r["m"], "grams": round(r["g"], 2), "prints": r["n"]}
            for r in db.execute(
                "SELECT substr(p.date,1,7) m, COALESCE(SUM(pi.grams),0) g, "
                "COUNT(DISTINCT p.id) n FROM prints p "
                "LEFT JOIN print_items pi ON pi.print_id = p.id "
                "GROUP BY m ORDER BY m"
            )
        ]
        by_filament = [
            {"name": r["name"], "hex": r["hex"], "grams": round(r["g"], 2), "prints": r["n"]}
            for r in db.execute(
                "SELECT f.name, f.hex, COALESCE(SUM(pi.grams),0) g, COUNT(DISTINCT pi.print_id) n "
                "FROM print_items pi JOIN filaments f ON f.id = pi.filament_id "
                "GROUP BY f.id ORDER BY g DESC"
            )
        ]
        by_material = [
            {"material": r["material"], "grams": round(r["g"], 2)}
            for r in db.execute(
                "SELECT f.material, COALESCE(SUM(pi.grams),0) g "
                "FROM print_items pi JOIN filaments f ON f.id = pi.filament_id "
                "GROUP BY f.material ORDER BY g DESC"
            )
        ]
        top_projects = [
            {"project": r["project"], "grams": round(r["g"], 2)}
            for r in db.execute(
                "SELECT p.project, COALESCE(SUM(pi.grams),0) g FROM prints p "
                "JOIN print_items pi ON pi.print_id = p.id "
                "GROUP BY p.project ORDER BY g DESC LIMIT 12"
            )
        ]
        by_weekday = [0.0] * 7
        for r in db.execute(
            "SELECT CAST(strftime('%w', p.date) AS INTEGER) w, COALESCE(SUM(pi.grams),0) g "
            "FROM prints p JOIN print_items pi ON pi.print_id = p.id GROUP BY w"
        ):
            by_weekday[r["w"]] = round(r["g"], 2)

        tot = db.execute(
            "SELECT COUNT(DISTINCT p.id) n, COALESCE(SUM(pi.grams),0) g, "
            "MIN(p.date) first, MAX(p.date) last FROM prints p "
            "LEFT JOIN print_items pi ON pi.print_id = p.id"
        ).fetchone()
        bad = db.execute(
            "SELECT COUNT(DISTINCT p.id) n, COALESCE(SUM(pi.grams),0) g FROM prints p "
            "LEFT JOIN print_items pi ON pi.print_id = p.id WHERE p.failed = 1"
        ).fetchone()
        worst_fail = [
            {"project": r["project"], "grams": round(r["g"], 2), "n": r["n"]}
            for r in db.execute(
                "SELECT p.project, COALESCE(SUM(pi.grams),0) g, COUNT(DISTINCT p.id) n "
                "FROM prints p JOIN print_items pi ON pi.print_id = p.id "
                "WHERE p.failed = 1 GROUP BY p.project ORDER BY g DESC LIMIT 8"
            )
        ]

        fils = self.filaments()
        month = date.today().strftime("%Y-%m")
        this_month = next((m for m in by_month if m["month"] == month), {"grams": 0, "prints": 0})

        return {
            "by_month": by_month,
            "by_filament": by_filament,
            "by_material": by_material,
            "top_projects": top_projects,
            "by_weekday": by_weekday,
            "total_prints": tot["n"] or 0,
            "total_grams": round(tot["g"] or 0, 2),
            "failed_prints": bad["n"] or 0,
            "failed_grams": round(bad["g"] or 0, 2),
            "worst_failures": worst_fail,
            "n_dry": sum(1 for f in fils if f["needs_dry"] and not f["archived"]),
            "first_date": tot["first"],
            "last_date": tot["last"],
            "month_grams": this_month["grams"],
            "month_prints": this_month["prints"],
            "available_g": round(sum(f["remaining"] + f["spare_g"] for f in fils), 2),
            "open_g": round(sum(f["remaining"] for f in fils), 2),
            "stock_spools": sum(f["stock"] for f in fils),
            "n_filaments": len(fils),
            "n_low": sum(1 for f in fils if f["low"]),
        }
