# dups: play send wav into GE250 and record return (WinMM duplex)
param([string]$Send, [double]$RecSecs, [string]$Out, [string]$DevicePattern = "MOOER")
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -Path "$PSScriptRoot\winmm.cs"
$ins = [WinMM]::ListIn(); $outs = [WinMM]::ListOut()
$inDev = -1; $outDev = -1
for ($i=0; $i -lt $ins.Count; $i++)  { if ($ins[$i]  -match $DevicePattern) { $inDev  = $i } }
for ($i=0; $i -lt $outs.Count; $i++) { if ($outs[$i] -match $DevicePattern) { $outDev = $i } }
if ($inDev -lt 0 -or $outDev -lt 0) { Write-Output "endpoint missing (pattern=$DevicePattern)"; exit 1 }
Write-Output ("devices: in=#" + $inDev + "  out=#" + $outDev)
$bytes = [System.IO.File]::ReadAllBytes($Send)
$sr = [BitConverter]::ToInt32($bytes, 24); $ch = [BitConverter]::ToUInt16($bytes, 22); $bits = [BitConverter]::ToUInt16($bytes, 34)
if ($sr -ne 48000 -or $ch -ne 2 -or $bits -ne 16) { Write-Output ("bad format " + $sr + "/" + $ch + "/" + $bits); exit 1 }
$pcmLen = $bytes.Length - 44
$pcm = New-Object byte[] $pcmLen
[Array]::Copy($bytes, 44, $pcm, 0, $pcmLen)
Write-Output ("playing {0:N2} s, recording {1:N2} s" -f ($pcmLen/4/48000), $RecSecs)
$r = [WinMM]::Duplex($outDev, $inDev, $pcm, 48000, 2, 16, $RecSecs, 8)
Write-Output ("  " + $r.Info)
$rl = $r.Data.Length
$hdr = New-Object byte[] 44
$bw = [System.Text.Encoding]::ASCII
[Array]::Copy($bw.GetBytes("RIFF"), 0, $hdr, 0, 4); [Array]::Copy([BitConverter]::GetBytes([int](36+$rl)), 0, $hdr, 4, 4)
[Array]::Copy($bw.GetBytes("WAVEfmt "), 0, $hdr, 8, 8); [Array]::Copy([BitConverter]::GetBytes([int]16), 0, $hdr, 16, 4)
[Array]::Copy([BitConverter]::GetBytes([int16]1), 0, $hdr, 20, 2); [Array]::Copy([BitConverter]::GetBytes([int16]2), 0, $hdr, 22, 2)
[Array]::Copy([BitConverter]::GetBytes([int]48000), 0, $hdr, 24, 4); [Array]::Copy([BitConverter]::GetBytes([int](48000*4)), 0, $hdr, 28, 4)
[Array]::Copy([BitConverter]::GetBytes([int16]4), 0, $hdr, 32, 2); [Array]::Copy([BitConverter]::GetBytes([int16]16), 0, $hdr, 34, 2)
[Array]::Copy($bw.GetBytes("data"), 0, $hdr, 36, 4); [Array]::Copy([BitConverter]::GetBytes([int]$rl), 0, $hdr, 40, 4)
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
$fs = [System.IO.File]::Create($Out); $fs.Write($hdr, 0, 44); $fs.Write($r.Data, 0, $rl); $fs.Close()
Write-Output ("saved " + $Out)
