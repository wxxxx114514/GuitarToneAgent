# GPU 环境：独立 uv venv，装 CUDA 版 torch + audio-separator
# 注意：UV_CACHE_DIR 必须设在workspace里（默认缓存在 C:\Users 下会被沙箱挡）
# <包根> = 含 tone.bat 的目录；从 $PSScriptRoot\.. 往上找
$PkgRoot = $PSScriptRoot
if (Test-Path (Join-Path $PSScriptRoot '..\tone.bat')) {
  $PkgRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
$ErrorActionPreference = 'Continue'
$env:UV_CACHE_DIR = "$PkgRoot\_env\uv_cache"
$env:UV_PYTHON_INSTALL_DIR = "$PkgRoot\_env\uv_python"
$env:TMP = "$PkgRoot\_env\tmp"
$env:TEMP = "$PkgRoot\_env\tmp"
$VENV = "$PkgRoot\_env\venv_gpu"
$UV = '<包外>\uv\uv.exe'

Write-Output '=== [1/3] 建 venv ==='
if (Test-Path $VENV) { Write-Output "  已存在: $VENV" }
else { & $UV venv --python '<包外>\py\python.exe' $VENV 2>&1 }

$PY = Join-Path $VENV 'Scripts\python.exe'
Write-Output ("  python: " + $PY)

Write-Output ''
Write-Output '=== [2/3] 装 CUDA 版 torch 2.14.0 (2.42 GB) ==='
& $UV pip install --python $PY 'torch==2.14.0' --index-url https://download.pytorch.org/whl/cu126 2>&1 | Select-Object -Last 12

Write-Output ''
Write-Output '=== [3/3] 装其余依赖 ==='
& $UV pip install --python $PY audio-separator soundfile numpy pyyaml 2>&1 | Select-Object -Last 12

Write-Output ''
Write-Output '=== 验证 ==='
& $PY -c "import torch; print('  torch', torch.__version__); print('  cuda available:', torch.cuda.is_available()); print('  device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')" 2>&1
