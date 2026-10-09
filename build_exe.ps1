# 打包「秦彻 · 桌面宠物」为可分发的 Windows 程序（PyInstaller，onedir）
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python -and (Test-Path 'D:\Coding\Python313\python.exe')) {
    $python = 'D:\Coding\Python313\python.exe'
}
if (-not $python) { throw '未找到 python' }

# Keep unrelated toolchains' ICU/OpenSSL DLLs out of the application bundle.
# PyInstaller also searches PATH when resolving native library dependencies.
$originalPath = $env:PATH
$buildExitCode = 1
try {
    $env:PATH = @((Split-Path -Parent $python),
        (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join [IO.Path]::PathSeparator
    & $python -m PyInstaller --noconfirm --clean --windowed --noupx `
    --name QinChePet `
    --icon "$root\app\assets\qinche.ico" `
    --add-data "$root\app\assets;assets" `
    --add-data "$root\pets\qinche-q;bundled_pets/qinche-q" `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtQuickWidgets `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtCharts `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtSql `
    --exclude-module PySide6.QtTest `
    --exclude-module PySide6.QtDesigner `
    --exclude-module PySide6.QtHelp `
    --exclude-module PySide6.QtBluetooth `
    --exclude-module PySide6.QtOpenGL `
    --exclude-module PySide6.QtOpenGLWidgets `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module numpy `
    --exclude-module tkinter `
    --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" `
    "$root\app\main.py"
    $buildExitCode = $LASTEXITCODE
}
finally {
    $env:PATH = $originalPath
}

if ($buildExitCode -ne 0) {
    Write-Error "PyInstaller 打包失败（退出码：$buildExitCode）" -ErrorAction Continue
    exit $buildExitCode
}

Write-Host ""
Write-Host "打包完成：$root\dist\QinChePet\QinChePet.exe"
