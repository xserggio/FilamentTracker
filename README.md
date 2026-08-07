<div align="center">

<img src="brand/benchy-navy-tile.png" width="96" alt="Filament Tracker">

# Filament Tracker

**Keep track of your 3D printing filament: how much is left on each spool, what
you have in stock, and where every gram went.**

A small desktop app for Windows. No account, no cloud, no telemetry — your data
lives in a single SQLite file next to the executable.

[Español](README.es.md) · [Download](#download) · [Manual](#manual)

<img src="docs/dashboard.png" alt="Dashboard">

</div>

---

## Why

Most of us end up with a spreadsheet: a row per print, a formula per spool, and a
sinking feeling every time we swap a roll. This app is that spreadsheet, except it
knows what a spool is — that a roll has a brand, that it runs out, that you replace
it with another one that might be from a different manufacturer, and that PETG
needs drying more often than PLA.

## Features

- **Live spool levels.** Every print you log is subtracted from the roll that is
  currently fitted. Open a new roll and the counter starts over without losing
  history.
- **Spares with their own identity.** Stock is not a counter: each spare spool has
  its own brand, spool type and weight, so your black can be Bambu Lab while its
  two spares are eSUN.
- **Weigh instead of guess.** Put the spool on a scale, enter the reading, and the
  app subtracts the empty-spool weight for that brand and spool type.
- **Drying reminders.** Per-material intervals, counted from opening and reset
  every time you log a drying.
- **Failed prints.** Flag a print as failed and correct the grams it actually used —
  the material that never came out goes back on the roll.
- **Reads what Bambu Studio sliced.** Slice a plate and a card offers to log
  the print with the grams already filled in and a spool suggested per colour.
  You confirm; it remembers.
- **Statistics.** Grams per month, most used filaments, split by material, hungriest
  projects and wasted material.
- **Excel import.** Bring across an existing spreadsheet in one go.
- **Six languages.** English, Spanish, French, German, Portuguese and Italian.

## Download

**1.** Download **`Filament Tracker.exe`** from the
[latest release](../../releases/latest).

**2.** Put it wherever you like — Desktop, Documents, a USB stick.

**3.** Double-click it. That's it.

No installer, no Python, no command line. It is one file; the first time you run it
a `data` folder appears next to it with your database inside.

<details>
<summary><b>Windows says "Windows protected your PC"</b></summary>

That is SmartScreen, and it says that about every program that has not paid for a
code-signing certificate. Click **More info** and then **Run anyway**.

If you would rather not take my word for it, the source is all here and you can
[build the executable yourself](#building-the-executable).
</details>

<details>
<summary><b>Nothing happens, or it mentions WebView2</b></summary>

The app draws its interface with Microsoft's WebView2 runtime. Windows 11 ships with
it; some Windows 10 installs do not. If it is missing, the app says so and offers to
open the [download page](https://developer.microsoft.com/microsoft-edge/webview2/) —
install it, then run the app again.
</details>

<details>
<summary><b>Moving the app to another folder or PC</b></summary>

Take the `data` folder with it. That folder is your database; leave it behind and
the app starts empty.
</details>

---

## Manual

### The model in one paragraph

A **filament** is a material and colour you print with — `PLA - black`. At any time
it has one **roll** fitted, with a weight, an opening date, a brand and a spool
type. It may also have **spares** waiting in a drawer, each with their own brand,
type and weight. A **print** records a date, a project and how many grams of each
filament it used.

Remaining grams on the fitted roll are:

```
remaining = roll weight − grams printed since it was opened + manual correction
```

Prints dated *before* the roll was opened count towards the filament's lifetime
total but do not touch the current roll. That is what lets you open a new spool
without wiping your history.

### Inventory

<img src="docs/inventory.png" alt="Inventory">

One card per filament, with the level of the fitted roll and a bar that turns amber
and then red as it empties. Click the name to open its **detail sheet**: every roll
it has had, with brand, how much was consumed from each and how long it lasted, plus
the list of prints that used it.

The card footer has, in order: days since the roll was opened, the spare counter
(`−` / number / `+`), a **scale** button, a **droplet** button and **New spool**.

| Button | What it does |
|---|---|
| `−` / `+` | Remove or add a spare. New spares inherit the fitted roll's brand and type. |
| the number | Opens the spare list — brand, spool type and weight, editable per spare. |
| ⚖ | Correct the grams left, weighing the spool. |
| 💧 | Log a drying. |
| New spool | Fit a fresh roll, optionally consuming one of the spares. |

Filters at the top: text search, material, sort order, *low only*, *with spares* and
*show archived*.

### Logging a print

`New print` takes a date, a project name, one row per colour with its grams, an
optional link to the model page, and notes. There is no four-colour limit.

<img src="docs/history.png" alt="History">

In the history, each row has a link button (if you saved a URL), a **`!`** button,
an edit button and a delete button.

### After slicing in Bambu Studio

When you slice, Bambu Studio writes the plate into a folder of its own, and in
there are the grams of every filament it is about to use. Filament Tracker reads
that folder and offers the print instead of making you type it:

> **Just sliced** · chimenea escalada D2.2 — 7.5 g · PLA
> *Not now* · **Log this print**

**Log this print** opens the normal form with the project name, the grams and a
spool already picked per colour. Nothing is recorded until you press Save, and
you can change anything first.

**The colour in a sliced file is not the spool you loaded.** Most of the time you
pick a profile because it is the only one that exists — there is no Matte under
Generic, so you select Bambu Lab's whatever spool is on the printer — or you
change the colour on the printer's screen and the slicer never hears about it.
So the suggestion goes on the material and the product line first (a *Matte*
profile looks for a matte spool), and only uses the colour to break a tie. A row
it is not sure about is highlighted in amber with *Check the spool*.

**It learns.** The spool you confirm is remembered against that exact
material + profile + colour, so the next time the same thing is sliced there is
nothing to guess. Settings › Bambu Studio lists everything it has learned, and
anything wrong can be forgotten with one click.

The card can be switched off in Settings › Bambu Studio. *Not now* hides it and
brings it back next time; the **×** dismisses that slice for good. A slice you
never printed is simply never confirmed.

This reads Bambu Studio's own temporary folder, which is not a documented
interface. If a future version moves it, the card just stops appearing — nothing
else changes.

### Failed prints

The **`!`** button opens a short dialog that does two things: marks the print as
failed, and lets you **correct the grams actually used**. A print that stopped
halfway did not consume what you planned, so you enter what really came out and it
replaces the original figures — the unused material goes back on the roll and the
statistics recalculate. A colour set to 0 g is dropped from the print.

Failed prints still subtract material, because it was extruded all the same. They
just get tagged, can be filtered with *failed only*, and feed the **Wasted material**
figure in Statistics.

### Drying

Every roll stores the date of its last drying. The clock starts when the roll is
opened (a fresh spool comes dry) and resets each time you log one.

The card shows a droplet badge: blue with the number of days when it is fine, amber
with *dry it* once past the limit. It also appears in the dashboard alerts.

Limits depend on the plastic and live in **Settings → Drying by material**. The
defaults: PLA and its variants 60 days, PLA-CF/ABS/ASA 45, PETG 30, TPU and PC 14,
PA/Nylon/PVA 7. Anything not listed uses 45.

### Weighing a spool

In the ⚖ dialog you enter what the scale reads with the whole spool on it and the
**empty spool weight**; the grams left are worked out for you.

That weight is pre-filled from the roll's **brand** and **spool type** — both are
dropdowns, and changing either updates the figure. The starting values come from
[SpoolmanDB](https://github.com/Donkie/SpoolmanDB), cross-checked against
[The Empty Spool](https://theemptyspool.cc/) and the Bambu Lab forum:

| Brand | Plastic | Cardboard |
|---|---|---|
| Bambu Lab | 250 g | 196 g |
| eSUN | 240 g | 170 g |
| Prusament | 193 g | — |
| Eryone | 187 g | — |
| Geeetech | 180 g | — |
| Overture | — | 155 g |
| Elegoo | 154 g | 154 g |
| Polymaker | — | 140 g |
| Sunlu | 130 g | — |
| Creality | 225 g | 120 g |
| Anycubic | 127 g | 125 g |
| Hatchbox | 251 g | — |
| JAYO | — | 120 g |
| Unknown brand | 220 g | 160 g |

**Treat these as a starting point.** The spread is wide even within one brand —
Bambu ranges from 196 to 253 g, eSUN from 161 to 253 — because the tooling changes
between versions. So the moment you correct the tare by weighing one of your own
spools, the app stores **your** number for that brand and type and uses it from then
on. They are also editable by hand in **Settings → Empty spool weight by brand**.

### Statistics

<img src="docs/stats.png" alt="Statistics">

Grams per month, most used filaments, split by material, hungriest projects and
wasted material. The KPI tiles on the Dashboard and here are clickable and take you
to the matching view with the filters already applied.

### Importing from Excel

**Settings → Import from Excel** reads a spreadsheet exported from Google Sheets
with the sheets `Inventario`, `Historial de Impresiones` and
`Respuestas de formulario 2` (the shape a Google Form produces). Rows sharing a date
and project are grouped into one multi-colour print. Re-importing the same file does
not duplicate anything.

If your spreadsheet has a different shape, `importer.py` is about 150 readable lines.

### Backups

Every time the app starts it saves a copy of the database in `data/backups/`, one
per day, keeping the last 10. It uses SQLite's backup API rather than copying the
file, so the copy is consistent even mid-write. **Settings → Data** shows how many
there are, lets you force one and opens the folder.

### Your data

Everything lives in `data/filaments.db`, a plain SQLite file. Nothing is sent
anywhere. To back it up, copy that file. To inspect it, any SQLite browser will do.

---

## For developers

### Running from source

```bash
git clone https://github.com/xserggio/FilamentTracker.git
cd FilamentTracker
py -m pip install -r requirements.txt
py app.py
```

Python 3.10+ and the two dependencies in `requirements.txt` (`pywebview` and
`openpyxl`).

### Building the executable

```bash
py -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File build.ps1
```

Leaves `dist/Filament Tracker.exe` with the icon from `brand/`.

`core.py` deliberately separates read-only resources (`web/`, which PyInstaller
extracts to a temporary folder) from data that must survive (the database, always
next to the executable). Without that split the database would end up in the temp
folder and vanish on exit.

## Project layout

```
app.py         pywebview window and the bridge to the interface
core.py        SQLite schema, paths, remaining-grams maths and statistics
importer.py    Excel reader
slicer.py      reads the plates Bambu Studio has sliced
build.ps1      PyInstaller packaging
web/           index.html · style.css · app.js · i18n.js · icon.ico
brand/         logo in navy, black and white (svg, png, ico)
tools/         demo database generator and screenshot script
data/          your database (not in the repo)
```

## Credits

Empty spool weights from [SpoolmanDB](https://github.com/Donkie/SpoolmanDB) and
[The Empty Spool](https://theemptyspool.cc/), both community-maintained. Built on
[pywebview](https://pywebview.flowrl.com/).

## License

[MIT](LICENSE).
