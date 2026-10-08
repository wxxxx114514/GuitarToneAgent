# tools/ · 本 skill 自带的 8 个工具

> ★ 全部**自定位**（不依赖任何外部目录），**可以单独拷走用**。
> ★ 完整索引（含验证状态四档）见 **../reference/11-工具清单.md**。

## 一、驱动（每轮都用）

| 文件 | 职责 | 状态 |
|---|---|---|
| `do_reamp.ps1` | ★ 送 + 录（WinMM 双工）：把 wav 播进设备，同时录回传 | 🟢 本轮实证（reamp\ 共 104 个 wav，其中 wet* 75）|
| `make_send.py` | 造发送信号：单声道 -> 48k/2ch/16bit + **自动裁空白** + 归一化到 −32 dBFS + 前后加静音 | 🟢 本轮实证（产出与本轮 `sendTarget.wav` **逐字节相同**）|
| `winmm.cs` | ★ 双工录音核心（WinMM）：ListIn / ListOut / Duplex / RecordOnly | 🟢 本轮实证 |

## 二、分轨（★ 可选 · 只在走「模型分轨」时用）

| 文件 | 职责 | 状态 |
|---|---|---|
| `dl_bsr.py` | 下 BS-Roformer SW 6-stem 模型（断点续传 + 代理切换 + sha256 校验）| ⚪ 本轮未跑（模型已在）|
| `dl_models.py` | 兼容别名 -> `dl_bsr.py` | ⚪ 本轮未跑 |
| `dl_resume.py` | 分段 Range 下载 + 重试（被 `dl_bsr.py` import）| ⚪ 本轮未跑 |
| `load_bsr.py` | 跑分轨（运行时注册 audio-separator 加载本地权重）| ⚪ 本轮未用（分轨是现成的）|

## 三、用法

```powershell
# 送 + 录（B 组：送参考曲段；A 组标定送 sendL32.wav）
powershell -NoProfile -ExecutionPolicy Bypass -File <本项目>\tools\do_reamp.ps1 ^
  -Send <发送wav> -RecSecs 14.1 -Out <录音wav>
# ★ 换设备：加 -DevicePattern "<新设备名片段>"（默认 "MOOER"）

# 造发送信号（★ 默认【自动裁空白】—— 与本轮做法、与 09 §一 的口径一致）
<本项目>\.venv\Scripts\python.exe <本项目>\tools\make_send.py ^
  "<用户录的那份 DI>" sendTarget.wav
#   参数: <源> <出> [峰值dBFS]      峰值默认 -32
#   要指定区间（不裁空白）: ... make_send.py <源> <出> -32 --from 12.0 --secs 10.05

# 分轨（可选）：先下模型 -> 再跑
<本项目>\.venv\Scripts\python.exe <本项目>\tools\dl_bsr.py              # 下模型（667 MB）
<本项目>\.venv\Scripts\python.exe <本项目>\tools\dl_bsr.py --check       # 只校验已有文件
<本项目>\.venv\Scripts\python.exe <本项目>\tools\load_bsr.py <歌> <出>   # 跑分轨
```

## 四、为什么是这 8 个（而不是把 40 个工具都搬来）

| 方案 | 为什么不 |
|---|---|
| 把 40 个工具都搬来 | ✗ 那 40 个里 **33 个靠 `__file__` 定位旧包根**（models / presets / songs / _env）—— 那套目录结构本 skill 不带 |
| **只留自足的这 8 个（采用）** | ✓ **零外部依赖** · 可以单独拷走 · 能独立跑出「**送 / 录 / 造信号 / 分轨**」四件事 |

★ 本轮评估过的其它工具（含 🔴 已验不能跑的 `reamp2.ps1` / `dump_sent.ps1`）作为**历史记录**留在
　 `../reference/11-工具清单.md §二` —— 只说明「当时为什么选 / 不选」，**不构成依赖**。
