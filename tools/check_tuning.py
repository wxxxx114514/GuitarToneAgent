"""调弦：记录用户给的答案 + （次要的）音频诊断

    ★ 定位：调弦属于【输入】，不属于分析。演奏者知道自己的调弦，而音频里几乎测不准
      （实测 BlackShout 的低音带里贝斯比吉他响 27.7 dB —— 吉他自己的低音没露头）。
      所以【主路径】是：用户说了 -> --set=<名字> 记下来。（BlackShout 实测：低音带里吉他比贝斯轻 27.7 dB。）
      下面是【次要路径】：用户不确定、或怀疑 spec 记错时才跑，它经常给不出结论，
      那时正确动作就是回去问用户，而不是硬给一个答案。

    ── 只诊断，【不替你改 spec】

用法:
  python check_tuning.py [歌曲目录]                 诊断（不写任何东西）
  python check_tuning.py [歌曲目录] --set=drop_d    确认后手动设（唯一会写盘的用法）

支持的调弦: standard / drop_d / half_down / drop_c
            （默认路径只走 standard / drop_d；另两套要显式 --set）

三条纪律（08-工作流详解.md §9.1）:
  · 默认标准调弦，不要一上来就问用户
  · 不要采信"比 D2/E2 出现率"这类自动判定 —— 它量到的其实是频谱裙边在 73/82 Hz 各漏多少
  · 可靠的交叉验证是【物理不可能性】: 把实际被弹到的低音列出来，看哪套调弦能解释它们

★ 这个脚本能做的只有【证伪】:
    某个音在某套调弦下弹不出来  ->  一定不是那套           （成立）
    所有音都能在某套调弦下弹出  ->  就是那套               （不成立，可能只是弹得高，也可能降了半音）
  所以它只给建议，改 spec 必须显式 --set，并且要让用户确认一句。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import (song_dir, P, require, load_mono, f0_track, utf8_stdout,
                     MIN_DOM_SHARE, MIN_FRAMES,
                     BASS_FMIN_HZ, BASS_FMAX_HZ)   # ★ 阈值与低频边界都共用 songlib 的，不另写一份

utf8_stdout()

NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
def hz(m): return 440.0*2**((m-69)/12.0)
def nm(m): return "%s%d" % (NAMES[m % 12], m//12 - 1)

# 六弦空弦 MIDI（6 弦到 1 弦）。四套表逐弦核对过（见 08-工作流详解.md §9.1）
TUNINGS = {
    "standard":  {6:40, 5:45, 4:50, 3:55, 2:59, 1:64},   # E A D G B E
    "drop_d":    {6:38, 5:45, 4:50, 3:55, 2:59, 1:64},   # D A D G B E
    "half_down": {6:39, 5:44, 4:49, 3:54, 2:58, 1:63},   # Eb
    "drop_c":    {6:36, 5:43, 4:48, 3:53, 2:57, 1:62},   # C G C F A D
}
DEFAULT_PATH = ["standard", "drop_d"]          # 默认只走这两套
ALL = ["standard", "drop_d", "half_down", "drop_c"]

# 任何一套调弦都弹不出来的最高音 = 四套里最低的空弦（drop_c 的 C2 = 65.4 Hz）
IMPOSSIBLE_BELOW = min(min(t.values()) for t in TUNINGS.values())        # 36
# 低音区：低于这个音就算"这条轨的低音证据"
LOW_ZONE = 48                                                            # C3 = 130.8 Hz
# 判据余量：某套调弦"弹不出来"的帧占比 ≤ 这个数才算它能解释。
# ★ 为什么不是 0：f0 估计偶尔会错半个音，留 2% 的余量。
# ★ 失效条件：轨里真有一小撮（<2%）超出该套音域的音时，会被当成噪声放过。
TOL_BELOW = 0.02
# 主音占比太低就不足以定案（真歌实测主音只占 25.4% —— 那种时候不该给建议）
# 样本量下限：少于这么多帧就不足以给出"否掉了谁"这种硬结论（实测 synC_drop_B 只剩 8 帧）
# 贝斯交叉验证的时间闸门：只有"同一时刻"才算串音
BASS_DT_MAX = 0.05      # s
# 剔除上限：判据把大半条轨都判成串音时，是判据失效，不是轨脏
BASS_DROP_MAX = 0.50
# 支持的调弦里吉他的最低音：drop_c 的 6 弦空弦 C2 = 65.4 Hz。
# 归位之后仍低于这个下限的帧 = 工频 / 泄漏 / 估计器残渣 —— 这是唯一拦住 50/60 Hz 工频的地方。
# ★ 它必须在【归位之后】跑：归位前按 Hz 拦，会把标准调弦的开放 G 和弦（320003）整条轨删光
#   （那个和弦的合成周期基频中位就是 49.14 Hz）。
# 低音带污染判据（02-工具清单 §2.3 的泄漏判据：相关 + 电平差）
BLEED_BAND = (60.0, 100.0)   # D2 所在的带
BLEED_CORR = 0.50            # 吉他/贝斯 包络相关 高于它就说明两条轨在这个带里同源
BLEED_DB = -20.0             # 且吉他比贝斯低这么多 -> 无法确认归属（-6 太浅，会误伤"吉他真在弹"）

def band_env_db(x, sr, lo, hi, frame=4096, hop=512):
    """带通之后的逐帧 RMS（dB）—— 用来和贝斯轨比"这个带里谁在响" """
    from scipy.signal import butter, sosfilt
    sos = butter(4, [lo/(sr/2.0), hi/(sr/2.0)], "band", output="sos")
    y = sosfilt(sos, x).astype(np.float64)
    n = 1 + max(0, (len(y) - int(frame))//int(hop))
    r = np.empty(n)
    for i in range(n):
        s = y[i*int(hop):i*int(hop)+int(frame)]
        r[i] = np.sqrt((s*s).mean())
    return 20*np.log10(np.maximum(r, 1e-12))


GENRE_HINT = {
    "metal": "金属 / 硬摇滚常在 Drop D 上写 riff",
    "djent": "djent / 前卫基本是 Drop 系",
    "hard-rock": "硬摇滚常用 Drop D",
    "punk": "朋克多为标准调弦",
}

def main(argv):
    # 参数处理只认两种形态：一个歌曲目录 + 最多一个 --set=<名字>。
    # 其余一律报错 —— 静默忽略是原缺陷的通病（老版把位置参数 drop_c 完全忽略、零提示）。
    unknown = [a for a in argv if a.startswith("--") and not a.startswith("--set=")]
    if unknown:
        print("不认识的选项: %s" % " ".join(unknown))
        print("  可用: --set=<名字>（%s）" % " / ".join(ALL))
        return 2
    sets = [a.split("=", 1)[1] for a in argv if a.startswith("--set=")]
    if len(sets) > 1:
        print("--set 给了 %d 次: %s —— 只许一次（不确定就先跑诊断）" % (len(sets), " / ".join(sets)))
        return 2
    rest = [a for a in argv if not a.startswith("--")]
    dir_arg, stray = None, []
    for a in rest:
        if dir_arg is None and os.path.isdir(a): dir_arg = a
        else: stray.append(a)
    if stray:
        print("不认识的参数: %s" % " ".join(
            ("%s（这个目录不存在？）" % a) if (os.sep in a or "/" in a or a.endswith(".json")) else a
            for a in stray))
        print("  调弦名要写成 --set=<名字>，位置参数只用来指歌曲目录。")
        print("  可选: %s" % " / ".join(ALL))
        return 2
    D = song_dir(dir_arg)
    sp = P(D, "spec")
    spec = json.load(open(sp, encoding="utf-8-sig")) if sp.exists() else {}

    # ---- --set: 唯一会写盘的用法 ----
    if sets:
        raw = sets[0]
        want = raw.strip().lower().replace("-", "_")     # 归一化：Drop-D / drop_D / DROP_D 都认
        if want in ("dropd", "drop"): want = "drop_d"
        if want in ("standard", "std", "e"): want = "standard"
        if want in ("halfdown", "half_step", "eb", "half"): want = "half_down"
        if want in ("dropc",): want = "drop_c"
        if want != raw:
            print("（你写的是 %r，按 %s 处理）" % (raw, want))
        if want not in ALL:
            print("未知调弦: %s" % want)
            print("  可选: %s" % " / ".join(ALL))
            print("  默认路径只走 %s" % " / ".join(DEFAULT_PATH))
            return 2
        spec["tuning"] = want
        spec["tuning_source"] = "user"          # ★ 唯一可信的来源：用户确认过
        spec.pop("tuning_evidence", None)       # 旧的自动判定证据一律作废，不留着误导下游
        json.dump(spec, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("已设为 %s（tuning_source=user）" % want)
        print("  下一步: tone.bat run di_instructions.py   —— 指法会按这套重算")
        return 0

    # ---- 诊断（不写盘）----
    g = require(P(D, "guitar"), "吉他轨")
    x, sr = load_mono(g)
    print("=" * 62)
    print("  调弦诊断: %s" % os.path.basename(str(D)))
    print("=" * 62)
    print("  吉他轨 %.1f s" % (len(x)/sr))

    # ★ 低音带预检（先判后算）：调弦靠的就是最低那几个音，而那是贝斯的主场。
    #   用的是 02-工具清单 §2.3 的泄漏判据（带内包络相关 + 电平差），只是带取 60-100 Hz
    #   （D2 所在；文档那处写 30-70 Hz，用途不同）。
    #   ★ 措辞纪律：相关高【不等于】串音 —— 两件乐器都在这个带里弹，相关照样高
    #     （实测：吉他干净弹 D2、贝斯弹 E1、差 7 个半音，相关仍有 +0.68）。
    #     所以只能说「无法确认这些低音是吉他弹的」，不能说「这是串音」。
    band_abstain = False
    bpath0 = D / "stems" / "bass.wav"
    if bpath0.exists():
        xb0, srb0 = load_mono(bpath0)
        n0 = min(len(x), len(xb0))
        eg0 = band_env_db(x, sr, BLEED_BAND[0], BLEED_BAND[1])
        eb0 = band_env_db(xb0[:n0], srb0, BLEED_BAND[0], BLEED_BAND[1])
        m0 = min(len(eg0), len(eb0))
        if m0 > 10 and eg0[:m0].std() > 1e-6 and eb0[:m0].std() > 1e-6:
            corr0 = float(np.corrcoef(eg0[:m0], eb0[:m0])[0, 1])
            # ★ 电平差只在【两边同时都在响】的帧上算：贝斯在这个带里没内容时，
            #   差值会算出一个上百 dB 的假数字（实测 +223.5 dB）。
            live0 = (eg0[:m0] > eg0[:m0].max()-30) & (eb0[:m0] > eb0[:m0].max()-30)
            if live0.sum() < 10:
                print("  [低音带预检] 吉他与贝斯在这个带里很少同时响（%d 帧）—— 无法比较，跳过预检。" % int(live0.sum()))
                d0 = None
            else:
                d0 = float(np.median(eg0[:m0][live0] - eb0[:m0][live0]))
                print("  [低音带预检] %.0f-%.0f Hz: 吉他/贝斯 包络相关 %+.2f，电平差中位 %+.1f dB（同为发声的 %d 帧）"
                      % (BLEED_BAND[0], BLEED_BAND[1], corr0, d0, int(live0.sum())))
            if d0 is not None and corr0 > BLEED_CORR and d0 < BLEED_DB:
                band_abstain = True
                print("      -> 这个带里两条轨同步、而吉他明显更轻：**无法确认最低那几个音是吉他弹的**。")
                print("         调弦靠的正是这一段，所以本项不再往下算 —— 交给用户。")
                print("         ★ 失效条件：相关高也可能只是「两件乐器都在这个带里弹」")
                print("           （实测差 7 个半音时相关仍有 +0.68），所以它挡不住也别当成铁证。")
    if band_abstain:
        print()
        print("  -> **测不出调弦**（低音带无法确认归属）。正确动作是【问用户】：")
        print("     让他在琴上读一下 6 弦空弦音高，或直接问「你是不是 Drop D / 降半音」。")
        cur1 = spec.get("tuning")
        if cur1:
            print("     当前 spec 记的是 %s（%s）—— 它没有独立证据支撑，下游要当【未确认】用。"
                  % (cur1, "用户确认过" if spec.get("tuning_source") == "user" else "来源不明"))
        print()
        print("  ★ 本脚本不改 spec.json。确认之后自己敲：")
        print("      tone.bat run check_tuning.py --set=<你确认的那一套>")
        return 0

    # 吉他：fmax 提到 1200（否则 >400 Hz 的音会被报低一个八度 —— 实测 A4 报成 A3）；
    #       min_playable_hz=63 是【归位之后】的音域下限门：低于它的一律不当音符，
    #       它同时承担了挡 50/60 Hz 工频的职责（★ 必须在归位之后，否则会误杀和弦）。
    st = {}
    t_g, m_g = f0_track(x, sr, fmin=25.0, fmax=1200.0, stats=st, min_playable_hz=63.0)
    # 分母要写清：n_gated 是"有声/电平门"挡掉的（分母是全帧），后面三个是候选帧里挡掉的
    n_cand = st.get("n_raw", 0) - st.get("n_gated", 0)
    print("  f0 帧 %d -> 有声/电平门挡掉 %d -> 候选 %d；候选里 低于音域下限 %d / 平谱 %d / 该处无分量 %d / 缺二次谐波 %d -> 有效 %d"
          % (st.get("n_raw", 0), st.get("n_gated", 0), n_cand,
             st.get("n_too_low", 0), st.get("n_flat", 0), st.get("n_no_pitch", 0),
             st.get("n_no_h2", 0), st.get("n_kept", 0)))
    if n_cand and st.get("n_too_low", 0) > 0.5*n_cand:
        # ★ 不能说成"很可能用了更低调弦"：白噪声、工频、贝斯漏音都会 100% 触发这一条
        #   （审计实测）。同一份代码的另一分支写的是两种可能，这里必须一致。
        print("  !! 候选帧里 %.0f%% 归位后仍低于音域下限（<63 Hz）—— 两种可能，都要去问用户："
              % (100.0*st["n_too_low"]/n_cand))
        print("     ① 这首用了本脚本不支持的更低调弦（drop B / drop A 之类）")
        print("     ② 轨里以工频 / 低频泄漏为主（那就不是调弦问题，是分轨问题）")
    if len(m_g) == 0:
        # ★ 分母用【候选帧数】：旧写法拿全帧数当分母，于是"门吃光 100%"也会走进"轨是空的"分支。
        n_low = st.get("n_too_low", 0)
        if n_low > 0.3*max(n_cand, 1):
            print("  !! 候选帧里 %d/%d 归位后仍低于音域下限（<63 Hz）—— 这些音吉他按支持的调弦弹不出来。"
                  % (n_low, n_cand))
            print("     两种可能：① 这首用了更低的调弦（drop B / drop A 之类，本脚本不支持）")
            print("                 ② 轨里以工频/低频泄漏为主。**都要去问用户**，不要按标准调弦硬算。")
        elif n_cand == 0:
            print("  !! 一个候选帧都没有 —— 轨可能是空的，也可能整条轨都没有可信音高。")
            print("     先查分轨（stems/guitar.wav 是不是静音），再谈调弦。")
        else:
            print("  !! 一个有效帧都没测到（候选 %d 帧：低于音域下限 %d / 平谱 %d / 该处无分量 %d / 缺二次谐波 %d）—— 没有可信音高。"
                  % (n_cand, st.get("n_too_low", 0), st.get("n_flat", 0),
                     st.get("n_no_pitch", 0), st.get("n_no_h2", 0)))
            print("     调弦这一项测不了，去问用户。")
        return 1
    low_mask = (m_g <= LOW_ZONE)         # ★ 掩码单独留着：后面算归位率要按同一批帧对齐
    low = m_g[low_mask]                  # 含 C3 本身：它是标准调弦 6 弦 8 品的自然把位
    print("  有效帧 %d，其中低音区(≤%s) %d 帧" % (len(m_g), nm(LOW_ZONE), len(low)))

    # ★ 这里【没有】"物理不可能"这一段了：音域下限门（63 Hz）在 f0_track 里就挡掉了，
    #   能进到 low 的音不可能再低于 IMPOSSIBLE_BELOW(65.4) —— 留着它只会永远打印"0 帧 (0.0%)"，
    #   而下面那两句解释性文案永远不会被看到（审计实测 60+ 夹具全打 0 帧）。
    #   ★ 上面 low 与这里 t_low 必须用【同一个比较符】：一个 < 一个 <= 会让"时刻"与"音高"
    #   来自不同的帧 —— 实测真歌上 24.1% 的比较音高不是该时刻的真实音高。
    t_low = np.asarray(t_g)[low_mask]
    assert len(t_low) == len(low), "时刻与音高帧数不一致：%d vs %d" % (len(t_low), len(low))
    keep = np.ones(len(low), dtype=bool)                     # 逐帧"留着"掩码
    print()

    # ② 贝斯交叉验证：同刻同音 = 泄漏（对【全部】低音帧做，不可能带里的也做 ——
    #    那些正好用来验证"它们确实是贝斯漏进来的"，比"猜是倍频错误"强）
    leak_hi = leak_lo = 0
    has_bass = False
    b = D / "stems" / "bass.wav"
    if b.exists():
        xb, srb = load_mono(b)
        n = min(len(x), len(xb))
        t_b, m_b = f0_track(xb[:n], srb, fmin=BASS_FMIN_HZ, fmax=BASS_FMAX_HZ,
                        min_playable_hz=BASS_FMIN_HZ)   # ★ 与 bass_reference 同源（覆盖 A0=27.5，不只是 5 弦低 B=30.87）
        if len(m_b):
            has_bass = True
            tb, mb = np.asarray(t_b), np.asarray(m_b)
            hit = np.zeros(len(low), dtype=bool)
            for i, (tt, mm) in enumerate(zip(t_low, low)):
                if tt*sr >= n: continue
                # ★ 时间闸门：先找最近的贝斯帧，再比 |Δt|。
                #   旧写法用 searchsorted 取"最近的后继帧"后直接 clip，从不比 Δt ——
                #   实测贝斯只在 t=10 s 响一个音，能把 0-4 s 的 347 帧全判成串音。
                j = int(np.clip(np.searchsorted(tb, tt), 0, len(tb)-1))
                if abs(tb[j] - tt) > BASS_DT_MAX: continue
                if mb[j] == mm:                       # f0 已取整到半音，这里就是"同一个音"
                    hit[i] = True
                    if mm < IMPOSSIBLE_BELOW: leak_lo += 1
                    else: leak_hi += 1
            n_hit = int(hit.sum())
            if n_hit > BASS_DROP_MAX * len(low):
                # ★ 判据把大半条轨都判成串音 —— 那是判据失效，不是轨脏。
                #   典型触发：吉他与贝斯【同度齐奏】（流行/摇滚很常见），两者音高本来就一样，
                #   音频上无法分离。实测同度齐奏的合成件 1723/1723 帧全灭 → 旧版输出"全是泄漏，按标准走"。
                print("  [警告] 贝斯交叉验证命中 %d/%d 帧（>%.0f%%）—— 无法与吉他内容分离，本道判据失效"
                      % (n_hit, len(low), BASS_DROP_MAX*100))
                print("         典型原因：吉他与贝斯同度齐奏。已【放弃剔除】，结果按「没有交叉验证」处理。")
                has_bass = False
                leak_hi = leak_lo = 0
            else:
                keep &= ~hit
                print("  [剔除] 贝斯同刻同音（同一半音，|Δt| ≤ %.0f ms）: 低音区 %d + 不可能带 %d 帧"
                      % (BASS_DT_MAX*1000, leak_hi, leak_lo))
        else:
            print("  [跳过] 贝斯轨一个有效帧都没测到")
    if not has_bass:
        print("  [跳过] 没有可用的贝斯交叉验证 —— 这项证据会变弱（结论里会标出来）")

    keep_mask = keep
    keep = low[keep_mask]

    if len(keep) == 0:
        print()
        if len(low) == 0:
            print("  !! 这条轨的低音区（≤%s）【没有内容】—— 调弦这一项测不了。" % nm(LOW_ZONE))
            print("     不是「轨脏」，是这条轨根本没弹低音弦。正确动作是【问用户】。")
        else:
            print("  !! 低音区 %d 帧被剔光了 —— 剩不下可用的音高证据。" % len(low))
            print("     按默认【标准调弦】走，并让用户确认一句。")
        return 0

    # ③ 剩下的低音分布
    print()
    # ★ 口径纪律：这些是【f0 估计器的输出】，不是"这首歌弹了哪些音"。
    #   复音的次谐波与弱基频在音频上不可分（审计实测：同一段素材换门/倍数，音名会成片变化），
    #   所以分布只能当证据看，不能当事实引。归位率就是它的歧义程度。
    # ★ 分子与分母必须同源：都是【保留下来的低音区帧】。
    #   旧写法分子数候选帧、分母用句子主语（保留帧），打出过"292 帧里 1239 帧经过归位，占 100%"这种假命题。
    sh = np.asarray(st.get("shifted", []), dtype=bool)
    if sh.size == len(m_g):
        n_shift = int(sh[low_mask][keep_mask].sum())
    else:
        n_shift = 0
    shift_pct = 100.0*n_shift/max(len(keep), 1)
    print("  [保留] %d 帧（其中 %d 帧经过次谐波归位，占 %.0f%%）。低音区检出的音高（f0 估计器输出，含歧义）:"
          % (len(keep), n_shift, shift_pct))
    c = {}
    for m in keep: c[int(m)] = c.get(int(m), 0) + 1
    for m, n in sorted(c.items(), key=lambda z: -z[1])[:6]:
        print("      %-4s %6.1f Hz  %5.1f%%  %s" % (nm(m), hz(m), 100.0*n/len(keep), "#"*int(40.0*n/len(keep))))

    # ★ 判据用【主音】（占比最高的那个低音），不用"最低音"。
    #   为什么：少数几帧低音可能是串音/倍频错误（真歌实测低音区 1/3 是物理不可能的音）。
    #   拿最低音定案，会因为这少数几帧把标准调弦误判成 Drop D（实测踩过）。
    #   反过来，主音低于某套的空弦 -> 那套一定不成立（这是硬结论）。
    dom = max(c.items(), key=lambda z: z[1])
    dom_m, dom_n = dom[0], dom[1]
    dom_share = 100.0*dom_n/len(keep)
    p1 = int(np.percentile(keep, 1))
    print()
    print("  主音（占比最高）: %s (%.1f Hz)  %.1f%%" % (nm(dom_m), hz(dom_m), dom_share))
    print("  最低音（1%% 分位）: %s (%.1f Hz) —— 只作参考" % (nm(p1), hz(p1)))

    # ④ 哪几套能解释【全部】低音。
    #    ★ 判据不是"主音够不够高"：那样会出现"能解释"和"它有 12% 的帧弹不出来"打在同一行，
    #      再加上一条 --set 命令 —— 实测让人照着一个会写错盘的命令敲（tune_dropc 真值 drop_c）。
    print()
    print("  哪几套调弦能解释【全部】这些低音（弹不出来的帧 ≤ %.0f%% 才算）:" % (TOL_BELOW*100))
    ok_list = []
    for name in ALL:
        floor = min(TUNINGS[name].values())
        below = 100.0*sum(n for m, n in c.items() if m < floor)/len(keep)
        good = below <= TOL_BELOW*100
        if good: ok_list.append(name)
        print("      %-10s 最低空弦 %-4s  %-10s  它弹不出来的帧 %5.1f%%"
              % (name, nm(floor), "能解释" if good else "解释不通", below))

    # ⑤ 结论：只有【证伪】是硬的，选哪一套永远要人确认 —— 所以不打印可直接复制的名字。
    print()
    refuted = [n for n in ALL if n not in ok_list]
    weak = (dom_share < MIN_DOM_SHARE*100) or (not has_bass) or (shift_pct > 50.0)
    if not ok_list:
        print("  -> 四套都解释不通 —— 剩下的低音仍不足以支撑任何一套。**测不出调弦。**")
        print("     按默认【标准】走，并把这一项标成【待用户确认】。")
    elif len(keep) < MIN_FRAMES:
        refuted = []          # ★ 样本不足就【不许】再打"spec 被否掉了"（它会紧跟在这句后面自相矛盾）
        # ★ 样本太少时连"否掉了谁"都不该说：8 帧也去否掉三套调弦，是拿噪声当证据
        #   （实测 synC_drop_B 只剩 8 帧，照样进了"并列 4 套"的结论）。
        print("  -> 样本只有 %d 帧（< %d）—— 不足以否掉或支持任何一套。**交给用户。**"
              % (len(keep), MIN_FRAMES))
    else:
        # ★ 措辞纪律：「只能证伪」意味着——能说的是"这些音否掉了谁"，
        #   不能说成"结论就是谁"。所以证伪那半句用肯定语气，选择那半句永远带条件。
        if refuted:
            print("  -> 这些低音【否掉了】: %s（它们弹不出这些音 —— 这是硬结论）。" % " / ".join(refuted))
        if len(ok_list) == 1:
            print("     剩下的证据只与 %s 相容（其余全被否）。" % ok_list[0])
        else:
            print("     并列 %d 套都还没被否掉: %s" % (len(ok_list), " / ".join(ok_list)))
            print("     —— 同一个低音，在标准是空弦、在 Drop D 是 2 品，指法完全不同。")
        why = []
        if dom_share < MIN_DOM_SHARE*100: why.append("主音只占 %.1f%%" % dom_share)
        if not has_bass: why.append("没有可用的贝斯交叉验证")
        if len(ok_list) > 1: why.append("并列 %d 套" % len(ok_list))
        if shift_pct > 50.0: why.append("%.0f%% 的音高靠次谐波归位得到（估计器歧义大）" % shift_pct)
        if len(keep) < MIN_FRAMES: why.append("样本只有 %d 帧" % len(keep))
        print("     **本工具在任何情况下都不给建议**：上面只是「否掉了谁」，选哪一套要人确认。")
        if why:
            print("     （证据强度：%s）" % "；".join(why))
        hint = GENRE_HINT.get(str(spec.get("genre", "")).lower())
        if hint: print("     曲风先验: %s" % hint)
        print()
        print("     ★ 怎么定：让用户在琴上确认 6 弦空弦音高（或直接说「我 Drop D」）。")
        print("       确认之后自己敲： tone.bat run check_tuning.py --set=<你确认的那一套>")
        print("       （工具不预填名字 —— 预填等于替你下了结论）")

    cur = spec.get("tuning")
    src = spec.get("tuning_source")
    print()
    if cur:
        tag = "用户确认过" if src == "user" else "来源不明（旧版脚本自动写的）"
        print("  当前 spec: tuning=%s（%s）" % (cur, tag))
        if cur in refuted:
            print("  !! 但 spec 记的 %s 被上面这些低音【否掉了】—— 照它算出来的指法会差音。" % cur)
    else:
        print("  当前 spec: 没有 tuning 字段 —— 下游按【标准调弦】算，但那是默认值不是确认值。")
    if not ok_list or len(ok_list) > 1:
        print("  这一项【没有定论】。按默认【标准】走 —— 那是 08-工作流详解.md §9.1 定的默认政策，")
        print("  不是从音频推出来的结论；下游要把它当【未确认】对待。")

    print()
    print("  ★ 本脚本不改 spec.json。确认之后自己敲：")
    print("      tone.bat run check_tuning.py --set=<你确认的那一套>")
    print("  ★ 让用户在设备/琴上确认一句再写：同一个低音，标准调弦和 Drop D 的指法完全不同。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
