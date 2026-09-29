# 把项目根的两个 skill 源同步到 install-skill\（发布前跑一次）
# 用法:  powershell -NoProfile -ExecutionPolicy Bypass -File tools\sync-skill-src.ps1
#
# 关系：
#   项目根 SKILL.md + reference\            <- 权威源（改这里）
#     -> install-skill\guitar-tone-agent\   <- 分发副本（脚本生成，别手改）
#   项目根 docs\..\guitar-tone-manual      <- 附属 skill 的源在 .dsh 里，这里只做校验提示
$ErrorActionPreference = 'Stop'
$Pkg = Split-Path -Parent $PSScriptRoot
$dst = Join-Path $Pkg 'install-skill\guitar-tone-agent'

if (-not (Test-Path (Join-Path $Pkg 'SKILL.md'))) { Write-Host ('找不到 ' + $Pkg + '\SKILL.md') -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force -Path (Join-Path $dst 'reference') | Out-Null
Copy-Item (Join-Path $Pkg 'SKILL.md') -Destination (Join-Path $dst 'SKILL.md') -Force
Copy-Item (Join-Path $Pkg 'reference\*') -Destination (Join-Path $dst 'reference') -Force

# 逐份哈希校验（只数个数会漏掉内容漂移）
$bad = @()
$names = @('SKILL.md') + @(Get-ChildItem (Join-Path $Pkg 'reference') -File | ForEach-Object { 'reference\' + $_.Name })
foreach ($f in $names) {
  $a = Join-Path $Pkg $f; $b = Join-Path $dst $f
  if (-not (Test-Path -LiteralPath $b)) { $bad += ($f + ' 缺失'); continue }
  if ((Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash) { $bad += $f }
}
$n = (Get-ChildItem (Join-Path $dst 'reference') -File).Count
if ($bad.Count -eq 0) { Write-Host ('OK  install-skill 已同步：SKILL.md + ' + $n + ' 份 reference 全部一致') -ForegroundColor Green }
else { Write-Host ('!! 不一致 ' + $bad.Count + ' 个: ' + ($bad -join ', ')) -ForegroundColor Red; exit 1 }

# 附属 skill 的一致性提示（源在 .dsh\skills 里，不在本包）
$manualSrc = Join-Path $dst '..\guitar-tone-manual\SKILL.md'
$manualLive = Join-Path $env:USERPROFILE '..\.dsh\skills\guitar-tone-manual\SKILL.md'
if (Test-Path $manualSrc) { Write-Host ('附属 skill 源: ' + (Resolve-Path $manualSrc).Path) }
