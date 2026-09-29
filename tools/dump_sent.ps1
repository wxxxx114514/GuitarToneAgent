# Reamp: play DI into GE250 effects chain, record wet output
# env: DI_FILE DI_FROM DI_SECS REC_SECS OUT_WAV
Add-Type -Path '$PSScriptRoot\winmm.cs'
$diFile  = if ($env:DI_FILE) { $env:DI_FILE } else { '$PSScriptRoot\di\synth_di.wav' }
$fromSec = if ($env:DI_FROM) { [double]$env:DI_FROM } else { 0.0 }
$diSecs  = if ($env:DI_SECS) { [double]$env:DI_SECS } else { 12.0 }
$recSecs = if ($env:REC_SECS) { [double]$env:REC_SECS } else { 14.0 }
$outWav  = '$PSScriptRoot\reamp\sent_pcm.wav'
New-Item -ItemType Directory -Force -Path (Split-Path $outWav) | Out-Null

$ins = [WinMM]::ListIn();  $outs = [WinMM]::ListOut()
$inDev = -1; $outDev = -1
for ($i = 0; $i -lt $ins.Count; $i++)  { if ($ins[$i]  -match 'MOOER') { $inDev  = $i } }
for ($i = 0; $i -lt $outs.Count; $i++) { if ($outs[$i] -match 'MOOER') { $outDev = $i } }
if ($inDev -lt 0 -or $outDev -lt 0) { Write-Output 'GE250 endpoint missing'; exit 1 }
Write-Output ("devices: in=#$inDev (" + $ins[$inDev].Split('|')[1].Trim() + ")  out=#$outDev (" + $outs[$outDev].Split('|')[1].Trim() + ")")

$bytes = [System.IO.File]::ReadAllBytes($diFile)
$sr   = [BitConverter]::ToInt32($bytes, 24)
$ch   = [BitConverter]::ToUInt16($bytes, 22)
$bits = [BitConverter]::ToUInt16($bytes, 34)
$frameBytes = [int]($ch * ($bits / 8))
Write-Output ("DI: $sr Hz / $ch ch / $bits bit")

$start = [int]($fromSec * $sr)
$count = [int]($diSecs * $sr)
$pcm = New-Object byte[] ($count * 4)
$written = 0; $clip = 0
$bytesLen = $bytes.Length
for ($i = 0; $i -lt $count; $i++) {
  $src = 44 + ($start + $i) * $frameBytes
  if ($src + $frameBytes -gt $bytesLen) { break }
  if ($bits -eq 24) {
    $b0 = [int]$bytes[$src]; $b1 = [int]$bytes[$src+1]; $b2 = [int]$bytes[$src+2]
    $v = $b0 -bor ($b1 -shl 8) -bor ($b2 -shl 16)
    if ($v -band 0x800000) { $v = $v - 0x1000000 }
    $r = [math]::Round($v / 256.0)
    if ($r -gt 32767) { $r = 32767; $clip++ } elseif ($r -lt -32768) { $r = -32768; $clip++ }
    $s = [int16]$r
  } elseif ($bits -eq 16) {
    $s = [BitConverter]::ToInt16($bytes, $src)
  } else { $s = 0 }
  $b = [BitConverter]::GetBytes($s)
  [Array]::Copy($b, 0, $pcm, $written*4, 2)
  [Array]::Copy($b, 0, $pcm, $written*4+2, 2)
  $written++
}
if ($written -eq 0) { Write-Output 'no audio'; exit 1 }
$pcm = $pcm[0..($written*4-1)]
Write-Output ("sending {0:N2} s, {1} frames, clipped={2}" -f ($written / $sr), $written, $clip)


$hdr = New-Object byte[] 44
$bw = [System.Text.Encoding]::ASCII
[Array]::Copy($bw.GetBytes('RIFF'), 0, $hdr, 0, 4)
[Array]::Copy([BitConverter]::GetBytes([int](36 + $pcm.Length)), 0, $hdr, 4, 4)
[Array]::Copy($bw.GetBytes('WAVEfmt '), 0, $hdr, 8, 8)
[Array]::Copy([BitConverter]::GetBytes([int]16), 0, $hdr, 16, 4)
[Array]::Copy([BitConverter]::GetBytes([int16]1), 0, $hdr, 20, 2)
[Array]::Copy([BitConverter]::GetBytes([int16]2), 0, $hdr, 22, 2)
[Array]::Copy([BitConverter]::GetBytes([int]48000), 0, $hdr, 24, 4)
[Array]::Copy([BitConverter]::GetBytes([int](48000*4)), 0, $hdr, 28, 4)
[Array]::Copy([BitConverter]::GetBytes([int16]4), 0, $hdr, 32, 2)
[Array]::Copy([BitConverter]::GetBytes([int16]16), 0, $hdr, 34, 2)
[Array]::Copy($bw.GetBytes('data'), 0, $hdr, 36, 4)
[Array]::Copy([BitConverter]::GetBytes([int]$pcm.Length), 0, $hdr, 40, 4)
$fs = [System.IO.File]::Create($outWav)
$fs.Write($hdr, 0, 44); $fs.Write($pcm, 0, $pcm.Length); $fs.Close()
Write-Output ("saved " + $outWav)

Write-Output ("saved " + $outWav)
