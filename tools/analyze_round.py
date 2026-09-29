"""一轮湿声 vs 目标曲线（逐频段 + 分和弦）
用法:  python analyze_round.py [歌曲目录] [湿声文件]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import song_dir, file_args, P, require, load_mono, envelope, find_start, FC, db

D = song_dir()
argv = file_args()
wet_name = argv[0] if argv else "wet.wav"
WET = P(D, "reamp") / wet_name
require(WET, "湿声")
require(P(D, "target"), "目标曲线（先跑 target_whole.py）")
target = np.load(P(D, "target"))[1]

x, sr = load_mono(WET, sr=48000)
st = find_start(x, sr)
pk = db(np.abs(x).max()); rms = db(np.sqrt((x.astype(np.float64)**2).mean()))
nclip = int((np.abs(x) >= 0.999).sum())
print("=== %s" % wet_name)
print("    %.1f s  峰值 %.2f dBFS  RMS %.2f dBFS  起点 %.2f s" % (len(x)/sr, pk, rms, st))
print("    削顶样本(>=0.999): %d  %s" % (nclip, "(OK)" if nclip==0 else "!! 有削顶，结果不可信"))
if nclip > 0: sys.exit(1)

e = envelope(x[int((st+0.1)*sr):], sr)
d = e - target
print()
print("=== vs 目标曲线 ===")
print("  %8s %10s %10s %9s" % ("频率","实测","目标","差"))
for k, fc in enumerate(FC):
    bar = " "*max(0, int(round((d[k]+7)*3))) + "*"
    print("  %6d Hz %10.1f %10.1f %+9.2f %s" % (fc, e[k], target[k], d[k], bar))
rms_err = float(np.sqrt((d**2).mean()))
print("  RMS %.2f dB   最大 %.2f dB" % (rms_err, np.abs(d).max()))
print("  参考: 可行动空间 0.62 dB；优秀 < 0.8；可用 < 1.5")

# 分和弦
mk = P(D, "di") / "palm_di_marks.json"
if mk.exists():
    marks = json.load(open(mk, encoding="utf-8"))
    print()
    print("=== 分根音（看误差是否随音高变化）===")
    per = {}
    for name, (a, b) in marks.items():
        if name == "silence": continue
        seg = x[int(a*sr)+int(0.05*sr):int(b*sr)]
        if len(seg) < 16384: continue
        ee = envelope(seg, sr); dd = ee - target; per[name] = dd
        print("  %-10s RMS %.2f dB" % (name, np.sqrt((dd**2).mean())))
    if len(per) >= 2:
        dep = np.array(list(per.values())).std(0)
        print("  音高依赖: 平均 %.2f dB  -> %s" % (dep.mean(),
              "误差与音高基本无关（单个 EQ 能修）" if dep.mean() < 1.0 else "随音高变化，单 EQ 修不干净"))
print()
print("RESULT %.4f" % rms_err)
