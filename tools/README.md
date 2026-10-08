# tools/ · 本 skill 自带的脚本

> ★ 这里只放【本轮真机实测跑通过、且包内没有可用等价物】的脚本。
> 包里 39 个脚本 + winmm.cs 的完整索引见 reference/11-工具清单.md（每条含绝对路径、一句职责、命令、验证状态四档）。

## 本目录文件

| 文件 | 职责 | 来源 | 改动 |
|---|---|---|---|
| do_reamp.ps1 | ★ 送 + 录（WinMM 双工）：把 wav 播进设备，同时录回传 | 复制 <gt-test>\reamp\do_reamp.ps1（本轮实证：reamp\ 共 104 个 wav，其中 wet* 75）| 只把写死的包路径改成 $PSScriptRoot\winmm.cs，使本目录可独立运行 |
| make_send.py | 造发送信号：单声道 → 48k/2ch/16bit + 归一化到 −32 dBFS + 前后加静音 | 复制 <gt-test>\reamp\make_send.py（本轮实证：sendL32.wav / sendTarget.wav）| **无改动** |
| winmm.cs | ★ 双工录音核心（WinMM）：ListIn / ListOut / Duplex / RecordOnly | 复制 <包根>\tools\winmm.cs | **无改动**（包内原件也仍在，两处一致） |

## 用法

```powershell
# 送 + 录（B 组：送参考曲段；A 组标定送 sendL32.wav）
powershell -NoProfile -ExecutionPolicy Bypass -File <本项目>\tools\do_reamp.ps1 ^
  -Send <发送wav> -RecSecs 14.1 -Out <录音wav>
# ★ 换设备：加 -DevicePattern "<新设备名片段>"（默认 "MOOER"）

# 造发送信号：python make_send.py <源> <出> <起始秒> <时长> <峰值dBFS>
<包根>\venv\Scripts\python.exe <本项目>\tools\make_send.py ^
  <用户录的那份 DI> sendTarget.wav 0 10.05 -32
```

## 为什么这里只有 3 个文件，而不把包内 39 个脚本复制过来

| 方案 | 为什么不 |
|---|---|
| 复制包内 39 个脚本 | ✗ 它们全部靠 __file__ / parents[1] 定位**包根**（models/ · presets/ · songs/ · _env/ · _tmp_param/ · venv/）；复制出去立刻断 |
| 在新目录建 junction（目录联接）| ✗ ① 会让「新目录里的写入」穿透进包里，违反「不在包里改」；② junction 不可移植（拷贝/压缩即失效）|
| **索引 + 只复制本轮实证驱动（采用）** | ✓ 包保持只读、零维护；本目录又能独立跑出「送 / 录 / 造信号」三件事 |

★ 复制的这两个驱动**不是包里的工具**，是 gt-test 里这一轮自己写、自己跑通的；复制/修正它们不涉及「改包」。
★ 包里 39 个脚本一律**不动**（包括已知不能直接运行的 reamp2.ps1 / dump_sent.ps1 —— 见 reference/11-工具清单.md 的验证状态）。
