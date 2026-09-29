# 电吉他效果器调音 Agent —— 工作区入口
# 推荐直接跑 tone.bat（绕开执行策略）
#
#   tone list                     列出所有歌曲
#   tone new 歌名 原曲.flac       新建一首
#   tone run <脚本> [参数...]     在 $env:SONG_DIR 的上下文里跑脚本
#   tone env                      检查环境（Python / 依赖 / 模型 / ffmpeg）

param(
  [Parameter(Mandatory=$true, Position=0)][string]$Cmd,
  [Parameter(Position=1)][string]$A1 = "",
  [Parameter(Position=2)][string]$A2 = "",
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest = @()
)
$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'   # 否则中文输出在控制台乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = if ($PSScriptRoot) { $PSScriptRoot } elseif ($env:TONE_ROOT) { $env:TONE_ROOT } else { $null }
if (-not $Root) { Write-Host '定位不到包根目录。请设 TONE_ROOT' -ForegroundColor Red; exit 1 }
$Songs  = Join-Path $Root 'songs'
$Src    = Join-Path $Root 'tools'
$Models = Join-Path $Root 'models'

function Test-RealPython($p) {
  if (-not $p) { return $false }
  if (-not (Test-Path -LiteralPath $p)) { return $false }
  # 只排除 Windows Store 的假 python（转发到应用商店的存根，跑起来会报错）
  if ($p -like '*\WindowsApps\*') { return $false }
  return $true
}

# ---- 自愈：venv 的 pyvenv.cfg 里 home 是绝对路径，包搬家后会失效 ----
$vcfg = Join-Path $Root 'venv\pyvenv.cfg'
if (Test-Path -LiteralPath $vcfg) {
  $want = Join-Path $Root 'python'
  $lines = @(Get-Content -LiteralPath $vcfg -Raw -Encoding UTF8) -split "`r?`n"
  $fixed = $lines | ForEach-Object {
    if ($_ -match '^\s*home\s*=') { "home = $want" } else { $_ }
  }
  $new = ($fixed -join "`r`n")
  if ($new -ne (Get-Content -LiteralPath $vcfg -Raw -Encoding UTF8)) {
    Set-Content -LiteralPath $vcfg -Value $new -Encoding UTF8 -NoNewline
    Write-Host "[自愈] venv\pyvenv.cfg -> home = $want" -ForegroundColor DarkGray
  }
}

$cands = @()
$cands += (Join-Path $Root 'venv\Scripts\python.exe')
$cands += $env:TONE_PY
$cfg = Join-Path $Root 'python_path.txt'
if (Test-Path -LiteralPath $cfg) {
  # 注意：PowerShell 5.1 的 Get-Content 按 CRLF 切行；
  # 文件若是 LF 换行，整个文件会被当成一行（注释和路径粘连）。
  # 所以用 -Raw 自己切，两种换行都兼容。
  $txt = Get-Content -LiteralPath $cfg -Raw -Encoding UTF8
  ($txt -split "`r?`n") | ForEach-Object {
    $s = $_.Trim()
    if ($s -and -not $s.StartsWith('#')) { $cands += $s }
  }
}
$PY = $null
foreach ($c in $cands) { if (Test-RealPython $c) { $PY = $c; break } }
if (-not $PY) {
  foreach ($n in @('py','python','python3')) {
    $w = Get-Command $n -ErrorAction SilentlyContinue
    if ($w -and (Test-RealPython $w.Source)) { $PY = $w.Source; break }
  }
}

switch ($Cmd.ToLower()) {
  'list' {
    if (-not (Test-Path -LiteralPath $Songs)) { Write-Host '还没有歌曲目录（tone new 新建）'; break }
    Write-Host "工作区: $Root"
    Get-ChildItem -LiteralPath $Songs -Directory | ForEach-Object {
      $mark = if (Test-Path -LiteralPath (Join-Path $_.FullName 'target.npy')) { '已有目标曲线' } else { '未建目标' }
      Write-Host ("  {0,-24} {1}" -f $_.Name, $mark)
    }
  }
  'new' {
    if (-not $A1 -or -not $A2) { Write-Host '用法: tone new 歌名 原曲.flac'; break }
    if (-not $PY) { Write-Host '找不到 Python。见 README 环境准备' -ForegroundColor Red; break }
    & $PY (Join-Path $Src 'new_song.py') $A1 $A2
  }
  'run' {
    if (-not $env:SONG_DIR) { Write-Host '没设 SONG_DIR' -ForegroundColor Red; break }
    if (-not $A1) { Write-Host '用法: tone run 脚本名 [参数...]'; break }
    if (-not $PY) { Write-Host '找不到 Python。见 README 环境准备' -ForegroundColor Red; break }
    $script = Join-Path $Src $A1
    if (-not (Test-Path -LiteralPath $script)) { Write-Host "脚本不存在: $script" -ForegroundColor Red; break }
    $env:PYTHONIOENCODING = 'utf-8'
    Write-Host ("[SONG_DIR] " + $env:SONG_DIR) -ForegroundColor DarkGray
    $all = @($script, $env:SONG_DIR)
    if ($A2) { $all += $A2 }
    if ($Rest.Count -gt 0) { $all += $Rest }
    & $PY @all
  }
  'env' {
    Write-Host "包根目录 : $Root"
    Write-Host "Python   : $(if ($PY) { $PY } else { '!! 未找到' })"
    if ($PY) { Write-Host "版本     : $(& $PY --version 2>&1)" }
    $ck = Join-Path $Models 'BS-Rofo-SW-Fixed.ckpt'
    if (Test-Path -LiteralPath $ck) {
      Write-Host "分离模型 : OK  $([math]::Round((Get-Item -LiteralPath $ck).Length/1MB)) MB"
    } else { Write-Host '分离模型 : !! 缺失' -ForegroundColor Red }
    $ff = Join-Path $Root 'ffmpeg\ffmpeg.exe'
    Write-Host "ffmpeg   : $(if (Test-Path -LiteralPath $ff) { 'OK（包内）' } else { '-- 包内没有，看 PATH' })"
    if ($PY) {
      Write-Host '关键依赖 :'
      & $PY -c "import importlib.util as U`nfor m in ['numpy','scipy','soundfile','librosa','torch']:`n    print('   {:<12} {}'.format(m, 'OK' if U.find_spec(m) else '!! 缺失'))" 2>&1
    }
  }
  default { Write-Host "未知命令: $Cmd（可用: list / new / run / env）" }
}
