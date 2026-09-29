"""DI -> 设备格式（48k/2ch/16bit）+ 自动归一化 + 自验证
用法:  python meas_prep.py [歌曲目录] [DI文件]
环境:  TARGET_PEAK(-32)  PAD_HEAD(0.5)  PAD_TAIL(2.0)  SEND_NAME  DI_NAME
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from songlib import song_dir, file_args, P

SR = 48000
TARGET_PEAK = float(os.environ.get("TARGET_PEAK") or -32.0)
PAD_HEAD = float(os.environ.get("PAD_HEAD") or 0.5)
PAD_TAIL = float(os.environ.get("PAD_TAIL") or 2.0)

D = song_dir()
argv = file_args()
di_name = os.environ.get("DI_NAME") or (argv[0] if argv else "palm_di.wav")
send_name = os.environ.get("SEND_NAME") or "to_send.wav"
DI = P(D, "di") / di_name
SEND = P(D, "reamp") / send_name
SENT = P(D, "reamp") / "sent_pcm.wav"

if not DI.exists():
    print("找不到 DI: %s" % DI); sys.exit(2)

x, sr = sf.read(str(DI), always_2d=True, dtype="float32")   # ★ 立体声安全
assert sr == SR, "DI 采样率 %d != %d" % (sr, SR)
mono = x.mean(1)
print("歌曲目录: %s" % D)
print("DI: %s   %.2f s  %d ch -> 单声道" % (DI.name, len(mono)/SR, x.shape[1]))

pk0 = float(np.abs(mono).max())
gain_db = TARGET_PEAK - 20*np.log10(max(pk0,1e-12))
mono = mono * (10.0 ** (gain_db/20.0))
pk = float(np.abs(mono).max())
print("    峰值 %.2f -> %.2f dBFS  (增益 %+.2f dB)" % (20*np.log10(max(pk0,1e-12)), TARGET_PEAK, gain_db))

nh, nt = int(PAD_HEAD*SR), int(PAD_TAIL*SR)
sig = np.concatenate([np.zeros(nh,np.float32), mono, np.zeros(nt,np.float32)])
s16 = np.clip(np.round(sig*32767.0), -32768, 32767).astype(np.int16)
st = np.stack([s16, s16], axis=1)
for p in (SEND, SENT):
    p.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(p), st, SR, subtype="PCM_16")

dur = len(sig)/SR
print("发送: %.2f s  -> %s" % (dur, SEND))
print()
print("=== 自验证 ===")
back, _ = sf.read(str(SEND), always_2d=True, dtype="float32")
seg = back[nh:nh+len(mono), 0]
d = np.abs(seg - mono)
print("  最大逐样本差 %.6f (%.1f dBFS)" % (d.max(), 20*np.log10(max(d.max(),1e-12))))
print("  相关系数     %.6f   %s" % (np.corrcoef(mono, seg)[0,1],
      "OK" if np.corrcoef(mono, seg)[0,1] > 0.999 else "!! 不对"))
print("  左右一致:", bool(np.allclose(back[:,0], back[:,1])))
print()
print("REC_SECS=%.2f" % (dur + 1.0))
