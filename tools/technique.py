"""奏法分析：测参考曲里各奏法的占比

判据是【音符衰减】—— 闷音 100-250 ms 就死，开放弹响 1 s 以上。
配方在 songlib.note_decay_times()，判据的限制见 06-奏法处理.md §7.1。

用法:  python technique.py [歌曲目录]
输出:  更新 <歌曲目录>/spec.json 的 technique 字段
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import (song_dir, P, require, load_mono,
                     note_decay_report, DECAY_RECIPE, chord_segments,
                     CHORD_BUDGET_S, SEG_MIN_PCT)

# ★ 分类阈值 —— 必须用真实录音标定（闷音 / 开放 各录一条同样的音）
TH_MUTE = -150.0    # 衰减斜率 < -150 dB/s -> 闷音
TH_OPEN = -50.0     # 衰减斜率 > -50 dB/s  -> 开放
CALIBRATED = False  # ← 用真实标尺录音标定过之后改成 True

D = song_dir()
g = require(P(D, "guitar"), "吉他轨")
x, sr = load_mono(g)
print("歌曲目录: %s   吉他轨 %.1f s" % (D, len(x)/sr))

# ---- 主判据：音符衰减时间 ----
t_dec, dec, INFO = note_decay_report(x, sr)
# ★ 覆盖率的分母是【检出的 onset 数】，不是"测得出衰减的音符数" ——
#   我上一版写 len(t_dec) 打出了「34 个 onset 里 34 个测得出（100%）」，真值是 34/198 = 17.2%。
#   打印出来的硬数字是假的，而它是给所有判据当门的那个数。
N_ONSET = int(INFO.get("n_onsets", 0))
N_MEAS = int(INFO.get("n_measured", len(t_dec)))
COVERAGE = float(INFO.get("coverage", 0.0))
print()
print("=== 判据：音符衰减斜率（峰值后 <= %.2f s 窗口内拟合，dB/s）===" % DECAY_RECIPE["slope_window_s"])
if len(dec) == 0:
    print("  !! 没测到音符事件，无法判奏法"); sys.exit(1)
print("  测到 %d 个音符   中位 %.3f s   p10 %.3f   p25 %.3f   p75 %.3f   p90 %.3f"
      % (len(dec), np.median(dec), np.percentile(dec,10), np.percentile(dec,25),
         np.percentile(dec,75), np.percentile(dec,90)))
edges = [-1e9, -400, -250, -150, -80, -50, -25, 0.0]
hist, _ = np.histogram(dec, bins=edges)
for i, h in enumerate(hist):
    if h: print("    %6.0f ~ %6.0f dB/s  %4d 个 (%4.1f%%)  %s"
                % (edges[i], edges[i+1], h, 100.0*h/len(dec), "#"*int(50.0*h/len(dec))))
if not CALIBRATED:
    print("  !! 阈值 %.0f / %.0f dB/s 【尚未用真实录音标定】，是合成信号推的初值。" % (TH_MUTE, TH_OPEN))
    print("     标定方法：闷音、开放 各录一条同样的音，跑 tools/calib_decay.py（见 Skill 7.2）")

LAB = ["闷音" if d < TH_MUTE else ("开放" if d > TH_OPEN else "中间") for d in dec]
from collections import Counter
cnt = Counter(LAB); n = len(LAB)
# ★ 单位：占比必须【按时间】算。
#   旧口径是「按音符个数」，而 di_instructions 拿它当【时间占比】用（T = 26 × share/Σshare）——
#   项目自己量过两种口径差 9.0 个百分点，0.155 s 的闷音在个数口径里被高估约 15 倍。
#   每个音的时长用同一个物理量推：衰减到 -60 dB 要多久 = 60 / |斜率|（闷音 -250 dB/s -> 0.24 s，开放 -30 -> 2 s）。
DUR = [min(5.0, 60.0/max(abs(d), 1e-6)) for d in dec]
TOTD = sum(DUR) or 1.0
SH_TIME = {k: 100.0*sum(DUR[i] for i in range(n) if LAB[i] == k)/TOTD for k in ("闷音", "中间", "开放")}
SH_CNT = {k: 100.0*cnt.get(k, 0)/n for k in ("闷音", "中间", "开放")}
print()
print("=== 奏法占比【按时间】（下游用的就是这个口径）===")
for k in ["闷音", "中间", "开放"]:
    print("  %-4s %5.1f%%   %s   （按音符个数 %4.1f%%，差 %+4.1f 点）"
          % (k, SH_TIME[k], "#"*int(60*SH_TIME[k]/100), SH_CNT[k], SH_CNT[k]-SH_TIME[k]))
print("  覆盖：%d 个 onset 里只有 %d 个测得出衰减（%.1f%%）—— 覆盖率低时上面的数不可当结论"
      % (N_ONSET, N_MEAS, 100.0*COVERAGE))

print()
print("=== 分段衰减中位值（每 20 秒）===")
for t0 in range(0, int(len(x)/sr)-20, 20):
    m = (t_dec >= t0) & (t_dec < t0+20)
    if m.sum() < 3: continue
    dd = dec[m]
    c2 = Counter([LAB[i] for i in np.where(m)[0]])
    s2 = sum(c2.values())
    print("  %4d-%4d s   斜率中位 %5.0f dB/s   闷音 %4.0f%%   中间 %4.0f%%   开放 %4.0f%%"
          % (t0, t0+20, np.median(dd), 100*c2.get("闷音",0)/s2, 100*c2.get("中间",0)/s2, 100*c2.get("开放",0)/s2))

sp = P(D, "spec")
spec = json.load(open(sp, encoding="utf-8-sig")) if sp.exists() else {}

# ── 用户直接说（主路径）：只问【能当事实回答】的问题 ──────────────────────
#   主奏法是哪种 / 有没有另一种明显不同的 / 那种大概几秒。
#   ★ 不问百分比：用户读不出百分比，只能编一个 —— 那是把推断搬进人脑再盖「以你为准」的章。
ARG = {}
for _a in sys.argv[1:]:
    if _a.startswith("--") and "=" in _a:
        _k, _v = _a[2:].split("=", 1)
        ARG[_k] = _v
TXT = {"palm": "闷音", "mid": "正常拨弦", "open": "放开手"}   # 给用户看的
CN = {"palm": "闷音", "mid": "中间", "open": "开放"}          # ★ 分类用的标签（SH_* 的键）
KEYS = ("palm", "mid", "open")
USER = "main" in ARG
SET_AT = __import__("datetime").date.today().isoformat()

if USER:
    main = ARG["main"]
    if main not in TXT:
        print("!! --main 只能是 %s" % " / ".join(TXT)); sys.exit(2)
    alt = ARG.get("alt") or None
    if alt in ("none", "", None):
        alt = None
    if alt is not None and alt not in TXT:
        print("!! --alt 只能是 %s / none" % " / ".join(TXT)); sys.exit(2)
    if alt == main:
        alt = None
    alt_sec = float(ARG.get("alt-sec", 0) or 0)
    # ★ 用户答的是【秒】，当场换算成 pct（唯一真相），回显再由 pct 现算 → 不会两个真相源
    pct = {k: 0.0 for k in KEYS}
    if alt and alt_sec > 0:
        share = min(0.9, alt_sec / CHORD_BUDGET_S)
        pct[alt] = round(100.0 * share, 1)
        pct[main] = round(100.0 - pct[alt], 1)
    else:
        pct[main] = 100.0
else:
    # 测量路径：口径是【按时间】（下游就是这么用的）
    pct = {k: round(SH_TIME[CN[k]], 1) for k in KEYS}

MEASURED = {
    "count_pct": {k: round(SH_CNT[CN[k]], 1) for k in KEYS},   # 旧口径（按音符个数）—— 留痕
    "time_pct": {k: round(SH_TIME[CN[k]], 1) for k in KEYS},   # 按时间
    "coverage": round(COVERAGE, 3),
    "n_onset": N_ONSET,
    "n_notes": N_MEAS,
    "calibrated": bool(CALIBRATED),
    "recipe": DECAY_RECIPE["recipe_version"],
}
spec["technique"] = {"pct": pct, "measured": MEASURED, "set_at": SET_AT}
# ★ 来源标记放【顶层】（与 tuning_source 一致）：只有 == "user" 才算用户确认过
spec["technique_source"] = "user" if USER else "measured"
# ★ 写侧不抽函数：四种输入的处置各不相同（technique 要【留着 measured 当对照】）
json.dump(spec, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ── 回显：段与秒必须由【和 di_instructions 同一个函数】算出来 ──────────────
SEGS = chord_segments(pct)
print()
print("=== 这次要录什么（%s）===" % ("你确认的" if USER else "【测量值，未经确认】"))
TOT = sum(s for _, s in SEGS)
for _k, _s in SEGS:
    print("  %-6s 约 %.0f 秒" % (TXT[_k], _s))
print("  %-6s （单音音阶，固定必录；秒数由 di_instructions 按调式算，这里不重复一份）" % "音阶")
if USER:
    # ★ 门槛【不在这里重新推】—— 直接问 chord_segments 的结果。
    #   我上一版写 alt_sec < 3.0，而真正的门槛是 pct >= 10%（≈2.6 s）：2.6~3.0 秒那一段
    #   段落其实建出来了，屏幕却说没建 —— 相邻两行直接打架。
    _built = [k for k, _s in SEGS if k != "scale"]
    if alt and alt not in _built:
        print("  ★ 你说「%s 只有 %.1f 秒」—— 低于成段门槛（占比 %.0f%%，约 %.1f 秒），"
              "所以【不出这个段落】= 那一段不录。确认吗？"
              % (TXT[alt], alt_sec, SEG_MIN_PCT, SEG_MIN_PCT / 100.0 * CHORD_BUDGET_S))
    if alt and alt_sec > CHORD_BUDGET_S / 2.0:
        print("  ★ 你给的「另一段」比主奏法还长（%.0f%%）—— 已按【长的当第 1 段】排；"
              "如果说反了，重跑并把 --main/--alt 对调。"
              % (100.0 * min(0.9, alt_sec / CHORD_BUDGET_S)))
    if len(SEGS) == 1:
        print("  ★ 只有一种奏法 -> 只录一段；verify_di 的奏法自参照会跳过（它需要 2 种），"
              "这不是漏检，已记进 di_plan。")
else:
    print("  要改：tone.bat run technique.py --main=palm|mid|open [--alt=... --alt-sec=秒]")

# ── 分歧告警：三道门一起满足才允许提（否则整个落在噪声带里）──────────────
CAN_DISAGREE = (COVERAGE >= 0.30) and (N_MEAS >= 20) and bool(CALIBRATED)
if USER:
    if CAN_DISAGREE:
        worst = max((abs(pct[k] - MEASURED["time_pct"][k]), k) for k in KEYS)
        if worst[0] > 20.0:
            print()
            print("  ⚠️ 你说的是 %s；我测到的是 %s（%s 差 %.0f 点）—— **以你为准**。"
                  % (" / ".join("%s %.0f%%" % (TXT[k], pct[k]) for k in KEYS),
                     " / ".join("%s %.0f%%" % (TXT[k], MEASURED["time_pct"][k]) for k in KEYS),
                     TXT[worst[1]], worst[0]))
            print("     差这么多通常意味着有我没见过的弹法，值得看一眼。")
    else:
        print()
        print("  我测到的仅供参考、【不参与任何判断】：覆盖 %.1f%%（<30%%）、n=%d（<20）、标定=%s"
              % (100.0*COVERAGE, N_MEAS, "是" if CALIBRATED else "否"))
print()
print("已更新 %s" % sp)
print(">>> 下一步：按上面的段落让用户录 DI（见 Skill 9.1 路径 A）")
