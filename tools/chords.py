"""调性 + 和弦识别（按乐句算 chroma，不逐音扒）
用法:  python chords.py [歌曲目录]
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import librosa
from songlib import song_dir, P, require, load_mono

NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
D = song_dir()
g = require(P(D, "guitar"), "吉他轨")
x, sr = load_mono(g)
print("歌曲目录: %s   吉他轨 %.1f s" % (D, len(x)/sr))

tempo, beats = librosa.beat.beat_track(y=x, sr=sr, hop_length=512, units="time")
tempo = float(np.atleast_1d(tempo)[0])
bar = 4 * 60.0/tempo
print("估计速度 %.1f BPM   小节长度 %.2f s" % (tempo, bar))
print("  (librosa 常给实际值的一半，只影响切分粒度，不影响调性)")

def tpl(root, kind):
    t = np.zeros(12); r = NAMES.index(root)
    t[r] = 1.0; t[(r+7)%12] = 1.0
    if kind == "maj": t[(r+4)%12] = 1.0
    elif kind == "min": t[(r+3)%12] = 1.0
    return t
TPL = [(r,k,tpl(r,k)) for r in NAMES for k in ("pow","maj","min")]

res = []
for i in range(int((len(x)/sr)/(bar/2))):
    t0 = i*bar/2; t1 = min(t0+bar, len(x)/sr)
    if t1-t0 < 0.3: break
    seg = x[int(t0*sr):int(t1*sr)]
    if np.sqrt((seg.astype(np.float64)**2).mean()) < 1e-4: continue
    v = librosa.feature.chroma_cqt(y=seg, sr=sr, hop_length=512).mean(1)
    if v.sum() < 1e-6: continue
    v = v/v.sum()
    best = max((((r,k), float(np.dot(v, t/np.linalg.norm(t)))) for r,k,t in TPL), key=lambda z: z[1])
    res.append((t0, best[0][0], best[0][1]))

from collections import Counter
print()
print("=== 根音分布 ===")
cc = Counter(r[1] for r in res)
for nm, n in cc.most_common(12):
    print("  %-4s %4d 小节 (%2.0f%%)  %s" % (nm, n, 100*n/len(res), "#"*int(n*40/max(1,cc.most_common(1)[0][1]))))
print()
print("=== 和弦类型 ===")
ck = Counter(r[2] for r in res)
for nm, n in ck.most_common():
    print("  %-5s %4d (%2.0f%%)" % (nm, n, 100*n/len(res)))
print("  注意: 失真强力和弦的三度常被谐波掩盖，maj/min 判定仅供参考")

seq = []
for t0, r, k in res:
    lab = r + {"pow":"5","maj":"","min":"m"}[k]
    if seq and seq[-1][0] == lab: seq[-1][2] += 1
    else: seq.append([lab, t0, 1])
print()
print("=== 和弦进行（压缩）===")
print("  " + "  ".join("%s x%d" % (a,c) for a,b,c in seq[:60]))

# 写回 spec.json
sp = P(D, "spec")
spec = json.load(open(sp, encoding="utf-8")) if sp.exists() else {}
spec["key"] = cc.most_common(1)[0][0]
spec["key_hist"] = {k: round(100.0*v/len(res),1) for k,v in cc.most_common(6)}
spec["chords"] = [a for a,b,c in seq[:20]]
json.dump(spec, open(sp,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print()
print("已更新 %s" % sp)
