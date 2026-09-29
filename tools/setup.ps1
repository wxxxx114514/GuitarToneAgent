# 一键装环境：uv sync（按 pyproject.toml + uv.lock）+ 下模型 + 自检
# 用法:  powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup.ps1
#        -SkipModel 只装 Python 环境；-CheckOnly 只自检
param([switch]$SkipModel, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$Pkg = Split-Path -Parent $PSScriptRoot
Write-Host ('包根: ' + $Pkg) -ForegroundColor Cyan

# uv 缓存必须放在可写位置（默认 %LOCALAPPDATA%\uv\cache 在沙箱下会被拒）
$env:UV_CACHE_DIR        = Join-Path $Pkg '_env\uv_cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Pkg '_env\uv_python'

if (-not $CheckOnly) {
  # ---- 1) uv ----
  $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
  if (-not $uv) { foreach ($c in @('uv', (Join-Path $env:USERPROFILE '.local\bin\uv.exe'))) { if (Test-Path $c) { $uv = $c; break } } }
  if (-not $uv) { Write-Host 'uv 未安装。装法： powershell -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor Red; exit 1 }
  Write-Host ('uv: ' + $uv)

  # ---- 2) 解释器：优先用包内自带的 python\，没有就让 uv 自己装一个 ----
  $bundled = Join-Path $Pkg 'python\python.exe'
  if (Test-Path $bundled) { $env:UV_PYTHON = $bundled; Write-Host ('解释器: 包内 ' + $bundled) }
  else { Write-Host '解释器: 包内没有 python\，交给 uv 下载 CPython 3.13' }

  # ---- 3) 装环境 ----
  Push-Location $Pkg
  try {
    & $uv sync
    if ($LASTEXITCODE -ne 0) { throw ('uv sync 失败，exit=' + $LASTEXITCODE) }
  } finally { Pop-Location }
  $venv = Join-Path $Pkg '.venv\Scripts\python.exe'
  if (-not (Test-Path $venv)) { Write-Host '!! 没生成 .venv' -ForegroundColor Red; exit 1 }
  Write-Host ('环境: ' + $venv) -ForegroundColor Green
} else {
  $venv = Join-Path $Pkg '.venv\Scripts\python.exe'
}

# ---- 4) 模型（699 MB，不进 git） ----
if (-not $SkipModel -and -not $CheckOnly) {
  & $venv (Join-Path $Pkg 'tools\dl_models.py')
  if ($LASTEXITCODE -ne 0) { Write-Host '!! 模型下载/校验失败' -ForegroundColor Red; exit 1 }
}

# ---- 5) 自检 ----
Write-Host ''
Write-Host '=== 自检 ===' -ForegroundColor Cyan
& $venv -c "import sys,numpy,scipy,soundfile,librosa,torch,onnxruntime;print('  python',sys.version.split()[0]);print('  numpy',numpy.__version__,'| scipy',scipy.__version__,'| librosa',librosa.__version__);print('  torch',torch.__version__,'| cuda:',torch.cuda.is_available())"
& $venv (Join-Path $Pkg 'tools\dl_models.py') --check
Write-Host ''
Write-Host '完成。用法：tone.bat list / tone.bat new 歌名 原曲.flac / tone.bat run analyze_round.py wet.wav' -ForegroundColor Green
