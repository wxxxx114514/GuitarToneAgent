"""检测/设置调弦，写回 spec.json
   自动判据：Drop D 的 6 弦是 D2(73.4Hz)，标准是 E2(82.4Hz)
            曲子里大量用 6 弦低把位时，D2 出现率会明显高于 E2
用法:  python check_tuning.py [歌曲目录] [standard|drop_d]   （或 --set=drop_d）
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import librosa
from songlib import song_dir, P, require, load_mono

D = song_dir()
g = require(P(D, "guitar"), "吉他轨")
x, sr = load_mono(g)
spec_p = P(D, "spec")
spec = json.load(open(spec_p, encoding="utf-8")) if spec_p.exists() else {}

want = None
if len(sys.argv) > 2 and sys.argv[2] in ("standard", "drop_d"):
    want = sys.argv[2]
for a in sys.argv[1:]:
    if a.startswith("--set="):
        want = a.split("=", 1)[1]; break
if want in ("standard", "drop_d"):
    spec["tuning"] = want
    json.dump(spec, open(spec_p,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("已设为 %s" % want); sys.exit(0)
if want:
    print("未知调弦: %s（可选 standard / drop_d）" % want); sys.exit(2)

print("检测调弦（吉他轨 %.1f s）..." % (len(x)/sr))
f0, _, _ = librosa.pyin(x, fmin=60, fmax=400, sr=sr, frame_length=4096, hop_length=512)
ok = ~np.isnan(f0)
m = np.round(69 + 12*np.log2(f0[ok]/440.0)).astype(int)
w = {}
for mm in m:
    if mm < 60: w[mm] = w.get(mm, 0) + 1
tot = sum(w.values()) or 1
d2, e2 = w.get(38,0), w.get(40,0)
print("  D2(73.4Hz) %.2f%%   E2(82.4Hz) %.2f%%   比值 %.2f" % (100*d2/tot, 100*e2/tot, d2/max(e2,1)))
if d2 > e2*1.5:
    t, why = "drop_d", "D2 明显多于 E2"
elif e2 > d2*1.5:
    t, why = "standard", "E2 明显多于 D2"
else:
    t, why = spec.get("tuning", "standard"), "两者相当，沿用当前值"
print("  -> %s（%s）" % (t, why))
print()
print("  ⚠️ 吉他轨低音区可能有贝斯泄漏（实测 B1 占 27%%，那是 61.7Hz，吉他弹不到）")
print("     所以自动判定仅供参考，能问用户就问一句。")

spec["tuning"] = t
spec["tuning_evidence"] = "D2 %.1f%% vs E2 %.1f%%" % (100*d2/tot, 100*e2/tot)
json.dump(spec, open(spec_p,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print()
print("已写 spec.json: tuning = %s" % t)
