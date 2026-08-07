# Capturas de la ventana para el README. Requiere la app compilada o py app.py.
#   powershell -ExecutionPolicy Bypass -File tools\shots.ps1
#
# Antes de ejecutarlo, genera la base de ejemplo:
#   py tools\make_demo_db.py data\filaments.db
# El script la pone en ingles y apaga el aviso de Bambu Studio, para que las
# capturas no dependan de lo que haya laminado quien las saca.
param([string]$OutDir = "docs")

Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force $OutDir | Out-Null

py -c "from core import Store; Store('data/filaments.db').set_settings({'lang':'en','slicer_watch':'0','slicer_dir':'','currency':'EUR'})"
py tools\make_demo_slice.py data\_demo_slices

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Shot {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
'@

# La ficha no es una vista, es un modal: se abre por su filamento. Y las dos
# ultimas necesitan el vigilante encendido sobre el laminado de ejemplo, que
# `db` prepara antes de arrancar la ventana.
$WATCH = "{'slicer_watch':'1','slicer_dir':'data/_demo_slices','slicer_seen':'0'}"
$steps = @(
  @{ name = "dashboard"; js = "setView('dashboard');" },
  @{ name = "inventory"; js = "setView('inventory');" },
  @{ name = "history";   js = "setView('history');" },
  @{ name = "stats";     js = "setView('stats');" },
  @{ name = "detail";    js = "setView('inventory'); setTimeout(() => openDetail(S.filaments.find((f) => f.name === 'PETG - black')), 900);" },
  @{ name = "slice";     js = "setView('dashboard');"; db = $WATCH },
  @{ name = "sliceform"; js = "setView('dashboard'); setTimeout(() => document.getElementById('sliceAdd').click(), 6000);"; db = $WATCH }
)

# Restos de una tanda anterior. Se filtra por nombre de proceso: por titulo de
# ventana alcanzaba a cualquier programa con "Filament Tracker" en el suyo, y el
# titulo de un navegador es el de su pestana activa.
function Stop-AppLeftovers {
    Get-Process -EA SilentlyContinue |
        Where-Object { $_.ProcessName -in @("pythonw", "python", "Filament Tracker") -and
                       $_.MainWindowTitle -eq "Filament Tracker" } |
        Stop-Process -Force
}

Copy-Item "web\app.js" "web\_app.js.bak" -Force

foreach ($s in $steps) {
    Stop-AppLeftovers
    Copy-Item "web\_app.js.bak" "web\app.js" -Force
    if ($s.db) { py -c "from core import Store; Store('data/filaments.db').set_settings($($s.db))" }
    Add-Content "web\app.js" "`nwindow.addEventListener('load', () => setTimeout(() => { try { $($s.js) } catch(e){} }, 1200));"
    Start-Sleep -Milliseconds 700
    # Se guarda el proceso que arrancamos: buscar por titulo engancharia cualquier
    # otra instancia abierta -- por ejemplo el .exe compilado, con datos reales.
    $proc = Start-Process -FilePath "pythonw" -ArgumentList "app.py" `
        -WorkingDirectory (Get-Location) -PassThru
    # el aviso del laminador llega despues del arranque, asi que esos dos esperan mas
    Start-Sleep -Seconds $(if ($s.db) { 24 } else { 14 })

    $p = Get-Process -Id $proc.Id -EA SilentlyContinue
    if (-not $p -or -not $p.MainWindowHandle -or $p.MainWindowHandle -eq 0) {
        Write-Host "no arranco para $($s.name)" -ForegroundColor Red; continue
    }
    $r = New-Object Shot+RECT
    [Shot]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc(); [Shot]::PrintWindow($p.MainWindowHandle, $hdc, 2) | Out-Null; $g.ReleaseHdc($hdc)
    $bmp.Save("$OutDir\$($s.name).png", [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Host "$OutDir\$($s.name).png"
}

Copy-Item "web\_app.js.bak" "web\app.js" -Force
Remove-Item "web\_app.js.bak" -Force
py -c "from core import Store; Store('data/filaments.db').set_settings({'slicer_watch':'0','slicer_dir':''})"
Stop-AppLeftovers
