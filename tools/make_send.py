"""生成要送进 GE250 的 wav：单声道 -> 48k/2ch/16bit，归一化到目标峰值，前后加静音"""
import sys, os, numpy as np, soundfile as sf
SR = 48000
src = sys.argv[1]; out = sys.argv[2]
from_s = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
secs   = float(sys.argv[4]) if len(sys.argv) > 4 else 12.0
peak   = float(sys.argv[5]) if len(sys.argv) > 5 else -32.0
ph, pt = 0.5, 2.0
x, sr = sf.read(src, always_2d=True, dtype="float32")
mono = x.mean(1)
if sr != SR:
    import librosa
    mono = librosa.resample(mono, orig_sr=sr, target_sr=SR)
    print("重采样 %d -> %d" % (sr, SR))
a = int(from_s*SR); b = a + int(secs*SR)
seg = mono[a:b]
pk0 = float(np.abs(seg).max()) if len(seg) else 0.0
g = peak - 20*np.log10(max(pk0, 1e-12))
seg = seg * (10.0 ** (g/20.0))
sig = np.concatenate([np.zeros(int(ph*SR), np.float32), seg, np.zeros(int(pt*SR), np.float32)])
s16 = np.clip(np.round(sig*32767.0), -32768, 32767).astype(np.int16)
sf.write(out, np.stack([s16, s16], 1), SR, subtype="PCM_16")
print("送出: %s" % out)
print("  源峰值 %.2f dBFS -> 归一化 %.2f dBFS (增益 %+.2f dB)" % (20*np.log10(max(pk0,1e-12)), peak, g))
print("  长度 %.2f s (信号 %.2f + 前 0.5 + 后 2.0)" % (len(sig)/SR, len(seg)/SR))
print("REC_SECS=%.2f" % (len(sig)/SR + 1.5))
