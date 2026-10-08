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
    # 织体判据：这一帧有几个"显著音级"（占 chroma 总能量 >= 15% 的 bin 个数）
    #   单音 = 1（基频和谐波都折叠到同一个音级）；强力和弦 = 2；三和弦 = 3+
    npc = int((v >= 0.15).sum())
    res.append((t0, best[0][0], best[0][1], npc, best[1]))

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

print()
print("=== 织体（先判这个，再决定要不要用和弦表）===")
_npc = np.array([z[3] for z in res], dtype=float)
_sc  = np.array([z[4] for z in res], dtype=float)
print("  每帧显著音级数  平均 %.2f   中位 %.0f" % (_npc.mean(), np.median(_npc)))
print("  分布  " + "   ".join("%d个音级 %2.0f%%" % (k, 100*(_npc==k).mean()) for k in range(1,6) if (_npc==k).any()))
print("  参照  单音=1   强力和弦=2   三和弦=3")
print("  和弦模板最高匹配  平均 %.3f   中位 %.3f" % (_sc.mean(), np.median(_sc)))
_tm = float(_npc.mean())
if _tm < 1.8: TEX = "single"
elif _tm < 2.4: TEX = "power"
else: TEX = "chord"
print("  [织体] %s" % {"single":"单音型（旋律 / riff）—— 和弦模板匹配无意义，别用",
                       "power":"强力和弦型（根音 + 五度）",
                       "chord":"和弦型（三音以上）"}[TEX])
print("  !! 这只是【线索】，不是结论：阈值只在干净 DI 上试过（单音 1.06 / 和弦 1.91），")
print("     且有个单音样本报了 2.46 的反例。真实用途是分轨吉他轨，还受")
print("     混音高通 + 失真互调 + 贝斯串音 三道干扰（见 Skill 7.6）。")
print("     拿不准就按【织体未知】处理：让用户照谱子弹主 riff，别硬判。")

seq = []
for t0, r, k, _n, _s in res:
    lab = r + {"pow":"5","maj":"","min":"m"}[k]
    if seq and seq[-1][0] == lab: seq[-1][2] += 1
    else: seq.append([lab, t0, 1])
print()
print("=== 和弦进行（压缩）===")
print("  " + "  ".join("%s x%d" % (a,c) for a,b,c in seq[:60]))

# 写回 spec.json
sp = P(D, "spec")
spec = json.load(open(sp, encoding="utf-8-sig")) if sp.exists() else {}
# ★ 用户确认过的值【不许覆盖】（与 check_tuning.py 的先例一致）；推断值必须带来源。
#   为什么必须带来源：`key_mode` 是用【和弦三度】推的，而本脚本自己就打印
#   「失真强力和弦的三度常被谐波掩盖，maj/min 判定仅供参考」—— 那条不可靠的三度
#   曾被 di_instructions 当成定调式的证据（推断套推断），没人能看出它从哪来。
_usrc = str(spec.get("key_source") or "") == "user"
if _usrc:
    print("  [写回] key 用户确认过 —— 我没动")
else:
    spec["key"] = cc.most_common(1)[0][0]
    spec["key_source"] = "inferred_chroma"
_msrc = str(spec.get("key_mode_source") or "") == "user"
if _msrc:
    print("  [写回] key_mode 用户确认过 —— 我没动")
else:
    _nmin = ck.get("min", 0); _nmaj = ck.get("maj", 0)
    spec["key_mode"] = ("min" if _nmin > _nmaj else "maj") if (_nmin + _nmaj) > 0 else "unknown"
    spec["key_mode_source"] = "inferred_chord_thirds"   # ★ 三度不可靠 -> 下游必须当【假设值】看
spec["key_hist"] = {k: round(100.0*v/len(res),1) for k,v in cc.most_common(6)}
if str(spec.get("chords_source") or "") == "user":
    print("  [写回] chords 用户确认过 —— 我没动")
else:
    spec["chords"] = [a for a,b,c in seq[:20]]
    spec["chords_source"] = "inferred_chroma"
spec["texture"] = TEX
spec["texture_npc"] = round(_tm, 2)
spec["texture_score"] = round(float(_sc.mean()), 3)
json.dump(spec, open(sp,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print()
print("已更新 %s" % sp)
