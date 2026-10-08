# -*- coding: utf-8 -*-
"""从【贝斯轨】提取参考信息：根音分布 / 最常出现的音级 / 证据强度

★ 定位：这是【参考】，不是结论。它不说「这首歌是什么调」，它说
  「贝斯帧里最常出现哪个音级、这个占比有多强、样本够不够、有没有钳位伪影」——
  调性的权威是 chords.py（从吉他 chroma 推），本工具只做交叉参考（见 reference/08 §权威）。

⚠️ 逐帧测 f0 后【按帧数加权】，不要按起音分段的时长加权（后者会被个别长音带偏——
   实测 G 有个 4.9 s 的长音，把 G 抬到 22%）。

用法:  python bass_reference.py [歌曲目录]
写回:  spec.json 的 bass_note_pct / bass_ref / bass_ref_source
       并【幂等 pop】掉旧字段（见文末两栏）

失效条件（说不出失效条件的判据不许用）：
  ① 低音是持续音（A 小调歌里全程 E 的 riff）-> 最常出现的音级是【贝斯声部的性质】，不是主音；
  ② 分布接近均匀 -> argmax 是噪声（实测 Am-F-C-G：G 25.4 / F 24.9 / A 24.9 / C 24.8，0.5 个百分点选出 G）；
  ③ 有钳位帧（f0 贴 fmin）-> 那个占比本身是伪影（实测 B0 配 fmin=35 -> C# 99.9%、有效帧还报 100%）；
     ★ clamped = 0 **不等于**整条轨可信 —— fmax 侧不是「钉住」而是【报低一个八度】（批 1 在 f0_track 上验过 A4->A3 100%），这条探测抓不到；
  ④ 换加权口径能翻盘（实测同一份素材：帧加权 F 24.9% vs 4 秒窗计数 F 66.7%）；
  ⑤ 它说不出贝斯轨里有没有串音 —— 占比高不等于证据强（跨声部串音本项目只测过反方向）。
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import librosa
from songlib import (song_dir, P, require, load_mono, db, spec_save,
                     BASS_FMIN_HZ, BASS_FMAX_HZ, MIN_DOM_SHARE, MIN_FRAMES)

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CLAMP_CENTS = 50.0          # |cents(f0) − cents(fmin)| < 50 视为钳位帧
SEG_S = 20.0                # 与 songlib.channel_check 的分段一致

D = song_dir()
b = require(D / "stems" / "bass.wav", "贝斯轨")
x, sr = load_mono(b)
print("贝斯轨 %.1f s  %d Hz" % (len(x) / sr, sr))
print("f0 下限 %.1f Hz（覆盖 A0 = 27.5 Hz；★ 是 drop-A，不是「6 弦」——6 弦最低也是 B0 = 30.87）" % BASS_FMIN_HZ)

# ── ① 逐帧 f0（长窗 pyin，不分段）──────────────────────────────────
f0, vf, vp = librosa.pyin(x, fmin=BASS_FMIN_HZ, fmax=BASS_FMAX_HZ, sr=sr,
                          frame_length=4096, hop_length=512)
ok = ~np.isnan(f0)
n_frames = int(ok.sum()); n_all = int(len(f0))
coverage = n_frames / max(n_all, 1)

# ── ② 钳位帧（伪影探测，比"报最低有效音"有用得多）──────────────────
if n_frames:
    _cents = 1200.0 * np.log2(np.maximum(f0[ok], 1e-9) / BASS_FMIN_HZ)
    clamped = int((np.abs(_cents) < CLAMP_CENTS).sum())
else:
    clamped = 0
clamped_pct = 100.0 * clamped / max(n_frames, 1)

# ── ③ 音级分布（按帧数加权 = 真正的时间占比）────────────────────────
midi = np.full(len(f0), -1)
midi[ok] = np.round(69 + 12 * np.log2(f0[ok] / 440.0)).astype(int)
w = np.zeros(12)
for m in midi[ok]:
    w[m % 12] += 1
w = w / w.sum() if w.sum() else w
order = list(np.argsort(-w))
if n_frames == 0:
    # ★ 一个有效帧都没有时【不存在】"最常出现的音级"。写个 "C" 进 spec，它会跟这首歌走到下一个会话。
    #   （03-陷阱清单 记过分离器给出精确全零的轨；审计反例 3）
    top = None; top_name = None; top_pct = 0.0; gap_to_2nd = 0.0
    print()
    print("!! 本轨一个有效帧都没有 —— 没有音级分布可报（全零 / 全静音 / pyin 完全跟丢）")
else:
    top = int(order[0]); second = int(order[1])
    top_pct = 100.0 * float(w[top]); top_name = NAMES[top]
    gap_to_2nd = 100.0 * float(w[top] - w[second])

print()
print("=== 音级分布（★ 按帧数加权）===")
for k in order:
    if w[k] < 0.005:
        continue
    print("  %-3s %5.1f%%  %s" % (NAMES[k], 100 * w[k], "#" * int(60 * w[k])))
print("  覆盖率 %.1f%%（%d / %d 帧）· 钳位帧 %d（%.1f%%）"
      % (100 * coverage, n_frames, n_all, clamped, clamped_pct))
print()
if n_frames:
    print("  -> 最常出现的贝斯音级 %s（占 %.1f%%），与第二名差 %.1f 个百分点"
          % (top_name, top_pct, gap_to_2nd))
print("     ★ 这不叫「主音」：低音是持续音、分布平、或有钳位帧时，它都不是主音。")

# ── ④ 证据强度（不是结论，是筛子：带理由的 status）────────────────
reasons = []
if n_frames == 0:
    reasons.append("有效帧 0（没有分布可报）")
elif top_pct < MIN_DOM_SHARE * 100:
    reasons.append("最常出现的音级只占 %.1f%% < %.0f%%" % (top_pct, MIN_DOM_SHARE * 100))
if n_frames < MIN_FRAMES:
    reasons.append("样本只有 %d 帧 < %d" % (n_frames, MIN_FRAMES))
if clamped > 0:
    reasons.append("有 %d 帧贴 f0 下限（钳位伪影）" % clamped)
status = "ok" if not reasons else "weak"
print("  证据强度：%s%s" % (status, "" if status == "ok" else "（" + "；".join(reasons) + "）"))
if status == "weak":
    print("     -> 这份参考**不足以支撑任何调性/根音结论**；下游（di_instructions 的交叉校验）会据此不报冲突。")

# ── ⑤ 逐 4 秒的根音（★ 留屏幕、不落盘）────────────────────────────
BAR = 4.0
times = librosa.times_like(f0, sr=sr, hop_length=512)
print()
print("=== 逐 %.0f 秒的贝斯根音（只看和声节奏，**不要当根音占比用** —— 与上面的帧数加权是两个口径）===" % BAR)
roots = []
for t0 in np.arange(0, len(x) / sr - BAR, BAR):
    m = (times >= t0) & (times < t0 + BAR) & ok
    if m.sum() < 5:
        continue
    ww = np.zeros(12)
    for mm in midi[m]:
        ww[mm % 12] += 1
    ww /= ww.sum()
    roots.append((t0, NAMES[int(np.argmax(ww))], float(ww.max())))
seq = []
for t0, nm, conf in roots:
    if seq and seq[-1][0] == nm:
        seq[-1][2] += 1
    else:
        seq.append([nm, t0, 1])
if roots:
    print("  " + "  ".join("%s×%d" % (a, c) for a, _, c in seq[:60]))
    from collections import Counter
    cc = Counter(a for _, a, _ in roots)
    print("  窗口计数：" + "  ".join("%s %d" % (nm, n) for nm, n in cc.most_common(8)))
else:
    print("  （没有够长的窗口）")

# ── ⑥ 跟吉他轨对照 —— 只打印，不落盘 ─────────────────────────────
# ★ 不写 warning 字段：它比较的是两个推断，重算成本是 0；一落盘就有"过期"这一类
#   （实测它粘住过：第 1 次不一致写入，第 2 次已一致仍然留着）。消费者自己从 bass_ref + key 重算。
g = P(D, "guitar")
if g.exists():
    gg, _ = load_mono(g)
    nn = min(len(gg), len(x))
    cg = librosa.feature.chroma_cqt(y=gg[:nn], sr=sr, hop_length=512).mean(1)
    kg = NAMES[int(np.argmax(cg))]
    print()
    print("=== 跟吉他轨对照（仅供参考，不落盘）===")
    print("  贝斯最常出现的音级 %s   吉他 chroma 的 argmax %s   %s"
          % (top_name, kg, "相同" if kg == top_name else "不同"))
    print("  (逐 10 秒的 argmax 会跳，不要用那个判一致性——实测只有 21% 相符，是噪声)")
    if kg != top_name:
        print("  -> 两者不同只说明两个声部的分布重心不同，**不是谁的错**；调性的权威是 chords.py（吉他 chroma），")
        print("     别据此改 key。真正的交叉校验在 di_instructions（只出证伪）。")

# ── ⑦ 写盘 + 旧字段清理 ─────────────────────────────────────────
sp = P(D, "spec")
spec = json.load(open(sp, encoding="utf-8-sig")) if sp.exists() else {}
if n_frames:
    spec["bass_note_pct"] = {NAMES[k]: round(100 * float(w[k]), 1) for k in order[:8] if w[k] > 0.005}
else:
    spec.pop("bass_note_pct", None)      # 0 帧 -> 不写空分布（写了会被读成"每个音级都是 0%"）
spec["bass_ref"] = {
    "top_pc": top_name, "top_pc_pct": round(top_pct, 1), "gap_to_2nd": round(gap_to_2nd, 1),
    "coverage": round(coverage, 3), "n_frames": n_frames, "n_all_frames": n_all,
    "clamped_frames": clamped, "clamped_pct": round(clamped_pct, 2),
    "screen": {"status": status, "reasons": reasons,
               "thresholds": {"min_dom_share": MIN_DOM_SHARE, "min_frames": MIN_FRAMES,
                              "clamp_cents": CLAMP_CENTS}},
    "note": "★ top_pc = 帧时间占比最高的音级，不是主音、不是根音；clamped=0 不等于整条轨可信（fmax 侧会报低八度）",
    "params": {"fmin_hz": BASS_FMIN_HZ, "fmax_hz": BASS_FMAX_HZ,
               "frame": 4096, "hop": 512, "weighting": "frame"},
}
spec["bass_ref_source"] = "bass_f0"

# ★ 旧字段清理（幂等 pop）—— 两栏分开写，否则工具头读起来像它负责这些字段，下一个会话会"恢复"它们
for k in ("key_from_bass", "chords_from_bass", "bass_root_windows"):   # 本工具自己的旧名字
    spec.pop(k, None)
for k in ("bass_weight_s", "warning", "tuning_evidence"):              # 历史遗留，**本工具不生产**
    spec.pop(k, None)
# ★ 别在这里补 tuning_source —— 那会伪造"用户确认过"；唯一合法写点是 check_tuning.py 的 --set 路径。
spec_save(sp, spec)

print()
print("证据强度 %s%s" % (status, "" if n_frames else " · 最常出现的音级：无（0 个有效帧）"))
print("已更新 %s（并清掉旧字段：key_from_bass / chords_from_bass / bass_root_windows / bass_weight_s / warning / tuning_evidence）" % sp)
