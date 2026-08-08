# Empaqueta la app en un unico .exe. Requiere: py -m pip install pyinstaller
# Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
#
# El .exe no se puede sobrescribir mientras la app este abierta. Windows tampoco
# suelta el fichero en el instante en que matas el proceso, asi que este script
# espera a que lo suelte de verdad, y al terminar comprueba que el binario se ha
# escrito AHORA. Comprobar solo que el fichero existe daba por buena una
# compilacion fallida y dejaba en su sitio el exe de la version anterior.
Set-Location $PSScriptRoot

$Exe = "dist\Filament Tracker.exe"
$antes = if (Test-Path $Exe) { (Get-Item $Exe).LastWriteTimeUtc } else { [datetime]::MinValue }

# Solo el ejecutable compilado, por nombre de proceso. Filtrar por titulo de
# ventana alcanzaba a cualquier programa que tuviera "Filament Tracker" en el
# suyo -- un navegador con el repo abierto, sin ir mas lejos.
$vivos = Get-Process -Name "Filament Tracker" -EA SilentlyContinue
if ($vivos) {
    Write-Host "Cerrando $($vivos.Count) instancia(s) abiertas..." -ForegroundColor DarkGray
    $vivos | Stop-Process -Force
    $vivos | Wait-Process -Timeout 15 -EA SilentlyContinue
}

# y esperar a que el fichero quede realmente libre antes de invocar a PyInstaller
if (Test-Path $Exe) {
    $libre = $false
    foreach ($i in 1..20) {
        try {
            $fs = [IO.File]::Open((Resolve-Path $Exe), 'Open', 'ReadWrite', 'None')
            $fs.Close(); $libre = $true; break
        } catch { Start-Sleep -Milliseconds 400 }
    }
    if (-not $libre) {
        Write-Host "`n$Exe sigue en uso. Cierra la aplicacion y vuelve a intentarlo." -ForegroundColor Red
        exit 1
    }
}

py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "Filament Tracker" `
    --icon "brand\icon-navy-tile.ico" `
    --add-data "web;web" `
    --add-data "catalog.json;." `
    app.py
$codigo = $LASTEXITCODE

# los restos de compilacion no hacen falta para distribuir
Remove-Item "build" -Recurse -Force -EA SilentlyContinue

if ($codigo -ne 0) {
    Write-Host "`nPyInstaller ha fallado (codigo $codigo)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Exe)) {
    Write-Host "`nLa compilacion no ha dejado ningun ejecutable." -ForegroundColor Red
    exit 1
}
$despues = (Get-Item $Exe).LastWriteTimeUtc
if ($despues -le $antes) {
    Write-Host "`n$Exe no se ha escrito: sigue siendo el de antes ($despues)." -ForegroundColor Red
    Write-Host "Es lo que pasa cuando la aplicacion estaba abierta al compilar." -ForegroundColor Red
    exit 1
}

$mb = [math]::Round((Get-Item $Exe).Length / 1MB, 1)
Write-Host "`nListo: $Exe ($mb MB, escrito $($despues.ToLocalTime().ToString('HH:mm:ss')))" -ForegroundColor Green
Write-Host "La base de datos vive en dist\data\ , junto al ejecutable." -ForegroundColor DarkGray
