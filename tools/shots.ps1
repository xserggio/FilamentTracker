# Capturas de la ventana para el README. Requiere la app compilada o py app.py.
#   powershell -ExecutionPolicy Bypass -File tools\shots.ps1
param([string]$OutDir = "docs")

Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force $OutDir | Out-Null

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

$views = @("dashboard", "inventory", "history", "stats")
Copy-Item "web\app.js" "web\_app.js.bak" -Force

foreach ($v in $views) {
    Get-Process -EA SilentlyContinue |
        Where-Object { $_.MainWindowTitle -eq "Filament Tracker" } | Stop-Process -Force
    Copy-Item "web\_app.js.bak" "web\app.js" -Force
    Add-Content "web\app.js" "`nwindow.addEventListener('load', () => setTimeout(() => { try { setView('$v'); } catch(e){} }, 1200));"
    Start-Sleep -Milliseconds 700
    Start-Process -FilePath "pythonw" -ArgumentList "app.py" -WorkingDirectory (Get-Location)
    Start-Sleep -Seconds 13

    $p = Get-Process -EA SilentlyContinue |
        Where-Object { $_.MainWindowTitle -eq "Filament Tracker" } | Select-Object -First 1
    if (-not $p) { Write-Host "no arranco para $v" -ForegroundColor Red; continue }
    $r = New-Object Shot+RECT
    [Shot]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc(); [Shot]::PrintWindow($p.MainWindowHandle, $hdc, 2) | Out-Null; $g.ReleaseHdc($hdc)
    $bmp.Save("$OutDir\$v.png", [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Host "$OutDir\$v.png"
}

Copy-Item "web\_app.js.bak" "web\app.js" -Force
Remove-Item "web\_app.js.bak" -Force
Get-Process -EA SilentlyContinue |
    Where-Object { $_.MainWindowTitle -eq "Filament Tracker" } | Stop-Process -Force
