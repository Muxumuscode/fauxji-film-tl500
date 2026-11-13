# Builds dist\SajinGenzo.exe (Windows, one file). Run from the safelight folder:   powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $py -m pip install --quiet -r requirements.txt -r requirements-build.txt
& $py -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'tests failed' }
& $py packaging\make_icon.py build\icon
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name SajinGenzo `
    --icon "$PSScriptRoot\build\icon\safelight.ico" --distpath dist --workpath build\pyinstaller --specpath build `
    --exclude-module tkinter --exclude-module unittest --collect-all pillow_heif `
    "$PSScriptRoot\packaging\launcher.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Get-Item dist\SajinGenzo.exe | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
