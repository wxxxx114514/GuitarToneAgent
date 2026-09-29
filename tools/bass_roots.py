"""从【贝斯轨】提取根音与和弦
   ⚠️ 关键：逐帧测 f0 后【按帧数加权】，不要按起音分段的时长加权
      （后者会被个别长音带偏——实测 G 有个 4.9s 的长音，把 G 抬到 22%）

用法:  python bass_roots.py [歌曲目录]
写回:  spec.json  的 key_from_bass / bass_notes / chords_from_bass
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import librosa
from songlib import song_dir, P, require, load_mono

NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
def m2n(m): return "%s%d" % (NAMES[m % 12], m//12 - 1)

D = song_dir()
b = require(D / "stems" / "bass.wav", "贝斯轨")
g = P(D, "guitar")
x, sr = load_mono(b)
print("贝斯轨 %.1f s  %d Hz" % (len(x)/sr, sr))

# ---- ① 逐帧 f0（长窗 pyin，不分段）----
f0, vf, vp = librosa.pyin(x, fmin=35, fmax=400, sr=sr, frame_length=4096, hop_length=512)
times = librosa.times_like(f0, sr=sr, hop_length=512)
ok = ~np.isnan(f0)
midi = np.full(len(f0), -1)
midi[ok] = np.round(69 + 12*np.log2(f0[ok]/440.0)).astype(int)
print("有效帧 %d / %d (%.0f%%)" % (ok.sum(), len(f0), 100*ok.sum()/len(f0)))

# ---- ② 音级分布（按帧数加权 = 真正的时间占比）----
w = np.zeros(12)
for m in midi[ok]: w[m % 12] += 1
w /= w.sum()
print()
print("=== 音级分布（按帧数加权）===")
for k in np.argsort(-w):
    if w[k] < 0.005: continue
    print("  %-3s %5.1f%%  %s" % (NAMES[k], 100*w[k], "#"*int(60*w[k])))
key = int(np.argmax(w))
fifth = (key + 7) % 12
print()
print("  -> 主音 %s (%.0f%%)，属音 %s (%.0f%%)" % (NAMES[key], 100*w[key], NAMES[fifth], 100*w[fifth]))

# ---- ③ 逐 4 秒的根音（比逐小节稳，比整段细）----
BAR = 4.0
print()
print("=== 逐 %.0f 秒的贝斯根音 ===" % BAR)
roots = []
for t0 in np.arange(0, len(x)/sr - BAR, BAR):
    m = (times >= t0) & (times < t0 + BAR) & ok
    if m.sum() < 5: continue
    ww = np.zeros(12)
    for mm in midi[m]: ww[mm % 12] += 1
    ww /= ww.sum()
    k = int(np.argmax(ww))
    roots.append((t0, NAMES[k], float(ww[k])))
seq = []
for t0, nm, conf in roots:
    if seq and seq[-1][0] == nm: seq[-1][2] += 1
    else: seq.append([nm, t0, 1])
print("  " + "  ".join("%s×%d" % (a,c) for a,_,c in seq[:60]))

from collections import Counter
cc = Counter(a for _, a, _ in roots)
print()
print("=== 根音分布（逐 %.0f 秒窗口）===" % BAR)
for nm, n in cc.most_common(8):
    print("  %-3s %3d 窗口 (%4.1f%%)  %s" % (nm, n, 100*n/len(roots), "#"*int(50*n/len(roots))))

# ---- ④ 跟吉他对照，不一致就警告 ----
warn = ""
if g.exists():
    gg, _ = load_mono(g)
    nn = min(len(gg), len(x))
    cg = librosa.feature.chroma_cqt(y=gg[:nn], sr=sr, hop_length=512).mean(1)
    cg /= cg.sum()
    kg = NAMES[int(np.argmax(cg))]
    print()
    print("=== 跟吉他轨对照 ===")
    print("  贝斯主音 %s   吉他 chroma 主音 %s   %s"
          % (NAMES[key], kg, "一致 OK" if kg == NAMES[key] else "!! 不一致，需人工确认"))
    print("  (逐 10 秒的 argmax 会跳，不要用那个判一致性——实测只有 21% 相符，是噪声)")
    if kg != NAMES[key]:
        warn = "bass/guitar key disagreement: %s vs %s" % (NAMES[key], kg)

# ---- ⑤ 主要和弦 ----
mains = [nm for nm, n in cc.most_common(4) if n/len(roots) >= 0.08]
sp = P(D, "spec")
spec = json.load(open(sp, encoding="utf-8")) if sp.exists() else {}
spec["key_from_bass"] = NAMES[key]
spec["bass_note_pct"] = {NAMES[k]: round(100*float(w[k]),1) for k in np.argsort(-w)[:8] if w[k] > 0.005}
spec["bass_root_windows"] = {nm: n for nm, n in cc.most_common(8)}
spec["chords_from_bass"] = [m + "5" for m in mains]
if warn: spec["warning"] = warn
json.dump(spec, open(sp,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print()
print("主音 %s，主要和弦根音 %s" % (NAMES[key], " / ".join(mains)))
print("已更新 %s" % sp)
