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


def utf8_stdout():
    """直接跑脚本时（不经 tone.bat）中文和符号不炸。

    tone.bat 会 chcp 65001 并设 PYTHONIOENCODING=utf-8；但文档里也有直接
    「python xxx.py」的用法，那时 Windows 控制台默认 GBK，遇到 ★/⚠ 这类字符会
    UnicodeEncodeError 把脚本打断 —— 报错的行号还跟真正的问题无关。
    """
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass


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
    r"""取【文件/选项】那类位置参数。

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

CH_LAST = {}          # 最近一次读入的声道证据，供上层复核/落盘
# ★ 阈值与标定记录（用真 stems 拼的对抗样本，20 s/段，同一配方）：
#     样本                         cos min / p10 / med      env 中位 / 最大 (dB)   判
#     bass  L|R   真文件           0.9883 / 0.9956 / 0.9995  0.083 / 0.443        同内容
#     guitar L|R  真文件           0.9969 / 0.9985 / 0.9991  0.240 / 0.352        同内容
#     guitar|bass 真两音源（同步）  0.8910 / 0.9108 / 0.9822  6.700 / 9.758        两音源
#     guitar|vocals 真两音源（同步）0.9291 / 0.9524 / 0.9768  8.003 / 10.361       两音源
#   → **env_rms 才是真判别量**：同内容最大 0.443 dB vs 两音源中位 6.7 dB（15 倍余量）；
#     chroma 的 0.99 坐在一条缝上（同内容最差 0.9883 / 两音源最好 0.9291），取中点 = 0.96。
#   统计量保留 min（也保留 p10）：两音源的 med 只低 0.017，min 低 0.097 —— min 有分辨力。
CHROMA_SAME = 0.96    # 逐段 chroma 余弦下限（同内容）【实测中点，不是标定值】
ENV_SAME_DB = 0.5     # 13 段包络差的 RMS 上限（dB，同内容）—— 有实测支撑（0.443 vs 6.7）
# ★ 逐段比较前的【电平门】：段 RMS 比"整轨段 RMS 中位"低超过这么多 dB 的段，不参与比较。
#   实测（BlackShout bass.wav）：第 0 段 RMS = −111.1 dBFS，比中位低 94.3 dB —— chroma 是在噪声上算的，
#   余弦没有意义；而原有的跳过只有 std() < 1e-9（**数字**静音），−111 dBFS 的抖动过得去。
#   ★ 这就是那个「贝斯轨被判两音源」假警报的真凶 —— 不是"贝斯 chroma 天生低"（逐段 11/12 段 ≥ 0.9952，比吉他更同内容）。
LEVEL_GATE_DB = 30.0  # 【疑似】建议值，未标定（只证了 −94 dB 必须跳、−3 dB 必须留）


def channel_check(x, sr, seg_s=20.0):
    """立体声 -> (决策, 证据)。决策 = "mono"（同一把琴双轨，取平均是对的）或 "ask"（要问用户）

    ★ 为什么不用 L/R 波形相关：**同一把琴录两遍（双轨）和两把琴，波形相关都给 ~0 —— 没有分辨力。**
      实测 BlackShout：整轨 L/R 相关 0.0338（旧判据据此喊「不止一个音源」、还建议「用 L / 用 R」，
      而那正好是双轨歌不该做的事），但每 20 s 的 chroma 余弦 ≥ 0.9981、
      13 段包络差整轨 0.15 dB（分段中位 0.24 / 最大 0.35）、最佳时延相关只有 +0.0838（无固定时延）
      -> 它就是【同一把琴双轨】。
    失效条件：① 只有一首真歌的数字，"两把琴"没有真素材，阈值的分辨力没验过；
      ② 歌里两把琴弹同样的东西（同 riff 同音区）时本条也判 "mono" —— 那时平均反而没错；
      ③ 逐段 chroma 依赖调性内容，纯噪声段会给出无意义的余弦（已跳过静音段）。
      ④ **电平门的代价**：证据只存在于【安静段】时，那一段整段不参与比较（屏幕会报"跳过 N 段低电平"）。
         实测（把第 0 段两声道都压到 −40 dB、且那里 L=吉他/R=贝斯）：n_seg 11 / skip 1，结论只看剩下 11 段。
         ★ 诚实边界：对照组那段余弦 0.9916【没有翻转】—— 只能说他"不参与比较"，不能说"因此漏判"。
      ⑤ **单侧衰减不会误判**：余弦对电平不变，而电平门取的是【两声道合并】的段 RMS ->
         硬声像 / 一侧很轻的素材（R 衰减 −40/−60/−100 dB 实测全判 mono，cos≈1.0）不会被误伤。
      ④ **电平门的代价**：证据只存在于【安静段】时，那一段整段不参与比较（屏幕上会报"跳过 N 段低电平"）。
         实测（把第 0 段两声道都压到 −40 dB、且那里 L=吉他/R=贝斯）：n_seg 11 / skip 1，结论只看剩下 11 段。
         ★ 诚实边界：对照组那段余弦 0.9916【没有翻转】—— 所以能说的是"那段不参与比较"，不能说"因此漏判"。
      ⑤ **单侧衰减不会误判**：余弦对电平不变，而电平门取的是【两声道合并】的段 RMS ->
         硬声像 / 一侧很轻的素材（R 衰减 −40/−60/−100 dB 实测全判 mono，cos≈1.0）不会被这条门误伤。
    """
    import librosa
    L = x[:, 0].astype(np.float64); Rr = x[:, 1].astype(np.float64)
    if L.std() < 1e-9 or Rr.std() < 1e-9:
        both = (L.std() < 1e-9 and Rr.std() < 1e-9)
        return "mono", {"chroma_cos_min": None, "env_diff_rms_db": None, "waveform_corr": None,
                        "n_segments": 0,       # ★ 必须带上：否则下游 ev.get("n_segments",0) 会误判
                        "note": "两侧都是静音" if both else "有一侧是静音"}
    n = int(seg_s * sr); cos_list, env_list = [], []
    # ★【电平门】段 RMS 比“整轨段 RMS 中位”低超过 LEVEL_GATE_DB 的段不参与比较。
    #   实测（BlackShout bass.wav）第 0 段 RMS = −111.1 dBFS（比中位低 94.3 dB）—— chroma 是在噪声上算的，
    #   而原有的跳过只有 std()<1e-9（数字静音），−111 dBFS 的抖动过得去：这就是「贝斯轨被判两音源」假警报的真凶。
    _segs = [(s0, L[s0:s0+n], Rr[s0:s0+n]) for s0 in range(0, max(len(L) - n + 1, 1), n)]
    _rms = [np.sqrt((np.concatenate([a, b]).astype(np.float64)**2).mean()) for _, a, b in _segs if len(a) >= sr]
    _med = float(np.median(_rms)) if _rms else 0.0
    n_skipped_level = 0
    for s0, a, b in _segs:
        if len(a) < sr or a.std() < 1e-9 or b.std() < 1e-9:
            continue
        # ★ 太安静的段不参与比较（并计数 —— 屏幕要报被跳过的段数）
        if _med > 0 and db(np.sqrt((np.concatenate([a, b]).astype(np.float64)**2).mean())) < db(_med) - LEVEL_GATE_DB:
            n_skipped_level += 1
            continue
        ca = librosa.feature.chroma_cqt(y=a.astype(np.float32), sr=sr, hop_length=512).mean(1)
        cb = librosa.feature.chroma_cqt(y=b.astype(np.float32), sr=sr, hop_length=512).mean(1)
        cos_list.append(float(ca @ cb / (np.linalg.norm(ca)*np.linalg.norm(cb) + 1e-12)))
        ea, eb = envelope(a, sr), envelope(b, sr)   # 包络差取【中位】（典型段）；判据的最坏段由 chroma 的 min 承担
        env_list.append(float(np.sqrt(np.mean((ea - eb) ** 2))))
    cos_min = min(cos_list) if cos_list else 0.0
    env_rms = float(np.median(env_list)) if env_list else 99.0
    c_wave = float(np.corrcoef(L, Rr)[0, 1])
    same = (cos_min >= CHROMA_SAME) and (env_rms <= ENV_SAME_DB)
    return (("mono" if same else "ask"),
           {"chroma_cos_min": round(cos_min, 4), "env_diff_rms_db": round(env_rms, 3),
            "waveform_corr": round(c_wave, 4), "n_segments": len(cos_list),
            "n_skipped_level": n_skipped_level,
            "cos_p10": round(float(np.percentile(cos_list, 10)), 4) if cos_list else None,
            "cos_median": round(float(np.median(cos_list)), 4) if cos_list else None,
            "thresholds": {"chroma_cos": CHROMA_SAME, "env_db": ENV_SAME_DB,
                           "level_gate_db": LEVEL_GATE_DB}})

def load_mono(p, sr=None, quiet=False):
    """读成单声道（立体声安全）-> (mono, sr)

    ★ 声道自检（实测教训）：
      `温度差/guitar.wav` 的 L/R 相关只有 **0.3325**，起音密度 L 1.01/s vs R 2.36/s
      —— L 是主音、R 是节奏，**两把不同的琴**。
      `x.mean(1)` 会【静默】把它们平均成"两种音色的平均值"，
      而这个错目标会一路传到目标曲线和所有 EQ 解算，**中途没有任何地方会报错**。
      所以相关 < 0.90 必须喊出来。
    """
    import soundfile as sf
    x, s = sf.read(str(p), always_2d=True, dtype="float32")
    if sr is not None:
        assert s == sr, "%s 采样率 %d != %d（stems 是 44100，reamp 录音是 48000）" % (p, s, sr)
    if x.shape[1] >= 2:
        dec, ev = channel_check(x, s)
        ev["decision"] = dec
        CH_LAST[str(p)] = ev
        _cm, _ed = ev.get("chroma_cos_min"), ev.get("env_diff_rms_db")
        # ★ n_segments == 0：一次可比测量都没有，两个统计量是哨兵值（0.0 / 99.0）——
        #   不许拿它们当证据、更不许下「不止一个音源」这种硬结论（和 ④b 的"空集合"是同一类错）。
        if not quiet and (_cm is None or _ed is None):
            # ★【顺序很重要】：这条必须排在 n_segments==0 之前 —— 早退分支没有 n_segments 键时
            #   ev.get(...,0) 会取到 0，把"整条右声道全 0"（一个【确定】的答案）误报成
            #   "每段各有一侧静音"（无法判断）。实测这就是我上一轮修 T2-3 时把上一轮修好的 T1 遮掉的形态。
            print("  [声道] %s %s —— 按单声道处理"
                  % (str(p).replace(chr(92), "/").split("/")[-1], ev.get("note") or "无法比较内容"))
        elif not quiet and ev.get("n_segments", 0) == 0:
            print("  [声道] %s 一个可比的段都没有（每段都有一侧是静音）—— 无法判断，请人工看"
                  % str(p).replace(chr(92), "/").split("/")[-1])
        elif dec == "ask" and not quiet:
            print("  !! 声道自检: %s 里 L 与 R 的内容不一致" % str(p).replace(chr(92), "/").split("/")[-1])
            # ★【只报实际触发的那条】：原来无论谁触发都印两个括号，实测贝斯轨那次只有 chroma 触发、
            #   包络差却印着「（> 0.50）」（真值 0.083）—— 打印的数字不真，是 T2。
            _parts = []
            if _cm < CHROMA_SAME:
                _parts.append("逐段 chroma 余弦最低 %.4f（< %.2f）" % (_cm, CHROMA_SAME))
            if _ed > ENV_SAME_DB:
                _parts.append("%d 段包络差中位 %.3f dB（> %.2f）" % (ev.get("n_segments", 0), _ed, ENV_SAME_DB))
            _sk = ev.get("n_skipped_level") or 0
            print("     " + " · ".join(_parts) + ("；另有 %d 段因电平过低未参与比较" % _sk if _sk else ""))
            print("     -> 这条轨里【不止一个音源】。直接平均 = 两种音色混成一个，")
            print("        目标曲线和后面所有 EQ 解算都会建在这个错目标上。")
            print("     -> 要问用户：这首歌的吉他是【一把双轨】还是【两把各弹各的】；")
            print("        后者要指定用哪一把（target_channel = L / R）。")
        elif not quiet:
            _sk = ev.get("n_skipped_level") or 0
            print("  [声道] L/R 同内容（chroma 余弦 ≥ %.4f，包络差中位 %.3f dB%s）-> 取平均是对的"
                  % (_cm, _ed, ("，跳过 %d 段低电平" % _sk) if _sk else ""))
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
# 奏法判据：音符衰减（闷音 100-250 ms 死掉，开放 1 s 以上）。
# 频谱量（低频占比/质心）测的是音区高低和混音 EQ，不能判奏法 —— 见 07-已证伪路线.md §8.5。
DECAY_RECIPE = {
    "hp_hz": 80.0,          # 高通，去掉可能是贝斯漏进来的低频
    "frame": 1024,
    "hop": 128,
    "slope_window_s": 0.40, # 峰值后用于拟合衰减斜率的最长时长
    "min_span_s": 0.06,     # 太短的窗不算
    "min_drop_db": 6.0,     # 窗内至少要掉这么多 dB，否则这个音测不了
    "peak_window_s": 0.12,  # 峰值搜索窗
    "min_peak_db": -30.0,   # 峰值至少高出全局峰值这么多，否则不算一个音
    "recipe_version": "2026-09-29/b",
}

def _decay_core(x, sr, **over):
    """共用实现 -> (times[], rates[], info)

    每个音符：从峰值起，到【下一个音符起始】或 slope_window 为止（先到者），
    在这段里对 dB 包络做最小二乘拟合，得到衰减斜率（dB/s，负 = 在衰减）。

    ★ 为什么不用"降到峰值 -15 dB 所需的时间"：
      实测在密集段落里电平根本降不下来（下一个音立刻接上），
      那个量会跑到几十秒 —— BlackShout 真实吉他轨上 p90 = 23.4 s，全是假的。
      斜率只用峰值后那一小段，天然有界。

    info 记【覆盖率】—— 占比的底层样本有多大，是这一项的全部意义：
      n_onsets    检出的音符事件数（分母）
      n_measured  真能测出衰减的（分子）
      n_too_flat  min_drop_db 分钟内根本没掉下来 -> 测不了（密集段落全是这一类）
      coverage    n_measured / n_onsets
    """
    import librosa
    from scipy.signal import butter, sosfilt
    p = dict(DECAY_RECIPE); p.update(over)
    y = sosfilt(butter(4, p["hp_hz"]/(sr/2.0), "high", output="sos"), x).astype(np.float32)
    HOP = int(p["hop"])
    r = librosa.feature.rms(y=y, frame_length=int(p["frame"]), hop_length=HOP)[0]
    dbv = 20*np.log10(np.maximum(r, 1e-9))
    info = {"n_onsets": 0, "n_measured": 0, "n_too_flat": 0, "coverage": 0.0,
            "recipe": p["recipe_version"]}
    if len(dbv) < 4: return (np.array([]), np.array([]), info)
    ons = librosa.onset.onset_detect(y=y, sr=sr, hop_length=HOP, units="frames", backtrack=False)
    info["n_onsets"] = int(len(ons))
    ons = np.append(ons, len(dbv) + int(p["slope_window_s"]*sr/HOP))
    T, R = [], []
    peakw = int(p["peak_window_s"]*sr/HOP) + 1
    spanw = max(3, int(p["slope_window_s"]*sr/HOP))
    minw  = max(3, int(p["min_span_s"]*sr/HOP))
    for k, i0 in enumerate(ons[:-1]):
        seg = dbv[i0:i0+peakw]
        if len(seg) < 3: continue
        ip = i0 + int(np.argmax(seg))
        if dbv[ip] < dbv.max() + p["min_peak_db"]: continue
        # 衰减窗：到下一个 onset 或 slope_window 为止
        end = min(ip + spanw, int(ons[k+1]))
        if end - ip < minw: continue
        w = dbv[ip:end]
        if w[0] - w.min() < p["min_drop_db"]:
            info["n_too_flat"] += 1
            continue                                     # 这一段压根没掉下来，测不了
        tt = np.arange(len(w)) * HOP / float(sr)
        slope = float(np.polyfit(tt, w, 1)[0])           # dB/s
        if slope >= 0: continue                          # 没在衰减，丢弃
        T.append(ip*HOP/float(sr)); R.append(slope)
    info["n_measured"] = len(T)
    info["coverage"] = (float(len(T))/info["n_onsets"]) if info["n_onsets"] else 0.0
    return (np.array(T), np.array(R), info)


def note_decay_times(x, sr, **over):
    """-> (times[], rates[])   要看覆盖率用 note_decay_report()"""
    T, R, _ = _decay_core(x, sr, **over)
    return (T, R)


def note_decay_report(x, sr, **over):
    """-> (times[], rates[], info)   info 见 _decay_core"""
    return _decay_core(x, sr, **over)


def decay_ms(rate):
    """衰减斜率(dB/s) -> 外推的【掉 10 dB 要多少毫秒】

    这是 08-工作流详解.md §9.1 与 06-奏法处理.md §7.1 说的"快 ≥ 50 ms"的同一把尺子，
    全项目只在这里换算一次。

    ⚠️ 失效条件：斜率慢于 -25 dB/s 时，-10 dB 时间超过 0.40 s 的拟合窗（DECAY_RECIPE
    slope_window_s）—— 那就成了外推值。外推值只准用于【两段之间的比较】，
    不准当绝对时值引用。
    """
    if rate >= 0: return float("inf")
    return 10000.0/abs(rate)


def f0_track(x, sr, fmin=25.0, fmax=1200.0, hop=512, frame=4096,
             min_voiced_prob=0.0, level_floor_db=-45.0,
             min_prominence_db=6.0, stats=None, min_playable_hz=None):
    """逐帧基频 -> (times[], midi[])，只返回【验过的】帧

    ★ 四道检查，少一道就会被自己的估计器骗（四条都是实测踩出来的）。最终判据只有一条：
      **这个音必须在频谱上真的有分量**。另外三道是它的门与校正：

    ⓪ 电平门 level_floor_db：比全曲最响帧低 45 dB 以上的不算音。

    ① 八度归位（最重要）：pyin 在复音上会报【合成周期的基频】，比真正的音低若干八度 ——
       强力和弦 D2+A2+D3（2:3:4）报 D1；三和弦 F3+A3+C4（4:5:6）报 F1。
       所以：报出的 f 在频谱上没有分量、而它的 2/4/8 倍有 -> 取"有分量的最小倍数"。
       ★ 不要用"低于乐器最低音"当校正条件 —— 那个例外漏掉三和弦（F2 在吉他音域内）。
    ② 分量门（-25 dB）：归位之后必须在频谱上有分量，且不低于该帧最强分量的 -25 dB。
       （★ -35 太松：裙边也能过，于是任何小于 4 的倍数都会停在幻影上 —— 实测过。）
       ★ 只比"峰/底噪"不够：两个都很小的数也能比出 20 dB（实测 F 三和弦的泄漏尾巴）。
    ③ 对比度门 min_prominence_db：峰 比 0.5f~1.5f 带内的【10% 分位】高 6 dB 以上。
       底噪必须用 10% 分位而不是中位数 —— 和弦里别的音会落进这个带，把中位数抬起来。
    ④ 归位之后的下限门 min_playable_hz：仍低于 63 Hz 的一律不当音符（吉他按支持的调弦
       最低是 drop_c 的 C2 = 65.4 Hz）—— 这是拦工频的地方，**必须在归位之后**，否则会误杀和弦。

    ★ 失效条件（实测）：
      · 真实基频比该帧最强分量低 25 dB 以上（极瘦的拾音 + 强高通）-> 会被误升八度；
      · 高把位三和弦的基频落在低音区之外、本来就不参与调弦判断（Am = A3+C4+E4 全是 C3 以上）；
      · 噪声挡不干净（它是筛子不是判据）：当前门下白噪声/工频/带限噪声实测都是 0 帧，
        但这是**实例相关**的（同一构造换随机种子会漏几帧），不要当成定理。
    ★ 已经不用 voiced_prob 当门：它在小三和弦上是 0 帧（实测 Am 的 vprob 全部 < 0.15），
      而噪声靠 ②③ 两道门挡 —— 它是【筛子】不是【判据】：漏进来的少数帧要靠下游的
      最小占比（MIN_FRAMES / MIN_DOM_SHARE）与并列规则吸收。

    ★ fmin 默认 25 Hz，不是 35：5 弦贝斯低 B 是 30.87 Hz，fmin=35 够不到，
      实测会把 B 报成 C#（100% 置信、零告警）。
    """
    import librosa
    f0, _vflag, vprob = librosa.pyin(x, fmin=fmin, fmax=fmax, sr=sr,
                                     frame_length=int(frame), hop_length=int(hop))
    t = librosa.times_like(f0, sr=sr, hop_length=int(hop))
    # ① 有声门：阈值要【松】（0.15）。多音同时响（强力和弦）时 pyin 的 voiced_prob
    #    会掉到很低，卡 0.5 会把整首强力和弦的歌全挡掉（实测 D5/E5 直接 0 帧）。
    #    噪声靠下面的 ③ 峰度检查挡，不靠这一道。
    ok = ~np.isnan(f0) & (vprob >= min_voiced_prob)
    n_too_low = n_no_pitch = n_no_h2 = n_flat = 0

    # ② 电平门：比全曲最响帧低 level_floor_db 以上的不算音
    r = librosa.feature.rms(y=x, frame_length=int(frame), hop_length=int(hop))[0]
    if len(r) != len(f0):
        r = np.interp(np.linspace(0, 1, len(f0)), np.linspace(0, 1, len(r)), r)
    floor = r.max() * (10.0 ** (level_floor_db/20.0))
    ok &= (r > floor)

    # 验证用的频谱：【4 倍长的窗】。
    # 为什么不用同一个 4096：低频处一格的宽度就是 10.8 Hz，一个 31 Hz 的音主瓣
    # 会把整条"底噪带"占满 -> 峰和底噪分不开 -> 真音被当噪声丢掉（实测贝斯低 B）。
    # 16384 点 = 2.7 Hz 一格，峰和底噪才分得开；时间分辨率 93 ms，够用（音符都 >150 ms）。
    vn, vh = int(frame)*4, int(hop)*8
    SV = np.abs(librosa.stft(x, n_fft=vn, hop_length=vh))
    fV = librosa.fft_frequencies(sr=sr, n_fft=vn)
    bin_hz = float(sr)/vn
    nV = SV.shape[1]
    def vframe(i): return min(i*int(hop)//vh, nV-1)
    def peak_e(f, i):
        # 窗宽同时兜住"频率比例"和"频谱分辨率"：只写 ±3% 的话低频取不到格心。
        j, tol = vframe(i), max(f*0.03, 0.75*bin_hz)
        m = (fV >= f-tol) & (fV <= f+tol)
        return float(SV[m, j].max()) if m.any() else 0.0
    def prominence_db(f, i):
        """f 处的峰 比它周围（0.5f~1.5f）的底噪高多少 dB

        ★ 底噪用【10% 分位】不是中位数：和 string 里其它音（三和弦的另外两个音、
          强力和弦的五度）会落进这个带里，把中位数抬起来 -> 真音全被判成噪声
          （实测 prog_amin 的三和弦整条轨被丢光）。几个音撼动不了 10% 分位，
          而白噪声是平的，10% 分位 ≈ 峰 -> 照样挡住。
        """
        j = vframe(i)
        band = (fV >= f*0.5) & (fV <= f*1.5)
        if not band.any(): return -99.0
        loc = float(np.percentile(SV[band, j], 10))
        return 20*np.log10(max(peak_e(f, i), 1e-20)/max(loc, 1e-20))

    # ③ 【先归位，再验证有没有分量】—— 顺序不能反
    #    反了的话，强力和弦被报成的 D1 处本来就没能量 -> 先做峰度检查会把它当噪声丢掉，
    #    而它恰恰是真的音（缺失基频），只是低了一个八度。
    # "有分量"的门槛：该帧最强分量的 -25 dB。
    # ★ 为什么不能松到 -35：4:5:6 三和弦的合成基频在根音下方 4 倍处，而 2f/3f 那些
    #   位置上是**裙边**（实测比帧最强分量低 34.4 dB）—— 门松到 -35，裙边就能过，
    #   于是归位会停在幻影上（实测同素材只换门/倍数：开放 C 和弦从 C3 100% 变成 G2 60%，
    #   prog_amin 的低音分布 98.7% 是没弹过的音）。
    rel = 10.0 ** (-25.0/20.0)
    out_t, out_m, out_shift = [], [], []
    # 归位倍数【只留八度】：2/4/8。
    # ★ 不要加 3/6：4:5:6 三和弦（C3-E3-G3）的合成基频在根音下方 4 倍处，
    #   3 排在 4 前面会把正确的根音路径堵死，落到"五度下方"的幻影上
    #   （实测同素材：加 3 之后 开放 C 和弦 C3 100% → G2 60%）。
    #   真正的修法是把分量门收紧（见上），让裙边过不去，而不是加倍数。
    MULT = (2, 4, 8)
    for i in np.where(ok)[0]:
        f = float(f0[i])
        if f <= 0: continue
        # ★ 工频/超低残留的拒绝放到【归位之后】（见下面的下限门）。
        #   放在这里会误杀和弦：f0 估计器报的是**合成周期的基频**，
        #   一个标准调弦的开放 G 和弦（320003）原始 f0 中位就是 49.14 Hz ——
        #   按 Hz 带先拒绝，会把整条轨删光（实测 synQ_G：候选 672、有效 0）。
        # ③【次谐波归位】判据只有一条：这个音在频谱上真的有没有分量。
        #    ★ 不用"低于乐器最低音"当条件 —— 那个例外漏掉了【三和弦】：
        #      大三和弦 F3+A3+C4 的谐波是 4:5:6，其缺失基频落在 F2(87 Hz)，
        #      而 F2 在吉他音域内，例外条件救不到它（实测整条轨报出 F2，而琴从没弹过 F2）。
        #    所以：没有分量、而它的某个倍数有 -> f 是次谐波，升上去再看（最多 3 次）。
        #    取"有分量的最小倍数"，得到的就是这一帧真正的【最低音】。
        f_raw = f
        for _ in range(3):
            mx = SV[:, vframe(i)].max()
            if peak_e(f, i) >= mx * rel: break
            nxt = None
            for k in MULT:
                if peak_e(k*f, i) >= mx * rel: nxt = k*f; break
            if nxt is None: break
            f = nxt
        shifted = (f != f_raw)   # 归位率只在【最终留下】的帧上计（否则会算出一百多个百分点）
        # ④a 归位之后仍在【该乐器音域之外】的低频 -> 工频 / 泄漏 / 估计器残渣。
        #    ★ 这道门必须在【归位之后】—— 归位前按 Hz 拒绝会误杀和弦（见上）。
        #    ★ 下限由调用方给：吉他是 63（支持的调弦最低 drop_c 的 C2=65.4）；
        #      贝斯要给自己的下限（5 弦低 B = 30.87），否则低 B 会被这道门吃掉。
        if min_playable_hz is not None and f < min_playable_hz:
            n_too_low += 1
            continue
        # ④b 归位之后仍然没有分量 -> 这一帧没有可信音高（不是"一个音"，是噪声/泄漏）
        if peak_e(f, i) < SV[:, vframe(i)].max() * rel:
            n_no_pitch += 1
            continue
        # ④c 【谐波自证】一个真的基频，它的 2 倍处必须有分量（拨弦乐器的二次谐波）。
        #    ★ 它【只解决了一小部分】：实测 synM_openG 的幻影份额 72.2%→71.4%，
        #      因为它的 2f 判据复用了 peak_e 的 ±3% 宽容窗，而 2f 那里也有邻音主瓣的上沿
        #      （实测 253.02 Hz，只比帧最大低 16 dB）→ 照样过门。所以别把它当成"治好了"。
        #    ★ 代价（实测 BlackShout）：删掉 2.0% 的保留帧，其中 42% 判不出是真的还是 5/7 倍幻影。
        #      纯正弦 / 只有奇次谐波 / 二次谐波比帧最大低 25 dB 的音，都会被它删掉。
        #      实测标准调弦开放 G 和弦（320003），pyin 报 64.84 Hz，×2 落到 129.68 Hz，
        #      而那里只是 B2(123.47) 主瓣的上沿（-8.1 dB，比门高 17 dB）→
        #      报出【从没弹过的 C3 72.2%】（四种门/倍数配置都一样）。
        #      而 129.68 的 2 倍 = 259.4 Hz 在那个和弦里没有任何分量。
        #    ★ 强力和弦过得去：D5 = D2+A2+D3，校正后的 D2 的 2 倍就是 D3（和弦音本身）。
        if peak_e(2*f, i) < SV[:, vframe(i)].max() * rel:
            # ★ 单独计数：成因与"报出频率处没分量"不同（这里是【有分量但缺二次谐波】），
            #   混在一起会打出名不符实的统计（审计实测：tune_dropc 的"无分量 2"其实都有分量）。
            n_no_h2 += 1
            continue
        # ⑤ 峰/底噪的对比度：挡掉"平谱"（白噪声、带限噪声）。峰值和底噪都很小的时候
        #    光比比值是不够的 —— 所以④在前、⑤在后，两道一起用。
        if prominence_db(f, i) >= min_prominence_db:
            out_shift.append(bool(shifted))
            out_t.append(t[i]); out_m.append(int(np.round(69 + 12*np.log2(f/440.0))))
        else:
            n_flat += 1
    if stats is not None:
        stats.update(n_raw=int(len(f0)), n_gated=int((~ok).sum()), n_too_low=n_too_low,
                     n_no_pitch=n_no_pitch, n_no_h2=n_no_h2, n_flat=n_flat, n_kept=len(out_t),
                     shifted=np.asarray(out_shift, dtype=bool))   # 逐帧对齐，调用方按自己的子集算比例
    return np.asarray(out_t), np.asarray(out_m, dtype=int)

def find_start(x, sr, thr_db=-50, win_ms=10):
    win = int(win_ms/1000*sr)
    pk = np.abs(x).max(); thr = pk*(10**(thr_db/20))
    for i in range(0, max(len(x)-win,1), win):
        if np.abs(x[i:i+win]).max() > thr: return i/sr
    return 0.0


# ────────────────────────── 人工输入 vs 测量：统一约定 ──────────────────────────
# ★ 顶层 <key>_source = "user" 是【唯一】可信来源标记（tuning / technique / chords / key / genre）。
#   为什么用顶层而不是嵌套：调弦早就是 tuning_source，helper 一条规则、grep 一处搜全。
#   写侧不抽函数（四处确认后的处置各不相同：tuning 要 pop 旧证据、technique 要留 measured、
#   chords 要拒绝覆盖、genre 没有旧证据）；只有【读侧】抽这一条。

def is_user_confirmed(spec, key):
    """只有 spec[key+"_source"] == "user" 才算用户确认过。
    ★ 缺字段 / null / 拼错 / "measured" 一律为假 —— 不许返回 True，也不许抛异常。
    调用方要能打出【实际来源串】，所以配一个 source_of()。"""
    return str((spec or {}).get(key + "_source") or "") == "user"


def source_of(spec, key):
    """给屏幕用的实际来源串（缺字段也要说人话）"""
    return str((spec or {}).get(key + "_source") or "未标注")


# ────────────────────── 低频 / 音级判定的共享常量（★ 一处定义，禁止各写一份）──────────────────────
# 为什么必须共用：同一个量级上两套阈值 = 两个工具对同一份证据给出相反判定。
# 实测：贝斯直方图最高音级 31.2%（BlackShout），0.30 说"够定案"、0.40 说"不足" —— 而调弦链在同一首歌上
# 正是按 0.40 给的不定案。所以 MIN_DOM_SHARE 只有这一个来源。
BASS_FMIN_HZ = 25.0     # 贝斯 f0 下限。
                        # ★ 判据是「必须 < A0 = 27.5 Hz」—— 实测 fmin=25 时 A0 夹具：钳位 0 帧、top_pc A 100%；
                        #   fmin=30 就钳成 B 了（fmin=35 那版更狠：B0 钳成 C# 99.9%、还自报「有效帧 100%」）。25 留 2.5 Hz 余量。
                        # ★ 为什么不是 23（我第一版写 23，理由是错的）：23 在真素材上比 25 少 1.5% 的有效帧
                        #   （15395 vs 15631），sub-25 Hz 那点能量不是音符 —— 只是把伪影从 25.00 Hz 挪到 23.00 Hz；
                        #   更要紧的是它会改动 check_tuning 的贝斯交叉校验（f0_track 15074 -> 15011 帧），
                        #   让批 1 收官记录里的数字（2904 / 1439 / 主音 25.4%）不再是当前代码的输出。
                        # ★ 已知代价：25 Hz 仍会放进一点工频裙边；本工具用裸 pyin，没有 f0_track 的四道门。
BASS_FMAX_HZ = 400.0
DI_FMIN_HZ = 60.0       # 吉他 DI 的 f0 下限：drop_c 的 C2 = 65.4 Hz，60 是它下面留的门。
MIN_DOM_SHARE = 0.40    # 音级占比到多少才够"定案"（check_tuning 与 bass_reference 共用）
MIN_FRAMES = 30         # 样本量下限（占比再高，帧数太少也不算数）


def spec_save(path, spec):
    """原子 + 保留 BOM 写回 spec.json。

    ★ 用户手存的 spec.json 常带 BOM，写回时丢掉会让他的编辑器认不出（di_instructions 先踩过，这里提成共用）。
    """
    import json as _json
    enc = "utf-8"
    try:
        if open(path, "rb").read(3) == b"\xef\xbb\xbf":
            enc = "utf-8-sig"
    except Exception:
        pass
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding=enc) as f:
        _json.dump(spec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def num_or_none(spec, key):
    """把 spec[key] 当数读；读不出（缺字段 / None / 手写的非数字如 "7/10"）一律 None。

    ★ 为什么要抽出来：这是【第二个】消费者踩同一个坑 —— di_instructions 先崩，verify_di 后崩。
      手写字段不许让消费者的行为变成 traceback；读不出就当没有，由调用方决定少说哪句话。
    """
    try:
        v = (spec or {}).get(key)
        return None if v is None else float(v)
    except Exception:
        return None


# 起点预算与段落门槛 —— ★ 一处定义，两处共用（technique.py 的回显 / di_instructions 的计划）。
# 上次的教训：回显手写了「8 秒」，实际归一化后只有 5 秒。
CHORD_BUDGET_S = 26.0
SEG_MIN_PCT = 10.0          # 占比 <10% 的奏法不出段落（断崖，不是渐变）
SEG_MIN_S = 3.0             # 段落秒数下限
SEG_MAX_N = 2               # 最多两种奏法：用户路径与测量路径【结构相同】


def chord_segments(pct, budget=CHORD_BUDGET_S, max_n=SEG_MAX_N):
    """占比 -> [(奏法, 秒)]。★ 回显与 di_plan 必须都调它，不许各写一份。

    失效条件：占比全在门槛以下时退化成 [(mid, budget)]（等于"只录正常拨弦"），
    那时调用方要打印【没有别的段落】，别让用户以为是漏了。
    """
    items = sorted([(float(v), k) for k, v in (pct or {}).items() if float(v) >= SEG_MIN_PCT],
                   reverse=True)[:max_n]
    if not items:
        return [("mid", float(budget))]
    tot = sum(v for v, _ in items) or 1.0
    return [(k, max(SEG_MIN_S, float(round(budget * v / tot)))) for v, k in items]
