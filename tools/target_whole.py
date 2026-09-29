"""全曲目标曲线（从分离后的吉他轨）
用法:  python target_whole.py [歌曲目录]        或设 $env:SONG_DIR
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import song_dir, P, require, load_mono, envelope, FC, BANDS, db

D = song_dir()
g = require(P(D, "guitar"), "吉他轨")
x, sr = load_mono(g)
print("歌曲目录: %s" % D)
print("吉他轨  : %s  %.1f s  %d Hz" % (g.name, len(x)/sr, sr))

cur = envelope(x, sr)
out = P(D, "target")
np.save(out, np.vstack([np.array(FC), cur]))

print()
print("=== 全曲目标曲线（13 频段，相对）===")
for k, fc in enumerate(FC):
    print("  %6d Hz  %+6.2f" % (fc, cur[k]))
print()
print("已保存 %s" % out)

# 分段一致性自检
print()
print("=== 段间一致性（每 20 秒）===")
seg = 20; devs = []
for t0 in range(0, int(len(x)/sr)-seg, seg):
    e = envelope(x[int(t0*sr):int((t0+seg)*sr)], sr)
    d = e - cur
    devs.append((t0, float(np.sqrt((d**2).mean()))))
for t0, r in devs:
    print("  %4d-%4d s   %5.2f dB  %s" % (t0, t0+seg, r, "#"*int(r*4)))
arr = np.array([r for _, r in devs])
print("  中位 %.2f dB  p90 %.2f dB  最大 %.2f dB（%d s）"
      % (np.median(arr), np.percentile(arr,90), arr.max(), devs[int(np.argmax(arr))][0]))
