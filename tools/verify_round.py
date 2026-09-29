"""三层验证：绝对误差 / 逐帧指标 / EQ 模型标定
用法:  python verify_round.py [歌曲目录] <A湿声> <B湿声> [--units=...]
      单位格式: --units=100:-3,250:+13,630:+1,1600:-2,4000:-11
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import song_dir, file_args, P, require, load_mono, envelope, find_start, FC, db
from spec_metrics import align_pair, spectral_metrics

D = song_dir()
argv = file_args()
fa = argv[0] if len(argv) > 0 else "wet_A.wav"
fb = argv[1] if len(argv) > 1 else "wet_B.wav"
units = None
for a in sys.argv[1:]:
    if a.startswith("--units="):
        units = {}
        for kv in a.split("=", 1)[1].split(","):
            k, v = kv.split(":"); units[float(k)] = float(v)
        break

A, _ = load_mono(P(D,"reamp")/fa, sr=48000)
B, _ = load_mono(P(D,"reamp")/fb, sr=48000)
n = min(len(A), len(B)); A, B = A[:n], B[:n]
target = np.load(P(D, "target"))[1]

print("=== ① 绝对误差 ===")
E = {}
for tag, x in [("A", A), ("B", B)]:
    st = find_start(x, 48000)
    e = envelope(x[int((st+0.1)*48000):], 48000)
    E[tag] = e; d = e - target
    print("  %s (%s)  RMS %.2f dB   最大 %.2f dB  削顶 %d"
          % (tag, fa if tag=="A" else fb, np.sqrt((d**2).mean()), np.abs(d).max(),
             int((np.abs(x)>=0.999).sum())))
dA, dB = E["A"]-target, E["B"]-target
print("  改善 %.2f dB" % (np.sqrt((dA**2).mean()) - np.sqrt((dB**2).mean())))
print()
print("  %8s %10s %10s %10s" % ("频率","目标","A偏差","B偏差"))
for k, fc in enumerate(FC):
    print("  %6d Hz %10.1f %+10.2f %+10.2f" % (fc, target[k], dA[k], dB[k]))

print()
print("=== ② 逐帧指标（内容相同才有效）===")
B_al, lag, corr = align_pair(A, B, 48000, max_lag_ms=60)
m = spectral_metrics(A, B_al, 48000)
print("  对齐 lag %+.3f ms (哨兵: >5ms 异常)   相关 %.4f" % (lag/48000*1000, corr))
print("  LSD %.2f  LogMelMSE %.2f  MCD %.1f  SC %.4f  MultiRes %.2f"
      % (m["LSD"], m["LogMelMSE"], m["MCD"], m["SC"], m["MultiRes"]))

if units:
    print()
    print("=== ③ EQ 模型标定验证 ===")
    SIG, DBU = 0.985, 0.1848
    meas = E["B"] - E["A"]; meas -= meas.mean()
    pred = np.array([sum(v*DBU*np.exp(-(np.log2(f/k)**2)/(2*SIG*SIG)) for k, v in units.items()) for f in FC])
    pred -= pred.mean()
    print("  %8s %12s %12s %9s" % ("频率","实测变化","模型预测","差"))
    for k, fc in enumerate(FC):
        print("  %6d Hz %12.2f %12.2f %+9.2f" % (fc, meas[k], pred[k], meas[k]-pred[k]))
    err = meas - pred
    r = float(np.sqrt((err**2).mean()))
    print("  模型误差 RMS %.2f dB  -> %s" % (r, "标定可信" if r < 0.8 else "模型有偏差，需重新标定"))
