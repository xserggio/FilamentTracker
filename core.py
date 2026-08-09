"""Data layer: SQLite schema and all the inventory/history logic."""

import glob
import hashlib
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
    note          TEXT NOT NULL DEFAULT '',
    -- The day the scale overruled the books, so a roll carrying a correction
    -- says so instead of just quietly holding a different number.
    adjusted_at   TEXT NOT NULL DEFAULT ''
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

-- Every plate the app has read out of the slicer cache. That cache belongs to
-- Bambu Studio, not to us: it writes a plate's figures there, sometimes does not
-- write them at all, and clears them when it feels like it -- so an offer that
-- was on screen a minute ago can be gone for good. Reading it once and keeping
-- the result is the only way the offer survives the walk to the inventory tab
-- and back.
CREATE TABLE IF NOT EXISTS slices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    -- what makes two readings the same plate: name, total and every colour
    fingerprint   TEXT NOT NULL UNIQUE,
    -- where it was read from, and our own copy of it in data/slices
    path          TEXT NOT NULL DEFAULT '',
    copy_path     TEXT NOT NULL DEFAULT '',
    sliced_at     TEXT NOT NULL DEFAULT '',
    stamp         REAL NOT NULL DEFAULT 0,
    project       TEXT NOT NULL DEFAULT '',
    total         REAL NOT NULL DEFAULT 0,
    items         TEXT NOT NULL DEFAULT '[]',
    -- which reading produced those items, so a plate is re-read once after an
    -- improvement and not on every look
    parsed_with   INTEGER NOT NULL DEFAULT 0,
    logged_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_slices_when ON slices(sliced_at DESC);

-- A handful of prints that are really one thing: a house is a chimney and a
-- roof and a dozen balloons. The name on a print stays what it is -- plenty of
-- prints are a whole project on their own -- and the group sits above it,
-- optional, for the ones that are pieces of something bigger.
CREATE TABLE IF NOT EXISTS groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL DEFAULT ''
);

-- Which spool is in which AMS slot right now. A slot is identified by its
-- unit and position rather than by a row id, so the layout can grow or shrink
-- with the printer without renumbering anything. An empty slot is simply a row
-- that is not here.
CREATE TABLE IF NOT EXISTS ams_slots (
    unit          INTEGER NOT NULL,
    slot          INTEGER NOT NULL,
    filament_id   INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    loaded_at     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (unit, slot)
);

-- What the slicer wrote -> which spool it actually was. The colour in a sliced
-- file is whatever was picked on screen or inherited from the AMS slot, so it
-- rarely matches the real spool. Rather than guess forever, every confirmation
-- is remembered here and the next identical slice needs no guessing.
CREATE TABLE IF NOT EXISTS slicer_map (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signature     TEXT NOT NULL UNIQUE,
    filament_id   INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    hits          INTEGER NOT NULL DEFAULT 1,
    last_used     TEXT NOT NULL DEFAULT ''
);
"""

DEFAULT_SETTINGS = {
    "low_threshold_pct": "15",     # below this % a roll is flagged as low
    "default_spool_g": "1000",     # default weight of a new roll
    "warn_no_stock": "1",          # warn when a roll runs low with no spare
    "lang": "",                    # interface language ("" = detect from the OS)
    "theme": "dark",               # dark | light | auto (follow the system)
    "currency": "EUR",             # what prices are entered in; never converted
    "slicer_watch": "1",           # offer a print when Bambu Studio slices one
    "slicer_seen": "0",            # newest slice already offered (epoch seconds)
    "slicer_dir": "",              # folder to watch ("" = find it)
    "ams_units": "1",              # AMS units on the printer (0 = external spool only)
    "alert_mutes": "{}",           # alerts silenced until their situation clears
}

# How long an open spool lasts before it is worth drying, by plastic family.
# PLA is forgiving; PETG much less so; nylon and the solubles soak up moisture
# in a matter of days. This is the app's starting knowledge: it is copied into
# settings on first launch and can be changed from there.
DRY_DAYS = {
    # --- PLA and its variants ---
    "PLA": 60, "PLA+": 60, "PLA HS": 60, "PLA Silk": 60, "PLA Matte": 60,
    "PLA Glow": 45, "PLA Marble": 45, "PLA-CF": 45, "PLA Metal": 30, "PLA Wood": 30,
    "PLA Wood": 30, "PLA+WOOD": 30, "Wood": 30, "Flax": 30, "PLA Pearl": 60,
    # --- polyesters ---
    "PETG": 30, "PETG HF": 30, "PETG Rapid": 30, "PETG Translucent": 30,
    "PETG-CF": 25, "PCTG": 25, "PET": 20, "PET-CF": 20,
    # --- styrenics ---
    "ABS": 45, "ABS+": 45, "ABS-GF": 40, "ABS+GF20": 40,
    "ASA": 45, "ASA-CF": 40, "ASA-GF": 40, "HIPS": 45,
    # --- flexibles: the hardness grade does not change how thirsty it is ---
    "TPU": 14, "TPU-85A": 14, "TPU-90A": 14, "TPU-95A": 14, "TPU-55D": 14,
    "TPU-CF": 12, "TPE": 14,
    # --- engineering ---
    "PC": 14, "PC-CF": 12, "PC+ABS": 20, "PP": 30, "PPS-CF": 12,
    "PEEK": 10, "PEI": 10, "PVDF": 20, "PVB": 30,
    # --- polyamides: the thirstiest of the lot ---
    "PA": 7, "PA-CF": 7, "PA6": 7, "PA6-CF": 7, "PA6-GF": 7,
    "PA12": 10, "PA12-CF": 10, "PAHT-CF": 7, "Nylon": 7,
    # --- bio-based ---
    "PHA": 30, "GreenTEC": 45, "GreenTEC-CF": 40,
    # --- soluble supports ---
    "PVA": 5, "BVOH": 5, "Support": 30,
}
DRY_FALLBACK = 45

# How far the books may drift from the shelf before it is worth saying anything.
MISMATCH_MIN_G = 30.0
MISMATCH_PCT = 0.03


def dry_limit_for(material: str, table: dict) -> int:
    """Days of leeway for a material, falling back to its family.

    Manufacturers name products faster than any list can follow -- PETG Rapid,
    TPU-95A, PA6-CF -- and a name nobody has typed into the table used to land on
    the flat 45-day fallback, which for a PETG is wrong by half. What decides how
    fast a spool drinks is the plastic, not the trade name, so an unknown
    material is reduced to its family: everything up to the first separator, and
    then that stripped of its trailing digits.

        "PETG Rapid" -> PETG -> 30      "TPU-95A"  -> TPU  -> 14
        "PA6-CF"     -> PA6  -> 7       "ABS+ Pro" -> ABS  -> 45
    """
    name = (material or "").strip()
    if not name:
        return DRY_FALLBACK
    lower = {k.lower(): v for k, v in table.items()}
    if name.lower() in lower:
        return lower[name.lower()]

    head = re.split(r"[\s\-+_/]", name, 1)[0]
    for guess in (head, re.sub(r"\d+$", "", head)):
        if guess and guess.lower() in lower:
            return lower[guess.lower()]
    return DRY_FALLBACK

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


def slicer_parser() -> int:
    """The reading in use, without importing the slicer at module load."""
    import slicer

    return slicer.PARSER


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
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(slices)")}
        if cols and "copy_path" not in cols:
            self.db.execute(
                "ALTER TABLE slices ADD COLUMN copy_path TEXT NOT NULL DEFAULT ''")
            self.db.commit()
        if cols and "parsed_with" not in cols:
            self.db.execute(
                "ALTER TABLE slices ADD COLUMN parsed_with INTEGER NOT NULL DEFAULT 0")
            self.db.commit()

        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(rolls)")}
        if "adjusted_at" not in cols:
            self.db.execute(
                "ALTER TABLE rolls ADD COLUMN adjusted_at TEXT NOT NULL DEFAULT ''")
            self.db.commit()

        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(prints)")}
        if "group_id" not in cols:
            self.db.execute(
                "ALTER TABLE prints ADD COLUMN group_id INTEGER "
                "REFERENCES groups(id) ON DELETE SET NULL")
            self.db.commit()

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
        if "price" not in rcols:
            self.db.execute("ALTER TABLE rolls ADD COLUMN price REAL NOT NULL DEFAULT 0")
            self.db.commit()
        if "spool_type" not in rcols:
            self.db.execute(
                "ALTER TABLE rolls ADD COLUMN spool_type TEXT NOT NULL DEFAULT 'plastic'")
            self.db.commit()
        scols = {r["name"] for r in self.db.execute("PRAGMA table_info(spares)")}
        if "spool_type" not in scols:
            self.db.execute(
                "ALTER TABLE spares ADD COLUMN spool_type TEXT NOT NULL DEFAULT 'plastic'")
            self.db.commit()
        if "price" not in scols:
            self.db.execute("ALTER TABLE spares ADD COLUMN price REAL NOT NULL DEFAULT 0")
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
            # A filament can be owned without a spool ever having been fitted:
            # bought, still sealed, waiting in the drawer. There is no roll to
            # measure, so nothing is claimed about one -- the stock is what it has.
            sealed = roll is None
            if sealed:
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

            # What the ledger says, before clamping. Throwing the negative away
            # is what let the app show "empty" for a spool with plastic still on
            # it: the overshoot is the size of the disagreement between the books
            # and the shelf, and it is the only way to say how far off they are.
            ledger = 0.0 if sealed else weight - used + adjust
            remaining = 0.0 if sealed else max(0.0, ledger)
            over = 0.0 if sealed else max(0.0, -ledger)
            pct = 0.0 if sealed or not weight else (remaining / weight * 100)
            # Spools carry more than their nominal weight -- a "1 kg" spool is
            # often 1000-1030 g net -- and the empty-spool weight is an estimate
            # per brand. Overshooting by a little is normal and not worth
            # mentioning; this is the line past which it is worth a word.
            slack = max(MISMATCH_MIN_G, weight * MISMATCH_PCT)
            mismatch = over > slack
            # What the roll turned out to hold once a scale had its say. The
            # label is a claim; this is the measurement, and it is what a gram
            # off this roll actually cost.
            held = weight + adjust
            if held < 1:
                held = weight
            total_used = self.db.execute(
                "SELECT COALESCE(SUM(grams),0) g FROM print_items WHERE filament_id=?",
                (r["id"],),
            ).fetchone()["g"]
            rolls_used = self.db.execute(
                "SELECT COUNT(*) c FROM rolls WHERE filament_id=?", (r["id"],)
            ).fetchone()["c"]

            # A freshly opened spool comes dry from the factory, so if it has never
            # been dried the clock runs from the opening date.
            dry_limit = dry_limit_for(r["material"], dry_days)
            since_dry = days_since(dried or opened)
            # sealed plastic is dry: the clock starts when the bag is opened
            needs_dry = not sealed and since_dry is not None and since_dry > dry_limit

            spares = [
                {"id": s["id"], "brand": s["brand"], "weight": round(float(s["weight"]), 2),
                 "spool_type": s["spool_type"] or "plastic",
                 "price": round(float(s["price"]), 2)}
                for s in self.db.execute(
                    "SELECT id, brand, weight, spool_type, price FROM spares "
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
                    "price": round(float(roll["price"]), 2) if roll else 0.0,
                    # over what the roll really held, the same figure the cost
                    # of a print is worked out from, so the two never disagree
                    "price_per_g": round(float(roll["price"]) / held, 5)
                    if roll and roll["price"] and held else 0.0,
                    "roll_type": roll_type,
                    "tare_hint": round(self.tare_for(roll_brand, roll_type), 1),
                    "days_open": days_since(opened),
                    "days_since_dry": since_dry,
                    "dry_limit": dry_limit,
                    "needs_dry": needs_dry,
                    "used": round(used, 2),
                    "adjust": round(adjust, 2),
                    "remaining": round(remaining, 2),
                    "over": round(over, 2),
                    "mismatch": mismatch,
                    "pct": round(pct, 1),
                    "sealed": sealed,
                    # A roll nothing has been printed from, on a filament that
                    # has only ever had this one, is a spool that was recorded as
                    # open by mistake: it can go back to the drawer without
                    # losing anything. Once it has been printed from, the roll is
                    # the window those grams are counted in, so it stays.
                    "can_seal": not sealed and rolls_used <= 1 and used <= 0 and adjust == 0,
                    # unopened is not "empty": there is nothing wrong with it, so
                    # it raises no alert and does not count towards low spools
                    "low": not sealed and pct < low_pct,
                    "empty": not sealed and remaining <= 0.5,
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
        price = float(data.get("price") or 0)
        stock = int(data.get("stock") or 0)

        # Bought but not opened yet: no roll is fitted, so none is recorded. The
        # spools go straight to stock and one of them becomes the fitted roll the
        # day it is opened, which is also the day the drying clock should start.
        sealed = bool(data.get("sealed"))
        if sealed:
            stock = max(1, stock)
        else:
            self.db.execute(
                "INSERT INTO rolls(filament_id, opened_at, weight, adjust, brand, note, "
                "spool_type, price) VALUES(?,?,?,0,?,?,?,?)",
                (fid, opened, weight, brand, "first roll", stype, price),
            )
        self.db.commit()
        for _ in range(stock):
            self.add_spare(fid, brand=brand, weight=weight, spool_type=stype, price=price)
        return fid

    def seal(self, fid: int):
        """Take the fitted roll off and put that spool back in the drawer.

        For a spool recorded as open before it ever was. The roll is not thrown
        away so much as moved: it becomes a spare with the same weight, brand,
        type and price, because the physical spool is still on the shelf.
        """
        roll = self.current_roll(fid)
        if roll is None:
            return
        used = self.db.execute(
            "SELECT COALESCE(SUM(pi.grams),0) g FROM print_items pi "
            "JOIN prints p ON p.id = pi.print_id "
            "WHERE pi.filament_id=? AND p.date >= ?",
            (fid, roll["opened_at"]),
        ).fetchone()["g"]
        rolls = self.db.execute(
            "SELECT COUNT(*) c FROM rolls WHERE filament_id=?", (fid,)
        ).fetchone()["c"]
        if used > 0 or float(roll["adjust"]) != 0 or rolls > 1:
            raise ValueError("That roll has been printed from, so it cannot be sealed again.")

        self.add_spare(fid, brand=roll["brand"], weight=roll["weight"],
                       spool_type=roll["spool_type"], price=roll["price"])
        self.db.execute("DELETE FROM rolls WHERE id=?", (roll["id"],))
        self.db.commit()

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
                "UPDATE rolls SET weight=?, opened_at=?, brand=?, spool_type=?, price=? "
                "WHERE id=?",
                (weight, opened, brand,
                 norm_type(data.get("spool_type", roll["spool_type"])),
                 float(data.get("price", roll["price"]) or 0), roll["id"]),
            )
        self.db.commit()
        if "stock" in data:
            self.set_stock(fid, data["stock"])
        if data.get("sealed"):
            self.seal(fid)

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
                  spool_type: str = None, price: float = None) -> int:
        if brand is None:
            brand = self.default_brand(fid)
        if weight is None:
            weight = float(self.get_settings().get("default_spool_g", 1000))
        roll = self.current_roll(fid)
        if spool_type is None:
            spool_type = (roll["spool_type"] if roll else "plastic") or "plastic"
        if price is None:
            # a replacement usually costs what the last one did
            price = float(roll["price"]) if roll else 0.0
        cur = self.db.execute(
            "INSERT INTO spares(filament_id, brand, weight, added_at, spool_type, price) "
            "VALUES(?,?,?,?,?,?)",
            (fid, (brand or "").strip(), float(weight), today(),
             norm_type(spool_type), float(price or 0)),
        )
        self.db.commit()
        return cur.lastrowid

    def update_spare(self, sid: int, brand: str = None, weight: float = None,
                     spool_type: str = None, price: float = None):
        cur = self.db.execute("SELECT * FROM spares WHERE id=?", (sid,)).fetchone()
        if cur is None:
            raise ValueError("That spare no longer exists.")
        self.db.execute(
            "UPDATE spares SET brand=?, weight=?, spool_type=?, price=? WHERE id=?",
            ((brand if brand is not None else cur["brand"]).strip(),
             float(weight if weight is not None else cur["weight"]),
             norm_type(spool_type if spool_type is not None else cur["spool_type"]),
             float(price if price is not None else cur["price"]), sid),
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
                 spool_type: str = None, price: float = None):
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
        if price is None:
            price = float(spare["price"]) if spare else 0.0
        opened = opened or today()

        self.db.execute(
            "INSERT INTO rolls(filament_id, opened_at, weight, adjust, brand, note, "
            "spool_type, price) VALUES(?,?,?,0,?,'',?,?)",
            (fid, opened, float(weight), brand, norm_type(spool_type), float(price or 0)),
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
        self.db.execute("UPDATE rolls SET adjust=?, adjusted_at=? WHERE id=?",
                        (adjust, today(), roll["id"]))
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

    # ---------- cost ----------

    def _price_index(self) -> dict:
        """Price per gram of every roll, with the window it was fitted for.

        A print is costed with the roll that was on the printer that day, not
        with today's price: replacing a spool at a different price must not
        rewrite what last month cost.
        """
        index = {}
        for r in self.db.execute(
            "SELECT filament_id, opened_at, weight, adjust, price FROM rolls "
            "ORDER BY filament_id, opened_at, id"
        ):
            # What the roll really held, not what the label claimed. A spool
            # weighed after the books had drifted is the better figure of the
            # two, and using the nominal weight instead overcharges every print
            # that came off it -- by seventeen percent on a kilo that turned out
            # to hold nearly twelve hundred grams.
            held = float(r["weight"]) + float(r["adjust"] or 0)
            if held < 1:
                held = float(r["weight"])
            index.setdefault(r["filament_id"], []).append(
                (r["opened_at"], float(r["price"]) / held
                 if r["price"] and held else 0.0)
            )
        return index

    def _cost_of(self, index: dict, fid: int, when: str, grams: float) -> float:
        rolls = index.get(fid)
        if not rolls:
            return 0.0
        per_g = 0.0
        for opened, rate in rolls:          # rolls come in chronological order
            if opened <= when:
                per_g = rate
            else:
                break
        if per_g == 0.0:                    # printed before any priced roll
            per_g = next((r for _, r in reversed(rolls) if r), 0.0)
        return grams * per_g

    def print_costs(self) -> dict:
        """Cost of every print, by id. Empty while nothing has a price."""
        index = self._price_index()
        if not any(rate for rolls in index.values() for _, rate in rolls):
            return {}
        out = {}
        for r in self.db.execute(
            "SELECT p.id, p.date, pi.filament_id, pi.grams FROM prints p "
            "JOIN print_items pi ON pi.print_id = p.id"
        ):
            out[r["id"]] = out.get(r["id"], 0.0) + self._cost_of(
                index, r["filament_id"], r["date"], float(r["grams"]))
        return {k: round(v, 4) for k, v in out.items()}

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

    # ---------- what the slicer has shown us ----------

    KEEP_SLICES = 200

    def slice_archive(self) -> str:
        """Where the plates the app has read are kept, next to the database."""
        return os.path.join(os.path.dirname(self.path), "slices")

    def _archive_slice(self, fp: str, src: str) -> str:
        """Take our own copy of the plate file, since Bambu Studio takes its back.

        Keeping the file and not only what we understood of it means a later
        reading can be better than today's. The slot a plate pulled from was
        being read wrong until recently; with the file in hand, the plates
        already seen get the fix too, instead of only the ones sliced after it.

        The timestamp is copied with it -- the date of a plate is the date of
        its file, and a copy that looked freshly made would lie about when it
        was sliced.
        """
        if not src or not os.path.exists(src):
            return ""
        into = self.slice_archive()
        try:
            os.makedirs(into, exist_ok=True)
            dest = os.path.join(
                into, hashlib.sha1(fp.encode("utf-8")).hexdigest()[:16] + ".3mf")
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
            return dest
        except OSError:
            return ""

    def _prune_archive(self) -> None:
        """Drop the files of plates no longer in the table."""
        into = self.slice_archive()
        if not os.path.isdir(into):
            return
        keep = {os.path.basename(r["copy_path"])
                for r in self.db.execute(
                    "SELECT copy_path FROM slices WHERE copy_path <> ''")}
        for fn in os.listdir(into):
            if fn.endswith(".3mf") and fn not in keep:
                try:
                    os.remove(os.path.join(into, fn))
                except OSError:
                    pass

    def remember_slice(self, data: dict) -> None:
        """Keep a plate read from the cache, so losing the file does not lose it.

        The same plate read again is the same row: the fingerprint is the name,
        the total and every colour, which is what tells one plate from another
        when the file it came from has been renamed or replaced.
        """
        fp = (data.get("fingerprint") or "").strip()
        if not fp:
            return
        copy_path = self._archive_slice(fp, data.get("path") or "")
        self.db.execute(
            "INSERT INTO slices(fingerprint, path, copy_path, sliced_at, stamp, "
            "project, total, items, parsed_with) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(fingerprint) DO UPDATE SET path=excluded.path, "
            "sliced_at=excluded.sliced_at, stamp=excluded.stamp, "
            "copy_path=CASE WHEN excluded.copy_path <> '' "
            "THEN excluded.copy_path ELSE slices.copy_path END, "
            "items=excluded.items, parsed_with=excluded.parsed_with",
            (fp, data.get("path") or "", copy_path, data.get("sliced_at") or "",
             float(data.get("stamp") or 0), data.get("project") or "",
             float(data.get("total") or 0),
             json.dumps(data.get("items") or [], ensure_ascii=False),
             slicer_parser()),
        )
        # A cache this app has watched for a year is still only worth a page or
        # two of history, and the rest is dead weight in every backup.
        self.db.execute(
            "DELETE FROM slices WHERE id NOT IN "
            "(SELECT id FROM slices ORDER BY sliced_at DESC, id DESC LIMIT ?)",
            (self.KEEP_SLICES,))
        self.db.commit()
        self._prune_archive()

    def known_slice_files(self) -> set:
        """The files already taken in, so a sweep does not open them again."""
        return {(r["path"], r["stamp"]) for r in self.db.execute(
            "SELECT path, stamp FROM slices WHERE path <> ''")}

    def stored_slices(self, limit: int = 30, reread: bool = False) -> list:
        """Plates the app has read, newest first, whatever became of the files.

        With `reread`, where our own copy of the file survives it is read
        again rather than trusting what was written down at the time: the
        reading improves, and a plate kept as a file gets the better reading,
        not only the ones sliced after it. A better reading is written back,
        so it is paid for once and not on every look -- which matters, because
        the card asks for this every minute and opening thirty files each time
        would be a strange way to spend a minute.
        """
        import slicer

        out = []
        for r in self.db.execute(
            "SELECT * FROM slices ORDER BY sliced_at DESC, id DESC LIMIT ?",
            (int(limit),),
        ):
            items = None
            stale = r["parsed_with"] != slicer.PARSER
            if reread and stale and r["copy_path"] and os.path.exists(r["copy_path"]):
                again = slicer.read_slice(r["copy_path"])
                if again and again.get("items"):
                    items = again["items"]
                    self.db.execute(
                        "UPDATE slices SET items=?, parsed_with=? WHERE id=?",
                        (json.dumps(items, ensure_ascii=False),
                         slicer.PARSER, r["id"]))
                    self.db.commit()
            if items is None:
                try:
                    items = json.loads(r["items"])
                except ValueError:
                    items = []
            out.append({"fingerprint": r["fingerprint"], "path": r["path"],
                        "copy_path": r["copy_path"],
                        "sliced_at": r["sliced_at"], "stamp": r["stamp"],
                        "project": r["project"], "total": r["total"],
                        "items": items, "logged_at": r["logged_at"]})
        return out

    def mark_slice_logged(self, fingerprint: str) -> None:
        """A print has been recorded from this plate, so the list can say so."""
        self.db.execute("UPDATE slices SET logged_at=? WHERE fingerprint=?",
                        (today(), fingerprint))
        self.db.commit()

    # ---------- groups: several prints that are one thing ----------

    def group_id_for(self, name: str):
        """The id of a group by name, made on the spot if it is new."""
        name = (name or "").strip()
        if not name:
            return None
        row = self.db.execute(
            "SELECT id FROM groups WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        if row:
            return row["id"]
        cur = self.db.execute(
            "INSERT INTO groups(name, created_at) VALUES(?,?)", (name, now()))
        self.db.commit()
        return cur.lastrowid

    def groups(self) -> list:
        """Every group with what it has cost so far."""
        return [dict(r) for r in self.db.execute(
            "SELECT g.id, g.name, COUNT(DISTINCT p.id) prints, "
            "COALESCE(SUM(pi.grams),0) grams, MIN(p.date) first, MAX(p.date) last "
            "FROM groups g "
            "LEFT JOIN prints p ON p.group_id = g.id "
            "LEFT JOIN print_items pi ON pi.print_id = p.id "
            "GROUP BY g.id ORDER BY grams DESC, g.name COLLATE NOCASE")]

    def set_group(self, print_ids, name):
        """Put these prints in a group, or take them out of whatever they were in.

        An empty name ungroups. Groups left with nothing in them are dropped:
        a group is only ever a way of holding prints together, so an empty one
        is not a thing anybody wants to see in a list.
        """
        gid = self.group_id_for(name) if (name or "").strip() else None
        ids = [int(x) for x in (print_ids or [])]
        if ids:
            marks = ",".join("?" * len(ids))
            self.db.execute(
                "UPDATE prints SET group_id = ? WHERE id IN (%s)" % marks, [gid] + ids)
        self.db.execute(
            "DELETE FROM groups WHERE id NOT IN (SELECT DISTINCT group_id FROM prints "
            "WHERE group_id IS NOT NULL)")
        self.db.commit()
        return gid

    # ---------- what is loaded in the AMS ----------

    AMS_SLOTS_PER_UNIT = 4
    EXTERNAL = 0          # the spool holder on the side: always there, never in a unit

    def ams(self) -> list:
        """Every slot the printer has, in order, with whatever is in it.

        The external spool holder is unit 0 and always present -- it exists with
        or without an AMS, and plenty of prints come off it.
        """
        try:
            units = max(0, min(4, int(self.get_settings().get("ams_units", 1))))
        except ValueError:
            units = 1

        loaded = {(r["unit"], r["slot"]): (r["filament_id"], r["loaded_at"] or "")
                  for r in self.db.execute(
                      "SELECT unit, slot, filament_id, loaded_at FROM ams_slots")}
        by_id = {f["id"]: f for f in self.filaments()}

        def cell(unit, slot, external=False):
            fid, when = loaded.get((unit, slot), (None, ""))
            return {"unit": unit, "slot": slot, "external": external,
                    "loaded_at": when, "filament": by_id.get(fid)}

        out = []
        for unit in range(1, units + 1):
            for slot in range(1, self.AMS_SLOTS_PER_UNIT + 1):
                out.append(cell(unit, slot))
        out.append(cell(self.EXTERNAL, 1, external=True))
        return out

    def ams_by_plate_slot(self, before: str = "") -> dict:
        """AMS contents keyed by the number a sliced plate uses for that slot.

        Bambu Studio numbers a plate's filaments straight through the units, so
        the second unit starts at 5. The external holder is left out: a plate
        has no way of pointing at it, so nothing could be matched to it anyway.

        `before` is the date of a slice, and it is what keeps a hand-kept tab
        from lying about the past: a spool recorded as loaded *after* a plate
        was sliced was not in that slot when it was sliced, so it is no
        evidence about it. Loaded the same day counts -- fitting a spool and
        slicing with it happen within minutes of each other, and the tab only
        stores the day.
        """
        try:
            units = max(0, min(4, int(self.get_settings().get("ams_units", 1))))
        except ValueError:
            units = 1
        # Straight off the slots table rather than through ams(): that one
        # builds the whole inventory to hang a filament on each slot, and this
        # is asked once per plate -- thirty plates were costing thirty
        # inventories to learn thirty filament ids.
        out = {}
        for r in self.db.execute(
            "SELECT unit, slot, filament_id, loaded_at FROM ams_slots"
        ):
            if r["unit"] == self.EXTERNAL or r["unit"] > units:
                continue
            if before and (r["loaded_at"] or "") > before[:10]:
                continue
            n = (r["unit"] - 1) * self.AMS_SLOTS_PER_UNIT + r["slot"]
            out[n] = r["filament_id"]
        return out

    def set_ams_slot(self, unit: int, slot: int, filament_id=None):
        """Put a spool in a slot, or empty it.

        A spool can only be in one slot: loading it somewhere else takes it out
        of wherever it was, because that is what happened in the real world.
        """
        unit, slot = int(unit), int(slot)
        self.db.execute("DELETE FROM ams_slots WHERE unit=? AND slot=?", (unit, slot))
        if filament_id:
            self.db.execute("DELETE FROM ams_slots WHERE filament_id=?", (int(filament_id),))
            self.db.execute(
                "INSERT INTO ams_slots(unit, slot, filament_id, loaded_at) VALUES(?,?,?,?)",
                (unit, slot, int(filament_id), today()))
        self.db.commit()

    # ---------- what the slicer said -> which spool it was ----------

    def remember_match(self, signature: str, fid: int):
        """Learn a confirmation so the same slice never has to be guessed twice."""
        sig = (signature or "").strip()
        if not sig:
            return
        self.db.execute(
            "INSERT INTO slicer_map(signature, filament_id, hits, last_used) "
            "VALUES(?,?,1,?) ON CONFLICT(signature) DO UPDATE SET "
            "filament_id=excluded.filament_id, hits=hits+1, last_used=excluded.last_used",
            (sig, int(fid), today()),
        )
        self.db.commit()

    def recall_match(self, signature: str):
        r = self.db.execute(
            "SELECT filament_id FROM slicer_map WHERE signature=?",
            ((signature or "").strip(),)
        ).fetchone()
        return r["filament_id"] if r else None

    def forget_match(self, signature: str):
        self.db.execute("DELETE FROM slicer_map WHERE signature=?", (signature,))
        self.db.commit()

    def learned_matches(self) -> list:
        return [dict(r) for r in self.db.execute(
            "SELECT m.signature, m.hits, m.last_used, f.id, f.name, f.hex "
            "FROM slicer_map m JOIN filaments f ON f.id = m.filament_id "
            "ORDER BY m.hits DESC, m.last_used DESC")]

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
               date_from: str = "", date_to: str = "", group_id: int = None) -> list:
        sql = "SELECT p.*, g.name AS group_name FROM prints p "\
              "LEFT JOIN groups g ON g.id = p.group_id"
        args = []
        where = []
        if filament_id:
            sql += " JOIN print_items pi ON pi.print_id = p.id"
            where.append("pi.filament_id = ?")
            args.append(filament_id)
        if search:
            # the group counts as part of the name for searching: looking for
            # "casa UP" should find its pieces whatever each one is called
            where.append("(p.project LIKE ? OR g.name LIKE ?)")
            args += [f"%{search}%", f"%{search}%"]
        if group_id is not None:
            where.append("p.group_id = ?" if group_id else "p.group_id IS NULL")
            if group_id:
                args.append(group_id)
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
        costs = self.print_costs()
        out = []
        for r in rows:
            items = items_by_print.get(r["id"], [])
            out.append(
                {
                    "id": r["id"],
                    "cost": round(costs.get(r["id"], 0.0), 2),
                    "date": r["date"],
                    "project": r["project"],
                    "group_id": r["group_id"],
                    "group_name": r["group_name"] or "",
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

        # "group" absent means leave it alone -- an edit that does not mention
        # the group must not silently pull a print out of one
        gid = self.group_id_for(data["group"]) if "group" in data else None
        set_group = "group" in data

        if pid:
            self.db.execute(
                "UPDATE prints SET date=?, project=?, notes=?, failed=?, url=? WHERE id=?",
                (pdate, project, notes, failed, url, pid),
            )
            if set_group:
                self.db.execute("UPDATE prints SET group_id=? WHERE id=?", (gid, pid))
            self.db.execute("DELETE FROM print_items WHERE print_id=?", (pid,))
        else:
            cur = self.db.execute(
                "INSERT INTO prints(date, project, notes, created_at, failed, url, group_id) "
                "VALUES(?,?,?,?,?,?,?)",
                (pdate, project, notes, now(), failed, url, gid),
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
        # What each month was actually made of. The monthly chart is the one
        # place the whole palette shows up at once, and the colours are not a
        # decoration: they are the filaments that were spent.
        splits = {}
        for r in db.execute(
            "SELECT substr(p.date,1,7) m, f.name, f.hex, COALESCE(SUM(pi.grams),0) g "
            "FROM prints p JOIN print_items pi ON pi.print_id = p.id "
            "JOIN filaments f ON f.id = pi.filament_id "
            "GROUP BY m, f.id ORDER BY m, g DESC"
        ):
            splits.setdefault(r["m"], []).append(
                {"name": r["name"], "hex": r["hex"], "grams": round(r["g"], 2)})
        for entry in by_month:
            entry["split"] = splits.get(entry["month"], [])

        by_filament = [
            {"name": r["name"], "hex": r["hex"], "grams": round(r["g"], 2), "prints": r["n"]}
            for r in db.execute(
                "SELECT f.name, f.hex, COALESCE(SUM(pi.grams),0) g, COUNT(DISTINCT pi.print_id) n "
                "FROM print_items pi JOIN filaments f ON f.id = pi.filament_id "
                "GROUP BY f.id ORDER BY g DESC"
            )
        ]
        # Every bar in Statistics is made of the filaments that made it, so each
        # one carries the split it is built from -- the same idea as the monthly
        # chart, and the reason none of them needs an invented colour.
        def split_by(key_sql, group_sql):
            out = {}
            for r in db.execute(
                "SELECT %s k, f.name, f.hex, COALESCE(SUM(pi.grams),0) g "
                "FROM prints p JOIN print_items pi ON pi.print_id = p.id "
                "JOIN filaments f ON f.id = pi.filament_id "
                "GROUP BY %s ORDER BY g DESC" % (key_sql, group_sql)
            ):
                out.setdefault(r["k"], []).append(
                    {"name": r["name"], "hex": r["hex"], "grams": round(r["g"], 2)})
            return out

        mat_split = split_by("f.material", "f.material, f.id")
        mat_prints = {r["m"]: r["n"] for r in db.execute(
            "SELECT f.material m, COUNT(DISTINCT pi.print_id) n FROM print_items pi "
            "JOIN filaments f ON f.id = pi.filament_id GROUP BY f.material")}
        by_material = [
            {"material": r["material"], "grams": round(r["g"], 2),
             "prints": mat_prints.get(r["material"], 0),
             "split": mat_split.get(r["material"], [])}
            for r in db.execute(
                "SELECT f.material, COALESCE(SUM(pi.grams),0) g "
                "FROM print_items pi JOIN filaments f ON f.id = pi.filament_id "
                "GROUP BY f.material ORDER BY g DESC"
            )
        ]
        # A print in a group counts under the group; one without keeps its own
        # name. That is the whole trick: grouping changes nothing for the prints
        # that are a project all by themselves.
        NAME = "COALESCE((SELECT g.name FROM groups g WHERE g.id = p.group_id), p.project)"
        proj_split = split_by(NAME, NAME + ", f.id")
        proj_prints = {r["k"]: r["n"] for r in db.execute(
            "SELECT %s k, COUNT(*) n FROM prints p GROUP BY k" % NAME)}
        # What a project cost is the sum of what its prints cost, each with the
        # roll that was fitted the day it was printed. Working it out here and
        # not in the query is what keeps that rule in one place.
        all_costs = self.print_costs()
        proj_cost = {}
        if all_costs:
            for r in db.execute("SELECT p.id, %s k FROM prints p" % NAME):
                c = all_costs.get(r["id"])
                if c:
                    proj_cost[r["k"]] = proj_cost.get(r["k"], 0.0) + c
        top_projects = [
            {"project": r["gname"], "grams": round(r["g"], 2),
             "group_id": r["gid"],
             "prints": proj_prints.get(r["gname"], 0),
             "cost": round(proj_cost.get(r["gname"], 0.0), 2),
             "split": proj_split.get(r["gname"], [])}
            for r in db.execute(
                # the alias must not be "project": prints has a column by that
                # name, and SQLite would bind GROUP BY to the column instead of
                # to this expression -- grouping by the old names while showing
                # the group's, which reads as a group that lost most of its grams
                "SELECT %s AS gname, MAX(p.group_id) gid, "
                "COALESCE(SUM(pi.grams),0) g FROM prints p "
                "JOIN print_items pi ON pi.print_id = p.id "
                "GROUP BY gname ORDER BY g DESC LIMIT 12" % NAME
            )
        ]
        # Every bar in this app is made of the filaments that made it, so this
        # one carries its colours too rather than being a grey stub.
        DOW = "CAST(strftime('%w', p.date) AS INTEGER)"
        dow_split = split_by(DOW, DOW + ", f.id")
        by_weekday = [{"grams": 0.0, "split": dow_split.get(i, [])} for i in range(7)]
        for r in db.execute(
            "SELECT %s w, COALESCE(SUM(pi.grams),0) g "
            "FROM prints p JOIN print_items pi ON pi.print_id = p.id GROUP BY w" % DOW
        ):
            by_weekday[r["w"]]["grams"] = round(r["g"], 2)

        tot = db.execute(
            "SELECT COUNT(DISTINCT p.id) n, COALESCE(SUM(pi.grams),0) g, "
            "MIN(p.date) first, MAX(p.date) last FROM prints p "
            "LEFT JOIN print_items pi ON pi.print_id = p.id"
        ).fetchone()
        bad = db.execute(
            "SELECT COUNT(DISTINCT p.id) n, COALESCE(SUM(pi.grams),0) g FROM prints p "
            "LEFT JOIN print_items pi ON pi.print_id = p.id WHERE p.failed = 1"
        ).fetchone()
        # Which colours a failure ate, not only how much: a run of failures on
        # the one spool you are short of is a different problem from the same
        # grams spread over everything.
        fail_split = {}
        for r in db.execute(
            "SELECT p.project k, f.name, f.hex, COALESCE(SUM(pi.grams),0) g "
            "FROM prints p JOIN print_items pi ON pi.print_id = p.id "
            "JOIN filaments f ON f.id = pi.filament_id "
            "WHERE p.failed = 1 GROUP BY p.project, f.id ORDER BY g DESC"
        ):
            fail_split.setdefault(r["k"], []).append(
                {"name": r["name"], "hex": r["hex"], "grams": round(r["g"], 2)})
        worst_fail = [
            {"project": r["project"], "grams": round(r["g"], 2), "n": r["n"],
             "split": fail_split.get(r["project"], [])}
            for r in db.execute(
                "SELECT p.project, COALESCE(SUM(pi.grams),0) g, COUNT(DISTINCT p.id) n "
                "FROM prints p JOIN print_items pi ON pi.print_id = p.id "
                "WHERE p.failed = 1 GROUP BY p.project ORDER BY g DESC LIMIT 8"
            )
        ]

        fils = self.filaments()
        month = date.today().strftime("%Y-%m")
        costs = self.print_costs()
        dates = {r["id"]: r["date"] for r in db.execute("SELECT id, date FROM prints")}
        failed_ids = {r["id"] for r in db.execute("SELECT id FROM prints WHERE failed = 1")}
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
            "has_prices": bool(costs),
            "total_cost": round(sum(costs.values()), 2),
            "month_cost": round(sum(c for pid, c in costs.items()
                                    if dates.get(pid, "").startswith(month)), 2),
            "failed_cost": round(sum(costs.get(pid, 0.0) for pid in failed_ids), 2),
            "stock_value": round(sum(
                f["remaining"] * f["price_per_g"]
                + sum(sp["price"] for sp in f["spares"]) for f in fils), 2),
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
