$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m pip install 'pyinstaller>=6.16'
if ($LASTEXITCODE -ne 0) { throw 'Could not install build tools' }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ConvoVault-Studio --collect-data convovault --distpath release launch_studio.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
Write-Output 'Built release/ConvoVault-Studio.exe'
