"""噪声审计：链路每一环的信噪比 + 工频
用法:  python noise_audit.py [歌曲目录]

⚠️ 工频必须在【静音段】里量。在音乐段落里量会撞上音符
   （实测：120 Hz 的测量撞上了 B2 = 123.5 Hz，得出假结论）。
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import song_dir, P, load_mono, db

def snr(x, sr, tag):
    w = int(0.010*sr); n = len(x)//w
    if n < 10: return
    r = np.sqrt(np.array([(x[i*w:(i+1)*w].astype(np.float64)**2).mean() for i in range(n)]))
    noise, sig = float(np.percentile(r,1)), float(np.percentile(r,90))
    ratio = db(sig) - db(noise)
    flag = "OK" if ratio > 40 else "!! 偏低"
    print("  %-30s %6.1f s  %5d Hz  峰值 %7.2f  信号 %7.2f  底噪 %7.2f  信噪比 %5.1f dB  %s"
          % (tag, len(x)/sr, sr, db(np.abs(x).max()), db(sig), db(noise), ratio, flag))

def hum(x, sr, t0, t1, tag):
    """在静音段里量工频柱"""
    seg = x[int(t0*sr):int(t1*sr)]
    N = 16384
    if len(seg) < N:
        print("  %-30s (静音段太短)" % tag); return
    acc = np.zeros(N//2+1); c = 0
    for s in range(0, max(len(seg)-N,1), N//2):
        acc += np.abs(np.fft.rfft(seg[s:s+N]*np.hanning(N)))**2; c += 1
    sp = np.sqrt(acc/max(c,1)); f = np.fft.rfftfreq(N, 1/sr)
    base = float(np.median(sp[(f>200)&(f<8000)])) + 1e-12
    out = []
    for fc in (50, 100, 150, 200, 250):
        m = (f>=fc-1.5)&(f<=fc+1.5)
        v = float(sp[m].max()) if m.any() else 1e-12
        out.append("%dHz %+.0f" % (fc, db(v)-db(base)))
    print("  %-30s 静音 %.1f-%.1f s   %s" % (tag, t0, t1, "  ".join(out)))

D = song_dir()
print("歌曲目录: %s" % D)
print()
print("=== ① 信噪比（每环）===")
for tag, p in [("DI（用户录）", P(D,"di")/"palm_di.wav"),
               ("发送信号", P(D,"reamp")/"to_send.wav")]:
    if p.exists(): snr(load_mono(p)[0], load_mono(p)[1], tag)
    else: print("  %-30s (不存在)" % tag)
for tag, p in [("吉他轨", P(D,"guitar")), ("贝斯轨", D/"stems"/"bass.wav")]:
    if p.exists(): snr(load_mono(p)[0], load_mono(p)[1], tag)
    else: print("  %-30s (不存在)" % tag)
rm = P(D, "reamp")
if rm.exists():
    for f in sorted(os.listdir(rm)):
        if f.startswith("wet") and f.endswith(".wav"):
            xx, ss = load_mono(rm/f); snr(xx, ss, "湿声 " + f)

print()
print("=== ② 工频（必须在静音段里量）===")
print("  提示：给个静音区间，或者看湿声录音开头的前导静音")
for tag, p in [("DI", P(D,"di")/"palm_di.wav")]:
    if p.exists():
        xx, ss = load_mono(p)
        hum(xx, ss, 0.05, 0.45, tag)     # meas_prep 会在开头放 0.5s 静音
rm = P(D, "reamp")
if rm.exists():
    for f in sorted(os.listdir(rm)):
        if f.startswith("wet") and f.endswith(".wav"):
            xx, ss = load_mono(rm/f)
            hum(xx, ss, 0.05, 0.45, "湿声 " + f)

print()
print("=== ③ 判据 ===")
print("""
  DI          信噪比 > 40 dB
  湿声录音     信噪比 > 80 dB（设备有噪声门）
  参考曲吉他轨  静音段应该是数字静音（−240 dBFS）
               有残余说明分离模型有泄漏（见 Skill §2.3）
  工频         比信号低 40 dB 以上就无所谓
""")
