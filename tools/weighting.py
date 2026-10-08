r"""给误差向量加权：地板大的频段降权（修不了），可行动大的频段升权（值得修）

   用法: python weighting.py [歌曲目录]
   数据来源：<歌曲目录>\reamp\ 下的 wet_*.wav，跟 target.npy 比
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, soundfile as sf
from songlib import song_dir, P

SR = 48000
BANDS = [(80,113),(113,160),(160,226),(226,320),(320,452),(452,640),(640,905),
         (905,1280),(1280,1810),(1810,2560),(2560,3620),(3620,5120),(5120,7240)]
FC = np.array([int((a*b)**0.5) for a, b in BANDS], dtype=float)

def curve(p):
    """一个 wav -> 13 频段包络（去均值）"""
    x, _ = sf.read(p, always_2d=True, dtype="float32")
    x = x.mean(1)
    N, HOP = 8192, 4096
    acc = np.zeros(N//2+1); c = 0
    for s in range(0, max(len(x)-N, 1), HOP):
        acc += np.abs(np.fft.rfft(x[s:s+N]*np.hanning(N)))**2; c += 1
    if c == 0: return None
    sp = np.sqrt(acc/c)
    f = np.fft.rfftfreq(N, 1/SR)
    v = np.array([10*np.log10(sp[(f>=a)&(f<b)].sum()+1e-20) for a, b in BANDS])
    return v - v.mean()

D = song_dir()
tgt = np.load(str(P(D, "target")), allow_pickle=True)
tcur = tgt[1].astype(float); tcur -= tcur.mean()
RM = P(D, "reamp")
RUNS = [(p.stem[4:], str(p)) for p in sorted(RM.glob("wet_*.wav"))] if RM.exists() else []
if not RUNS:
    print("没找到 " + str(RM) + " 下的 wet_*.wav"); sys.exit(1)
print("歌曲目录:", D)
print("找到 %d 个湿声: %s" % (len(RUNS), ", ".join(t for t, _ in RUNS)))
print()
E = {}
for tag, p in RUNS:
    c = curve(p)
    if c is not None: E[tag] = c - tcur

# ==== 频段加权 ====
# 地板大的频段降权（修不了），可行动大的频段升权（值得修）
print("=== 频段权重 ===")
print("  %8s %10s %10s %10s" % ("频段", "地板", "可行动", "建议权重"))
W = np.zeros(len(BANDS))
for i, (a, b) in enumerate(BANDS):
    fl = np.array([E[t][i] for t in E])
    m, s = float(fl.mean()), float(fl.std())
    W[i] = s / (abs(m) + 1e-9)
    print("  %6dHz %10.2f %10.2f %10.3f" % (FC[i], m, s, W[i]))
Wn = W / W.mean()
print()
print("  归一化后权重（均值=1）:")
print("   " + "  ".join("%d:%.2f" % (FC[i], Wn[i]) for i in range(len(FC))))
print()
print("  地板大 = 修不掉（源/内容差异）；可行动大 = 值得盯")
print("  详见 Skill §6.2 / §6.3")
