# Brand assets

The Benchy mark, vectorised, ready for packaging and documentation.

| File | Colour | Use |
|---|---|---|
| `benchy-navy-tile.png` · `icon-navy-tile.ico` | `#1B2A52` plate, white mark | **Executable and installer icon.** The plate gives it its own background, so it stays readable on both the dark and the light Windows taskbar. |
| `benchy-black-tile.png` · `icon-black-tile.ico` | `#111318` plate, white mark | Same idea, in black. |
| `benchy-navy.svg` · `.png` · `icon-navy.ico` | `#1B2A52` | Flat, transparent background. Light backgrounds only. |
| `benchy-black.svg` · `.png` · `icon-black.ico` | `#111318` | Print and monochrome documentation. |
| `benchy-white.svg` · `.png` · `icon-white.ico` | `#FFFFFF` | Dark backgrounds. This is the one the app sidebar uses. |

All with a transparent background. The `.ico` files carry 16, 24, 32, 48, 64, 128
and 256 px.

`web/icon.ico` is separate: it keeps the purple gradient because it is the window
icon at runtime and has to work against either taskbar theme.

**No flat colour survives both taskbars.** Contrast ratios against the dark
(`#202020`) and light (`#F3F3F3`) Windows 11 taskbars:

| Icon | Dark | Light | Worst case |
|---|---|---|---|
| Flat navy | 1.16× | 12.62× | invisible |
| Flat black | 1.14× | 16.75× | invisible |
| Flat white | 16.29× | 1.11× | invisible |
| Navy plate, white mark | — | — | always readable |

Hence the plate for anything that lands on a taskbar.

**For another colour:** the `.svg` files are a single `<path>`; change the `fill`
attribute. Regenerating the `.ico` files needs `pillow`.

**Packaging with PyInstaller** — the executable icon is passed separately from the
window icon:

```bash
pyinstaller --noconsole --name "Filament Tracker" --icon brand/icon-navy-tile.ico --add-data "web;web" app.py
```
