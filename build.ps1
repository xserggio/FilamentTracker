# Empaqueta la app en un unico .exe. Requiere: py -m pip install pyinstaller
# Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
Set-Location $PSScriptRoot

# Solo el ejecutable compilado, por nombre de proceso. Filtrar por titulo de
# ventana alcanzaba a cualquier programa que tuviera "Filament Tracker" en el
# suyo -- un navegador con el repo abierto, sin ir mas lejos.
Get-Process -Name "Filament Tracker" -EA SilentlyContinue | Stop-Process -Force

py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "Filament Tracker" `
    --icon "brand\icon-navy-tile.ico" `
    --add-data "web;web" `
    --add-data "catalog.json;." `
    app.py

# los restos de compilacion no hacen falta para distribuir
Remove-Item "build" -Recurse -Force -EA SilentlyContinue

if (Test-Path "dist\Filament Tracker.exe") {
    $mb = [math]::Round((Get-Item "dist\Filament Tracker.exe").Length / 1MB, 1)
    Write-Host "`nListo: dist\Filament Tracker.exe ($mb MB)" -ForegroundColor Green
    Write-Host "La base de datos vive en dist\data\ , junto al ejecutable." -ForegroundColor DarkGray
} else {
    Write-Host "`nLa compilacion ha fallado." -ForegroundColor Red
}
