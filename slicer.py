"""Reads what Bambu Studio just sliced.

Every time you slice, Bambu Studio writes a project into its own temporary
folder. Inside is a `slice_info.config` listing, per filament, the grams and
metres it will use, the material, the colour on screen and the object name.
That is everything a print record needs, so it can be offered for confirmation
instead of typed by hand.

Two things this deliberately does not do:

* It does not identify the spool from the colour alone. The colour in a sliced
  file is whatever was picked on screen or inherited from the AMS slot, and it
  routinely has nothing to do with the spool actually loaded. Material and
  product line come first, colour only breaks ties, and a confirmation is
  always asked for.
* It does not watch the printer. This fires when you slice, not when you print,
  so a slice you never printed is simply dismissed.

The folder is Bambu Studio's private cache rather than a documented interface.
If a future version moves it, nothing else in the app is affected: the feature
just stops finding files.
"""

import os
import re
import tempfile
import zipfile
from datetime import datetime

CACHE_DIRNAME = "bamboo_model"


def candidate_dirs() -> list:
    """The folders a Bambu Studio slice cache is normally found in.

    Usually one: %TEMP%\bamboo_model. The second entry matters when TEMP has
    been redirected somewhere else, which leaves the slices behind in the
    account's own temp folder.
    """
    seen, out = set(), []
    bases = [tempfile.gettempdir(),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")]
    for base in bases:
        if not base:
            continue
        path = os.path.join(base, CACHE_DIRNAME)
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def cache_dir(custom: str = "") -> str:
    """The folder to watch: the one set by hand, or the first that exists.

    A folder set by hand is returned whether it exists or not, so the interface
    can say it is wrong instead of silently going back to the default.
    """
    if custom:
        return custom
    found = [p for p in candidate_dirs() if os.path.isdir(p)]
    return found[0] if found else candidate_dirs()[0]


def folder_status(custom: str = "") -> dict:
    """What the interface needs to show about the folder being watched."""
    path = cache_dir(custom)
    exists = os.path.isdir(path)
    plates = 0
    if exists:
        for _dirpath, _dirs, files in os.walk(path):
            plates += sum(1 for f in files if f.lower().endswith(".3mf"))
    return {"path": path, "exists": exists,
            "custom": bool(custom), "plates": plates,
            "candidates": candidate_dirs()}


def _attrs(fragment: str) -> dict:
    return dict(re.findall(r'(\w+)="([^"]*)"', fragment))


def read_slice(path: str) -> dict:
    """Pull the filament usage out of one sliced .3mf.

    Returns {} for anything that is not a readable slice, so a half-written file
    being watched is simply skipped.
    """
    try:
        z = zipfile.ZipFile(path)
        names = z.namelist()
    except (zipfile.BadZipFile, OSError):
        return {}

    info = next((n for n in names if n.endswith("slice_info.config")), None)
    if not info:
        return {}
    try:
        xml = z.read(info).decode("utf-8", "ignore")
    except (KeyError, OSError):
        return {}

    items = []
    for frag in re.findall(r"<filament ([^/>]+)/>", xml):
        a = _attrs(frag)
        try:
            grams = float(a.get("used_g") or 0)
        except ValueError:
            grams = 0.0
        if grams <= 0:
            continue
        try:
            slot = int(a.get("id") or 0)
        except ValueError:
            slot = 0
        items.append({
            "material": (a.get("type") or "").strip(),
            "hex": (a.get("color") or "").strip(),
            "grams": round(grams, 2),
            "metres": round(float(a.get("used_m") or 0), 2),
            "tray": (a.get("tray_info_idx") or "").strip(),
            # which filament slot the plate pulled this from, 1-based
            "slot": slot,
        })
    if not items:
        return {}

    # The object name is the closest thing to a project name. Several objects on
    # one plate get joined so the user recognises what they sliced.
    objects = list(dict.fromkeys(
        m for m in re.findall(r'<object[^>]*name="([^"]+)"', xml) if m))
    project = ", ".join(_clean_name(o) for o in objects[:3])

    # There is one profile per slot the printer has, but only the slots a plate
    # actually used appear above. Pairing them by position hands the filament in
    # slot 4 the profile of slot 1 on any plate that does not start at 1 -- and
    # the product line in that profile is the strongest term in the ranking, so
    # a single-colour plate off the last slot was being matched against the
    # wrong product line entirely.
    profiles = _profiles(z, names)
    for i, item in enumerate(items):
        at = item["slot"] - 1 if item["slot"] else i
        item["profile"] = profiles[at] if 0 <= at < len(profiles) else ""

    return {
        "path": path,
        "project": project,
        "items": items,
        "total": round(sum(i["grams"] for i in items), 2),
        "sliced_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds"),
    }


def _clean_name(name: str) -> str:
    """'chimenea_escalada_D2.2.stl' -> 'chimenea escalada D2.2'."""
    base = re.sub(r"\.(stl|3mf|step|stp|obj)$", "", name.strip(), flags=re.I)
    return re.sub(r"[_]+", " ", base).strip()


def _profiles(z, names) -> list:
    """Filament profile names per slot, e.g. 'Bambu PLA Matte @BBL A1'.

    The product line in there ("Matte", "Silk") describes the filament and is
    worth matching on. The vendor is not: when a material only exists under one
    manufacturer's profile you are forced to pick it whatever spool is loaded.
    """
    cfg = next((n for n in names if n.endswith("project_settings.config")), None)
    if not cfg:
        return []
    try:
        import json

        data = json.loads(z.read(cfg).decode("utf-8", "ignore"))
    except (KeyError, OSError, ValueError):
        return []
    ids = data.get("filament_settings_id")
    return [str(x) for x in ids] if isinstance(ids, list) else []


# Bump this when read_slice starts getting something out of a plate that it did
# not before. Plates kept as files are read again once, and only once, after a
# version that knows more about them.
PARSER = 2


def latest_slices(limit: int = 8, since: float = 0, custom: str = "",
                  skip=None) -> list:
    """The most recently sliced projects, newest first.

    `skip` is a set of (path, mtime) already known. Walking the folder is
    cheap; opening every plate in it is not, and a sweep that runs every
    minute would keep re-reading the same files to learn nothing. Skipped
    files do not count towards the limit either -- the limit is on how much
    new work one sweep does.
    """
    root = cache_dir(custom)
    if not os.path.isdir(root):
        return []
    found = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(".3mf"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if mtime > since and (not skip or (full, mtime) not in skip):
                found.append((mtime, full))
    found.sort(reverse=True)

    # One slicing run leaves several near-identical files in the cache. They are
    # the same print, so only the newest of each is worth offering.
    out, seen = [], set()
    for mtime, full in found:
        data = read_slice(full)
        if not data:
            continue
        key = fingerprint(data)
        if key in seen:
            continue
        seen.add(key)
        data["fingerprint"] = key
        data["stamp"] = mtime
        out.append(data)
        if len(out) >= limit:
            break
    return out


def fingerprint(data: dict) -> str:
    """What tells one plate from another, independent of the file it came from.

    The name, the total and every colour. Bambu Studio renames and rewrites the
    files in its cache, so the path is no use as an identity -- and the app has
    to recognise a plate it has already read even when the file it read it from
    is gone.
    """
    return "|".join([
        data.get("project") or "",
        "%.2f" % float(data.get("total") or 0),
    ] + ["%s:%s:%.2f" % (i.get("material") or "", i.get("hex") or "",
                         float(i.get("grams") or 0))
         for i in (data.get("items") or [])])


ns = None                    # filled lazily to avoid a circular import


def _lines(profile: str) -> set:
    """Words in a profile that describe the filament rather than the vendor.

    'Bambu PLA Matte @BBL A1' -> {'matte'}. The vendor is dropped on purpose: a
    material that only exists under one manufacturer's profile forces that
    choice regardless of which spool is loaded, so it says nothing about the
    spool. The product line does.
    """
    base = re.sub(r"\s*@.*$", "", profile or "").lower()
    skip = {"bambu", "generic", "lab", "pla", "petg", "abs", "asa", "tpu", "pc",
            "pa", "pva", "hips", "pp", "pet", "pctg", "filament", "basic",
            "support", "for"}
    return {w for w in re.split(r"[^a-z0-9+]+", base) if w and w not in skip and len(w) > 2}


# How far the colour can be off before a slot's own answer is worth a second
# look. Two colours you would call the same shade sit under 3; ten is a colour
# you would name differently but not argue about.
COLOUR_DOUBT = 10.0


def candidates(item: dict, filaments: list, remembered=None, loaded=None) -> dict:
    """Which spool the slicer most likely meant, and why.

    Ranking, strongest first:

    1. a confirmation already given for this exact slice signature
    2. what the AMS says is in the slot this plate pulled from
    3. same material  (a hard filter -- PLA is never PETG)
    4. the product line matches, e.g. a "Matte" profile against a filament
       whose name says matte
    5. colour, only to break ties, because it is the least trustworthy signal

    `loaded` maps a plate's filament slot to the spool the AMS tab says was in
    it when the plate was sliced. It is not a tie-break: a spool that was
    physically in the slot the plate pulled from is the spool the print used,
    whatever colour was picked on screen -- and the colour on screen disagrees
    most of the time, which is the whole reason any of this is hard.

    Because that tab is kept by hand, it is only believed after two checks it
    cannot pass while out of date. It is asked with the date of the slice, so a
    slot fitted afterwards is never offered; and it goes through the same
    material filter as everything else, so a tab claiming PLA where the plate
    says PETG drops out. Past both, it answers -- and when the colour flatly
    disagrees the answer is shown as one to check rather than as settled.

    `confident` is only true for a remembered match, for a slot whose colour
    also roughly agrees, or for a near-perfect colour on a same-material,
    same-line filament.
    """
    global ns
    if ns is None:
        import catalog as ns

    mat = (item.get("material") or "").strip().lower()
    lines = _lines(item.get("profile"))
    target = ns.lab(item.get("hex"))
    in_slot = (loaded or {}).get(item.get("slot") or 0)

    family = mat.split()[0] if mat else ""

    scored = []
    for f in filaments:
        if f.get("archived"):
            continue
        fmat = (f.get("material") or "").strip().lower()
        # The slicer reports the family, so a spool recorded as "PLA HS" must
        # still be offered when it says "PLA" -- just below the exact matches.
        exact = bool(mat) and fmat == mat
        same_family = bool(family) and fmat.split()[:1] == [family]
        if mat and not (exact or same_family):
            continue
        name = (f.get("name") or "").lower()
        line_hit = bool(lines) and any(w in name for w in lines)
        other = ns.lab(f.get("hex"))
        delta = ns.delta_e(target, other) if (target and other) else 999.0
        # One score rather than a strict order of tie-breaks, so a much closer
        # colour can still beat a filament that merely matches the product line.
        # The penalties are in delta-E units: about the gap between two colours
        # you would call different.
        score = delta + (0 if line_hit else 10) + (0 if exact else 4)
        scored.append({
            "id": f["id"], "name": f["name"], "hex": f.get("hex"),
            "delta": round(delta, 2), "line_hit": line_hit, "exact_material": exact,
            # reaching here means the material agrees, so a spool the tab puts
            # in this slot is one the plate really could have used
            "in_ams": in_slot is not None and f["id"] == in_slot,
            "score": round(score, 2), "remaining": f.get("remaining", 0),
        })
    scored.sort(key=lambda c: c["score"])

    pick, confident, from_slot = None, False, 0
    if remembered:
        hit = next((c for c in scored if c["id"] == remembered), None)
        if hit is None:
            hit = next((
                {"id": f["id"], "name": f["name"], "hex": f.get("hex"),
                 "delta": 0.0, "line_hit": True, "in_ams": False,
                 "remaining": f.get("remaining", 0)}
                for f in filaments if f["id"] == remembered), None)
        if hit:
            scored = [hit] + [c for c in scored if c["id"] != hit["id"]]
            pick, confident = hit["id"], True
    # The slot answers before the score does. Moving it to the front rather
    # than weighting it also keeps two slots of one plate off the same spool:
    # a spool is in one slot or none, so at most one slot can claim it.
    if pick is None:
        hit = next((c for c in scored if c["in_ams"]), None)
        if hit:
            scored = [hit] + [c for c in scored if c["id"] != hit["id"]]
            pick = hit["id"]
            confident = hit["delta"] < COLOUR_DOUBT
            from_slot = item.get("slot") or 0
    if pick is None and scored:
        best = scored[0]
        pick = best["id"]
        confident = best["line_hit"] and best["delta"] < 3

    return {"pick": pick, "confident": confident, "options": scored[:8],
            # reported only when the slot is why this spool was chosen, so the
            # card can say where the suggestion came from
            "from_slot": from_slot}


def signature(item: dict) -> str:
    """A stable key for "this filament, sliced this way".

    Product line plus colour: the same combination coming round again means the
    same spool, which is what makes a confirmation worth remembering.
    """
    profile = re.sub(r"\s*@.*$", "", item.get("profile") or "").strip().lower()
    return "|".join((
        (item.get("material") or "").lower(),
        profile,
        (item.get("hex") or "").lower(),
    ))
