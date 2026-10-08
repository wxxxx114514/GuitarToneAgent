# 电吉他效果器调音 Agent

> 用真实硬件（**MOOER GE250** 综合效果器）做**音色复制**与**人机交互调音**。

**核心闭环**：参考音频 → 目标指纹 → 改预设 JSON → reamp 测量 → 误差 → 搜索参数 → 循环

---

## 先说清楚：这是一个 Agent Skill 包，不是一个 Python 库

| | |
|---|---|
| **它是什么** | 一套方法论 + 可执行工具，以 **Agent Skill** 形式交付 |
| **入口是什么** | 让 AI 助手加载 `SKILL.md`，不是 `pip install` |
| **没有 AI 能用吗** | 能用一半：`tools/` 的脚本可以直接跑，但「读哪份文档、下一步做什么」靠人 |
| **clone 下来能直接跑吗** | 不能。环境要先用 `tools/setup.ps1` 重建（约 4.5 GB），模型要下载（699 MB） |

### 仓库里哪些是必须的，哪些能不看

```
SKILL.md               ← 入口（86 行，AI 每次整份加载）
reference/ 14 份        ← 方法论正文（按需读，是核心资产）
tools/                 ← 真正干活的脚本 + 装环境的脚本
pyproject.toml uv.lock ← 环境清单（能重建出同样的环境）
models/MANIFEST.json   ← 模型的来源与 sha256（权重本身不进库）
install-skill/         ← 装到 .dsh/skills 用的副本（脚本生成，别手改）
docs/                  ← 完整版方法论 + 示例会话记录 + 打包说明
songs/ presets/        ← 实例数据：一条完整闭环的输入与产物
```

**不进库的**（`.gitignore` 挡住）：`venv/` `python/` `ffmpeg/` `models/*.ckpt`、所有 `stems/` 与 `reamp/*.wav`。

### 两个 skill 的关系

```
guitar-tone-agent      主：完整方法论 + GE250 落地（预设是文件 → 程序改）
      └─ guitar-tone-manual  附属：同一套方法，落地换成「出表格 → 人手动拧」
```
两者是**平级**的两个 skill（DSH 只扫一层，不能互相嵌套），共享同一份 `reference/`。
安装方式见 [install-skill/安装说明.md](install-skill/安装说明.md)。

### 改完东西要同步

```powershell
powershell -File tools\sync-skill-src.ps1    # 项目根 -> install-skill\（逐份哈希校验）
powershell -File ..\sync-skill.ps1            # 项目根 -> .dsh\skills\（逐份哈希校验）
```

## 这是什么

给一首歌的吉他音色「画像」，然后在真实效果器上把它调出来。

不是软件仿真 —— **一切以真机测量为准**。吉他干声（DI）通过 USB 送进 GE250，
录回湿声，跟参考曲的目标曲线比，用最小二乘解出下一个预设该怎么改。

| 项 | 值 |
|---|---|
| **输入** | 一首歌（flac / wav） |
| **输出** | 一个能用的 GE250 预设（`.mo`） |
| **关键实测指标** | EQ 模型标定误差 **0.43 dB RMS** |

## 快速开始

### 1. 检查环境

```bat
tone env
```

### 2. 新建一首歌

```bat
tone new "歌名" "D:\path\原曲.flac"
```

### 3. 完整流程（详见 SKILL.md §9）

```bat
:: 先切到这首歌（后面所有命令都靠它定位数据；不设就必须显式传歌曲目录）
set SONG_DIR=%CD%\songs\歌名

:: 一、分轨（GPU 约 95 秒/首）
tone run load_bsr.py 输入音频 输出目录   :: 包内分离（见 reference/02）；日常也可用包外 `<StemSep 目录>\separate.ps1`

:: 二、目标曲线 + 调性 / 和弦 / 奏法占比
tone run target_whole.py
tone run chords.py
tone run bass_reference.py
tone run check_tuning.py
tone run technique.py

:: 三、生成给用户看的录音指令（只写弦号 + 品数，不含乐理）
tone run di_instructions.py

:: 四、用户录完干声 → 验证 → 归一化
tone run verify_di.py            :: 默认 di\palm_di.wav，可跟一个文件名
tone run meas_prep.py           :: 默认同上，可跟一个文件名

:: 五、闭环：reamp → 算误差 → 解参数 → 新预设
tone run analyze_round.py wet.wav   :: 湿声在 reamp\ 下，写文件名即可（文件名不会当成歌曲目录）
```

> **参数形状统一约定**：`tone run <脚本> [歌曲目录] [文件/选项]`。
> 设了 `SONG_DIR` 时**只写文件名**就行；没设就写成 `tone run analyze_round.py songs\歌名 wet.wav`。
> 两者混用也对，脚本会自己判断第一个参数是不是目录（`--song=<目录>` 是显式逃生口）。

## 目录结构

```text
GuitarToneAgent\
├─ tone.bat / tone.ps1     入口（list / new / run / env）
├─ SKILL.md                指令文档（86 行，整份加载）
├─ reference\              14 份参考资料（按需读，不常驻上下文）
├─ pyproject.toml / uv.lock  依赖清单（环境可由它重建）
├─ tools\                  全部脚本
│   ├─ songlib.py          * 共享库（描述子配方钉死在这里）
│   ├─ new_song.py         建歌曲工作区
│   ├─ target_whole.py     目标曲线（用全曲，不用单奏法段）
│   ├─ chords.py           调性 + 主要和弦
│   ├─ bass_reference.py   从贝斯轨提参考（根音分布，不是结论）
│   ├─ check_tuning.py     调弦判定（标准 / Drop D / 降半音 / Drop C）
│   ├─ technique.py        奏法占比（闷音 / 中间 / 开放）
│   ├─ di_instructions.py  * 给小白看的录音指令（弦号 + 品数）
│   ├─ verify_di.py        * 验证用户录的干声（自参照奏法检查）
│   ├─ meas_prep.py        归一化 + 格式转换 + 自验证
│   ├─ analyze_round.py    一轮湿声 vs 目标
│   ├─ verify_round.py     三层验证（绝对误差 / 逐帧 / EQ 标定）
│   ├─ noise_audit.py      链路噪声审计（信噪比 + 工频）
│   ├─ gen_palm_di.py      合成 DI（* 仅供参考，见 SKILL §9.1）
│   ├─ spec_metrics.py     逐帧指标（LSD / MCD / MultiRes）
│   ├─ error_decompose.py  地板 vs 可行动
│   ├─ dl_models.py        分轨模型下载 + sha256 校验
│   ├─ setup.ps1           一键装环境（uv sync + 下模型 + 自检）
│   ├─ reamp2.ps1          reamp 播放（WinMM）
│   └─ winmm.cs            WinMM P/Invoke 封装
├─ models\                分轨模型 + MANIFEST.json（sha256）
├─ presets\               设备导出的预设文件 + history\ 历史产物（★ 不是起点来源）
├─ docs\                  方法论完整版 + 示例会话记录
├─ python\ venv\          包内自带运行时（可直接跑）
└─ songs\                 每首歌一个目录（数据 + 结论）
```

## 环境准备

**两种方式，任选一种。**

**A. 直接跑**（包内已带完整运行时，零安装、可离线）

| 组件 | 位置 | 说明 |
|---|---|---|
| Python | `python\` | 3.13.13 基础解释器 |
| venv | `venv\` | torch + librosa + numpy 全套依赖（64 个包） |
| 分离模型 | `models\` | BS-Roformer 6 轨（699 MB） |
| ffmpeg | `ffmpeg\` | 音频格式转换 |

```bat
tone env      :: 确认环境
```

**B. 按清单重建**（环境不进版本库，靠 `pyproject.toml` + `uv.lock` 复现）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup.ps1
```

它做三件事：`uv sync` 建 `.venv`（63 个包，版本已冻结）→ `dl_bsr.py` 下模型并校验 sha256 → 自检。
想分步就照 [reference/10-环境与依赖.md](reference/10-环境与依赖.md) 走。

> `tone.ps1` 找 Python 的顺序：包内 `venv\` → `.venv\` → `TONE_PY` → `python_path.txt` → `py`/`python`/`python3`。
> 所以 A、B 两种环境都能直接被 `tone.bat` 用上。

### 搬到别的机器 / 别的盘

整个文件夹拷过去即可。两件事会自动处理：

1. **硬链接自动变真复制**（硬链接不跨卷，Windows 会拷成真实文件）
2. **`venv\pyvenv.cfg` 自动重写** —— `tone.ps1` 每次启动都检查 `home` 路径，
   指向包内的 `python\`。所以搬完直接能跑，**不用重建环境**。

> **拷完不要删 `python\` 目录** —— venv 依赖它作为 base_prefix。

### 如果想用外部环境

在 `python_path.txt` 里加一行路径，或者设环境变量：

```powershell
$env:TONE_PY = "D:\some\other\python.exe"
```

优先级：包内 venv  >  `TONE_PY`  >  `python_path.txt`  >  `py`  >  PATH。
**自动跳过 Windows Store 的假 python**（那个跑起来只会弹应用商店）。
## 读文档的正确姿势

`SKILL.md`（86 行）每次都会整份加载，它只放铁律 + 工作流 + 索引。
细节在 `reference/` 的 14 份里，**按需读，不常驻上下文**：

| 你想干什么 | 读哪份 |
|---|---|
| 刚接手这个项目 | `reference/00-边界.md`（能做什么、上限在哪） |
| 要开始一首新歌 | `reference/08-工作流详解.md` |
| 设备连不上 / USB | `reference/01-硬件与信号链.md` |
| 某个脚本干什么 | `reference/02-工具清单.md` |
| 测量结果看着不对 | `reference/03-陷阱清单.md`（每条都真实踩过） |
| 误差降不下去了 | `reference/05-指标体系.md`（地板 vs 可行动） |
| 要改 EQ 参数 | `reference/09-参数速查与经典配置.md` §10.1 · §10.4 |
| 描述子数字对不上 | `reference/06-奏法处理.md` §7.2（配方钉死） |
| **要选箱头 / 箱体 / 推子** | `reference/09-参数速查与经典配置.md` **§10.7** |
| 参考曲分析拿不准 | `reference/11-扒谱边界.md` |
| **不是 GE250，换别的效果器** | `reference/12-其他效果器.md` → 加载附属 skill `guitar-tone-manual` |
| 想试新方法 | `reference/07-已证伪路线.md`（先看有没有试过） |

## 三条最容易踩的坑

1. **内容不匹配的比对是无效的**（§7.3）

   DI 的奏法 / 调性 / 和声 / 调弦必须跟目标一致。
   实测：奏法不对齐时，测出的「音色误差」里 **60% 是假的**。

2. **界面显示的 dB 不要拿来算参数**（§10.4）

   GE250 界面的刻度跟真实刻度差约 3 倍。

3. **描述子配方必须钉死在代码里**（§7.2）

   同一个描述、两个人实现，实测差 **35.5 个百分点**。
   配方在 `tools/songlib.py` 的 `DESC_RECIPE`，改任何一格都要重新标定锚点。

## 已验证的关键数字

| 项 | 实测 |
|---|---|
| 设备实时比 | 1.000x（10.000 s -> 10.006 s） |
| 设备确定性 | 0.008 dB RMS / 0.022 dB max |
| 往返延迟 | 100-250 ms（**每次都要重新对齐**） |
| EQ 刻度 | 1 单位 = 0.1848 dB，sigma 约 0.985 八度 |
| EQ 模型误差 | **0.43 dB RMS** |
| 可行动空间 | 0.62 dB RMS |
| 误差地板（某首歌） | 1.36 dB RMS |

---

## 授权 / License

**保留所有权利（All rights reserved）** —— 本仓库未采用开源许可证。

| 可以 | 不可以 |
|---|---|
| 阅读、学习，把这套方法用在自己的设备上 | **商业使用** |
| 按这里的思路做你自己的调音流程 | **复制/修改后重新发布** |
| 在文章里引用，**注明来源并附仓库链接** | **去掉署名当成自己的东西** |

简单说：**看和学没问题，别拿去卖，也别打包成别人的作品。**
有商业授权、转载、合作的需求，请开 Issue 联系。

> 仓库**不包含**任何音频或音乐作品；`songs/` 里只有数值结果，
> 其中的歌曲名/艺人名仅用于描述来源，相关权利归各自所有者。
> 第三方依赖（PyTorch / librosa / audio-separator 等）与模型权重各有其自己的许可，本仓库不重新分发。

---

*指令见 [SKILL.md](SKILL.md)；14 份参考资料在 [reference/](reference/)。*
