# 启动「秦彻 · 桌面宠物」（源码模式）
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python -and (Test-Path 'D:\Coding\Python313\python.exe')) {
    $python = 'D:\Coding\Python313\python.exe'
}
if (-not $python) { throw '未找到 python，请安装 Python 3.10+ 或修改本脚本中的解释器路径' }

& $python "$root\app\main.py"
exit $LASTEXITCODE
