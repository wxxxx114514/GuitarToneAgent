"""生成要送进设备的 wav：单声道 -> 48k/2ch/16bit，归一化到目标峰值，前后加静音

用法:
  # ① 推荐：自动裁空白（首尾留白不参与）—— 与 09-测量协议 §一 一致
  python make_send.py <源wav> <出wav> [峰值dBFS]           # 峰值默认 -32

  # ② 指定区间（不裁空白）
  python make_send.py <源wav> <出wav> <峰值dBFS> --from <起始秒> --secs <时长秒>

  # ③ 兼容旧写法（<起始秒> <时长> <峰值> 三个位置参数）
  python make_send.py <源wav> <出wav> <起始秒> <时长> <峰值dBFS>

裁空白口径: 10 ms 帧 RMS，门限 -60 dBFS，取【首/末个有声帧】之间。
"""
import sys, os, argparse, numpy as np, soundfile as sf

SR = 48000
PH, PT = 0.5, 2.0          # 前后静音（秒）
TRIM_FRAME = 0.010         # 10 ms
TRIM_DB = -60.0            # 「有没有声」的门


def trim_silence(m, sr):
    """裁掉首尾空白 -> (段, 前留白秒, 后留白秒)"""
    N = int(TRIM_FRAME * sr); n = len(m) // N
    if n == 0:
        return m, 0.0, 0.0
    r = np.sqrt(np.array([(m[i*N:(i+1)*N] ** 2).mean() for i in range(n)]))
    db = 20*np.log10(np.maximum(r, 1e-12))
    idx = np.where(db > TRIM_DB)[0]
    if len(idx) == 0:
        return m, 0.0, 0.0
    a0, a1 = int(idx[0]*N), int((idx[-1]+1)*N)
    return m[a0:a1], a0/sr, (len(m)-a1)/sr


def main():
    argv = sys.argv[1:]
    # 兼容旧写法: <源> <出> <起始秒> <时长> <峰值>
    legacy = None
    if len(argv) >= 5 and not argv[3].startswith("--"):
        try:
            legacy = (float(argv[2]), float(argv[3]), float(argv[4]))
            argv = argv[:2] + argv[5:]
        except ValueError:
            legacy = None
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("src"); p.add_argument("out")
    p.add_argument("peak", nargs="?", type=float, default=-32.0, help="目标峰值 dBFS（默认 -32）")
    p.add_argument("--from", dest="from_s", type=float, default=None, help="起始秒（给了就不裁空白）")
    p.add_argument("--secs", type=float, default=None, help="时长秒")
    p.add_argument("--no-trim", action="store_true", help="不裁空白（整段）")
    if legacy:
        a = p.parse_args([argv[0], argv[1], str(legacy[2])])
        a.from_s, a.secs = legacy[0], legacy[1]
    else:
        a = p.parse_args(argv)

    x, sr = sf.read(a.src, always_2d=True, dtype="float32")
    mono = x.mean(1)
    if sr != SR:
        import librosa
        mono = librosa.resample(mono, orig_sr=sr, target_sr=SR)
        print("重采样 %d -> %d" % (sr, SR))

    if a.from_s is not None or a.secs is not None:
        s0 = int((a.from_s or 0.0) * SR)
        s1 = s0 + int((a.secs if a.secs is not None else len(mono)/SR) * SR)
        seg = mono[s0:s1]; how = "指定区间 %.2f~%.2f s（不裁空白）" % (s0/SR, s1/SR)
    elif a.no_trim:
        seg = mono; how = "整段（不裁空白）"
    else:
        seg, lead, tail = trim_silence(mono, SR)
        how = "自动裁空白（前留白 %.2f s · 后留白 %.2f s）" % (lead, tail)

    pk0 = float(np.abs(seg).max()) if len(seg) else 0.0
    g = a.peak - 20*np.log10(max(pk0, 1e-12))
    seg = seg * (10.0 ** (g/20.0))
    sig = np.concatenate([np.zeros(int(PH*SR), np.float32), seg,
                          np.zeros(int(PT*SR), np.float32)])
    s16 = np.clip(np.round(sig*32767.0), -32768, 32767).astype(np.int16)
    sf.write(a.out, np.stack([s16, s16], 1), SR, subtype="PCM_16")
    print("送出: %s" % a.out)
    print("  %s" % how)
    print("  峰值 %.2f -> %.2f dBFS (增益 %+.2f dB) · 信号 %.2f s · 总长 %.2f s"
          % (20*np.log10(max(pk0, 1e-12)), a.peak, g, len(seg)/SR, len(sig)/SR))
    print("REC_SECS=%.2f" % (len(sig)/SR + 1.5))


if __name__ == "__main__":
    main()
