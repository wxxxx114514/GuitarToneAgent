r"""所有分析脚本共用的【歌曲目录】解析

设计目标：脚本不假设是哪首歌。
   优先级:  命令行参数  >  $SONG_DIR  >  报错退出（不猜）

约定目录结构:
   <歌曲目录>\
       source.txt     原曲路径
       stems\         分离结果（guitar.wav / bass.wav / ...）
       target.npy     全曲目标曲线（13 频段）
       spec.json      演奏规格
       di\            干声
       reamp\         每轮录音
       notes.md       进展记录
"""
import os, sys
from pathlib import Path

BANDS = [(80,113),(113,160),(160,226),(226,320),(320,452),(452,640),(640,905),(905,1280),
         (1280,1810),(1810,2560),(2560,3620),(3620,5120),(5120,7240)]
FC = [int((a*b)**0.5) for a,b in BANDS]

SIX = ["vocals","bass","drums","guitar","piano","other"]

HELP = (
    "未指定歌曲目录。四种用法：\n"
    "  1) 设环境变量:  $env:SONG_DIR='$PkgRoot\\songs\\<歌名>'\n"
    "  2) 命令行参数:  python xxx.py <歌曲目录> [文件/选项]\n"
    "  3) 显式指定:    python xxx.py --song=<歌曲目录> [文件/选项]\n"
    "  4) 新建一首:    python new_song.py \"歌名\" \"原曲.flac\"\n"
)

def song_dir(arg=None, must_exist=True):
    """定位歌曲目录。

    优先级：显式参数 > $env:SONG_DIR > argv[1]（且必须真的是个已存在的目录）
    > --song=<目录>

    为什么 argv[1] 要加 is_dir 判断：多个脚本的用法是
    `xxx.py [歌曲目录] [文件/选项]`，argv[1] 大多数时候是文件名或
    调弦名（如 wet.wav / drop_d），误把它当目录会直接报“歌曲目录不存在”。
    """
    cand = arg or os.environ.get("SONG_DIR")
    if not cand and len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        if Path(sys.argv[1]).expanduser().is_dir():
            cand = sys.argv[1]
    if not cand:
        for a in sys.argv[1:]:
            if a.startswith("--song="):
                cand = a.split("=", 1)[1]; break
    d = cand
    if not d:
        print(HELP); sys.exit(2)
    p = Path(d).expanduser().resolve()
    if must_exist and not p.exists():
        print("歌曲目录不存在: %s\n%s" % (p, HELP)); sys.exit(2)
    return p

def file_args():
    """取【文件/选项】那类位置参数。

    约定：`xxx.py [歌曲目录] [文件/选项]` —— argv[1] 若真是目录就跳过它，
    剩下的才当作文件/选项。这样下面两种写法都对：
        analyze_round.py songs\BlackShout wet.wav
        $env:SONG_DIR=...; analyze_round.py wet.wav
    """
    a = sys.argv[1:]
    if a and Path(a[0]).expanduser().is_dir():
        a = a[1:]
    return [x for x in a if not x.startswith("-")]


def P(d, kind):
    """取歌曲目录下的标准位置"""
    d = Path(d)
    return {
        "stems":   d / "stems",
        "guitar":  d / "stems" / "guitar.wav",
        "target":  d / "target.npy",
        "di":      d / "di",
        "reamp":   d / "reamp",
        "spec":    d / "spec.json",
        "notes":   d / "notes.md",
        "source":  d / "source.txt",
    }[kind]

def require(p, what="文件"):
    p = Path(p)
    if not p.exists():
        print("缺少%s: %s" % (what, p)); sys.exit(2)
    return p

# ---- 共用的小工具 ----
import numpy as np

def db(v):
    return 20*np.log10(np.maximum(v, 1e-12))

def envelope(x, sr, bands=None):
    """时间平均 1/3 倍频程包络（去均值）"""
    bands = bands or BANDS
    N = 16384; acc = np.zeros(N//2+1); c = 0
    for s in range(0, max(len(x)-N, 1), 8192):
        acc += np.abs(np.fft.rfft(x[s:s+N]*np.hanning(N)))**2; c += 1
    sp = np.sqrt(acc/max(c,1)); f = np.fft.rfftfreq(N, 1/sr)
    v = np.array([10*np.log10(sp[(f>=a)&(f<b)].sum()+1e-20) for a,b in bands])
    return v - v.mean()

def load_mono(p, sr=None):
    import soundfile as sf
    x, s = sf.read(str(p), always_2d=True, dtype="float32")
    if sr is not None:
        assert s == sr, "%s 采样率 %d != %d（stems 是 44100，reamp 录音是 48000）" % (p, s, sr)
    return x.mean(1), s


# ============================================================
# 奏法描述子 —— ★ 配方钉死在这里，所有脚本必须调这个函数
# ============================================================
#
# 【为什么钉死】两个都懂行的人、都照「低频占比(100–450Hz) + 频谱质心」实现，
# 实测差 35.5 个百分点。描述里少写一个自由度，后人就多一次 1.6 倍。
#
# 【变体谱系】同一份 di.wav / c.wav，7 种实现（跨度 35.5 点）：
#   A pool + rms幅度      61.6% / 652 Hz
#   C pool + 平均幅度     66.3% / 582 Hz
#   G 逐帧 + 幅度 + mean  73.3% / 511 Hz
#   F 逐帧 + 幅度 + median 75.8% / 467 Hz
#   B pool + 平均功率     86.0% / 307 Hz
#   E 逐帧 + 功率 + mean  90.9% / 298 Hz
#   D 逐帧 + 功率 + median 97.1% / 325 Hz   ← 本配方（D）
#
# 【各格权重】（di.wav，只改一处）：
#   聚合顺序（per_frame vs pool）  功率域内差 11 点   ← 最大
#   域（功率/幅度/RMS幅度）        差约 20~25 点，质心差 2 倍
#   统计量（median/mean）          6~8 点
#   门限（有/无）                  3~4 点
#   窗长 2048~16384                ~1 点
#   hop                            0
#   分母上限 6k~24k                0（★ 仅对干声成立，见下）
#
# 根因：低频占比是【非线性】运算 —— 先聚合后算比值 ≠ 先算比值后聚合。
#
DESC_RECIPE = {
    # ---- 聚合顺序 ★★★ 最大的一格 ----
    "aggregation": "per_frame_then_stat",
    #   "per_frame_then_stat"  逐帧算比值/质心，再跨帧统计
    #   "pool_then_ratio"      先把频谱池化，再从池化谱算比值/质心

    # ---- 域（★ 两种聚合下语义不同，故拆成两格）----
    "per_frame_domain": "power",       # aggregation=per_frame 时生效："power" | "amplitude"
    "pooled_domain": "power",          # aggregation=pool 时生效：
    #   "power"          池化 |X|^2 再算比值          -> 86.0%
    #   "amplitude"      池化 |X|   再算比值          -> 66.3%
    #   "rms_amplitude"  池化 |X|^2 后【逐 bin 开方】 -> 61.6%   ★ 别跟上面混

    # ---- 跨帧统计（仅 aggregation=per_frame 时有效）----
    "frame_statistic": "median",       # "median" | "mean"

    # ---- 时频分析 ----
    "n_fft": 8192,
    "hop": 4096,
    "window": "hann",
    "gate_db": -60.0,

    # ---- 频段与分母 ----
    "band_lo": 100.0,
    "band_hi": 450.0,
    "denominator_hi_hz": None,         # None = 到 Nyquist
    #   ⚠️ 实测「分母上限无影响」只对【干声】成立（拾音器+线材低通，6k 以上没能量）。
    #      失真湿声在 10k 以上有大量谐波 —— 用湿声测时必须重新确认这一格。

    # ---- 版本锚 ----
    "recipe_version": "2026-09-28/b",
}

def _spec_frames(x, sr, p):
    """逐帧幅度谱（已过门限）-> (f, [A...])"""
    N = int(p["n_fft"]); HOP = int(p["hop"])
    w = np.hanning(N) if p["window"] == "hann" else np.ones(N)
    f = np.fft.rfftfreq(N, 1.0/sr)
    out = []
    for i in range(0, max(len(x)-N, 1), HOP):
        seg = x[i:i+N]
        if len(seg) < N: break
        g = p.get("gate_db")
        if g is not None:
            if db(np.sqrt((seg.astype(np.float64)**2).mean())) < g: continue
        out.append(np.abs(np.fft.rfft(seg*w)))
    return f, out

def technique_descriptor(x, sr, **over):
    """奏法描述子 -> (低频占比%, 频谱质心Hz)

    ★ 配方见 DESC_RECIPE。改任何一格都必须重新标定锚点（见 §7.2）。

    ⚠️ 干声和湿声的绝对值不可横向比（失真堆谐波、混音又高通）。
       绝对锚点只用于【湿声】；干声一律用【自参照】。
    """
    p = dict(DESC_RECIPE); p.update(over)
    f, frames = _spec_frames(x, sr, p)
    if not frames: return (float("nan"), float("nan"))
    m_lo = (f >= p["band_lo"]) & (f <= p["band_hi"])
    m_den = np.ones_like(f, bool)
    if p["denominator_hi_hz"]: m_den = f <= p["denominator_hi_hz"]

    if p["aggregation"] == "per_frame_then_stat":
        dom = p["per_frame_domain"]
        fr, ce = [], []
        for A in frames:
            V = A**2 if dom == "power" else A
            t = V[m_den].sum()
            if t <= 0: continue
            fr.append(100.0*V[m_lo].sum()/t)
            ce.append(float((f[m_den]*V[m_den]).sum()/t))
        if not fr: return (float("nan"), float("nan"))
        fn = np.median if p["frame_statistic"] == "median" else np.mean
        return (float(fn(fr)), float(fn(ce)))

    else:   # pool_then_ratio
        acc = np.zeros_like(frames[0])
        for A in frames: acc += A**2          # 功率池化
        acc /= len(frames)
        dom = p["pooled_domain"]
        V = acc if dom == "power" else (np.sqrt(acc) if dom == "rms_amplitude" else None)
        if V is None:                          # amplitude：池化幅度
            accA = np.zeros_like(frames[0])
            for A in frames: accA += A
            V = accA / len(frames)
        t = V[m_den].sum()
        if t <= 0: return (float("nan"), float("nan"))
        return (float(100.0*V[m_lo].sum()/t), float((f[m_den]*V[m_den]).sum()/t))

def technique_descriptor_frames(x, sr, **over):
    """逐帧版本 -> (times[], lowmid%[], centroid[])。仅 aggregation=per_frame 时有意义。"""
    p = dict(DESC_RECIPE); p.update(over)
    N = int(p["n_fft"]); HOP = int(p["hop"])
    w = np.hanning(N) if p["window"] == "hann" else np.ones(N)
    f = np.fft.rfftfreq(N, 1.0/sr)
    m_lo = (f >= p["band_lo"]) & (f <= p["band_hi"])
    dom = p.get("per_frame_domain", "power")
    T, FR, CE = [], [], []
    for i in range(0, max(len(x)-N, 1), HOP):
        seg = x[i:i+N]
        if len(seg) < N: break
        g = p.get("gate_db")
        if g is not None:
            if db(np.sqrt((seg.astype(np.float64)**2).mean())) < g: continue
        A = np.abs(np.fft.rfft(seg*w))
        V = A**2 if dom == "power" else A
        t = V.sum()
        if t <= 0: continue
        T.append(i/sr); FR.append(100.0*V[m_lo].sum()/t); CE.append(float((f*V).sum()/t))
    return (np.array(T), np.array(FR), np.array(CE))
def find_start(x, sr, thr_db=-50, win_ms=10):
    win = int(win_ms/1000*sr)
    pk = np.abs(x).max(); thr = pk*(10**(thr_db/20))
    for i in range(0, max(len(x)-win,1), win):
        if np.abs(x[i:i+win]).max() > thr: return i/sr
    return 0.0
